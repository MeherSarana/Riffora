"""One Discord voice player and playback state for a single guild."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from typing import Any, Awaitable, Callable

import discord

from .queue import MusicQueue
from .youtube import YouTubeExtractor

logger = logging.getLogger(__name__)
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin",
    "options": "-vn -loglevel warning",
}


class MusicPlayer:
    def __init__(self, guild_id: int, extractor: YouTubeExtractor, manager: Any, ffmpeg_path: str | None = None):
        self.guild_id = guild_id
        self.extractor = extractor
        self.manager = manager
        # discord.py passes ``executable`` directly to subprocess. ``None`` is
        # not a valid Windows executable path, so use PATH lookup by default.
        self.ffmpeg_path = ffmpeg_path or os.getenv("FFMPEG_PATH") or "ffmpeg"
        self.queue = MusicQueue()
        self.voice_client: discord.VoiceClient | None = None
        self.current: dict[str, Any] | None = None
        self._started_at: float | None = None
        self._paused_at: float | None = None
        self._paused_total = 0.0
        self.loop_enabled = False
        self.volume = 1.0
        self._queue_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._contexts: deque[Any] = deque(maxlen=10)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._update_callback: Callable[[int, dict[str, Any]], Awaitable[None]] | None = None

    def set_update_callback(self, callback: Callable[[int, dict[str, Any]], Awaitable[None]] | None) -> None:
        self._update_callback = callback

    def _notify_update(self) -> None:
        callback = self._update_callback
        if callback is None:
            return
        try:
            asyncio.get_running_loop().create_task(self._publish_update(callback))
        except RuntimeError:
            logger.debug("Skipping player update outside the event loop for guild %s", self.guild_id)

    async def _publish_update(self, callback: Callable[[int, dict[str, Any]], Awaitable[None]]) -> None:
        try:
            await callback(self.guild_id, self.snapshot())
        except Exception:
            logger.exception("Could not publish player update for guild %s", self.guild_id)

    @property
    def connected(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_connected())

    def remember_context(self, context: Any) -> None:
        if context is not None and context not in self._contexts:
            self._contexts.append(context)

    async def join(self, channel: discord.abc.Connectable) -> discord.VoiceClient:
        guild = getattr(channel, "guild", None)
        if guild is None or guild.id != self.guild_id:
            raise ValueError("Voice channel belongs to a different server.")
        voice_client = guild.voice_client
        if voice_client is None:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)
        self.voice_client = voice_client
        self._loop = asyncio.get_running_loop()
        self._notify_update()
        return voice_client

    async def enqueue(self, song: dict[str, Any], context: Any = None) -> None:
        self.remember_context(context)
        async with self._queue_lock:
            self.queue.add(song)
        self._notify_update()
        await self.start_next()

    async def start_next(self) -> None:
        async with self._start_lock:
            voice_client = self.voice_client
            if not voice_client or not voice_client.is_connected() or voice_client.is_playing() or voice_client.is_paused():
                return
            while self.queue:
                song = self.queue.pop(0)
                try:
                    fresh_song = await self.extractor.refresh(song)
                    if not fresh_song.get("url"):
                        raise ValueError("No audio stream URL was returned.")
                    source = discord.FFmpegPCMAudio(fresh_song["url"], executable=self.ffmpeg_path, **FFMPEG_OPTIONS)
                    source = discord.PCMVolumeTransformer(source, volume=self.volume)
                    self.current = fresh_song
                    self._started_at = time.monotonic()
                    self._paused_at = None
                    self._paused_total = 0.0
                    self._loop = asyncio.get_running_loop()
                    voice_client.play(source, after=self._after_playback)
                    await self._announce_now_playing(fresh_song)
                    self._notify_update()
                    return
                except Exception:
                    logger.exception("Could not start track in guild %s", self.guild_id)
                    await self._announce_error(song)
            self.current = None
            self._notify_update()

    def _after_playback(self, error: Exception | None) -> None:
        if error:
            logger.error("Discord audio playback error in guild %s: %s", self.guild_id, error)
        loop = self._loop
        if loop and not loop.is_closed():
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self._playback_finished()))

    async def _playback_finished(self) -> None:
        if self.loop_enabled and self.current:
            async with self._queue_lock:
                self.queue.add(self.current)
        self.current = None
        self._started_at = None
        self._paused_at = None
        self._paused_total = 0.0
        self._notify_update()
        await self.start_next()

    async def _send_to_context(self, *args: Any, **kwargs: Any) -> None:
        while self._contexts:
            try:
                await self._contexts[-1].send(*args, **kwargs)
                return
            except (discord.HTTPException, AttributeError, RuntimeError):
                self._contexts.pop()

    async def _announce_now_playing(self, song: dict[str, Any]) -> None:
        embed = discord.Embed(title="🎵 Now Playing", description=song.get("title", "Unknown track"), color=discord.Color.green())
        if song.get("thumbnail"):
            embed.set_thumbnail(url=song["thumbnail"])
        try:
            from backend.bot.commands import MusicControls
            await self._send_to_context(embed=embed, view=MusicControls(self.manager))
        except Exception:
            logger.exception("Could not send now-playing message for guild %s", self.guild_id)

    async def _announce_error(self, song: dict[str, Any]) -> None:
        try:
            await self._send_to_context(f"❌ Could not play **{song.get('title', 'track')}**. Skipping it.")
        except Exception:
            logger.exception("Could not report playback failure for guild %s", self.guild_id)

    def pause(self) -> bool:
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            self._paused_at = time.monotonic()
            self._notify_update()
            return True
        return False

    def resume(self) -> bool:
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            if self._paused_at is not None:
                self._paused_total += time.monotonic() - self._paused_at
                self._paused_at = None
            self._notify_update()
            return True
        return False

    def skip(self) -> bool:
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()
            self._notify_update()
            return True
        return False

    async def stop(self, disconnect: bool = False) -> None:
        async with self._queue_lock:
            self.queue.clear()
        self.current = None
        self._started_at = None
        self._paused_at = None
        self._paused_total = 0.0
        if self.voice_client:
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
            if disconnect and self.voice_client.is_connected():
                await self.voice_client.disconnect()
            if disconnect:
                self.voice_client = None
        self._notify_update()

    async def handle_voice_disconnect(self) -> None:
        """Keep an interrupted current track queued for the next explicit join."""
        if self.current:
            async with self._queue_lock:
                self.queue.prepend(self.current)
        self.current = None
        self._started_at = None
        self._paused_at = None
        self._paused_total = 0.0
        self.voice_client = None
        self._notify_update()

    async def remove(self, index: int) -> dict[str, Any]:
        async with self._queue_lock:
            if index < 0 or index >= len(self.queue):
                raise IndexError("Invalid queue index.")
            song = self.queue.pop(index)
        self._notify_update()
        return song

    async def shuffle(self) -> None:
        async with self._queue_lock:
            self.queue.shuffle()
        self._notify_update()

    async def set_volume(self, volume: float) -> None:
        if not 0 <= volume <= 2:
            raise ValueError("Volume must be between 0 and 2.")
        self.volume = volume
        if self.voice_client and isinstance(self.voice_client.source, discord.PCMVolumeTransformer):
            self.voice_client.source.volume = volume
        self._notify_update()

    async def set_loop(self, enabled: bool) -> None:
        self.loop_enabled = enabled
        self._notify_update()

    def snapshot(self) -> dict[str, Any]:
        now = self._paused_at if self._paused_at is not None else time.monotonic()
        elapsed = max(0.0, now - self._started_at - self._paused_total) if self._started_at is not None else 0.0
        channel = self.voice_client.channel if self.voice_client and self.voice_client.is_connected() else None
        return {
            "guild_id": self.guild_id,
            "connected": self.connected,
            "voice_channel": {"id": channel.id, "name": channel.name} if channel else None,
            "playing": self.current is not None and bool(self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused())),
            "paused": bool(self.voice_client and self.voice_client.is_paused()),
            "current": self.current,
            "elapsed": elapsed,
            "queue": self.queue.snapshot(),
            "loop_enabled": self.loop_enabled,
            "volume": self.volume,
        }
