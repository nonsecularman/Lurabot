"""
AuraBot — Redis Client
Async Redis with connection pooling, pub/sub, queue ops, and atomic helpers.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Optional

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from config import cfg
from core.logger import get_logger

log = get_logger("db.redis")

_pool: Optional[ConnectionPool] = None
_client: Optional[aioredis.Redis] = None


async def connect_redis() -> None:
    global _pool, _client
    log.info("Connecting to Redis…")
    _pool = ConnectionPool.from_url(
        cfg.REDIS_URL,
        password=cfg.REDIS_PASSWORD,
        max_connections=cfg.REDIS_MAX_CONNECTIONS,
        decode_responses=True,
    )
    _client = aioredis.Redis(connection_pool=_pool)
    await _client.ping()
    log.success("Redis connected.")


async def disconnect_redis() -> None:
    global _client, _pool
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.aclose()
    log.info("Redis disconnected.")


def redis() -> aioredis.Redis:
    if _client is None:
        raise RuntimeError("Redis not connected. Call connect_redis() first.")
    return _client


# ── Key builder ───────────────────────────────────────────────────────────────

class Keys:
    """Centralized Redis key namespace."""

    @staticmethod
    def queue(chat_id: int) -> str:
        return f"aura:queue:{chat_id}"

    @staticmethod
    def queue_state(chat_id: int) -> str:
        return f"aura:queue_state:{chat_id}"

    @staticmethod
    def playback(chat_id: int) -> str:
        return f"aura:playback:{chat_id}"

    @staticmethod
    def cooldown(user_id: int, command: str) -> str:
        return f"aura:cd:{user_id}:{command}"

    @staticmethod
    def flood(user_id: int) -> str:
        return f"aura:flood:{user_id}"

    @staticmethod
    def assistant(session_id: str) -> str:
        return f"aura:assistant:{session_id}"

    @staticmethod
    def cache(key: str) -> str:
        return f"aura:cache:{key}"

    @staticmethod
    def session(chat_id: int) -> str:
        return f"aura:session:{chat_id}"

    @staticmethod
    def lyrics_cache(track_id: str) -> str:
        return f"aura:lyrics:{track_id}"

    @staticmethod
    def user_settings(user_id: int) -> str:
        return f"aura:user_settings:{user_id}"


# ── Queue Ops ──────────────────────────────────────────────────────────────────

async def queue_push(chat_id: int, track: dict) -> int:
    return await redis().rpush(Keys.queue(chat_id), json.dumps(track))


async def queue_push_priority(chat_id: int, track: dict) -> int:
    return await redis().lpush(Keys.queue(chat_id), json.dumps(track))


async def queue_pop(chat_id: int) -> Optional[dict]:
    raw = await redis().lpop(Keys.queue(chat_id))
    return json.loads(raw) if raw else None


async def queue_peek(chat_id: int, count: int = 10) -> list[dict]:
    items = await redis().lrange(Keys.queue(chat_id), 0, count - 1)
    return [json.loads(i) for i in items]


async def queue_len(chat_id: int) -> int:
    return await redis().llen(Keys.queue(chat_id))


async def queue_clear(chat_id: int) -> None:
    await redis().delete(Keys.queue(chat_id))


async def queue_shuffle(chat_id: int) -> None:
    key = Keys.queue(chat_id)
    items = await redis().lrange(key, 0, -1)
    if not items:
        return
    import random
    random.shuffle(items)
    pipe = redis().pipeline()
    pipe.delete(key)
    for item in items:
        pipe.rpush(key, item)
    await pipe.execute()


# ── Playback State ─────────────────────────────────────────────────────────────

async def set_playback(chat_id: int, state: dict, ttl: int = 86400) -> None:
    await redis().setex(Keys.playback(chat_id), ttl, json.dumps(state))


async def get_playback(chat_id: int) -> Optional[dict]:
    raw = await redis().get(Keys.playback(chat_id))
    return json.loads(raw) if raw else None


async def del_playback(chat_id: int) -> None:
    await redis().delete(Keys.playback(chat_id))


# ── Cooldown / Flood ───────────────────────────────────────────────────────────

async def check_cooldown(user_id: int, command: str, ttl: int = 3) -> bool:
    """Returns True if user is on cooldown."""
    key = Keys.cooldown(user_id, command)
    result = await redis().set(key, "1", nx=True, ex=ttl)
    return result is None  # None means key already existed → on cooldown


async def increment_flood(user_id: int, window: int = 10) -> int:
    key = Keys.flood(user_id)
    count = await redis().incr(key)
    if count == 1:
        await redis().expire(key, window)
    return count


# ── Generic Cache ──────────────────────────────────────────────────────────────

async def cache_get(key: str) -> Optional[Any]:
    raw = await redis().get(Keys.cache(key))
    return json.loads(raw) if raw else None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    await redis().setex(Keys.cache(key), ttl, json.dumps(value))


async def cache_del(key: str) -> None:
    await redis().delete(Keys.cache(key))


# ── Pub/Sub ────────────────────────────────────────────────────────────────────

async def publish(channel: str, message: dict) -> None:
    await redis().publish(channel, json.dumps(message))


@asynccontextmanager
async def subscribe(*channels: str) -> AsyncGenerator[aioredis.client.PubSub, None]:
    pubsub = redis().pubsub()
    await pubsub.subscribe(*channels)
    try:
        yield pubsub
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.aclose()
  
