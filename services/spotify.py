"""
AuraBot — Spotify Service
Full Spotify Web API integration: search, track/album/playlist resolution.
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any, Dict, List, Optional

import httpx

from config import cfg
from core.logger import get_logger
from database.redis import cache_get, cache_set

log = get_logger("services.spotify")

TOKEN_CACHE_KEY = "spotify_token"


class SpotifyService:

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._token_expiry: float = 0

    async def _get_token(self) -> Optional[str]:
        if not (cfg.SPOTIFY_CLIENT_ID and cfg.SPOTIFY_CLIENT_SECRET):
            return None

        # Check Redis cache first
        cached = await cache_get(TOKEN_CACHE_KEY)
        if cached:
            return cached

        credentials = base64.b64encode(
            f"{cfg.SPOTIFY_CLIENT_ID}:{cfg.SPOTIFY_CLIENT_SECRET}".encode()
        ).decode()

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://accounts.spotify.com/api/token",
                    data={"grant_type": "client_credentials"},
                    headers={"Authorization": f"Basic {credentials}"},
                )
                data = resp.json()
                token = data["access_token"]
                ttl = data.get("expires_in", 3600) - 60
                await cache_set(TOKEN_CACHE_KEY, token, ttl=ttl)
                return token
        except Exception as e:
            log.error(f"Spotify auth failed: {e}")
            return None

    async def _request(self, endpoint: str, params: dict = {}) -> Optional[dict]:
        token = await self._get_token()
        if not token:
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.spotify.com/v1/{endpoint}",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            log.error(f"Spotify API error: {e}")
        return None

    async def get_track(self, url_or_id: str) -> Optional[Dict[str, Any]]:
        track_id = self._extract_id(url_or_id, "track")
        if not track_id:
            return None
        data = await self._request(f"tracks/{track_id}")
        if not data:
            return None
        artists = ", ".join(a["name"] for a in data.get("artists", []))
        return {
            "id": data["id"],
            "name": data["name"],
            "artist": artists,
            "album": data.get("album", {}).get("name"),
            "duration": data.get("duration_ms", 0) // 1000,
            "image": (data.get("album", {}).get("images") or [{}])[0].get("url"),
        }

    async def get_album_tracks(self, url_or_id: str) -> List[Dict[str, Any]]:
        album_id = self._extract_id(url_or_id, "album")
        if not album_id:
            return []
        data = await self._request(f"albums/{album_id}/tracks", {"limit": 50})
        if not data:
            return []
        tracks = []
        for item in data.get("items", []):
            artists = ", ".join(a["name"] for a in item.get("artists", []))
            tracks.append({
                "id": item["id"],
                "name": item["name"],
                "artist": artists,
                "duration": item.get("duration_ms", 0) // 1000,
            })
        return tracks

    async def get_playlist_tracks(self, url_or_id: str) -> List[Dict[str, Any]]:
        playlist_id = self._extract_id(url_or_id, "playlist")
        if not playlist_id:
            return []
        data = await self._request(f"playlists/{playlist_id}/tracks", {"limit": 100})
        if not data:
            return []
        tracks = []
        for item in data.get("items", []):
            t = item.get("track")
            if not t:
                continue
            artists = ", ".join(a["name"] for a in t.get("artists", []))
            tracks.append({
                "id": t["id"],
                "name": t["name"],
                "artist": artists,
                "duration": t.get("duration_ms", 0) // 1000,
                "image": (t.get("album", {}).get("images") or [{}])[0].get("url"),
            })
        return tracks

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        data = await self._request(
            "search", {"q": query, "type": "track", "limit": limit}
        )
        if not data:
            return []
        results = []
        for item in data.get("tracks", {}).get("items", []):
            artists = ", ".join(a["name"] for a in item.get("artists", []))
            results.append({
                "id": item["id"],
                "name": item["name"],
                "artist": artists,
                "duration": item.get("duration_ms", 0) // 1000,
            })
        return results

    @staticmethod
    def _extract_id(url_or_id: str, resource_type: str) -> Optional[str]:
        """Extract Spotify ID from URL or return raw ID."""
        if url_or_id.startswith("http"):
            parts = url_or_id.split("/")
            try:
                idx = parts.index(resource_type)
                raw = parts[idx + 1]
                return raw.split("?")[0]
            except (ValueError, IndexError):
                return None
        return url_or_id


spotify_service = SpotifyService()
      
