"""
AuraBot — Logger
Structured async-safe logging via Loguru with optional JSON output.
"""

from __future__ import annotations

import sys
from typing import Any

from loguru import logger as _loguru_logger

from config import cfg


def _json_formatter(record: dict[str, Any]) -> str:
    import json
    import traceback

    log = {
        "ts": record["time"].isoformat(),
        "lvl": record["level"].name,
        "logger": record["name"],
        "msg": record["message"],
        "file": f"{record['file'].name}:{record['line']}",
    }
    if record["exception"]:
        exc = record["exception"]
        log["exc"] = "".join(traceback.format_exception(exc.type, exc.value, exc.traceback))
    return json.dumps(log)


def setup_logger() -> None:
    _loguru_logger.remove()

    if cfg.LOG_JSON:
        _loguru_logger.add(
            sys.stdout,
            level=cfg.LOG_LEVEL,
            format=_json_formatter,
            serialize=False,
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )
    else:
        fmt = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        )
        _loguru_logger.add(
            sys.stdout,
            level=cfg.LOG_LEVEL,
            format=fmt,
            colorize=True,
            enqueue=True,
        )

    # Rotating file sink
    _loguru_logger.add(
        "logs/aurabot_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="100 MB",
        retention="14 days",
        compression="gz",
        enqueue=True,
    )


def get_logger(name: str = "aurabot"):
    return _loguru_logger.bind(name=name)


# Run setup on import
setup_logger()
log = get_logger()
