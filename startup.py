"""
AuraBot — Startup & Shutdown
Ordered lifecycle management for all services.
"""

from __future__ import annotations

import asyncio

from core.logger import get_logger
from core.metrics import setup_metrics

log = get_logger("lifecycle")


async def startup() -> None:
    """Boot all services in dependency order."""
    log.info("═══════════════════════════════════════")
    log.info("  AuraBot — Starting up…")
    log.info("═══════════════════════════════════════")

    from config import cfg

    # 1. Databases
    log.info("▶ Connecting databases...")
    from database.redis import connect_redis
    from database.mongo import connect_mongo
    await connect_redis()
    await connect_mongo()

    # 2. Metrics
    setup_metrics("AuraBot", "1.0.0")

    # 3. Assistant Pool
    log.info("▶ Starting assistant pool...")
    from core.assistant_manager import assistant_manager
    await assistant_manager.start()

    # 4. Music Player
    log.info("▶ Starting music player...")
    from music.player import player
    await player.start()

    # 5. Workers
    log.info("▶ Starting background workers...")
    from workers.stream_worker import stream_worker
    await stream_worker.start()

    # 6. Dashboard API (if enabled)
    if cfg.ENABLE_DASHBOARD:
        log.info(f"▶ Starting dashboard API on port {cfg.API_PORT}...")
        asyncio.create_task(_run_dashboard())

    log.success("✅ AuraBot fully started!")
    log.info("═══════════════════════════════════════")


async def shutdown() -> None:
    """Graceful shutdown in reverse order."""
    log.info("Shutting down AuraBot...")

    from workers.stream_worker import stream_worker
    await stream_worker.stop()

    from music.player import player
    await player.stop()

    from core.assistant_manager import assistant_manager
    await assistant_manager.stop()

    from database.redis import disconnect_redis
    from database.mongo import disconnect_mongo
    await disconnect_redis()
    await disconnect_mongo()

    log.info("AuraBot shutdown complete. Goodbye! 👋")


async def _run_dashboard() -> None:
    import uvicorn
    from api.dashboard import dashboard_app
    from config import cfg

    config = uvicorn.Config(
        app=dashboard_app,
        host=cfg.API_HOST,
        port=cfg.API_PORT,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    await server.serve()
