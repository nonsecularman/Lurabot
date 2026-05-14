"""
AuraBot — Security & ACL
Anti-spam, flood protection, cooldown system, and permission checks.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Callable, Optional

from pyrogram import Client
from pyrogram.types import Message

from config import cfg
from core.logger import get_logger
from database.redis import check_cooldown, increment_flood

log = get_logger("security")


# ── Permission Levels ─────────────────────────────────────────────────────────

class PermissionLevel:
    USER = 0
    DJ = 1
    ADMIN = 2
    SUDO = 3
    OWNER = 4


async def get_permission_level(client: Client, message: Message) -> int:
    uid = message.from_user.id if message.from_user else 0

    if uid == cfg.OWNER_ID:
        return PermissionLevel.OWNER
    if uid in cfg.SUDO_USERS:
        return PermissionLevel.SUDO

    # Check chat admin
    if message.chat.id < 0:  # group / supergroup
        try:
            member = await client.get_chat_member(message.chat.id, uid)
            from pyrogram.enums import ChatMemberStatus
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                return PermissionLevel.ADMIN
        except Exception:
            pass

        # Check DJ role in DB
        from database.repositories.chat_repo import chat_repo
        chat = await chat_repo.get(message.chat.id)
        if chat and uid in chat.dj_roles:
            return PermissionLevel.DJ

    return PermissionLevel.USER


# ── Decorators ────────────────────────────────────────────────────────────────

def require_permission(level: int = PermissionLevel.USER):
    """Decorator: ensures caller has at least `level` permission."""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(client: Client, message: Message, *args, **kwargs):
            user_level = await get_permission_level(client, message)
            if user_level < level:
                labels = {0: "user", 1: "DJ", 2: "admin", 3: "sudo", 4: "owner"}
                await message.reply_text(
                    f"🔒 This command requires **{labels[level]}** permission."
                )
                return
            return await func(client, message, *args, **kwargs)
        return wrapper
    return decorator


def cooldown(seconds: int = cfg.COMMAND_COOLDOWN):
    """Decorator: per-user per-command cooldown."""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(client: Client, message: Message, *args, **kwargs):
            uid = message.from_user.id if message.from_user else 0
            # Sudo/Owner bypass cooldowns
            if uid in cfg.SUDO_USERS:
                return await func(client, message, *args, **kwargs)
            on_cd = await check_cooldown(uid, func.__name__, ttl=seconds)
            if on_cd:
                return  # silently ignore; avoid reply spam
            return await func(client, message, *args, **kwargs)
        return wrapper
    return decorator


def flood_check(func: Callable):
    """Decorator: per-user flood protection."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        uid = message.from_user.id if message.from_user else 0
        if uid in cfg.SUDO_USERS:
            return await func(client, message, *args, **kwargs)
        count = await increment_flood(uid, window=10)
        if count > cfg.FLOOD_THRESHOLD:
            log.warning(f"Flood detected: user {uid} sent {count} commands in 10s")
            if count == cfg.FLOOD_THRESHOLD + 1:
                await message.reply_text("⚠️ Slow down! You're sending commands too fast.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def require_group(func: Callable):
    """Decorator: only works in groups."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        if message.chat.id > 0:
            await message.reply_text("❌ This command only works in groups.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def require_voice_chat(func: Callable):
    """Decorator: validates an active voice chat session exists."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        from music.player import player
        if not player.is_active(message.chat.id):
            await message.reply_text("❌ No active music session. Use /play to start.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def ban_check(func: Callable):
    """Decorator: reject banned users."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        uid = message.from_user.id if message.from_user else 0
        from database.repositories.user_repo import user_repo
        user = await user_repo.get(uid)
        if user and user.is_banned:
            await message.reply_text("🚫 You are banned from using this bot.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def full_guard(
    perm: int = PermissionLevel.USER,
    cd: int = cfg.COMMAND_COOLDOWN,
    group_only: bool = False,
):
    """Composite decorator: ban_check + flood_check + cooldown + permission."""
    def decorator(func: Callable):
        wrapped = func
        wrapped = require_permission(perm)(wrapped)
        wrapped = cooldown(cd)(wrapped)
        wrapped = flood_check(wrapped)
        wrapped = ban_check(wrapped)
        if group_only:
            wrapped = require_group(wrapped)
        return wrapped
    return decorator
