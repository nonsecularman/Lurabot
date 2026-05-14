"""
AuraBot — Configuration
Centralized settings via pydantic-settings with env-file support.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Telegram Core ──────────────────────────────────────────
    BOT_TOKEN: str
    API_ID: int
    API_HASH: str
    BOT_USERNAME: str = "AuraBot"

    # ── Assistant Accounts (comma-separated session strings) ───
    ASSISTANT_SESSIONS: List[str] = []

    # ── Owner & Sudo ───────────────────────────────────────────
    OWNER_ID: int
    SUDO_USERS: List[int] = []

    # ── MongoDB ────────────────────────────────────────────────
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "aurabot"

    # ── Redis ──────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None
    REDIS_MAX_CONNECTIONS: int = 50

    # ── Streaming ──────────────────────────────────────────────
    FFMPEG_PATH: str = "ffmpeg"
    FFPROBE_PATH: str = "ffprobe"
    DEFAULT_VOLUME: int = 100
    MAX_DURATION: int = 18000          # 5 hours (seconds)
    STREAM_QUALITY: str = "high"       # low | medium | high
    AUDIO_BITRATE: int = 128           # kbps
    YTDL_COOKIES: Optional[str] = None  # path to cookies file

    # ── Spotify ────────────────────────────────────────────────
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None

    # ── AI / OpenAI ────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    AI_MODEL: str = "gpt-4o-mini"
    AI_MAX_TOKENS: int = 800

    # ── FastAPI Dashboard ──────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8080
    API_SECRET_KEY: str = "change-me-in-production"
    API_ALLOWED_ORIGINS: List[str] = ["*"]

    # ── Security ──────────────────────────────────────────────
    RATE_LIMIT_COMMANDS: int = 5       # per user per 10 s
    FLOOD_THRESHOLD: int = 10
    COMMAND_COOLDOWN: int = 2          # seconds

    # ── Sticker System ────────────────────────────────────────
    QUOTE_FONT_PATH: str = "assets/fonts/NotoSans-Regular.ttf"
    STICKER_FONT_PATH: str = "assets/fonts/Montserrat-Bold.ttf"
    STICKER_SIZE: tuple[int, int] = (512, 512)

    # ── Anime / Waifu ─────────────────────────────────────────
    WAIFU_API_BASE: str = "https://api.waifu.pics"
    NEKOS_API_BASE: str = "https://nekos.best/api/v2"

    # ── Monitoring ────────────────────────────────────────────
    PROMETHEUS_PORT: int = 9090
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False

    # ── Feature Flags ─────────────────────────────────────────
    ENABLE_INLINE: bool = True
    ENABLE_AI: bool = True
    ENABLE_ANIME: bool = True
    ENABLE_STICKERS: bool = True
    ENABLE_DASHBOARD: bool = True
    ENABLE_PREMIUM: bool = False

    # ── Validators ────────────────────────────────────────────
    @field_validator("SUDO_USERS", "ASSISTANT_SESSIONS", mode="before")
    @classmethod
    def split_comma(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def validate_owner_in_sudo(self) -> "Settings":
        if self.OWNER_ID not in self.SUDO_USERS:
            self.SUDO_USERS = [self.OWNER_ID, *self.SUDO_USERS]
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Convenience singleton
cfg = get_settings()
