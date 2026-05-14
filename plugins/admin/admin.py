"""
AuraBot — Admin Plugin
Bot owner / sudo admin commands: ban, unban, broadcast, stats, maintenance.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message

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

        await message.reply_text(
            f"📊 **AuraBot Statistics**\n\n"
            f"👥 Total Users: `{total_users:,}`\n"
            f"💬 Total Chats: `{total_chats:,}`\n"
            f"🎵 Total Plays: `{total_plays:,}`\n"
            f"📡 Active Voice Calls: `{active_calls}`\n\n"
            f"**🤖 Assistants:**\n"
            f"Total: `{assistants['total']}` | "
            f"Ready: `{assistants['ready']}` | "
            f"Active Calls: `{assistants['active_calls']}`\n\n"
            f"🕐 Uptime: Since bot start"
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
            await message.reply_text("❌ Reply to the message you want to broadcast.")
            return
        status = await message.reply_text("📡 Broadcasting...")
        chats = await get_collection("chats").find({}).to_list(length=None)
        sent = failed = 0
        for chat in chats:
            try:
                await message.reply_to_message.forward(chat["chat_id"])
                sent += 1
                await asyncio.sleep(0.05)  # flood prevention
            except Exception:
                failed += 1
        await status.edit_text(
            f"📡 **Broadcast Complete**\n\n"
            f"✅ Sent: `{sent}`\n"
            f"❌ Failed: `{failed}`"
        )

    # ── /sudoadd / /sudorm ────────────────────────────────────────────────────
    @app.on_message(filters.command(["sudoadd"]) & filters.user([cfg.OWNER_ID]))
    async def cmd_sudo_add(client: Client, message: Message) -> None:
        target_id = await _resolve_target(client, message)
        if not target_id:
            return
        await user_repo.update(target_id, is_sudo=True)
        if target_id not in cfg.SUDO_USERS:
            cfg.SUDO_USERS.append(target_id)
        await message.reply_text(f"✅ User `{target_id}` added to sudo list.")

    @app.on_message(filters.command(["sudorm"]) & filters.user([cfg.OWNER_ID]))
    async def cmd_sudo_rm(client: Client, message: Message) -> None:
        target_id = await _resolve_target(client, message)
        if not target_id or target_id == cfg.OWNER_ID:
            await message.reply_text("❌ Cannot remove owner from sudo.")
            return
        cfg.SUDO_USERS = [u for u in cfg.SUDO_USERS if u != target_id]
        await message.reply_text(f"✅ User `{target_id}` removed from sudo list.")

    # ── /premium ──────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["premium"]) & filters.user(cfg.SUDO_USERS))
    async def cmd_premium(client: Client, message: Message) -> None:
        target_id = await _resolve_target(client, message)
        if not target_id:
            return
        args = message.command[1:]
        enable = not (args and args[0].lower() == "off")
        await user_repo.set_premium(target_id, enable)
        status = "granted ✅" if enable else "revoked ❌"
        await message.reply_text(f"💎 Premium {status} for user `{target_id}`.")

    # ── /chatban / /chatunban ──────────────────────────────────────────────────
    @app.on_message(filters.command(["chatban"]) & filters.user(cfg.SUDO_USERS) & filters.group)
    async def cmd_chatban(client: Client, message: Message) -> None:
        target_id = await _resolve_target(client, message)
        if not target_id:
            return
        await chat_repo.ban_user(message.chat.id, target_id)
        await message.reply_text(f"🚫 User `{target_id}` banned from music commands in this chat.")

    @app.on_message(filters.command(["chatunban"]) & filters.user(cfg.SUDO_USERS) & filters.group)
    async def cmd_chatunban(client: Client, message: Message) -> None:
        target_id = await _resolve_target(client, message)
        if not target_id:
            return
        await chat_repo.unban_user(message.chat.id, target_id)
        await message.reply_text(f"✅ User `{target_id}` unbanned in this chat.")

    # ── /djadd / /djrm ────────────────────────────────────────────────────────
    @app.on_message(filters.command(["djadd"]) & filters.group)
    @require_permission(PermissionLevel.ADMIN)
    async def cmd_dj_add(client: Client, message: Message) -> None:
        target_id = await _resolve_target(client, message)
        if not target_id:
            return
        await chat_repo.add_dj(message.chat.id, target_id)
        await message.reply_text(f"🎧 User `{target_id}` is now a DJ in this chat.")

    @app.on_message(filters.command(["djrm"]) & filters.group)
    @require_permission(PermissionLevel.ADMIN)
    async def cmd_dj_rm(client: Client, message: Message) -> None:
        target_id = await _resolve_target(client, message)
        if not target_id:
            return
        await chat_repo.remove_dj(message.chat.id, target_id)
        await message.reply_text(f"✅ DJ role removed for user `{target_id}`.")

    # ── /adminonly ────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["adminonly"]) & filters.group)
    @require_permission(PermissionLevel.ADMIN)
    async def cmd_admin_only(client: Client, message: Message) -> None:
        chat = await chat_repo.get_or_create(message.chat.id)
        new_val = not chat.is_admin_only
        await chat_repo.set_admin_only(message.chat.id, new_val)
        status = "enabled 🔒" if new_val else "disabled 🔓"
        await message.reply_text(f"Admin-only mode {status} for music commands.")

    # ── /ping ─────────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["ping"]))
    async def cmd_ping(client: Client, message: Message) -> None:
        import time
        t0 = time.monotonic()
        msg = await message.reply_text("🏓 Pong!")
        ms = (time.monotonic() - t0) * 1000
        await msg.edit_text(f"🏓 **Pong!** `{ms:.1f}ms`")

    # ── /help ─────────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["help", "start"]))
    async def cmd_help(client: Client, message: Message) -> None:
        await message.reply_text(
            "🎵 **AuraBot** — Premium Telegram Multimedia Bot\n\n"
            "**🎶 Music**\n"
            "`/play` — Play a song (name or URL)\n"
            "`/skip` — Skip current track\n"
            "`/pause` / `/resume` — Pause / Resume\n"
            "`/stop` — Stop and clear queue\n"
            "`/queue` — Show queue\n"
            "`/np` — Now playing\n"
            "`/volume` — Set volume (0-200)\n"
            "`/seek` — Seek to position\n"
            "`/loop` — Loop mode (track/queue/off)\n"
            "`/shuffle` — Shuffle queue\n"
            "`/filter` — Audio effects\n\n"
            "**🎨 Stickers**\n"
            "`/q` — Quote sticker (reply to a message)\n"
            "`/s <text>` — Text sticker\n\n"
            "**🌸 Anime**\n"
            "`/waifu` — Roll a waifu card\n"
            "`/hug` `/kiss` `/pat` `/slap` and more!\n"
            "`/marry` `/divorce` — Relationship system\n"
            "`/profile` — View your profile\n"
            "`/leaderboard` — Top XP rankings\n\n"
            "**🤖 AI**\n"
            "`/ask <question>` — Chat with AI\n"
            "`/recommend` — AI music recommendations\n\n"
            "**⚙️ Settings**\n"
            "`/adminonly` — Restrict to admins\n"
            "`/djadd` / `/djrm` — DJ roles\n"
            "`/ping` — Latency check"
        )


async def _resolve_target(client: Client, message: Message) -> Optional[int]:
    """Resolve target user from reply, mention, or ID argument."""
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
    await message.reply_text("❌ Please reply to a user or provide a user ID/username.")
    return None
