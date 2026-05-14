"""
AuraBot — Queue Worker
Async background worker that processes stream jobs from Redis pub/sub.
Handles retries, crash recovery, and worker health reporting.
"""

from __future__ import annotations

import asyncio
import json
import signal
import time
from typing import Optional

from config import cfg
from core.logger import get_logger
from database.redis import redis, subscribe, Keys

log = get_logger("worker.queue")

WORKER_HEARTBEAT_INTERVAL = 30  # seconds
WORKER_CHANNEL = "aura:jobs"


class QueueWorker:
    """
    Subscribes to Redis pub/sub channel for stream job events.
    Designed to be run as a standalone process for horizontal scaling.
    """

    def __init__(self, worker_id: str = "worker-0") -> None:
        self.worker_id = worker_id
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._start_time = time.time()

    async def start(self) -> None:
        self._running = True
        log.info(f"[{self.worker_id}] Starting queue worker...")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        await self._run_loop()

    async def stop(self) -> None:
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        log.info(f"[{self.worker_id}] Stopped.")

    async def _run_loop(self) -> None:
        async with subscribe(WORKER_CHANNEL) as pubsub:
            log.success(f"[{self.worker_id}] Listening on channel: {WORKER_CHANNEL}")
            async for message in pubsub.listen():
                if not self._running:
                    break
                if message["type"] != "message":
                    continue
                await self._handle_message(message["data"])

    async def _handle_message(self, raw: str) -> None:
        try:
            job = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(f"[{self.worker_id}] Invalid job payload: {raw!r}")
            return

        job_type = job.get("type")
        chat_id = job.get("chat_id")
        log.debug(f"[{self.worker_id}] Job: {job_type} for chat {chat_id}")

        handlers = {
            "play": self._handle_play,
            "skip": self._handle_skip,
            "stop": self._handle_stop,
            "seek": self._handle_seek,
        }

        handler = handlers.get(job_type)
        if handler:
            try:
                await asyncio.wait_for(handler(job), timeout=30.0)
            except asyncio.TimeoutError:
                log.error(f"[{self.worker_id}] Job {job_type} timed out for {chat_id}")
            except Exception as e:
                log.error(f"[{self.worker_id}] Job {job_type} failed: {e}")
        else:
            log.warning(f"[{self.worker_id}] Unknown job type: {job_type}")

    async def _handle_play(self, job: dict) -> None:
        from music.player import player
        from database.models import Track
        track = Track(**job["track"])
        await player.play(job["chat_id"], track, force=job.get("force", False))

    async def _handle_skip(self, job: dict) -> None:
        from music.player import player
        await player.skip(job["chat_id"])

    async def _handle_stop(self, job: dict) -> None:
        from music.player import player
        await player.stop_session(job["chat_id"])

    async def _handle_seek(self, job: dict) -> None:
        from music.player import player
        await player.seek(job["chat_id"], job.get("seconds", 0))

    async def _heartbeat_loop(self) -> None:
        while self._running:
            uptime = int(time.time() - self._start_time)
            await redis().setex(
                f"aura:worker:{self.worker_id}:heartbeat",
                WORKER_HEARTBEAT_INTERVAL * 2,
                json.dumps({"worker_id": self.worker_id, "uptime": uptime}),
            )
            await asyncio.sleep(WORKER_HEARTBEAT_INTERVAL)


async def publish_job(job: dict) -> None:
    """Helper to publish a job from any module."""
    from database.redis import publish
    await publish(WORKER_CHANNEL, job)


# ── Standalone entrypoint ─────────────────────────────────────────────────────

async def _main():
    import sys
    from database.mongo import connect_mongo
    from database.redis import connect_redis

    worker_id = sys.argv[1] if len(sys.argv) > 1 else "worker-0"
    await connect_redis()
    await connect_mongo()
    worker = QueueWorker(worker_id=worker_id)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(worker.stop()))

    await worker.start()


if __name__ == "__main__":
    asyncio.run(_main())
  
