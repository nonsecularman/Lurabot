"""
AuraBot — Music Plugin
All music-related Telegram commands.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import cfg
from core.security import PermissionLevel, cooldown, flood_check, require_group, ban_check
from database.models import AudioFilter, LoopMode
from database.repositories.user_repo import user_repo
from music.player import player
from music.queue import music_queue
from music.extractor import extractor
from core.logger import get_logger

log = get_logger("plugin.music")


def music_router(app: Client) -> None:
    """Register all music handlers on the Pyrogram client."""

    # ─────────────────── /play ───────────────────────────────────────────────

    @app.on_message(filters.command(["play", "p"]) & filters.group)
    @ban_check
    @flood_check
    @cooldown(3)
    async def cmd_play(client: Client, message: Message) -> None:
        query = " ".join(message.command[1:]).strip()

        # Support reply to Telegram audio/video
        if not query and message.reply_to_message:
            replied = message.reply_to_message
            if replied.audio or replied.voice or replied.video or replied.document:
                await _play_telegram_media(client, message, replied)
                return

        if not query:
            await message.reply_text(
                "**Usage:** `/play <song name or URL>`\n"
                "Or reply to an audio/video message."
            )
            return

        status_msg = await message.reply_text("🔍 **Searching...**")

        try:
            track = await player.play_from_query(
                message.chat.id, query, message.from_user.id
            )
            if not track:
                await status_msg.edit_text(
                    "❌ Could not find or extract the requested track. Try a different query."
                )
                return

            state = await music_queue.get_state(message.chat.id)
            queue_len = await music_queue.length(message.chat.id)

            if state and state.current and state.current.track_id != track.track_id:
                # Track queued, not playing immediately
                await status_msg.edit_text(
                    f"✅ **Added to Queue** `#{queue_len}`\n\n"
                    f"🎵 **{track.title}**\n"
                    f"👤 {track.artist or 'Unknown'}\n"
                    f"⏱ {track.duration_str}",
                    reply_markup=_track_buttons(message.chat.id),
                )
            else:
                await status_msg.edit_text(
                    f"▶️ **Now Playing**\n\n"
                    f"🎵 **{track.title}**\n"
                    f"👤 {track.artist or 'Unknown'}\n"
                    f"⏱ {track.duration_str}\n"
                    f"🔊 Source: `{track.source.title()}`",
                    reply_markup=_playback_buttons(message.chat.id),
                )
        except RuntimeError as e:
            await status_msg.edit_text(f"❌ Error: {e}")
        except Exception as e:
            log.error(f"Play error in {message.chat.id}: {e}")
            await status_msg.edit_text("❌ An unexpected error occurred.")

    # ─────────────────── /skip ───────────────────────────────────────────────

    @app.on_message(filters.command(["skip", "s"]) & filters.group)
    @ban_check
    @flood_check
    @cooldown(2)
    async def cmd_skip(client: Client, message: Message) -> None:
        if not player.is_active(message.chat.id):
            await message.reply_text("❌ Nothing is playing.")
            return
        next_track = await player.skip(message.chat.id)
        if next_track:
            await message.reply_text(
                f"⏭ **Skipped!**\n\n▶️ Now Playing: **{next_track.title}**"
            )
        else:
            await message.reply_text("⏹ Queue ended. No more tracks.")

    # ─────────────────── /pause / /resume ────────────────────────────────────

    @app.on_message(filters.command(["pause"]) & filters.group)
    @ban_check
    @cooldown(2)
    async def cmd_pause(client: Client, message: Message) -> None:
        ok = await player.pause(message.chat.id)
        await message.reply_text("⏸ **Paused.**" if ok else "❌ Nothing to pause.")

    @app.on_message(filters.command(["resume", "r"]) & filters.group)
    @ban_check
    @cooldown(2)
    async def cmd_resume(client: Client, message: Message) -> None:
        ok = await player.resume(message.chat.id)
        await message.reply_text("▶️ **Resumed.**" if ok else "❌ Nothing to resume.")

    # ─────────────────── /stop ────────────────────────────────────────────────

    @app.on_message(filters.command(["stop", "end"]) & filters.group)
    @ban_check
    @cooldown(5)
    async def cmd_stop(client: Client, message: Message) -> None:
        await player.stop_session(message.chat.id)
        await message.reply_text("⏹ **Music stopped** and queue cleared.")

    # ─────────────────── /queue ───────────────────────────────────────────────

    @app.on_message(filters.command(["queue", "q"]) & filters.group)
    @ban_check
    @cooldown(3)
    async def cmd_queue(client: Client, message: Message) -> None:
        state = await music_queue.get_state(message.chat.id)
        tracks = await music_queue.peek(message.chat.id, 10)

        if not state and not tracks:
            await message.reply_text("📭 Queue is empty.")
            return

        lines = []
        if state and state.current:
            lines.append(f"▶️ **Now:** {state.current.title} `[{state.current.duration_str}]`")
            lines.append("")
        if tracks:
            lines.append("**Up Next:**")
            for i, t in enumerate(tracks, 1):
                lines.append(f"`{i}.` {t.title} `[{t.duration_str}]`")

        total = await music_queue.length(message.chat.id)
        if total > 10:
            lines.append(f"\n_...and {total - 10} more tracks_")

        loop_emoji = {"none": "", "track": " 🔂", "queue": " 🔁"}[
            (state.loop if state else LoopMode.NONE)
        ]
        lines.append(f"\n📊 **{total} tracks in queue**{loop_emoji}")

        await message.reply_text("\n".join(lines))

    # ─────────────────── /nowplaying ─────────────────────────────────────────

    @app.on_message(filters.command(["nowplaying", "np"]) & filters.group)
    @ban_check
    @cooldown(5)
    async def cmd_nowplaying(client: Client, message: Message) -> None:
        state = await player.now_playing(message.chat.id)
        if not state or not state.current:
            await message.reply_text("❌ Nothing is currently playing.")
            return
        t = state.current
        status = "⏸ Paused" if state.is_paused else "▶️ Playing"
        filters_str = (
            ", ".join(f.value for f in state.filters) if state.filters else "None"
        )
        await message.reply_text(
            f"🎵 **Now Playing**\n\n"
            f"**{t.title}**\n"
            f"👤 {t.artist or 'Unknown Artist'}\n"
            f"⏱ Duration: `{t.duration_str}`\n"
            f"🔊 Volume: `{state.volume}%`\n"
            f"🎚 Filters: `{filters_str}`\n"
            f"🔁 Loop: `{state.loop.value}`\n"
            f"📡 Source: `{t.source}`\n"
            f"Status: {status}",
            reply_markup=_playback_buttons(message.chat.id),
        )

    # ─────────────────── /volume ──────────────────────────────────────────────

    @app.on_message(filters.command(["volume", "vol"]) & filters.group)
    @ban_check
    @cooldown(2)
    async def cmd_volume(client: Client, message: Message) -> None:
        args = message.command[1:]
        if not args:
            vol = await music_queue.get_volume(message.chat.id)
            await message.reply_text(f"🔊 Current volume: **{vol}%**")
            return
        try:
            vol = int(args[0])
        except ValueError:
            await message.reply_text("❌ Usage: `/volume <0-200>`")
            return
        if not 0 <= vol <= 200:
            await message.reply_text("❌ Volume must be between 0 and 200.")
            return
        await player.set_volume(message.chat.id, vol)
        await message.reply_text(f"🔊 Volume set to **{vol}%**")

    # ─────────────────── /seek ────────────────────────────────────────────────

    @app.on_message(filters.command(["seek"]) & filters.group)
    @ban_check
    @cooldown(3)
    async def cmd_seek(client: Client, message: Message) -> None:
        args = message.command[1:]
        if not args:
            await message.reply_text("❌ Usage: `/seek <seconds>`")
            return
        try:
            secs = int(args[0])
        except ValueError:
            await message.reply_text("❌ Provide seconds as a number.")
            return
        ok = await player.seek(message.chat.id, secs)
        if ok:
            m, s = divmod(secs, 60)
            await message.reply_text(f"⏩ Seeked to **{m:02d}:{s:02d}**")
        else:
            await message.reply_text("❌ Could not seek.")

    # ─────────────────── /loop ────────────────────────────────────────────────

    @app.on_message(filters.command(["loop"]) & filters.group)
    @ban_check
    @cooldown(2)
    async def cmd_loop(client: Client, message: Message) -> None:
        args = message.command[1:]
        current = await music_queue.get_loop(message.chat.id)
        if not args:
            modes = {"none": "off", "track": "🔂 track", "queue": "🔁 queue"}
            await message.reply_text(
                f"🔁 Current loop: **{modes[current.value]}**\n\n"
                f"Use `/loop track`, `/loop queue`, or `/loop off`"
            )
            return
        mode_map = {"off": LoopMode.NONE, "track": LoopMode.TRACK, "queue": LoopMode.QUEUE}
        mode = mode_map.get(args[0].lower())
        if not mode:
            await message.reply_text("❌ Options: `track`, `queue`, `off`")
            return
        await player.set_loop(message.chat.id, mode)
        labels = {LoopMode.NONE: "off", LoopMode.TRACK: "🔂 track", LoopMode.QUEUE: "🔁 queue"}
        await message.reply_text(f"Loop set to: **{labels[mode]}**")

    # ─────────────────── /shuffle ─────────────────────────────────────────────

    @app.on_message(filters.command(["shuffle"]) & filters.group)
    @ban_check
    @cooldown(3)
    async def cmd_shuffle(client: Client, message: Message) -> None:
        length = await music_queue.length(message.chat.id)
        if length == 0:
            await message.reply_text("📭 Queue is empty.")
            return
        await music_queue.shuffle(message.chat.id)
        await message.reply_text(f"🔀 Shuffled **{length}** tracks!")

    # ─────────────────── /filter ──────────────────────────────────────────────

    @app.on_message(filters.command(["filter", "fx"]) & filters.group)
    @ban_check
    @cooldown(5)
    async def cmd_filter(client: Client, message: Message) -> None:
        filter_list = (
            "`bass` — Bass Boost\n"
            "`nightcore` — Nightcore\n"
            "`vaporwave` — Vaporwave\n"
            "`reverb` — Reverb\n"
            "`echo` — Echo\n"
            "`8d` — 8D Audio\n"
            "`karaoke` — Karaoke\n"
            "`distortion` — Distortion\n"
            "`none` — Remove all filters"
        )
        args = message.command[1:]
        if not args:
            state = await music_queue.get_state(message.chat.id)
            active = (
                ", ".join(f.value for f in state.filters) if state and state.filters else "None"
            )
            await message.reply_text(
                f"🎚 **Audio Filters**\n\n"
                f"Active: `{active}`\n\n"
                f"Available:\n{filter_list}\n\n"
                f"Usage: `/filter <name>`"
            )
            return
        name = args[0].lower()
        filter_map = {
            "bass": AudioFilter.BASS_BOOST,
            "nightcore": AudioFilter.NIGHTCORE,
            "vaporwave": AudioFilter.VAPORWAVE,
            "reverb": AudioFilter.REVERB,
            "echo": AudioFilter.ECHO,
            "8d": AudioFilter.AUDIO_8D,
            "karaoke": AudioFilter.KARAOKE,
            "distortion": AudioFilter.DISTORTION,
            "none": AudioFilter.NONE,
        }
        af = filter_map.get(name)
        if af is None:
            await message.reply_text(f"❌ Unknown filter: `{name}`\n\nAvailable:\n{filter_list}")
            return
        await player.set_filter(message.chat.id, af)
        label = "None (removed)" if af == AudioFilter.NONE else af.value
        await message.reply_text(f"🎚 Filter set: **{label}**")

    # ─────────────────── Callback: playback buttons ───────────────────────────

    @app.on_callback_query(filters.regex(r"^music_(pause|resume|skip|stop)_(-?\d+)$"))
    async def cb_playback(client: Client, callback_query) -> None:
        action, chat_id_str = callback_query.matches[0].groups()
        chat_id = int(chat_id_str)
        uid = callback_query.from_user.id

        # Basic auth: must be chat member
        actions = {
            "pause": player.pause,
            "resume": player.resume,
            "skip": player.skip,
        }
        await callback_query.answer()
        if action == "stop":
            await player.stop_session(chat_id)
            await callback_query.message.edit_text("⏹ Music stopped.")
            return
        fn = actions.get(action)
        if fn:
            await fn(chat_id)
            await callback_query.message.edit_reply_markup(
                reply_markup=_playback_buttons(chat_id)
            )

    # ─────────────────── Helpers ──────────────────────────────────────────────

    async def _play_telegram_media(
        client: Client, message: Message, replied: Message
    ) -> None:
        media = replied.audio or replied.voice or replied.video or replied.document
        if not media:
            await message.reply_text("❌ Could not process that file.")
            return
        status = await message.reply_text("⬇️ **Downloading...**")
        try:
            file_path = await replied.download(in_memory=False)
            from database.models import Track
            import time, os
            track = Track(
                track_id=str(time.time()),
                title=getattr(media, "file_name", None) or "Telegram Audio",
                url=file_path,
                source="telegram",
                added_by=message.from_user.id,
            )
            await player.play(message.chat.id, track)
            await status.edit_text(
                f"▶️ **Playing:** {track.title}",
                reply_markup=_playback_buttons(message.chat.id),
            )
        except Exception as e:
            log.error(f"TG media play error: {e}")
            await status.edit_text("❌ Failed to play that file.")


def _playback_buttons(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏸", callback_data=f"music_pause_{chat_id}"),
            InlineKeyboardButton("▶️", callback_data=f"music_resume_{chat_id}"),
            InlineKeyboardButton("⏭", callback_data=f"music_skip_{chat_id}"),
            InlineKeyboardButton("⏹", callback_data=f"music_stop_{chat_id}"),
        ]
    ])


def _track_buttons(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Queue", callback_data=f"music_queue_{chat_id}"),
            InlineKeyboardButton("⏭ Skip", callback_data=f"music_skip_{chat_id}"),
        ]
    ])
          
