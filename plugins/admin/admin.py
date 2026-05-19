"""
AuraBot — Admin Plugin
Bot owner / sudo admin commands: ban, unban, broadcast, stats, maintenance.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import cfg
from core.logger import get_logger
from core.security import PermissionLevel, require_permission
from database.mongo import count_documents, get_collection
from database.repositories.user_repo import user_repo
from database.repositories.chat_repo import chat_repo
from music.player import player
from core.assistant_manager import assistant_manager

log = get_logger("admin")


def admin_router(app: Client) -> None:

    # ── /stats ────────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["stats", "status"]) & filters.user(cfg.SUDO_USERS))
    async def cmd_stats(client: Client, message: Message) -> None:
        total_users = await count_documents("users")
        total_chats = await count_documents("chats")
        total_plays = await count_documents("play_history")
        active_calls = len(player._active)
        assistants = assistant_manager.status()

        await message.reply_photo(
            photo="https://files.catbox.moe/ehehyi.jpg",
            caption=
            f"📊 **AuraBot Statistics**\n\n"
            f"👥 Total Users: `{total_users:,}`\n"
            f"💬 Total Chats: `{total_chats:,}`\n"
            f"🎵 Total Plays: `{total_plays:,}`\n"
            f"📡 Active Voice Calls: `{active_calls}`\n\n"
            f"🤖 **Assistants**\n"
            f"• Total: `{assistants['total']}`\n"
            f"• Ready: `{assistants['ready']}`\n"
            f"• Active Calls: `{assistants['active_calls']}`\n\n"
            f"⚡ AuraBot running smoothly!"
        )

    # ── /ban ──────────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["ban"]) & filters.user(cfg.SUDO_USERS))
    async def cmd_ban(client: Client, message: Message) -> None:
        target_id = await _resolve_target(client, message)
        if not target_id:
            return

        if target_id in cfg.SUDO_USERS:
            await message.reply_text("❌ Cannot ban a sudo user.")
            return

        await user_repo.ban(target_id)
        await message.reply_text(f"🚫 User `{target_id}` has been banned.")
        log.warning(f"Banned user {target_id} by {message.from_user.id}")

    # ── /unban ────────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["unban"]) & filters.user(cfg.SUDO_USERS))
    async def cmd_unban(client: Client, message: Message) -> None:
        target_id = await _resolve_target(client, message)

        if not target_id:
            return

        await user_repo.unban(target_id)
        await message.reply_text(f"✅ User `{target_id}` has been unbanned.")

    # ── /broadcast ────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["broadcast", "bc"]) & filters.user([cfg.OWNER_ID]))
    async def cmd_broadcast(client: Client, message: Message) -> None:

        if not message.reply_to_message:
            await message.reply_text("❌ Reply to a message to broadcast.")
            return

        status = await message.reply_text("📡 Broadcasting...")

        chats = await get_collection("chats").find({}).to_list(length=None)

        sent = 0
        failed = 0

        for chat in chats:
            try:
                await message.reply_to_message.forward(chat["chat_id"])
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                failed += 1

        await status.edit_text(
            f"📡 **Broadcast Complete**\n\n"
            f"✅ Sent: `{sent}`\n"
            f"❌ Failed: `{failed}`"
        )

    # ── /sudoadd ──────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["sudoadd"]) & filters.user([cfg.OWNER_ID]))
    async def cmd_sudo_add(client: Client, message: Message) -> None:

        target_id = await _resolve_target(client, message)

        if not target_id:
            return

        await user_repo.update(target_id, is_sudo=True)

        if target_id not in cfg.SUDO_USERS:
            cfg.SUDO_USERS.append(target_id)

        await message.reply_text(f"✅ User `{target_id}` added to sudo list.")

    # ── /sudorm ───────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["sudorm"]) & filters.user([cfg.OWNER_ID]))
    async def cmd_sudo_rm(client: Client, message: Message) -> None:

        target_id = await _resolve_target(client, message)

        if not target_id or target_id == cfg.OWNER_ID:
            await message.reply_text("❌ Cannot remove owner from sudo.")
            return

        cfg.SUDO_USERS = [u for u in cfg.SUDO_USERS if u != target_id]

        await message.reply_text(f"✅ User `{target_id}` removed from sudo list.")

    # ── /ping ─────────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["ping"]))
    async def cmd_ping(client: Client, message: Message) -> None:

        import time

        start = time.monotonic()

        msg = await message.reply_text("🏓 Pong!")

        end = (time.monotonic() - start) * 1000

        await msg.edit_text(f"🏓 **Pong!** `{end:.1f}ms`")

    # ── /help /start ──────────────────────────────────────────────────────────
    @app.on_message(filters.command(["help", "start"]))
    async def cmd_help(client: Client, message: Message) -> None:

        text = f"""
🎵 **AuraBot — Premium Telegram Multimedia Bot**

Hey {message.from_user.mention} 👋

I am **AuraBot**, an advanced Telegram music & management bot designed for powerful group experience ✨

━━━━━━━━━━━━━━━

🎶 **Music Features**
• High quality streaming
• Queue system
• Loop / Shuffle / Seek
• Filters & effects
• Voice chat support

🎨 **Sticker Features**
• Quote stickers
• Text stickers
• Inline sticker generation

🌸 **Anime Features**
• Waifu system
• Hug / Kiss / Pat / Slap
• Marriage system
• XP & leaderboard

🤖 **AI Features**
• AI Chat Assistant
• Smart music recommendations
• Fast responses

⚙️ **Group Features**
• DJ Roles
• Admin-only mode
• Premium features

━━━━━━━━━━━━━━━
✨ Use the buttons below to explore AuraBot.
"""

        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "➕ Add Me To Your Group",
                        url=f"https://t.me/{client.me.username}?startgroup=true"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📚 Commands",
                        callback_data="help_commands"
                    ),

                    InlineKeyboardButton(
                        "⚙️ Features",
                        callback_data="help_features"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "👤 Owner",
                        url=cfg.YOUR_OWNER
                    ),

                    InlineKeyboardButton(
                        "💬 Support",
                        url=cfg.YOUR_SUPPORT
                    ),
                ],
            ]
        )

        await message.reply_photo(
            photo="https://files.catbox.moe/wn6p15.jpg",
            caption=text,
            reply_markup=buttons
        )


async def _resolve_target(client: Client, message: Message) -> Optional[int]:

    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    args = message.command[1:]

    if args:
        try:
            return int(args[0].lstrip("@"))

        except ValueError:
            try:
                user = await client.get_users(args[0])
                return user.id

            except Exception:
                pass

    await message.reply_text(
        "❌ Please reply to a user or provide a valid user ID/username."
    )

    return None
