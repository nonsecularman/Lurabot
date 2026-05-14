"""
AuraBot — Music Queue
Redis-backed distributed queue with loop, shuffle, priority, and crash recovery.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import List, Optional

from database.models import LoopMode, QueueState, Track
from database.redis import (
    Keys,
    cache_del,
    cache_get,
    cache_set,
    del_playback,
    get_playback,
    queue_clear,
    queue_len,
    queue_peek,
    queue_pop,
    queue_push,
    queue_push_priority,
    queue_shuffle,
    redis,
    set_playback,
)
from core.logger import get_logger

log = get_logger("music.queue")


class MusicQueue:
    """
    Manages per-chat queue state backed by Redis.
    All operations are async-safe.
    """

    # ── Add / Remove ──────────────────────────────────────────────────────────

    async def add(self, chat_id: int, track: Track) -> int:
        await queue_push(chat_id, track.model_dump(mode="json"))
        log.debug(f"[{chat_id}] queued: {track.title}")
        return await queue_len(chat_id)

    async def add_next(self, chat_id: int, track: Track) -> None:
        """Insert track at front (plays next)."""
        await queue_push_priority(chat_id, track.model_dump(mode="json"))

    async def add_many(self, chat_id: int, tracks: List[Track]) -> int:
        pipe = redis().pipeline()
        for t in tracks:
            pipe.rpush(Keys.queue(chat_id), json.dumps(t.model_dump(mode="json")))
        await pipe.execute()
        return await queue_len(chat_id)

    async def pop(self, chat_id: int) -> Optional[Track]:
        raw = await queue_pop(chat_id)
        return Track(**raw) if raw else None

    async def peek(self, chat_id: int, count: int = 10) -> List[Track]:
        items = await queue_peek(chat_id, count)
        return [Track(**i) for i in items]

    async def length(self, chat_id: int) -> int:
        return await queue_len(chat_id)

    async def clear(self, chat_id: int) -> None:
        await queue_clear(chat_id)

    async def remove(self, chat_id: int, index: int) -> Optional[Track]:
        """Remove track at 0-based index."""
        key = Keys.queue(chat_id)
        items = await redis().lrange(key, 0, -1)
        if not (0 <= index < len(items)):
            return None
        removed = json.loads(items[index])
        # Rebuild queue without removed item
        pipe = redis().pipeline()
        pipe.delete(key)
        for i, item in enumerate(items):
            if i != index:
                pipe.rpush(key, item)
        await pipe.execute()
        return Track(**removed)

    async def shuffle(self, chat_id: int) -> None:
        await queue_shuffle(chat_id)
        log.debug(f"[{chat_id}] queue shuffled")

    async def move(self, chat_id: int, from_idx: int, to_idx: int) -> bool:
        key = Keys.queue(chat_id)
        items = await redis().lrange(key, 0, -1)
        if not (0 <= from_idx < len(items) and 0 <= to_idx < len(items)):
            return False
        item = items.pop(from_idx)
        items.insert(to_idx, item)
        pipe = redis().pipeline()
        pipe.delete(key)
        for i in items:
            pipe.rpush(key, i)
        await pipe.execute()
        return True

    # ── Playback State ─────────────────────────────────────────────────────────

    async def set_state(self, chat_id: int, state: QueueState) -> None:
        await set_playback(chat_id, state.model_dump(mode="json"))

    async def get_state(self, chat_id: int) -> Optional[QueueState]:
        raw = await get_playback(chat_id)
        return QueueState(**raw) if raw else None

    async def get_or_create_state(self, chat_id: int) -> QueueState:
        state = await self.get_state(chat_id)
        if not state:
            state = QueueState(chat_id=chat_id)
            await self.set_state(chat_id, state)
        return state

    async def update_state(self, chat_id: int, **kwargs) -> None:
        state = await self.get_or_create_state(chat_id)
        for k, v in kwargs.items():
            setattr(state, k, v)
        await self.set_state(chat_id, state)

    async def clear_state(self, chat_id: int) -> None:
        await del_playback(chat_id)
        await queue_clear(chat_id)

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def set_loop(self, chat_id: int, mode: LoopMode) -> None:
        await self.update_state(chat_id, loop=mode)

    async def get_loop(self, chat_id: int) -> LoopMode:
        state = await self.get_state(chat_id)
        return state.loop if state else LoopMode.NONE

    # ── Volume ────────────────────────────────────────────────────────────────

    async def set_volume(self, chat_id: int, volume: int) -> None:
        volume = max(0, min(200, volume))
        await self.update_state(chat_id, volume=volume)

    async def get_volume(self, chat_id: int) -> int:
        state = await self.get_state(chat_id)
        return state.volume if state else 100

    # ── Next Track Logic ──────────────────────────────────────────────────────

    async def get_next(self, chat_id: int) -> Optional[Track]:
        """
        Advance queue based on loop mode.
        Returns next track to play, or None if queue is exhausted.
        """
        state = await self.get_or_create_state(chat_id)

        if state.loop == LoopMode.TRACK:
            return state.current  # replay same track

        next_track = await self.pop(chat_id)

        if next_track is None:
            if state.loop == LoopMode.QUEUE and state.current:
                # Re-add current track and return it
                await self.add(chat_id, state.current)
                return await self.pop(chat_id)
            return None

        # If loop queue, re-enqueue current track at the back
        if state.loop == LoopMode.QUEUE and state.current:
            await self.add(chat_id, state.current)

        return next_track


# Singleton
music_queue = MusicQueue()
