"""Public routes for signing in and out with Discord OAuth2."""

from __future__ import annotations

import hmac
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from backend.security.authentication import (
    AuthenticationManager,
    OAuthFlowError,
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["authentication"])
STATE_TTL_SECONDS = 600


def _auth_manager(request: Request) -> AuthenticationManager:
    manager = getattr(request.app.state, "auth_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Authentication is not initialized.")
    return manager


@router.get("/status")
async def auth_status(request: Request):
    manager = _auth_manager(request)
    session = manager.get_session(request.cookies.get(SESSION_COOKIE_NAME))
    return {
        "configured": manager.configured,
        "authenticated": session is not None,
        "user": session.user if session else None,
    }


@router.get("/login")
async def login(request: Request):
    manager = _auth_manager(request)
    if not manager.configured:
        raise HTTPException(status_code=503, detail="Set the Discord OAuth values in .env before signing in.")
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(manager.authorization_url(state), status_code=302)
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        STATE_COOKIE_NAME,
        state,
        max_age=STATE_TTL_SECONDS,
        path="/api/auth/callback",
        httponly=True,
        secure=manager.cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, iss: str | None = None, error: str | None = None):
    manager = _auth_manager(request)
    state_cookie = request.cookies.get(STATE_COOKIE_NAME)
    if not state or not state_cookie or not hmac.compare_digest(state.encode(), state_cookie.encode()):
        response = RedirectResponse("/?auth=state_failed", status_code=303)
        response.delete_cookie(STATE_COOKIE_NAME, path="/api/auth/callback")
        return response
    if error or not code or iss != "https://discord.com":
        response = RedirectResponse("/?auth=cancelled", status_code=303)
        response.delete_cookie(STATE_COOKIE_NAME, path="/api/auth/callback")
        return response

    try:
        user, access_token, managed_guilds = await manager.authorize_code(code)
    except PermissionError:
        response = RedirectResponse("/?auth=not_allowed", status_code=303)
        response.delete_cookie(STATE_COOKIE_NAME, path="/api/auth/callback")
        return response
    except OAuthFlowError:
        logger.exception("Discord OAuth callback failed")
        response = RedirectResponse("/?auth=login_failed", status_code=303)
        response.delete_cookie(STATE_COOKIE_NAME, path="/api/auth/callback")
        return response

    session_id = manager.create_session(user, access_token, managed_guilds)
    response = RedirectResponse("/", status_code=303)
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=manager.session_ttl,
        path="/",
        httponly=True,
        secure=manager.cookie_secure,
        samesite="lax",
    )
    response.delete_cookie(STATE_COOKIE_NAME, path="/api/auth/callback")
    return response


@router.post("/logout")
async def logout(request: Request):
    manager = _auth_manager(request)
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session = manager.get_session(session_id)
    manager.remove_session(session_id)
    if session:
        await manager.revoke_access_token(session.access_token)
    response = Response(content='{"authenticated":false}', media_type="application/json")
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response
