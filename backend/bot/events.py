"""Discord lifecycle and voice-state event handlers."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from backend.music.player_manager import MusicPlayerManager

logger = logging.getLogger(__name__)


def setup_events(bot: commands.Bot, manager: MusicPlayerManager) -> None:
    @bot.event
    async def on_ready():
        logger.info("Logged in as %s", bot.user)

    @bot.event
    async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not member.guild:
            return
        player = manager.get_existing_player(member.guild.id)
        if member.bot:
            if bot.user and member.id == bot.user.id and before.channel is not None and after.channel is None and player:
                await player.handle_voice_disconnect()
            return
        voice_client = member.guild.voice_client
        if not player or not voice_client or not voice_client.is_connected():
            return
        if len(voice_client.channel.members) == 1:
            await player.stop(disconnect=True)
