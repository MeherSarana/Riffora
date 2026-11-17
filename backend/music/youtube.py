"""YouTube search and stream extraction using yt-dlp."""

from __future__ import annotations

import asyncio
from typing import Any

import yt_dlp

YTDL_OPTIONS = {
    "format": "bestaudio/best", "noplaylist": True, "quiet": True,
    "no_warnings": True, "default_search": "ytsearch", "js_runtimes": {"deno": {}},
}


class YouTubeExtractor:
    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self._options = {**YTDL_OPTIONS, **(options or {})}

    def _extract(self, query: str) -> dict[str, Any] | None:
        with yt_dlp.YoutubeDL(self._options) as ytdl:
            info = ytdl.extract_info(query, download=False)
        if not info:
            return None
        if info.get("entries") is not None:
            info = next((entry for entry in info["entries"] if entry), None)
        if not info:
            return None
        return {
            "title": info.get("title"), "url": info.get("url"),
            "webpage_url": info.get("webpage_url") or info.get("original_url") or query,
            "thumbnail": info.get("thumbnail"), "duration": info.get("duration"),
            "uploader": info.get("uploader"),
        }

    async def extract(self, query: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._extract, query)

    async def refresh(self, song: dict[str, Any]) -> dict[str, Any]:
        webpage_url = song.get("webpage_url")
        if not webpage_url:
            if song.get("url"):
                return song
            raise ValueError("Track has no source URL to refresh.")
        refreshed = await self.extract(webpage_url)
        if not refreshed or not refreshed.get("url"):
            raise ValueError(f"Could not refresh audio for {song.get('title', 'track')}.")
        return {**song, **refreshed}
