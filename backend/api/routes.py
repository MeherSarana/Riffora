"""HTTP API for the shared Discord music players."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.music.player_manager import MusicPlayerManager
from backend.security.authentication import (
    AuthenticationManager,
    DashboardSession,
    OAuthFlowError,
    get_authenticated_session,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(get_authenticated_session)])


class PlayRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    voice_channel_id: str | None = Field(default=None, pattern=r"^[0-9]+$")


class ConnectRequest(BaseModel):
    voice_channel_id: str = Field(pattern=r"^[0-9]+$")


class VolumeRequest(BaseModel):
    volume: float = Field(ge=0, le=2)


class LoopRequest(BaseModel):
    enabled: bool


def _bot(request: Request):
    bot = getattr(request.app.state, "bot", None)
    if bot is None or not bot.is_ready():
        raise HTTPException(status_code=503, detail="Discord bot is not connected yet.")
    return bot


def _manager(request: Request) -> MusicPlayerManager:
    manager = getattr(request.app.state, "player_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Music player manager is not ready.")
    return manager


def _discord_id(value: str) -> int:
    if not value.isdecimal():
        raise HTTPException(status_code=422, detail="Discord IDs must contain digits only.")
    return int(value)


async def _guild(request: Request, bot, guild_id: int):
    session: DashboardSession = get_authenticated_session(request)
    auth_manager: AuthenticationManager = request.app.state.auth_manager
    try:
        await auth_manager.refresh_managed_guilds(session)
    except OAuthFlowError as exc:
        logger.warning("Could not refresh Discord server permissions")
        raise HTTPException(status_code=503, detail="Could not verify your Discord server permissions. Try again shortly.") from exc
    if str(guild_id) not in session.managed_guilds:
        raise HTTPException(status_code=403, detail="You need server management permissions to control this server.")
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Server not found or the bot is not a member.")
    return guild


def _public_song(song: dict[str, Any] | None) -> dict[str, Any] | None:
    if song is None:
        return None
    return {key: song.get(key) for key in ("title", "webpage_url", "thumbnail", "duration", "uploader")}


def _player_response(player) -> dict[str, Any]:
    state = player.snapshot()
    state["guild_id"] = str(state["guild_id"])
    if state["voice_channel"]:
        state["voice_channel"]["id"] = str(state["voice_channel"]["id"])
    state["current"] = _public_song(state["current"])
    state["queue"] = [_public_song(song) for song in state["queue"]]
    return state


def _voice_channel(guild, channel_id: int):
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        raise HTTPException(status_code=404, detail="Voice channel not found in this server.")
    return channel


@router.get("/health")
async def health(request: Request):
    bot = getattr(request.app.state, "bot", None)
    return {"status": "ok", "discord_connected": bool(bot and bot.is_ready())}


@router.get("/guilds")
async def list_guilds(request: Request):
    session: DashboardSession = get_authenticated_session(request)
    auth_manager: AuthenticationManager = request.app.state.auth_manager
    bot = _bot(request)
    try:
        await auth_manager.refresh_managed_guilds(session)
    except OAuthFlowError as exc:
        raise HTTPException(status_code=503, detail="Could not verify your Discord server permissions. Try again shortly.") from exc
    return [
        {
            "id": str(guild.id),
            "name": guild.name,
            "icon": str(guild.icon.url) if guild.icon else None,
            "connected": bool(guild.voice_client and guild.voice_client.is_connected()),
        }
        for guild in bot.guilds
        if str(guild.id) in session.managed_guilds
    ]


@router.get("/guilds/{guild_id}/channels")
async def list_voice_channels(guild_id: str, request: Request):
    guild_id = _discord_id(guild_id)
    guild = await _guild(request, _bot(request), guild_id)
    return [
        {"id": str(channel.id), "name": channel.name, "type": "stage" if isinstance(channel, discord.StageChannel) else "voice"}
        for channel in [*guild.voice_channels, *guild.stage_channels]
    ]


@router.post("/guilds/{guild_id}/connect")
async def connect(guild_id: str, body: ConnectRequest, request: Request):
    guild_id = _discord_id(guild_id)
    bot = _bot(request)
    guild = await _guild(request, bot, guild_id)
    channel = _voice_channel(guild, int(body.voice_channel_id))
    player = _manager(request).get_player(guild_id)
    try:
        await player.join(channel)
    except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError) as exc:
        logger.warning("Could not connect player for guild %s: %s", guild_id, exc)
        raise HTTPException(status_code=502, detail="Discord could not connect the bot to that voice channel.") from exc
    return _player_response(player)


@router.post("/guilds/{guild_id}/disconnect")
async def disconnect(guild_id: str, request: Request):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    player = _manager(request).get_player(guild_id)
    await player.stop(disconnect=True)
    return _player_response(player)


@router.get("/guilds/{guild_id}/player")
async def get_player(guild_id: str, request: Request):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    return _player_response(_manager(request).get_player(guild_id))


@router.get("/guilds/{guild_id}/queue")
async def get_queue(guild_id: str, request: Request):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    player = _manager(request).get_player(guild_id)
    return {"guild_id": str(guild_id), "queue": [_public_song(song) for song in player.queue.snapshot()]}


@router.post("/guilds/{guild_id}/play")
async def play(guild_id: str, body: PlayRequest, request: Request):
    guild_id = _discord_id(guild_id)
    bot = _bot(request)
    guild = await _guild(request, bot, guild_id)
    manager = _manager(request)
    player = manager.get_player(guild_id)

    if body.voice_channel_id is not None:
        channel = _voice_channel(guild, int(body.voice_channel_id))
    elif player.connected:
        channel = None
    else:
        raise HTTPException(status_code=422, detail="Choose a voice channel before starting playback.")

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Search query cannot be blank.")
    try:
        song = await player.extractor.extract(query)
    except Exception as exc:
        logger.exception("Song extraction failed for guild %s", guild_id)
        raise HTTPException(status_code=502, detail="Song search or audio extraction failed.") from exc
    if not song or not song.get("title") or not song.get("url"):
        raise HTTPException(status_code=404, detail="No playable song was found.")

    if channel is not None:
        try:
            await player.join(channel)
        except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError) as exc:
            logger.warning("Could not connect player for guild %s: %s", guild_id, exc)
            raise HTTPException(status_code=502, detail="Discord could not connect the bot to that voice channel.") from exc

    await player.enqueue(song)
    return {"message": "Added to queue.", "song": _public_song(song), "player": _player_response(player)}


@router.post("/guilds/{guild_id}/pause")
async def pause(guild_id: str, request: Request):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    player = _manager(request).get_player(guild_id)
    if not player.pause():
        raise HTTPException(status_code=409, detail="Nothing is playing.")
    return _player_response(player)


@router.post("/guilds/{guild_id}/resume")
async def resume(guild_id: str, request: Request):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    player = _manager(request).get_player(guild_id)
    if not player.resume():
        raise HTTPException(status_code=409, detail="Playback is not paused.")
    return _player_response(player)


@router.post("/guilds/{guild_id}/skip")
async def skip(guild_id: str, request: Request):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    player = _manager(request).get_player(guild_id)
    if not player.skip():
        raise HTTPException(status_code=409, detail="Nothing is playing.")
    return _player_response(player)


@router.post("/guilds/{guild_id}/stop")
async def stop(guild_id: str, request: Request, disconnect: bool = False):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    player = _manager(request).get_player(guild_id)
    await player.stop(disconnect=disconnect)
    return _player_response(player)


@router.delete("/guilds/{guild_id}/queue/{index}")
async def remove_from_queue(guild_id: str, index: int, request: Request):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    player = _manager(request).get_player(guild_id)
    try:
        removed = await player.remove(index - 1)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail="Queue item not found.") from exc
    return {"removed": _public_song(removed), "player": _player_response(player)}


@router.post("/guilds/{guild_id}/shuffle")
async def shuffle(guild_id: str, request: Request):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    player = _manager(request).get_player(guild_id)
    await player.shuffle()
    return _player_response(player)


@router.put("/guilds/{guild_id}/volume")
async def set_volume(guild_id: str, body: VolumeRequest, request: Request):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    player = _manager(request).get_player(guild_id)
    await player.set_volume(body.volume)
    return _player_response(player)


@router.put("/guilds/{guild_id}/loop")
async def set_loop(guild_id: str, body: LoopRequest, request: Request):
    guild_id = _discord_id(guild_id)
    await _guild(request, _bot(request), guild_id)
    player = _manager(request).get_player(guild_id)
    await player.set_loop(body.enabled)
    return _player_response(player)
