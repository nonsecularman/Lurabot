"""
AuraBot — Source Extractor
Resolves and extracts playback URLs from all supported sources.
Uses yt-dlp for YouTube/SoundCloud/direct URLs.
"""

from __future__ import annotations

import asyncio
import re
from typing import List, Optional
from urllib.parse import urlparse

import yt_dlp

from config import cfg
from core.logger import get_logger
from database.models import Track

log = get_logger("extractor")


# ── URL Patterns ──────────────────────────────────────────────────────────────

YOUTUBE_REGEX = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)[\w-]+"
)
SPOTIFY_REGEX = re.compile(
    r"https?://open\.spotify\.com/(track|album|playlist|artist)/[\w]+"
)
SOUNDCLOUD_REGEX = re.compile(r"https?://soundcloud\.com/[\w/-]+")
APPLE_MUSIC_REGEX = re.compile(r"https?://music\.apple\.com/.+")


# ── yt-dlp Options ────────────────────────────────────────────────────────────

def _ydl_opts(audio_only: bool = True) -> dict:
    opts = {
        "format": "bestaudio/best" if audio_only else "best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "socket_timeout": 30,
        "retries": 3,
        "postprocessors": [],
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    }
    if cfg.YTDL_COOKIES:
        opts["cookiefile"] = cfg.YTDL_COOKIES
    return opts


def _ydl_playlist_opts() -> dict:
    opts = _ydl_opts()
    opts["noplaylist"] = False
    opts["extract_flat"] = "in_playlist"
    return opts


# ── Extractor ──────────────────────────────────────────────────────────────────

class SourceExtractor:
    """Extracts playable URLs and metadata from all supported sources."""

    async def resolve(self, query: str, user_id: int = 0) -> Optional[Track]:
        """
        Smart resolver: detects source type and returns a Track.
        query can be a URL or a search string.
        """
        query = query.strip()

        # Telegram file — handled elsewhere
        if query.startswith("tg://"):
            return None

        if SPOTIFY_REGEX.match(query):
            return await self._from_spotify(query, user_id)

        if SOUNDCLOUD_REGEX.match(query):
            return await self._from_ytdlp(query, user_id, source="soundcloud")

        if APPLE_MUSIC_REGEX.match(query):
            return await self._from_apple_music(query, user_id)

        if YOUTUBE_REGEX.match(query) or urlparse(query).scheme in ("http", "https"):
            return await self._from_ytdlp(query, user_id, source="youtube")

        # Plain text — YouTube search
        return await self._youtube_search(query, user_id)

    async def resolve_playlist(self, url: str, user_id: int = 0) -> List[Track]:
        """Resolve a playlist URL into multiple Tracks."""
        return await asyncio.to_thread(self._extract_playlist_sync, url, user_id)

    # ── YouTube / Generic URL ──────────────────────────────────────────────────

    async def _from_ytdlp(
        self, url: str, user_id: int, source: str = "youtube"
    ) -> Optional[Track]:
        return await asyncio.to_thread(self._extract_sync, url, user_id, source)

    def _extract_sync(self, url: str, user_id: int, source: str) -> Optional[Track]:
        with yt_dlp.YoutubeDL(_ydl_opts()) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None
                return self._info_to_track(info, user_id, source)
            except yt_dlp.utils.DownloadError as e:
                log.warning(f"yt-dlp extraction failed for {url}: {e}")
                return None

    def _extract_playlist_sync(self, url: str, user_id: int) -> List[Track]:
        tracks = []
        with yt_dlp.YoutubeDL(_ydl_playlist_opts()) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                entries = info.get("entries", [])
                for entry in entries[:50]:  # cap at 50
                    if entry and entry.get("url"):
                        track = self._info_to_track(entry, user_id, "youtube")
                        if track:
                            tracks.append(track)
            except Exception as e:
                log.warning(f"Playlist extraction failed: {e}")
        return tracks

    async def _youtube_search(self, query: str, user_id: int) -> Optional[Track]:
        search_url = f"ytsearch1:{query}"
        return await self._from_ytdlp(search_url, user_id, source="youtube")

    # ── Spotify ───────────────────────────────────────────────────────────────

    async def _from_spotify(self, url: str, user_id: int) -> Optional[Track]:
        if not (cfg.SPOTIFY_CLIENT_ID and cfg.SPOTIFY_CLIENT_SECRET):
            # Fallback: search YouTube
            title = await self._spotify_get_title(url)
            if title:
                return await self._youtube_search(title, user_id)
            return None
        # Full Spotify API integration when credentials available
        from services.spotify import spotify_service
        meta = await spotify_service.get_track(url)
        if not meta:
            return None
        search_q = f"{meta['name']} {meta['artist']}"
        track = await self._youtube_search(search_q, user_id)
        if track:
            # Enrich with Spotify metadata
            track.title = meta["name"]
            track.artist = meta["artist"]
            track.thumbnail = meta.get("image")
            track.source = "spotify"
        return track

    async def _spotify_get_title(self, url: str) -> Optional[str]:
        """Minimal Spotify scrape for title (no credentials)."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    follow_redirects=True,
                )
                match = re.search(r"<title>(.+?) - song by", resp.text)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    async def _from_apple_music(self, url: str, user_id: int) -> Optional[Track]:
        # Search YouTube as fallback for Apple Music
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            match = re.search(r'"og:title" content="(.+?)"', resp.text)
            if match:
                return await self._youtube_search(match.group(1), user_id)
        except Exception:
            pass
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _info_to_track(self, info: dict, user_id: int, source: str) -> Optional[Track]:
        url = info.get("url") or info.get("manifest_url")
        if not url:
            # Try formats
            for fmt in reversed(info.get("formats", [])):
                if fmt.get("url") and fmt.get("acodec") != "none":
                    url = fmt["url"]
                    break
        if not url:
            return None

        return Track(
            track_id=info.get("id", ""),
            title=info.get("title") or info.get("track") or "Unknown",
            artist=info.get("uploader") or info.get("artist"),
            album=info.get("album"),
            duration=int(info.get("duration") or 0),
            url=url,
            thumbnail=info.get("thumbnail"),
            source=source,
            is_live=bool(info.get("is_live")),
            added_by=user_id,
        )


# Singleton
extractor = SourceExtractor()
