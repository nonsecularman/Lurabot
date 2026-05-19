"""
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


# ── Track ──────────────────────────────────────────────────────────────────────

class Track(BaseModel):
    track_id: str
    title: str
    artist: Optional[str] = None
    album: Optional[str] =  None
