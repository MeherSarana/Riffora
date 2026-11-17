"""Prefix commands, slash commands, and interactive music controls."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from backend.music.player_manager import MusicPlayerManager

logger = logging.getLogger(__name__)


class MusicControls(discord.ui.View):
    def __init__(self, manager: MusicPlayerManager, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.manager = manager

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.manager.get_player(interaction.guild_id)
        await interaction.response.send_message("⏸ Paused" if player.pause() else "Nothing is playing.", ephemeral=True)

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.success)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.manager.get_player(interaction.guild_id)
        await interaction.response.send_message("▶ Resumed" if player.resume() else "Nothing is paused.", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.manager.get_player(interaction.guild_id)
        if player.voice_client:
            await player.stop(disconnect=True)
            await interaction.response.send_message("⏹ Disconnected", ephemeral=True)
        else:
            await interaction.response.send_message("Bot is not connected.", ephemeral=True)


class InteractionContext:
    """Send adapter that avoids relying on expiring interaction webhooks."""

    def __init__(self, *, channel: Any, client: commands.Bot, channel_id: int | None = None):
        self.channel = channel
        self.client = client
        self.channel_id = channel_id

    async def send(self, *args: Any, **kwargs: Any):
        if self.channel:
            return await self.channel.send(*args, **kwargs)
        channel = self.client.get_channel(self.channel_id) if self.channel_id else None
        if channel:
            return await channel.send(*args, **kwargs)
        raise RuntimeError("No channel is available for playback notifications.")


async def _connect_for_user(player, member: discord.Member):
    if member.voice is None or member.voice.channel is None:
        raise ValueError("Join a voice channel first!")
    return await player.join(member.voice.channel)


async def _queue_song(player, query: str, context: Any) -> dict[str, Any]:
    song = await player.extractor.extract(query)
    if not song:
        raise LookupError("No results found.")
    if not song.get("title") or not song.get("url"):
        raise ValueError("Could not extract audio from this video.")
    await player.enqueue(song, context)
    return song


def setup_commands(bot: commands.Bot, manager: MusicPlayerManager) -> None:
    @bot.command(name="join")
    async def join(ctx: commands.Context):
        if ctx.author.voice is None:
            await ctx.send("❌ Join a voice channel first!")
            return
        try:
            player = manager.get_player(ctx.guild.id)
            await player.join(ctx.author.voice.channel)
            player.remember_context(ctx)
            await ctx.send(f"🔊 Joined **{ctx.author.voice.channel.name}**")
        except asyncio.TimeoutError:
            await ctx.send("❌ Discord voice connection timed out. Try `!join` again.")
        except Exception as exc:
            logger.exception("Voice connection error")
            await ctx.send(f"❌ Could not connect to voice: `{exc}`")

    @bot.command(name="play")
    async def play(ctx: commands.Context, *, search: str):
        player = manager.get_player(ctx.guild.id)
        try:
            await _connect_for_user(player, ctx.author)
            song = await _queue_song(player, search, ctx)
            await ctx.send(f"🎵 Added to queue: **{song['title']}**")
        except (ValueError, LookupError) as exc:
            await ctx.send(f"❌ {exc}")
        except asyncio.TimeoutError:
            await ctx.send("❌ Voice connection timed out. Try `!play` again.")
        except Exception as exc:
            logger.exception("Could not load requested song")
            await ctx.send(f"❌ Could not load the song: `{exc}`")

    @bot.command(name="skip")
    async def skip(ctx: commands.Context):
        player = manager.get_player(ctx.guild.id)
        await ctx.send("⏭ Song skipped" if player.skip() else "❌ Nothing is playing.")

    @bot.command(name="queue")
    async def queue(ctx: commands.Context):
        player = manager.get_player(ctx.guild.id)
        if not player.queue:
            await ctx.send("🎵 Queue is empty")
            return
        embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.blue())
        embed.description = "\n".join(f"**{i}.** {song['title']}" for i, song in enumerate(player.queue[:10], 1))
        embed.set_footer(text=f"{len(player.queue)} songs in queue")
        await ctx.send(embed=embed)

    @bot.command(name="remove")
    async def remove(ctx: commands.Context, index: int):
        player = manager.get_player(ctx.guild.id)
        try:
            song = await player.remove(index - 1)
            await ctx.send(f"🗑 Removed **{song['title']}**")
        except IndexError:
            await ctx.send("❌ Invalid queue index.")

    @bot.command(name="shuffle")
    async def shuffle(ctx: commands.Context):
        player = manager.get_player(ctx.guild.id)
        if len(player.queue) < 2:
            await ctx.send("❌ Not enough songs to shuffle.")
            return
        await player.shuffle()
        await ctx.send("🔀 Queue shuffled")

    @bot.command(name="loop_cmd")
    async def loop_cmd(ctx: commands.Context):
        player = manager.get_player(ctx.guild.id)
        await player.set_loop(not player.loop_enabled)
        await ctx.send("🔁 Loop enabled" if player.loop_enabled else "🔁 Loop disabled")

    @bot.command(name="disconnect")
    async def disconnect(ctx: commands.Context):
        player = manager.get_player(ctx.guild.id)
        if not player.voice_client:
            await ctx.send("❌ Bot is not connected.")
            return
        await player.stop(disconnect=True)
        await ctx.send("👋 Disconnected")

    @bot.tree.command(name="join", description="Join your current voice channel")
    async def slash_join(interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
            await interaction.response.send_message("❌ Join a voice channel first!", ephemeral=True)
            return
        try:
            player = manager.get_player(interaction.guild_id)
            await player.join(interaction.user.voice.channel)
            player.remember_context(InteractionContext(channel=interaction.channel, client=bot, channel_id=interaction.channel_id))
            await interaction.response.send_message(f"🔊 Joined **{interaction.user.voice.channel.name}**")
        except Exception as exc:
            logger.exception("Voice connection error")
            await interaction.response.send_message(f"❌ Could not connect to voice: `{exc}`", ephemeral=True)

    @bot.tree.command(name="play", description="Play a song or YouTube search")
    @app_commands.describe(search="Song name, YouTube URL, or search query")
    async def slash_play(interaction: discord.Interaction, search: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
            await interaction.response.send_message("❌ Join a voice channel first!", ephemeral=True)
            return
        await interaction.response.defer()
        player = manager.get_player(interaction.guild_id)
        context = InteractionContext(channel=interaction.channel, client=bot, channel_id=interaction.channel_id)
        try:
            await player.join(interaction.user.voice.channel)
            song = await _queue_song(player, search, context)
            await interaction.followup.send(f"🎵 Added to queue: **{song['title']}**")
        except (ValueError, LookupError) as exc:
            await interaction.followup.send(f"❌ {exc}")
        except Exception as exc:
            logger.exception("Could not load requested song")
            await interaction.followup.send(f"❌ Could not load the song: `{exc}`")

    @bot.tree.command(name="skip", description="Skip the currently playing song")
    async def slash_skip(interaction: discord.Interaction):
        player = manager.get_player(interaction.guild_id)
        skipped = player.skip()
        await interaction.response.send_message("⏭ Song skipped" if skipped else "❌ Nothing is playing.", ephemeral=not skipped)

    @bot.tree.command(name="queue", description="Show the current music queue")
    async def slash_queue(interaction: discord.Interaction):
        player = manager.get_player(interaction.guild_id)
        if not player.queue:
            await interaction.response.send_message("🎵 Queue is empty")
            return
        embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.blue())
        embed.description = "\n".join(f"**{i}.** {song['title']}" for i, song in enumerate(player.queue[:10], 1))
        embed.set_footer(text=f"{len(player.queue)} songs in queue")
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="remove", description="Remove a song from the queue")
    @app_commands.describe(index="Queue number to remove")
    async def slash_remove(interaction: discord.Interaction, index: int):
        player = manager.get_player(interaction.guild_id)
        try:
            song = await player.remove(index - 1)
            await interaction.response.send_message(f"🗑 Removed **{song['title']}**")
        except IndexError:
            await interaction.response.send_message("❌ Invalid queue index.", ephemeral=True)

    @bot.tree.command(name="shuffle", description="Shuffle the music queue")
    async def slash_shuffle(interaction: discord.Interaction):
        player = manager.get_player(interaction.guild_id)
        if len(player.queue) < 2:
            await interaction.response.send_message("❌ Not enough songs to shuffle.", ephemeral=True)
            return
        await player.shuffle()
        await interaction.response.send_message("🔀 Queue shuffled")

    @bot.tree.command(name="loop", description="Toggle music loop mode")
    async def slash_loop(interaction: discord.Interaction):
        player = manager.get_player(interaction.guild_id)
        await player.set_loop(not player.loop_enabled)
        await interaction.response.send_message("🔁 Loop enabled" if player.loop_enabled else "🔁 Loop disabled")

    @bot.tree.command(name="disconnect", description="Disconnect the music bot")
    async def slash_disconnect(interaction: discord.Interaction):
        player = manager.get_player(interaction.guild_id)
        if not player.voice_client:
            await interaction.response.send_message("❌ Bot is not connected.", ephemeral=True)
            return
        await player.stop(disconnect=True)
        await interaction.response.send_message("👋 Disconnected")

    bot.music_player_manager = manager
