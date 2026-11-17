"""Backward-compatible local entry point for the Discord music bot."""

import logging
import os

from dotenv import load_dotenv

from backend.bot.client import create_bot
from backend.music.player_manager import MusicPlayerManager

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

player_manager = MusicPlayerManager(ffmpeg_path=os.getenv("FFMPEG_PATH") or None)
bot = create_bot(player_manager)


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Add it to your local .env file.")
    bot.run(token)
