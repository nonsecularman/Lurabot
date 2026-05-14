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
    album: Optional[str] = None
    duration: int = 0                  # seconds
    url: str                           # playback URL / file path
    thumbnail: Optional[str] = None
    source: str = "youtube"            # youtube | spotify | soundcloud | telegram | url
    file_id: Optional[str] = None      # for Telegram files
    is_live: bool = False
    added_by: int = 0                  # user_id
    added_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_str(self) -> str:
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"


# ── Queue State ────────────────────────────────────────────────────────────────

class QueueState(BaseModel):
    chat_id: int
    tracks: List[Track] = Field(default_factory=list)
    current: Optional[Track] = None
    position: int = 0                  # seconds into current track
    loop: LoopMode = LoopMode.NONE
    volume: int = 100
    filters: List[AudioFilter] = Field(default_factory=list)
    is_playing: bool = False
    is_paused: bool = False
    assistant_id: Optional[str] = None
    started_at: Optional[datetime] = None


# ── User ───────────────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    user_id: int
    username: Optional[str] = None
    full_name: str = ""
    lang: str = "en"
    xp: int = 0
    level: int = 1
    coins: int = 0
    is_premium: bool = False
    is_banned: bool = False
    is_sudo: bool = False
    bio: Optional[str] = None
    married_to: Optional[int] = None
    settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)

    @property
    def xp_for_next_level(self) -> int:
        return self.level * 100


# ── Chat ───────────────────────────────────────────────────────────────────────

class ChatSettings(BaseModel):
    chat_id: int
    title: str = ""
    lang: str = "en"
    is_admin_only: bool = False
    is_music_enabled: bool = True
    max_duration: int = 18000
    quality: StreamQuality = StreamQuality.HIGH
    default_volume: int = 100
    auto_leave: bool = True
    announce_track: bool = True
    dj_roles: List[int] = Field(default_factory=list)  # role user_ids
    banned_users: List[int] = Field(default_factory=list)
    settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Playlist ───────────────────────────────────────────────────────────────────

class Playlist(BaseModel):
    playlist_id: Optional[str] = None
    owner_id: int
    name: str
    description: str = ""
    tracks: List[Track] = Field(default_factory=list)
    is_public: bool = False
    thumbnail: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @property
    def total_duration(self) -> int:
        return sum(t.duration for t in self.tracks)


# ── Waifu ─────────────────────────────────────────────────────────────────────

class WaifuCard(BaseModel):
    waifu_id: str
    name: str
    series: str
    image_url: str
    rarity: WaifuRarity = WaifuRarity.COMMON
    stats: Dict[str, int] = Field(default_factory=dict)

    @property
    def rarity_emoji(self) -> str:
        return {"common": "⚪", "rare": "🔵", "epic": "🟣", "legendary": "🌟"}[self.rarity]


class WaifuInventoryItem(BaseModel):
    user_id: int
    waifu: WaifuCard
    obtained_at: datetime = Field(default_factory=datetime.utcnow)
    is_favorite: bool = False
    times_used: int = 0


# ── Play History ───────────────────────────────────────────────────────────────

class PlayHistoryEntry(BaseModel):
    user_id: int
    chat_id: int
    track: Track
    played_at: datetime = Field(default_factory=datetime.utcnow)
    duration_played: int = 0           # seconds actually played
  
