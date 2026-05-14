"""
AuraBot — Stream Worker
Manages FFmpeg transcoding tasks asynchronously with health monitoring.
Can run as independent worker for distributed setups.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from config import cfg
from core.logger import get_logger

log = get_logger("worker.stream")


@dataclass
class StreamTask:
    chat_id: int
    track_id: str
    started_at: float = field(default_factory=time.time)
    retries: int = 0
    MAX_RETRIES: int = 3

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at

    @property
    def can_retry(self) -> bool:
        return self.retries < self.MAX_RETRIES


class StreamWorker:
    """
    Monitors active FFmpeg stream processes.
    Auto-recovers failed streams by re-requesting playback.
    Tracks per-chat streaming metrics.
    """

    def __init__(self) -> None:
        self._tasks: Dict[int, StreamTask] = {}
        self._monitor_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        log.info("Stream worker started.")

    async def stop(self) -> None:
        if self._monitor_task:
            self._monitor_task.cancel()
        log.info("Stream worker stopped.")

    def register(self, chat_id: int, track_id: str) -> None:
        self._tasks[chat_id] = StreamTask(chat_id=chat_id, track_id=track_id)
        log.debug(f"[StreamWorker] Registered stream for chat {chat_id}")

    def unregister(self, chat_id: int) -> None:
        self._tasks.pop(chat_id, None)

    async def _monitor_loop(self) -> None:
        """Every 5 seconds, check if active streams are still alive."""
        while True:
            await asyncio.sleep(5)
            await self._check_streams()

    async def _check_streams(self) -> None:
        from music.ffmpeg import ffmpeg_engine
        from music.player import player

        dead_chats = []
        for chat_id, task in list(self._tasks.items()):
            if not ffmpeg_engine.is_running(chat_id):
                log.warning(f"[StreamWorker] Dead stream detected: chat {chat_id}")
                dead_chats.append(chat_id)

        for chat_id in dead_chats:
            task = self._tasks.get(chat_id)
            if not task:
                continue
            if task.can_retry:
                task.retries += 1
                log.info(f"[StreamWorker] Retry {task.retries}/{task.MAX_RETRIES} for chat {chat_id}")
                asyncio.create_task(self._recover_stream(chat_id))
            else:
                log.error(f"[StreamWorker] Max retries exceeded for chat {chat_id}. Stopping.")
                self.unregister(chat_id)
                asyncio.create_task(player.on_stream_end(chat_id))

    async def _recover_stream(self, chat_id: int) -> None:
        from music.player import player
        try:
            state = await player.now_playing(chat_id)
            if state and state.current:
                await player.play(chat_id, state.current, force=True, seekable=int(state.position))
        except Exception as e:
            log.error(f"[StreamWorker] Recovery failed for {chat_id}: {e}")

    def active_count(self) -> int:
        return len(self._tasks)

    def status(self) -> dict:
        return {
            "active_streams": self.active_count(),
            "streams": [
                {
                    "chat_id": t.chat_id,
                    "track_id": t.track_id,
                    "elapsed": round(t.elapsed),
                    "retries": t.retries,
                }
                for t in self._tasks.values()
            ],
        }


stream_worker = StreamWorker()
