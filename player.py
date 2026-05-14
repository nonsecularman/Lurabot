"""
AuraBot — Music Player
Orchestrates PyTgCalls voice sessions with queue management and state tracking.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, Optional, Set

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, AudioQuality
from pytgcalls.exceptions import (
    AlreadyJoinedError,
    GroupCallNotFound,
    NotInCallError,
)

from config import cfg
from core.assistant_manager import assistant_manager, AssistantAccount
from core.logger import get_logger
from database.models import AudioFilter, LoopMode, QueueState, Track
from database.repositories.chat_repo import chat_repo
from database.repositories.user_repo import user_repo
from music.extractor import extractor
from music.ffmpeg import ffmpeg_engine
from music.queue import music_queue

log = get_logger("music.player")


class MusicPlayer:
    """
    Top-level coordinator for all voice chat music sessions.
    One PyTgCalls instance per assistant account.
    """

    def __init__(self) -> None:
        self._calls: Dict[str, PyTgCalls] = {}   # assistant_id → PyTgCalls
        self._active: Set[int] = set()            # active chat_ids
        self._paused: Set[int] = set()

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        for acc in assistant_manager._accounts:
            if acc.is_ready and acc.client:
                call = PyTgCalls(acc.client)
                await call.start()
                self._calls[str(acc.index)] = call
                log.info(f"PyTgCalls started for assistant [{acc.index}]")

    async def stop(self) -> None:
        await ffmpeg_engine.stop_all()
        for call in self._calls.values():
            try:
                await call.stop()
            except Exception:
                pass

    def _get_call(self, assistant_id: str) -> Optional[PyTgCalls]:
        return self._calls.get(str(assistant_id))

    # ── Play ──────────────────────────────────────────────────────────────────

    async def play(
        self,
        chat_id: int,
        track: Track,
        *,
        force: bool = False,
        seekable: int = 0,
    ) -> None:
        """
        Start or queue a track. If already playing, enqueue.
        force=True skips the queue.
        """
        if self.is_active(chat_id) and not force:
            length = await music_queue.add(chat_id, track)
            log.info(f"[{chat_id}] Queued: {track.title} (pos #{length})")
            return

        state = await music_queue.get_or_create_state(chat_id)
        acc = await assistant_manager.join_voice_chat(chat_id)
        if not acc:
            raise RuntimeError("No available assistant to join voice chat.")

        # Stream audio
        proc = await ffmpeg_engine.create_stream(
            chat_id,
            track.url,
            volume=state.volume,
            filters=state.filters,
            is_live=track.is_live,
            seek=seekable,
        )

        call = self._get_call(str(acc.index))
        if not call:
            raise RuntimeError(f"No PyTgCalls instance for assistant [{acc.index}]")

        try:
            await call.play(
                chat_id,
                MediaStream(
                    audio_path=proc.stdout,
                    audio_parameters=AudioQuality.HIGH,
                ),
            )
        except AlreadyJoinedError:
            pass

        self._active.add(chat_id)
        self._paused.discard(chat_id)

        # Update state
        await music_queue.update_state(
            chat_id,
            current=track,
            is_playing=True,
            is_paused=False,
            assistant_id=str(acc.index),
            started_at=datetime.utcnow(),
        )

        log.success(f"[{chat_id}] ▶ Playing: {track.title}")

        # Record play history
        asyncio.create_task(self._record_history(chat_id, track))

        # Award XP to requester
        if track.added_by:
            asyncio.create_task(user_repo.add_xp(track.added_by, 5))

    async def play_from_query(
        self, chat_id: int, query: str, user_id: int
    ) -> Optional[Track]:
        """Extract + resolve + enqueue/play a track from a query string."""
        track = await extractor.resolve(query, user_id)
        if not track:
            return None

        # Check duration limit
        chat = await chat_repo.get(chat_id)
        max_dur = chat.max_duration if chat else cfg.MAX_DURATION
        if track.duration and track.duration > max_dur:
            return None  # caller should handle this

        await self.play(chat_id, track)
        return track

    # ── Controls ──────────────────────────────────────────────────────────────

    async def skip(self, chat_id: int) -> Optional[Track]:
        next_track = await music_queue.get_next(chat_id)
        if next_track:
            await self.play(chat_id, next_track, force=True)
        else:
            await self.stop_session(chat_id)
        return next_track

    async def pause(self, chat_id: int) -> bool:
        state = await music_queue.get_state(chat_id)
        if not state or not state.assistant_id:
            return False
        call = self._get_call(state.assistant_id)
        if not call:
            return False
        try:
            await call.pause_stream(chat_id)
            self._paused.add(chat_id)
            await music_queue.update_state(chat_id, is_paused=True, is_playing=False)
            return True
        except NotInCallError:
            return False

    async def resume(self, chat_id: int) -> bool:
        state = await music_queue.get_state(chat_id)
        if not state or not state.assistant_id:
            return False
        call = self._get_call(state.assistant_id)
        if not call:
            return False
        try:
            await call.resume_stream(chat_id)
            self._paused.discard(chat_id)
            await music_queue.update_state(chat_id, is_paused=False, is_playing=True)
            return True
        except NotInCallError:
            return False

    async def stop_session(self, chat_id: int) -> None:
        state = await music_queue.get_state(chat_id)
        if state and state.assistant_id:
            call = self._get_call(state.assistant_id)
            if call:
                try:
                    await call.leave_group_call(chat_id)
                except (NotInCallError, GroupCallNotFound):
                    pass

        await ffmpeg_engine.stop(chat_id)
        await music_queue.clear_state(chat_id)
        self._active.discard(chat_id)
        self._paused.discard(chat_id)
        await assistant_manager.release_assistant(chat_id)
        log.info(f"[{chat_id}] Session stopped.")

    async def seek(self, chat_id: int, seconds: int) -> bool:
        state = await music_queue.get_state(chat_id)
        if not state or not state.current:
            return False
        await self.play(chat_id, state.current, force=True, seekable=seconds)
        return True

    async def set_volume(self, chat_id: int, volume: int) -> None:
        await music_queue.set_volume(chat_id, volume)
        state = await music_queue.get_state(chat_id)
        if state and state.current:
            # Restart stream with new volume
            await self.play(chat_id, state.current, force=True)

    async def set_filter(self, chat_id: int, audio_filter: AudioFilter) -> None:
        state = await music_queue.get_or_create_state(chat_id)
        if audio_filter == AudioFilter.NONE:
            state.filters = []
        elif audio_filter not in state.filters:
            state.filters.append(audio_filter)
        await music_queue.update_state(chat_id, filters=state.filters)
        if state.current:
            await self.play(chat_id, state.current, force=True)

    async def set_loop(self, chat_id: int, mode: LoopMode) -> None:
        await music_queue.set_loop(chat_id, mode)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    async def on_stream_end(self, chat_id: int) -> None:
        """Called by FFmpeg watchdog when a stream ends naturally."""
        next_track = await music_queue.get_next(chat_id)
        if next_track:
            log.info(f"[{chat_id}] Auto-advancing to: {next_track.title}")
            await self.play(chat_id, next_track, force=True)
        else:
            # Check autoplay
            from music.autoplay import autoplay
            rec = await autoplay.get_recommendation(chat_id)
            if rec:
                await self.play(chat_id, rec, force=True)
            else:
                await self.stop_session(chat_id)

    # ── Status ────────────────────────────────────────────────────────────────

    def is_active(self, chat_id: int) -> bool:
        return chat_id in self._active

    def is_paused(self, chat_id: int) -> bool:
        return chat_id in self._paused

    async def now_playing(self, chat_id: int) -> Optional[QueueState]:
        return await music_queue.get_state(chat_id)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _record_history(self, chat_id: int, track: Track) -> None:
        from database.mongo import get_collection
        from datetime import datetime
        await get_collection("play_history").insert_one({
            "user_id": track.added_by,
            "chat_id": chat_id,
            "track_id": track.track_id,
            "title": track.title,
            "artist": track.artist,
            "source": track.source,
            "played_at": datetime.utcnow(),
        })


# Singleton
player = MusicPlayer()
