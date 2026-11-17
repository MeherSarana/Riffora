"""Build the Discord client without starting it as an import side effect."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from backend.bot.commands import setup_commands
from backend.bot.events import setup_events
from backend.music.player_manager import MusicPlayerManager

logger = logging.getLogger(__name__)


def create_bot(manager: MusicPlayerManager | None = None) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    player_manager = manager or MusicPlayerManager()
    setup_commands(bot, player_manager)
    setup_events(bot, player_manager)

    @bot.event
    async def setup_hook():
        synced = await bot.tree.sync()
        logger.info("Synced %s slash commands", len(synced))

    return bot
