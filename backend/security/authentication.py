"""Discord OAuth2 authorization-code flow and in-memory dashboard sessions."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import aiohttp
from fastapi import HTTPException, Request

from backend.security.permissions import can_manage_guild

logger = logging.getLogger(__name__)
SESSION_COOKIE_NAME = "music_dashboard_session"
STATE_COOKIE_NAME = "music_oauth_state"
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_REVOKE_URL = "https://discord.com/api/oauth2/token/revoke"


class OAuthFlowError(Exception):
    """Safe-to-report failure from the Discord OAuth flow."""


@dataclass
class DashboardSession:
    user: dict[str, Any]
    access_token: str
    managed_guilds: dict[str, dict[str, Any]]
    expires_at: float
    guilds_checked_at: float = field(default_factory=time.time)
    refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class AuthenticationManager:
    def __init__(self) -> None:
        self.client_id = os.getenv("DISCORD_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
        self.redirect_uri = os.getenv("DISCORD_REDIRECT_URI", "").strip()
        self.owner_user_id = os.getenv("DASHBOARD_OWNER_ID", "").strip()
        self.session_ttl = self._int_setting("SESSION_TTL_SECONDS", 43200, minimum=300)
        self.cookie_secure = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
        self._sessions: dict[str, DashboardSession] = {}

    @staticmethod
    def _int_setting(name: str, default: int, minimum: int) -> int:
        try:
            value = int(os.getenv(name, str(default)))
        except ValueError:
            return default
        return value if value >= minimum else default

    @property
    def configured(self) -> bool:
        return bool(
            self.client_id
            and self.client_secret
            and self.redirect_uri
            and self.owner_user_id.isdecimal()
        )

    def authorization_url(self, state: str) -> str:
        if not self.configured:
            raise OAuthFlowError("Discord OAuth is not configured.")
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "identify guilds",
            "state": state,
        }
        return f"{DISCORD_AUTHORIZE_URL}?{urlencode(params)}"

    async def _request_json(self, session: aiohttp.ClientSession, url: str, *, token: str | None = None) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        try:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.warning("Discord OAuth data request failed with status %s", response.status)
                    raise OAuthFlowError("Discord could not provide the requested account information.")
                return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise OAuthFlowError("Could not reach Discord during sign-in.") from exc

    async def _fetch_managed_guilds(self, token: str) -> dict[str, dict[str, Any]]:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            guilds = await self._request_json(session, f"{DISCORD_API_BASE}/users/@me/guilds", token=token)
        if not isinstance(guilds, list):
            raise OAuthFlowError("Discord returned an invalid server list.")
        return {
            str(guild["id"]): {
                "id": str(guild["id"]),
                "name": guild.get("name", "Unknown server"),
                "icon": guild.get("icon"),
            }
            for guild in guilds
            if isinstance(guild, dict) and guild.get("id") is not None and can_manage_guild(guild)
        }

    async def authorize_code(self, code: str) -> tuple[dict[str, Any], str, dict[str, dict[str, Any]]]:
        if not self.configured:
            raise OAuthFlowError("Discord OAuth is not configured.")
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    DISCORD_TOKEN_URL,
                    data={"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri},
                    auth=aiohttp.BasicAuth(self.client_id, self.client_secret),
                ) as response:
                    if response.status != 200:
                        logger.warning("Discord OAuth token exchange failed with status %s", response.status)
                        raise OAuthFlowError("Discord sign-in could not be completed.")
                    token_data = await response.json()
                access_token = token_data.get("access_token")
                if not access_token:
                    raise OAuthFlowError("Discord did not return an access token.")
                granted_scopes = set(str(token_data.get("scope", "")).split())
                if not {"identify", "guilds"}.issubset(granted_scopes):
                    await self.revoke_access_token(access_token)
                    raise OAuthFlowError("Discord did not grant the scopes needed for the dashboard.")
                user = await self._request_json(session, f"{DISCORD_API_BASE}/users/@me", token=access_token)
                if str(user.get("id", "")) != self.owner_user_id:
                    await self.revoke_access_token(access_token)
                    raise PermissionError("This Discord account is not allowed to use the dashboard.")
                guilds = await self._request_json(session, f"{DISCORD_API_BASE}/users/@me/guilds", token=access_token)
        except PermissionError:
            raise
        except OAuthFlowError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise OAuthFlowError("Could not complete sign-in with Discord.") from exc

        if not isinstance(guilds, list):
            raise OAuthFlowError("Discord returned an invalid server list.")
        managed_guilds = {
            str(guild["id"]): {
                "id": str(guild["id"]),
                "name": guild.get("name", "Unknown server"),
                "icon": guild.get("icon"),
            }
            for guild in guilds
            if isinstance(guild, dict) and guild.get("id") is not None and can_manage_guild(guild)
        }
        avatar_hash = user.get("avatar")
        user_id = str(user["id"])
        profile = {
            "id": user_id,
            "username": user.get("username", "Discord user"),
            "display_name": user.get("global_name") or user.get("username", "Discord user"),
            "avatar_url": f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=96" if avatar_hash else None,
        }
        return profile, access_token, managed_guilds

    async def revoke_access_token(self, access_token: str) -> None:
        if not access_token or not self.client_id or not self.client_secret:
            return
        timeout = aiohttp.ClientTimeout(total=8)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    DISCORD_REVOKE_URL,
                    data={"token": access_token, "token_type_hint": "access_token"},
                    auth=aiohttp.BasicAuth(self.client_id, self.client_secret),
                ) as response:
                    if response.status not in (200, 204):
                        logger.warning("Discord OAuth token revocation returned status %s", response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            logger.warning("Could not revoke the Discord OAuth token during sign-out")

    def create_session(self, user: dict[str, Any], access_token: str, guilds: dict[str, dict[str, Any]]) -> str:
        now = time.time()
        self._sessions = {key: value for key, value in self._sessions.items() if value.expires_at > now}
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = DashboardSession(
            user=user,
            access_token=access_token,
            managed_guilds=guilds,
            expires_at=now + self.session_ttl,
        )
        return session_id

    def get_session(self, session_id: str | None) -> DashboardSession | None:
        if not session_id:
            return None
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.expires_at <= time.time():
            self._sessions.pop(session_id, None)
            return None
        return session

    def remove_session(self, session_id: str | None) -> None:
        if session_id:
            self._sessions.pop(session_id, None)

    async def refresh_managed_guilds(self, session: DashboardSession, *, max_age: int = 60) -> None:
        if time.time() - session.guilds_checked_at < max_age:
            return
        async with session.refresh_lock:
            if time.time() - session.guilds_checked_at < max_age:
                return
            session.managed_guilds = await self._fetch_managed_guilds(session.access_token)
            session.guilds_checked_at = time.time()


def get_authenticated_session(request: Request) -> DashboardSession:
    manager: AuthenticationManager | None = getattr(request.app.state, "auth_manager", None)
    if manager is None or not manager.configured:
        raise HTTPException(status_code=503, detail="Discord OAuth is not configured.")
    session = manager.get_session(request.cookies.get(SESSION_COOKIE_NAME))
    if session is None:
        raise HTTPException(status_code=401, detail="Sign in with Discord to continue.")
    return session
