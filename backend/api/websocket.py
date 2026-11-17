"""Guild-scoped WebSocket connections for live player state updates."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.routes import _public_song
from backend.music.player_manager import MusicPlayerManager
from backend.security.authentication import (
    AuthenticationManager,
    OAuthFlowError,
    SESSION_COOKIE_NAME,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def public_player_state(state: dict[str, Any]) -> dict[str, Any]:
    """Remove stream URLs and preserve Discord snowflakes as strings."""
    safe_state = dict(state)
    safe_state["guild_id"] = str(safe_state["guild_id"])
    voice_channel = safe_state.get("voice_channel")
    if voice_channel:
        safe_state["voice_channel"] = {**voice_channel, "id": str(voice_channel["id"])}
    safe_state["current"] = _public_song(safe_state.get("current"))
    safe_state["queue"] = [_public_song(song) for song in safe_state.get("queue", [])]
    return safe_state


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, guild_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(guild_id, set()).add(websocket)

    async def disconnect(self, guild_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(guild_id)
            if sockets:
                sockets.discard(websocket)
                if not sockets:
                    self._connections.pop(guild_id, None)

    async def broadcast(self, guild_id: int, state: dict[str, Any]) -> None:
        async with self._lock:
            sockets = tuple(self._connections.get(guild_id, ()))
        if not sockets:
            return

        message = {
            "type": "player_update",
            "guild_id": str(guild_id),
            "state": public_player_state(state),
        }
        results = await asyncio.gather(*(socket.send_json(message) for socket in sockets), return_exceptions=True)
        failed = [socket for socket, result in zip(sockets, results) if isinstance(result, Exception)]
        if failed:
            async with self._lock:
                registered = self._connections.get(guild_id)
                if registered:
                    registered.difference_update(failed)
                    if not registered:
                        self._connections.pop(guild_id, None)


@router.websocket("/ws/guilds/{guild_id}")
async def guild_player_updates(websocket: WebSocket, guild_id: str) -> None:
    try:
        if not guild_id.isdecimal():
            raise ValueError("Guild ID must contain digits only.")
        numeric_guild_id = int(guild_id)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid guild ID.")
        return

    bot = getattr(websocket.app.state, "bot", None)
    manager: MusicPlayerManager | None = getattr(websocket.app.state, "player_manager", None)
    hub: WebSocketHub | None = getattr(websocket.app.state, "websocket_hub", None)
    auth_manager: AuthenticationManager | None = getattr(websocket.app.state, "auth_manager", None)
    session = auth_manager.get_session(websocket.cookies.get(SESSION_COOKIE_NAME)) if auth_manager else None
    if not auth_manager or not auth_manager.configured or not session:
        await websocket.close(code=1008, reason="Sign in with Discord to continue.")
        return
    try:
        await auth_manager.refresh_managed_guilds(session)
    except OAuthFlowError:
        await websocket.close(code=1013, reason="Could not verify Discord permissions.")
        return
    if str(numeric_guild_id) not in session.managed_guilds:
        await websocket.close(code=1008, reason="You do not have permission to control this server.")
        return
    if not bot or not bot.is_ready() or not manager or not hub or bot.get_guild(numeric_guild_id) is None:
        await websocket.close(code=1008, reason="Guild is unavailable.")
        return

    player = manager.get_player(numeric_guild_id)
    await hub.connect(numeric_guild_id, websocket)
    session_cookie = websocket.cookies.get(SESSION_COOKIE_NAME)
    try:
        await websocket.send_json({
            "type": "player_update",
            "guild_id": str(numeric_guild_id),
            "state": public_player_state(player.snapshot()),
        })
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                current_session = auth_manager.get_session(session_cookie)
                if current_session is None:
                    await websocket.close(code=1008, reason="Dashboard session expired.")
                    break
                try:
                    await auth_manager.refresh_managed_guilds(current_session)
                except OAuthFlowError:
                    await websocket.close(code=1013, reason="Could not verify Discord permissions.")
                    break
                if str(numeric_guild_id) not in current_session.managed_guilds:
                    await websocket.close(code=1008, reason="Server access was removed.")
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket connection failed for guild %s", numeric_guild_id)
    finally:
        await hub.disconnect(numeric_guild_id, websocket)
