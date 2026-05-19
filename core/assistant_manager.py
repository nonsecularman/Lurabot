"""
AuraBot — Assistant Manager
Manages a pool of Pyrogram assistant accounts for voice chat sessions.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pyrogram import Client
from pyrogram.errors import FloodWait

from config import cfg
from core.logger import get_logger

log = get_logger("assistant_manager")


@dataclass
class AssistantAccount:
    session: str
    index: int
    client: Optional[Client] = None
    is_ready: bool = False
    flood_until: float = 0.0
    active_calls: int = 0
    assigned_chats: Dict[int, bool] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        return self.is_ready and time.time() > self.flood_until

    @property
    def load(self) -> int:
        return self.active_calls


class AssistantManager:

    def __init__(self) -> None:
        self._accounts: List[AssistantAccount] = []
        self._chat_map: Dict[int, AssistantAccount] = {}
        self._lock = asyncio.Lock()

    # ─────────────────────────────────────────

    async def start(self) -> None:

        if not cfg.ASSISTANT_SESSIONS:
            log.warning("No assistant sessions configured.")
            return

        tasks = [
            self._init_account(i, s)
            for i, s in enumerate(cfg.ASSISTANT_SESSIONS)
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        ready = sum(
            1 for a in self._accounts
            if a.is_ready
        )

        log.success(
            f"Assistant pool ready: {ready}/{len(self._accounts)} accounts active."
        )

    async def stop(self) -> None:

        for acc in self._accounts:

            if acc.client and acc.is_ready:

                try:
                    await acc.client.stop()

                except Exception:
                    pass

        log.info("All assistant accounts stopped.")

    # ─────────────────────────────────────────

    async def _init_account(
        self,
        index: int,
        session: str
    ) -> None:

        acc = AssistantAccount(
            session=session,
            index=index
        )

        try:

            acc.client = Client(
                name=f"assistant_{index}",
                api_id=cfg.API_ID,
                api_hash=cfg.API_HASH,
                session_string=session,
            )

            await acc.client.start()

            me = await acc.client.get_me()

            acc.is_ready = True

            self._accounts.append(acc)

            log.info(
                f"Assistant [{index}] ready: @{me.username} (id={me.id})"
            )

        except Exception as e:

            log.error(
                f"Assistant [{index}] failed to start: {e}"
            )

    # ─────────────────────────────────────────

    async def get_assistant(
        self,
        chat_id: int
    ) -> Optional[AssistantAccount]:

        async with self._lock:

            # Existing assistant
            if chat_id in self._chat_map:

                acc = self._chat_map[chat_id]

                if acc.is_available:
                    return acc

                del self._chat_map[chat_id]

            # Available assistants
            available = [
                a for a in self._accounts
                if a.is_available
            ]

            if not available:

                log.warning("No available assistants!")

                return None

            # Lowest load assistant
            chosen = min(
                available,
                key=lambda a: a.load
            )

            self._chat_map[chat_id] = chosen

            chosen.active_calls += 1

            chosen.assigned_chats[chat_id] = True

            log.info(
                f"Assigned assistant [{chosen.index}] to chat {chat_id}"
            )

            return chosen

    # ─────────────────────────────────────────

    async def release_assistant(
        self,
        chat_id: int
    ) -> None:

        async with self._lock:

            if chat_id in self._chat_map:

                acc = self._chat_map.pop(chat_id)

                acc.active_calls = max(
                    0,
                    acc.active_calls - 1
                )

                acc.assigned_chats.pop(
                    chat_id,
                    None
                )

    # ─────────────────────────────────────────

    async def handle_floodwait(
        self,
        index: int,
        seconds: int
    ) -> None:

        async with self._lock:

            for acc in self._accounts:

                if acc.index == index:

                    acc.flood_until = (
                        time.time() + seconds + 2
                    )

                    log.warning(
                        f"Assistant [{index}] flooded for {seconds}s."
                    )

                    affected = [
                        cid
                        for cid, a in self._chat_map.items()
                        if a.index == index
                    ]

                    for chat_id in affected:
                        del self._chat_map[chat_id]

                    break

    # ─────────────────────────────────────────

    async def join_voice_chat(
        self,
        chat_id: int
    ) -> Optional[AssistantAccount]:

        acc = await self.get_assistant(chat_id)

        if not acc:
            return None

        try:

            # Check if assistant is in group
            await acc.client.get_chat(chat_id)

            return acc

        except FloodWait as fw:

            await self.handle_floodwait(
                acc.index,
                fw.value
            )

            return await self.join_voice_chat(chat_id)

        except Exception as e:

            log.error(
                f"Assistant [{acc.index}] could not access {chat_id}: {e}"
            )

            return None

    # ─────────────────────────────────────────

    async def leave_voice_chat(
        self,
        chat_id: int
    ) -> None:

        await self.release_assistant(chat_id)

    # ─────────────────────────────────────────

    def status(self) -> dict:

        return {

            "total": len(self._accounts),

            "ready": sum(
                1 for a in self._accounts
                if a.is_ready
            ),

            "available": sum(
                1 for a in self._accounts
                if a.is_available
            ),

            "active_calls": sum(
                a.active_calls
                for a in self._accounts
            ),

            "accounts": [

                {
                    "index": a.index,
                    "is_ready": a.is_ready,
                    "is_available": a.is_available,
                    "active_calls": a.active_calls,
                }

                for a in self._accounts
            ],
        }


assistant_manager = AssistantManager()
