"""
AuraBot — Chat Repository
"""

from __future__ import annotations

from typing import Optional

from database.models import ChatSettings
from database.mongo import find_one, upsert


class ChatRepository:
    COLLECTION = "chats"

    async def get(self, chat_id: int) -> Optional[ChatSettings]:
        doc = await find_one(self.COLLECTION, {"chat_id": chat_id})
        return ChatSettings(**doc) if doc else None

    async def get_or_create(self, chat_id: int, title: str = "") -> ChatSettings:
        doc = await find_one(self.COLLECTION, {"chat_id": chat_id})
        if doc:
            return ChatSettings(**doc)
        chat = ChatSettings(chat_id=chat_id, title=title)
        await upsert(self.COLLECTION, {"chat_id": chat_id}, chat.model_dump())
        return chat

    async def update(self, chat_id: int, **fields) -> None:
        await upsert(self.COLLECTION, {"chat_id": chat_id}, fields)

    async def set_admin_only(self, chat_id: int, value: bool) -> None:
        await self.update(chat_id, is_admin_only=value)

    async def set_quality(self, chat_id: int, quality: str) -> None:
        await self.update(chat_id, quality=quality)

    async def set_volume(self, chat_id: int, volume: int) -> None:
        await self.update(chat_id, default_volume=volume)

    async def ban_user(self, chat_id: int, user_id: int) -> None:
        from database.mongo import get_collection
        await get_collection(self.COLLECTION).update_one(
            {"chat_id": chat_id},
            {"$addToSet": {"banned_users": user_id}},
            upsert=True,
        )

    async def unban_user(self, chat_id: int, user_id: int) -> None:
        from database.mongo import get_collection
        await get_collection(self.COLLECTION).update_one(
            {"chat_id": chat_id},
            {"$pull": {"banned_users": user_id}},
        )

    async def is_banned(self, chat_id: int, user_id: int) -> bool:
        doc = await find_one(self.COLLECTION, {"chat_id": chat_id, "banned_users": user_id})
        return doc is not None

    async def add_dj(self, chat_id: int, user_id: int) -> None:
        from database.mongo import get_collection
        await get_collection(self.COLLECTION).update_one(
            {"chat_id": chat_id},
            {"$addToSet": {"dj_roles": user_id}},
            upsert=True,
        )

    async def remove_dj(self, chat_id: int, user_id: int) -> None:
        from database.mongo import get_collection
        await get_collection(self.COLLECTION).update_one(
            {"chat_id": chat_id},
            {"$pull": {"dj_roles": user_id}},
        )


chat_repo = ChatRepository()
