"""
AuraBot — FFmpeg Engine
Async FFmpeg subprocess management with filter chains, watchdog, and auto-reconnect.
"""

from __future__ import annotations

import asyncio
import re
import shlex
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from config import cfg
from core.logger import get_logger
from database.models import AudioFilter

log = get_logger("ffmpeg")


# ── Audio Filter Chains ───────────────────────────────────────────────────────

FILTER_CHAINS: Dict[AudioFilter, str] = {
    AudioFilter.BASS_BOOST:  "bass=g=20,dynaudnorm=f=200",
    AudioFilter.NIGHTCORE:   "asetrate=44100*1.25,aresample=44100,atempo=1.06",
    AudioFilter.VAPORWAVE:   "asetrate=44100*0.8,aresample=44100,atempo=0.9",
    AudioFilter.REVERB:      "aecho=0.8:0.9:1000:0.3",
    AudioFilter.ECHO:        "aecho=0.8:0.88:120:0.4",
    AudioFilter.AUDIO_8D:    "apulsator=hz=0.125",
    AudioFilter.KARAOKE:     "stereotools=mlev=0.1",
    AudioFilter.DISTORTION:  "acrusher=level_in=8:level_out=18:bits=8:mode=log:aa=1",
}


def build_filter_chain(filters: List[AudioFilter], volume: int = 100) -> Optional[str]:
    parts = []
    if volume != 100:
        parts.append(f"volume={volume / 100:.2f}")
    for f in filters:
        if f != AudioFilter.NONE and f in FILTER_CHAINS:
            parts.append(FILTER_CHAINS[f])
    return ",".join(parts) if parts else None


# ── FFmpeg Process ─────────────────────────────────────────────────────────────

@dataclass
class FFmpegProcess:
    process: asyncio.subprocess.Process
    chat_id: int
    started_at: float = field(default_factory=time.time)
    _stderr_task: Optional[asyncio.Task] = field(default=None, init=False)

    async def start_stderr_monitor(self) -> None:
        self._stderr_task = asyncio.create_task(self._monitor_stderr())

    async def _monitor_stderr(self) -> None:
        if not self.process.stderr:
            return
        async for line in self.process.stderr:
            decoded = line.decode(errors="replace").strip()
            if decoded and "error" in decoded.lower():
                log.warning(f"[FFmpeg:{self.chat_id}] {decoded}")

    async def terminate(self) -> None:
        if self.process.returncode is None:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
            except ProcessLookupError:
                pass
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()

    @property
    def is_alive(self) -> bool:
        return self.process.returncode is None


# ── Main FFmpeg Engine ─────────────────────────────────────────────────────────

class FFmpegEngine:
    """
    Manages per-chat FFmpeg processes.
    Handles filter chains, volume, adaptive bitrate, and reconnect for livestreams.
    """

    def __init__(self) -> None:
        self._processes: Dict[int, FFmpegProcess] = {}

    async def create_stream(
        self,
        chat_id: int,
        source: str,
        *,
        volume: int = 100,
        filters: Optional[List[AudioFilter]] = None,
        is_live: bool = False,
        seek: int = 0,
        quality: str = "high",
    ) -> asyncio.subprocess.Process:
        """
        Launch an FFmpeg process that outputs raw PCM to stdout
        for PyTgCalls to consume.
        """
        await self.stop(chat_id)

        filter_chain = build_filter_chain(filters or [], volume)
        bitrate = {"low": 64, "medium": 96, "high": 128}.get(quality, 128)

        cmd = self._build_command(
            source=source,
            filter_chain=filter_chain,
            bitrate=bitrate,
            seek=seek,
            is_live=is_live,
        )
        log.debug(f"[FFmpeg:{chat_id}] CMD: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=2 ** 23,  # 8 MB buffer
        )

        ffproc = FFmpegProcess(process=process, chat_id=chat_id)
        await ffproc.start_stderr_monitor()
        self._processes[chat_id] = ffproc

        # Start watchdog for non-live streams
        if not is_live:
            asyncio.create_task(self._watchdog(chat_id))

        return process

    def _build_command(
        self,
        source: str,
        filter_chain: Optional[str],
        bitrate: int,
        seek: int,
        is_live: bool,
    ) -> List[str]:
        cmd = [cfg.FFMPEG_PATH, "-hide_banner", "-loglevel", "error"]

        # Reconnect for HTTP streams
        if source.startswith("http"):
            cmd += [
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
            ]

        if seek > 0:
            cmd += ["-ss", str(seek)]

        cmd += ["-i", source]

        if is_live:
            cmd += ["-live_start_index", "-1"]

        # Audio filters
        if filter_chain:
            cmd += ["-af", filter_chain]

        cmd += [
            "-acodec", "pcm_s16le",
            "-ac", "2",
            "-ar", "48000",
            "-b:a", f"{bitrate}k",
            "-f", "s16le",
            "pipe:1",
        ]
        return cmd

    async def stop(self, chat_id: int) -> None:
        proc = self._processes.pop(chat_id, None)
        if proc:
            await proc.terminate()
            log.debug(f"[FFmpeg:{chat_id}] stopped.")

    async def stop_all(self) -> None:
        cids = list(self._processes.keys())
        await asyncio.gather(*[self.stop(cid) for cid in cids])

    def is_running(self, chat_id: int) -> bool:
        proc = self._processes.get(chat_id)
        return proc is not None and proc.is_alive

    async def _watchdog(self, chat_id: int) -> None:
        """Monitor process health and emit event on unexpected exit."""
        proc = self._processes.get(chat_id)
        if not proc:
            return
        await proc.process.wait()
        if chat_id in self._processes:
            # Process exited on its own — signal player
            log.info(f"[FFmpeg:{chat_id}] process ended naturally.")
            from music.player import player
            asyncio.create_task(player.on_stream_end(chat_id))

    async def get_duration(self, source: str) -> Optional[float]:
        """Use ffprobe to get media duration in seconds."""
        cmd = [
            cfg.FFPROBE_PATH, "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            source,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            import json
            data = json.loads(stdout)
            return float(data["format"]["duration"])
        except Exception as e:
            log.debug(f"ffprobe failed for {source}: {e}")
            return None


# Singleton
ffmpeg_engine = FFmpegEngine()
