"""
AuraBot — Autoplay Engine
Recommends next tracks using listening history + AI + YouTube search.
"""

from __future__ import annotations

import asyncio
import random
from typing import List, Optional

from config import cfg
from core.logger import get_logger
from database.models import Track
from database.mongo import get_collection

log = get_logger("music.autoplay")


class AutoplayEngine:
    """
    Generates track recommendations when the queue is exhausted.

    Strategy (in order):
    1. AI-based recommendation from recent history
    2. Related YouTube search from last track's artist
    3. Genre-based fallback
    """

    async def get_recommendation(self, chat_id: int) -> Optional[Track]:
        """Return a recommended next track for the chat."""
        last_track = await self._get_last_played(chat_id)
        if not last_track:
            return None

        # Try AI recommendation
        if cfg.ENABLE_AI and (cfg.OPENAI_API_KEY or cfg.ANTHROPIC_API_KEY):
            rec = await self._ai_recommend(chat_id, last_track)
            if rec:
                return rec

        # Fallback: search by artist
        if last_track.get("artist"):
            return await self._artist_search(last_track)

        return None

    async def _get_last_played(self, chat_id: int) -> Optional[dict]:
        doc = await get_collection("play_history").find_one(
            {"chat_id": chat_id},
            sort=[("played_at", -1)],
        )
        return doc

    async def _ai_recommend(self, chat_id: int, last_track: dict) -> Optional[Track]:
        try:
            # Fetch recent 10 plays
            docs = await get_collection("play_history").find(
                {"chat_id": chat_id}
            ).sort("played_at", -1).limit(10).to_list(length=10)

            history = [f"{d.get('title', '')} by {d.get('artist', '')}" for d in docs]
            from plugins.ai.assistant import ai_service
            recs = await ai_service.recommend_music(history, count=3)
            if not recs:
                return None

            # Search YouTube for the first recommendation
            from music.extractor import extractor
            query = recs[0]
            log.debug(f"[Autoplay:{chat_id}] AI rec: {query}")
            track = await extractor.resolve(query, user_id=0)
            return track
        except Exception as e:
            log.warning(f"Autoplay AI error: {e}")
            return None

    async def _artist_search(self, last_track: dict) -> Optional[Track]:
        artist = last_track.get("artist", "")
        title = last_track.get("title", "")
        if not artist:
            return None
        query = f"{artist} best songs"
        try:
            from music.extractor import extractor
            return await extractor.resolve(query, user_id=0)
        except Exception as e:
            log.warning(f"Autoplay artist search error: {e}")
            return None


autoplay = AutoplayEngine()
