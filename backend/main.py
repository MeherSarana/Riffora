"""Run the FastAPI dashboard API and Discord bot in one process."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.api.auth import router as auth_router
from backend.api.websocket import WebSocketHub, router as websocket_router
from backend.bot.client import create_bot
from backend.music.player_manager import MusicPlayerManager
from backend.security.authentication import AuthenticationManager

load_dotenv()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Add it to your local .env file.")

    manager = MusicPlayerManager(ffmpeg_path=os.getenv("FFMPEG_PATH") or None)
    websocket_hub = WebSocketHub()
    manager.set_update_callback(websocket_hub.broadcast)
    bot = create_bot(manager)
    bot_task = asyncio.create_task(bot.start(token), name="discord-bot")
    ready_task = asyncio.create_task(bot.wait_until_ready(), name="discord-ready")
    app.state.player_manager = manager
    app.state.websocket_hub = websocket_hub
    app.state.bot = bot
    app.state.auth_manager = AuthenticationManager()

    try:
        done, _ = await asyncio.wait(
            {bot_task, ready_task}, timeout=45, return_when=asyncio.FIRST_COMPLETED
        )
        if bot_task in done:
            await bot_task
            raise RuntimeError("Discord bot stopped before becoming ready.")
        if ready_task not in done:
            raise RuntimeError("Discord bot did not connect within 45 seconds.")
        logger.info("FastAPI and Discord bot are ready")
        yield
    finally:
        ready_task.cancel()
        if not bot.is_closed():
            await bot.close()
        if not bot_task.done():
            try:
                await asyncio.wait_for(bot_task, timeout=10)
            except asyncio.TimeoutError:
                bot_task.cancel()
                await asyncio.gather(bot_task, return_exceptions=True)
            except Exception:
                logger.exception("Discord bot exited with an error during shutdown")


app = FastAPI(title="Discord Music Bot API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(router)
app.include_router(auth_router)
app.include_router(websocket_router)


@app.get("/health", tags=["health"])
async def root_health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("API_PORT", "8000")))
