"""
AuraBot — Playlist Plugin
Personal playlists: create, add, remove, play, share.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from core.logger import get_logger
from core.security import ban_check, cooldown
from database.models import Playlist, Track
from database.mongo import (
    find_one, find_many, upsert, delete_one, get_collection
)
from music.player import player
import uuid
from datetime import datetime

log = get_logger("plugin.playlist")


def playlist_router(app: Client) -> None:

    @app.on_message(filters.command(["playlist", "pl"]))
    @ban_check
    @cooldown(3)
    async def cmd_playlist(client: Client, message: Message) -> None:
        args = message.command[1:]
        uid = message.from_user.id

        if not args:
            await _show_help(message)
            return

        sub = args[0].lower()

        if sub == "create":
            name = " ".join(args[1:]).strip()
            if not name:
                await message.reply_text("❌ Provide a name: `/playlist create My Playlist`")
                return
            existing = await find_one("playlists", {"owner_id": uid, "name": name})
            if existing:
                await message.reply_text(f"❌ You already have a playlist named **{name}**.")
                return
            pl = Playlist(
                playlist_id=str(uuid.uuid4()),
                owner_id=uid,
                name=name,
            )
            await upsert("playlists", {"playlist_id": pl.playlist_id}, pl.model_dump(mode="json"))
            await message.reply_text(f"✅ Playlist **{name}** created!")

        elif sub == "list":
            docs = await find_many("playlists", {"owner_id": uid}, sort=[("created_at", -1)])
            if not docs:
                await message.reply_text("📭 You have no playlists. Create one with `/playlist create <name>`")
                return
            lines = ["📋 **Your Playlists**\n"]
            for i, d in enumerate(docs, 1):
                lines.append(f"`{i}.` **{d['name']}** — {len(d.get('tracks', []))} tracks")
            await message.reply_text("\n".join(lines))

        elif sub == "add":
            if len(args) < 3:
                await message.reply_text("❌ Usage: `/playlist add <playlist name> <song>`")
                return
            pl_name = args[1]
            query = " ".join(args[2:])
            pl_doc = await find_one("playlists", {"owner_id": uid, "name": pl_name})
            if not pl_doc:
                await message.reply_text(f"❌ Playlist **{pl_name}** not found.")
                return
            from music.extractor import extractor
            status = await message.reply_text("🔍 Searching...")
            track = await extractor.resolve(query, user_id=uid)
            if not track:
                await status.edit_text("❌ Could not find that track.")
                return
            await get_collection("playlists").update_one(
                {"playlist_id": pl_doc["playlist_id"]},
                {"$push": {"tracks": track.model_dump(mode="json")},
                 "$set": {"updated_at": datetime.utcnow()}},
            )
            await status.edit_text(f"✅ Added **{track.title}** to **{pl_name}**.")

        elif sub == "play":
            pl_name = " ".join(args[1:]).strip()
            pl_doc = await find_one("playlists", {"owner_id": uid, "name": pl_name})
            if not pl_doc:
                pl_doc = await find_one("playlists", {"name": pl_name, "is_public": True})
            if not pl_doc or not pl_doc.get("tracks"):
                await message.reply_text(f"❌ Playlist **{pl_name}** not found or empty.")
                return
            tracks = [Track(**t) for t in pl_doc["tracks"]]
            status = await message.reply_text(f"🎵 Loading **{pl_name}** ({len(tracks)} tracks)...")
            from music.queue import music_queue
            added = await music_queue.add_many(message.chat.id, tracks[1:])
            await player.play(message.chat.id, tracks[0])
            await status.edit_text(
                f"▶️ Playing playlist **{pl_name}**\n"
                f"🎵 {len(tracks)} tracks queued."
            )

        elif sub == "delete":
            pl_name = " ".join(args[1:]).strip()
            deleted = await delete_one("playlists", {"owner_id": uid, "name": pl_name})
            if deleted:
                await message.reply_text(f"🗑 Playlist **{pl_name}** deleted.")
            else:
                await message.reply_text(f"❌ Playlist **{pl_name}** not found.")

        elif sub == "share":
            pl_name = " ".join(args[1:]).strip()
            pl_doc = await find_one("playlists", {"owner_id": uid, "name": pl_name})
            if not pl_doc:
                await message.reply_text(f"❌ Playlist **{pl_name}** not found.")
                return
            await get_collection("playlists").update_one(
                {"playlist_id": pl_doc["playlist_id"]},
                {"$set": {"is_public": True}},
            )
            await message.reply_text(
                f"🌐 Playlist **{pl_name}** is now **public**!\n"
                f"Anyone can play it with: `/playlist play {pl_name}`"
            )
        else:
            await _show_help(message)


async def _show_help(message: Message) -> None:
    await message.reply_text(
        "📋 **Playlist Commands**\n\n"
        "`/playlist create <name>` — Create a new playlist\n"
        "`/playlist list` — View your playlists\n"
        "`/playlist add <name> <song>` — Add a track\n"
        "`/playlist play <name>` — Play a playlist\n"
        "`/playlist delete <name>` — Delete a playlist\n"
        "`/playlist share <name>` — Make playlist public"
    )
