"""
AuraBot — MongoDB Client
Async MongoDB via Motor with connection pooling and health checks.
"""

from __future__ import annotations

from typing import Any, Optional, TypeVar

import motor.motor_asyncio
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import ServerSelectionTimeoutError

from config import cfg
from core.logger import get_logger

log = get_logger("db.mongo")

_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
_db: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None

T = TypeVar("T")


async def connect_mongo() -> None:
    global _client, _db

    log.info(f"MONGO URI => {cfg.MONGO_URI}")
    log.info("Connecting to MongoDB…")

    _client = motor.motor_asyncio.AsyncIOMotorClient(
        cfg.MONGO_URI,
        serverSelectionTimeoutMS=5000,
        maxPoolSize=50,
        minPoolSize=5,
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
    )

    try:
        await _client.admin.command("ping")

    except ServerSelectionTimeoutError as exc:
        log.critical(f"MongoDB connection failed: {exc}")
        raise

    _db = _client[cfg.MONGO_DB_NAME]

    log.success(f"MongoDB connected — DB: {cfg.MONGO_DB_NAME}")

    await _create_indexes()


async def disconnect_mongo() -> None:
    global _client

    if _client:
        _client.close()
        log.info("MongoDB disconnected.")


def get_db() -> motor.motor_asyncio.AsyncIOMotorDatabase:

    if _db is None:
        raise RuntimeError(
            "MongoDB is not connected. Call connect_mongo() first."
        )

    return _db


def get_collection(name: str):

    return get_db()[name]


async def _create_indexes() -> None:

    db = get_db()

    await db.users.create_indexes([
        IndexModel([("user_id", ASCENDING)], unique=True),
        IndexModel([("username", ASCENDING)]),
        IndexModel([("xp", DESCENDING)]),
    ])

    await db.chats.create_indexes([
        IndexModel([("chat_id", ASCENDING)], unique=True),
    ])

    await db.playlists.create_indexes([
        IndexModel([("owner_id", ASCENDING)]),
        IndexModel(
            [("name", ASCENDING), ("owner_id", ASCENDING)],
            unique=True
        ),
    ])

    await db.play_history.create_indexes([
        IndexModel(
            [("user_id", ASCENDING), ("played_at", DESCENDING)]
        ),
        IndexModel(
            [("chat_id", ASCENDING), ("played_at", DESCENDING)]
        ),
    ])

    await db.waifu_inventory.create_indexes([
        IndexModel([("user_id", ASCENDING)]),
        IndexModel([("waifu_id", ASCENDING)]),
    ])

    log.debug("MongoDB indexes ensured.")


async def find_one(collection: str, query: dict):

    return await get_collection(collection).find_one(query)


async def find_many(
    collection: str,
    query: dict,
    sort: Optional[list] = None,
    limit: int = 0,
    skip: int = 0,
):

    cursor = get_collection(collection).find(query)

    if sort:
        cursor = cursor.sort(sort)

    if skip:
        cursor = cursor.skip(skip)

    if limit:
        cursor = cursor.limit(limit)

    return await cursor.to_list(length=limit or None)


async def upsert(collection: str, query: dict, update: dict):

    return await get_collection(collection).update_one(
        query,
        {"$set": update},
        upsert=True
    )


async def delete_one(collection: str, query: dict):

    result = await get_collection(collection).delete_one(query)

    return result.deleted_count


async def count_documents(
    collection: str,
    query: dict = {}
):

    return await get_collection(collection).count_documents(query)


async def aggregate(collection: str, pipeline: list):

    cursor = get_collection(collection).aggregate(pipeline)

    return await cursor.to_list(length=None)
