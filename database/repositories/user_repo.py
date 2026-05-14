"""
AuraBot — User Repository
All user-related database operations.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from database.models import UserProfile
from database.mongo import find_one, upsert, find_many, count_documents, aggregate


class UserRepository:
    COLLECTION = "users"

    async def get(self, user_id: int) -> Optional[UserProfile]:
        doc = await find_one(self.COLLECTION, {"user_id": user_id})
        return UserProfile(**doc) if doc else None

    async def get_or_create(self, user_id: int, full_name: str = "", username: str = "") -> UserProfile:
        doc = await find_one(self.COLLECTION, {"user_id": user_id})
        if doc:
            return UserProfile(**doc)
        user = UserProfile(user_id=user_id, full_name=full_name, username=username)
        await upsert(self.COLLECTION, {"user_id": user_id}, user.model_dump())
        return user

    async def update(self, user_id: int, **fields) -> None:
        fields["last_seen"] = datetime.utcnow()
        await upsert(self.COLLECTION, {"user_id": user_id}, fields)

    async def add_xp(self, user_id: int, amount: int) -> tuple[int, bool]:
        """Add XP, returns (new_xp, leveled_up)."""
        user = await self.get(user_id)
        if not user:
            return 0, False
        new_xp = user.xp + amount
        leveled_up = new_xp >= user.xp_for_next_level
        update = {"xp": new_xp}
        if leveled_up:
            update["level"] = user.level + 1
        await upsert(self.COLLECTION, {"user_id": user_id}, update)
        return new_xp, leveled_up

    async def add_coins(self, user_id: int, amount: int) -> int:
        user = await self.get(user_id)
        if not user:
            return 0
        new_coins = max(0, user.coins + amount)
        await upsert(self.COLLECTION, {"user_id": user_id}, {"coins": new_coins})
        return new_coins

    async def ban(self, user_id: int) -> None:
        await upsert(self.COLLECTION, {"user_id": user_id}, {"is_banned": True})

    async def unban(self, user_id: int) -> None:
        await upsert(self.COLLECTION, {"user_id": user_id}, {"is_banned": False})

    async def set_premium(self, user_id: int, value: bool) -> None:
        await upsert(self.COLLECTION, {"user_id": user_id}, {"is_premium": value})

    async def get_leaderboard(self, limit: int = 10) -> List[UserProfile]:
        docs = await find_many(
            self.COLLECTION,
            {"is_banned": {"$ne": True}},
            sort=[("xp", -1)],
            limit=limit,
        )
        return [UserProfile(**d) for d in docs]

    async def marry(self, user_id: int, partner_id: int) -> None:
        await upsert(self.COLLECTION, {"user_id": user_id}, {"married_to": partner_id})
        await upsert(self.COLLECTION, {"user_id": partner_id}, {"married_to": user_id})

    async def divorce(self, user_id: int, partner_id: int) -> None:
        await upsert(self.COLLECTION, {"user_id": user_id}, {"married_to": None})
        await upsert(self.COLLECTION, {"user_id": partner_id}, {"married_to": None})

    async def total_users(self) -> int:
        return await count_documents(self.COLLECTION)

    async def top_listeners(self, limit: int = 10) -> list:
        return await aggregate("play_history", [
            {"$group": {"_id": "$user_id", "plays": {"$sum": 1}}},
            {"$sort": {"plays": -1}},
            {"$limit": limit},
        ])


user_repo = UserRepository()
