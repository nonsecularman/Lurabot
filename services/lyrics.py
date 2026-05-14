"""
AuraBot — Lyrics Service
Fetches lyrics from multiple sources with Redis caching.
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

import httpx

from config import cfg
from core.logger import get_logger
from database.redis import cache_get, cache_set

log = get_logger("lyrics")

LYRICS_CACHE_TTL = 86400  # 24 hours


class LyricsService:

    async def get_lyrics(self, title: str, artist: str = "") -> Optional[str]:
        cache_key = f"lyrics:{title}:{artist}".lower().replace(" ", "_")
        cached = await cache_get(cache_key)
        if cached:
            return cached

        # Try sources in order
        lyrics = (
            await self._from_lrclib(title, artist)
            or await self._from_lyrics_ovh(title, artist)
        )

        if lyrics:
            await cache_set(cache_key, lyrics, ttl=LYRICS_CACHE_TTL)
        return lyrics

    async def _from_lrclib(self, title: str, artist: str) -> Optional[str]:
        """lrclib.net — free, no key required."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://lrclib.net/api/search",
                    params={"track_name": title, "artist_name": artist, "limit": 1},
                )
                data = resp.json()
                if data and isinstance(data, list):
                    item = data[0]
                    return item.get("plainLyrics") or item.get("syncedLyrics")
        except Exception as e:
            log.debug(f"lrclib error: {e}")
        return None

    async def _from_lyrics_ovh(self, title: str, artist: str) -> Optional[str]:
        """lyrics.ovh — simple free API."""
        if not artist:
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
                resp = await client.get(url)
                data = resp.json()
                return data.get("lyrics")
        except Exception as e:
            log.debug(f"lyrics.ovh error: {e}")
        return None


lyrics_service = LyricsService()


def lyrics_router(app) -> None:
    from pyrogram import Client, filters
    from pyrogram.types import Message
    from core.security import ban_check, cooldown
    from music.player import player

    @app.on_message(filters.command(["lyrics", "ly"]))
    @ban_check
    @cooldown(10)
    async def cmd_lyrics(client: Client, message: Message) -> None:
        # Check for explicit query
        query_parts = message.command[1:]
        if query_parts:
            query = " ".join(query_parts)
            # Try to split "artist - title"
            if " - " in query:
                artist, title = query.split(" - ", 1)
            else:
                title, artist = query, ""
        else:
            # Use currently playing track
            state = await player.now_playing(message.chat.id)
            if not state or not state.current:
                await message.reply_text(
                    "❌ No track playing. Use `/lyrics Artist - Song Title`."
                )
                return
            title = state.current.title
            artist = state.current.artist or ""

        status = await message.reply_text(f"🔍 Searching lyrics for **{title}**...")
        lyrics = await lyrics_service.get_lyrics(title, artist)

        if not lyrics:
            await status.edit_text(
                f"❌ Lyrics not found for **{title}**.\n"
                f"Try: `/lyrics Artist - Song Title`"
            )
            return

        # Split into chunks if too long (Telegram 4096 char limit)
        MAX_LEN = 3800
        header = f"🎵 **{title}**" + (f" — {artist}" if artist else "") + "\n\n"
        full = header + lyrics.strip()

        if len(full) <= MAX_LEN:
            await status.edit_text(full)
        else:
            await status.delete()
            chunks = [full[i:i + MAX_LEN] for i in range(0, len(full), MAX_LEN)]
            for chunk in chunks:
                await message.reply_text(chunk)
          
