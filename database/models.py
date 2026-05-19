AuraBot — Data Models
Pydantic v2 models for all domain entities.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────

class LoopMode(str, Enum):
    NONE = "none"
    TRACK = "track"
    QUEUE = "queue"


class StreamQuality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WaifuRarity(str, Enum):
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class AudioFilter(str, Enum):
    NONE = "none"
    BASS_BOOST = "bass_boost"
    NIGHTCORE = "nightcore"
    VAPORWAVE = "vaporwave"
    REVERB = "reverb"
    ECHO = "echo"
    AUDIO_8D = "8d"
    KARAOKE = "karaoke"
    DISTORTION = "distortion"


# ── User ───────────────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    user_id: int
    name: Optional[str] = None
    username: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Chat Settings ─────────────────────────────────────────────────────────────

class ChatSettings(BaseModel):
    chat_id: int

    loop: bool = False
    shuffle: bool = False
    autoplay: bool = True
    admin_only: bool = False

    volume: int = 100
    quality: str = "high"

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Track ─────────────────────────────────────────────────────────────────────

class Track(BaseModel):
    track_id: str

    title: str

    artist: Optional[str] = None
    album: Optional[str] = None

    url: Optional[str] = None
    source: Optional[str] = None

    duration: Optional[int] = None

    thumbnail: Optional[str] = None

    added_by: Optional[int] = None

    is_live: bool = False

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Queue State ───────────────────────────────────────────────────────────────

class QueueState(BaseModel):
    chat_id: int

    current: Optional[Track] = None

    is_playing: bool = False
    is_paused: bool = False

    volume: int = 100

    loop_mode: LoopMode = LoopMode.NONE

    assistant_id: Optional[str] = None

    filters: List[AudioFilter] = []

    started_at: Optional[datetime] = None
