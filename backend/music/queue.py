"""In-memory, per-guild music queue."""

from __future__ import annotations

import random
from collections.abc import Iterable
from typing import Any


class MusicQueue:
    def __init__(self) -> None:
        self._songs: list[dict[str, Any]] = []

    def __len__(self) -> int:
        return len(self._songs)

    def __bool__(self) -> bool:
        return bool(self._songs)

    def __iter__(self):
        return iter(self._songs)

    def __getitem__(self, index):
        return self._songs[index]

    def add(self, song: dict[str, Any]) -> None:
        self._songs.append(dict(song))

    def prepend(self, song: dict[str, Any]) -> None:
        self._songs.insert(0, dict(song))

    def extend(self, songs: Iterable[dict[str, Any]]) -> None:
        self._songs.extend(dict(song) for song in songs)

    def pop(self, index: int = 0) -> dict[str, Any]:
        return self._songs.pop(index)

    def clear(self) -> None:
        self._songs.clear()

    def shuffle(self) -> None:
        random.shuffle(self._songs)

    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(song) for song in self._songs]
