"""Creates and owns independent players keyed by Discord guild ID."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .player import MusicPlayer
from .youtube import YouTubeExtractor


class MusicPlayerManager:
    def __init__(self, extractor: YouTubeExtractor | None = None, ffmpeg_path: str | None = None):
        self.extractor = extractor or YouTubeExtractor()
        self.ffmpeg_path = ffmpeg_path
        self._players: dict[int, MusicPlayer] = {}
        self._update_callback: Callable[[int, dict[str, Any]], Awaitable[None]] | None = None

    def get_player(self, guild_id: int) -> MusicPlayer:
        if guild_id not in self._players:
            player = MusicPlayer(guild_id, self.extractor, self, self.ffmpeg_path)
            player.set_update_callback(self._update_callback)
            self._players[guild_id] = player
        return self._players[guild_id]

    def get_existing_player(self, guild_id: int) -> MusicPlayer | None:
        return self._players.get(guild_id)

    def players(self) -> tuple[MusicPlayer, ...]:
        return tuple(self._players.values())

    def set_update_callback(
        self, callback: Callable[[int, dict[str, Any]], Awaitable[None]] | None
    ) -> None:
        self._update_callback = callback
        for player in self._players.values():
            player.set_update_callback(callback)
