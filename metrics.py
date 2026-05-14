"""
AuraBot — Prometheus Metrics
All metric counters, gauges, and histograms for monitoring.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

# ── Bot Info ──────────────────────────────────────────────────────────────────
bot_info = Info("aurabot", "AuraBot instance information")

# ── Commands ──────────────────────────────────────────────────────────────────
commands_total = Counter(
    "aurabot_commands_total",
    "Total commands processed",
    ["command", "status"],
)

# ── Music ─────────────────────────────────────────────────────────────────────
active_voice_calls = Gauge(
    "aurabot_active_voice_calls",
    "Number of active voice chat sessions",
)

tracks_played_total = Counter(
    "aurabot_tracks_played_total",
    "Total tracks played",
    ["source"],
)

stream_duration_seconds = Histogram(
    "aurabot_stream_duration_seconds",
    "Duration of audio streams in seconds",
    buckets=[30, 60, 120, 180, 300, 600, 1200, 1800, 3600],
)

queue_length = Histogram(
    "aurabot_queue_length",
    "Queue length at the time of track addition",
    buckets=[1, 2, 5, 10, 20, 50],
)

# ── Stickers ──────────────────────────────────────────────────────────────────
stickers_generated_total = Counter(
    "aurabot_stickers_generated_total",
    "Total stickers generated",
    ["type"],  # quote | text
)

sticker_render_seconds = Histogram(
    "aurabot_sticker_render_seconds",
    "Sticker generation time in seconds",
    ["type"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

# ── Anime / AI ────────────────────────────────────────────────────────────────
anime_requests_total = Counter(
    "aurabot_anime_requests_total",
    "Anime/waifu API requests",
    ["action"],
)

ai_requests_total = Counter(
    "aurabot_ai_requests_total",
    "AI API requests",
    ["backend", "status"],
)

# ── Users / Chats ─────────────────────────────────────────────────────────────
total_users = Gauge("aurabot_total_users", "Total registered users")
total_chats = Gauge("aurabot_total_chats", "Total registered chats")

# ── Workers ───────────────────────────────────────────────────────────────────
worker_jobs_total = Counter(
    "aurabot_worker_jobs_total",
    "Total jobs processed by workers",
    ["worker_id", "job_type", "status"],
)

# ── FFmpeg ────────────────────────────────────────────────────────────────────
ffmpeg_processes = Gauge(
    "aurabot_ffmpeg_processes",
    "Active FFmpeg processes",
)

ffmpeg_restarts_total = Counter(
    "aurabot_ffmpeg_restarts_total",
    "FFmpeg process restarts due to failure",
)


def setup_metrics(bot_name: str, version: str = "1.0.0") -> None:
    """Initialize static metric labels."""
    bot_info.info({"name": bot_name, "version": version})
