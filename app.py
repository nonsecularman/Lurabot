from __future__ import annotations
import os


"""
AuraBot — Main Entrypoint
Bootstraps the Pyrogram client, loads plugins, and manages lifecycle.
"""

import asyncio
import signal
import sys


from config import cfg
from core.logger import get_logger, setup_logger
from core.startup import startup, shutdown
from core.plugin_loader import load_all_plugins

# Use uvloop for maximum async throughput
uvloop.install()

setup_logger()
log = get_logger("app")


def build_client():
    from pyrogram import Client

    return Client(
        name="AuraBot",
        api_id=cfg.API_ID,
        api_hash=cfg.API_HASH,
        bot_token=cfg.BOT_TOKEN,
        workers=8,
        sleep_threshold=15,
    )


async def main() -> None:
    client = build_client()

    # Register all plugin handlers
    load_all_plugins(client)

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        log.info("Received shutdown signal.")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # Start Pyrogram client
    await client.start()
    log.success(f"Pyrogram client started: @{cfg.BOT_USERNAME}")

    # Boot all services
    await startup()

    log.info("AuraBot is running. Press Ctrl+C to stop.")
    await stop_event.wait()

    # Graceful teardown
    await shutdown()
    await client.stop()
    log.info("Pyrogram client stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
    except Exception as e:
        log.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
