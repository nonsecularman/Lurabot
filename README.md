# 🎵 AuraBot

**Production-grade Telegram Multimedia Ecosystem**

> Music streaming · Anime entertainment · AI assistant · Sticker generation · Distributed infrastructure

---

## ✨ Feature Overview

| Module | Features |
|---|---|
| 🎵 **Music** | YouTube, Spotify, SoundCloud, Telegram files, livestreams |
| 🎚 **Audio Filters** | Bass boost, Nightcore, 8D, Vaporwave, Reverb, Echo, Karaoke |
| 🌸 **Anime** | Waifu cards, reaction GIFs, collectibles, XP, marriage system |
| 🎨 **Stickers** | Quote stickers (`/q`), text stickers (`/s`) with 9 visual styles |
| 🤖 **AI** | Chat assistant, music recommendations, AI DJ mode |
| 📋 **Playlists** | Personal playlists, shareable, up to 100 tracks |
| 📡 **Dashboard** | FastAPI REST + WebSocket live dashboard |
| 🔒 **Security** | Flood protection, cooldowns, ACL permissions, ban system |
| 📊 **Monitoring** | Prometheus metrics, Grafana dashboards, structured logging |
| 🚀 **Scaling** | Redis pub/sub workers, multi-assistant balancing, Docker + K8s ready |

---

## 🏗 Architecture

```
Telegram Bot (Pyrogram)
        │
        ├── Plugin Layer (music, sticker, anime, ai, admin)
        │
        ├── Core Services
        │   ├── Assistant Manager (multi-account pool)
        │   ├── Music Player (PyTgCalls + FFmpeg)
        │   ├── Queue System (Redis-backed)
        │   └── Security (flood, cooldown, ACL)
        │
        ├── Workers
        │   ├── Stream Worker (FFmpeg health monitor)
        │   └── Queue Worker (Redis pub/sub, scalable)
        │
        ├── Databases
        │   ├── MongoDB (users, playlists, history, waifu)
        │   └── Redis (queues, playback state, cache, cooldowns)
        │
        └── FastAPI Dashboard (REST + WebSocket)
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- FFmpeg
- MongoDB
- Redis
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)

### 1. Clone & Setup

```bash
git clone https://github.com/youruser/AuraBot.git
cd AuraBot
cp .env.example .env
```

### 2. Configure `.env`

```env
BOT_TOKEN=your_bot_token
API_ID=your_api_id
API_HASH=your_api_hash
OWNER_ID=your_telegram_id
MONGO_URI=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379/0
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run

```bash
python app.py
```

---

## 🐳 Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f bot

# Scale workers
docker-compose up -d --scale worker=3
```

Services started:
- `bot` — AuraBot on port 8080
- `redis` — Redis 7.2
- `mongodb` — MongoDB 7.0
- `nginx` — Reverse proxy on port 80
- `prometheus` — Metrics on port 9090
- `grafana` — Dashboard on port 3000

---

## 📖 Command Reference

### 🎵 Music
| Command | Description |
|---|---|
| `/play <query/URL>` | Play from YouTube, Spotify, SoundCloud, or Telegram |
| `/skip` | Skip current track |
| `/pause` / `/resume` | Pause / resume |
| `/stop` | Stop and clear queue |
| `/queue` | Show queue |
| `/np` | Now playing |
| `/volume <0-200>` | Set volume |
| `/seek <seconds>` | Seek to position |
| `/loop track\|queue\|off` | Set loop mode |
| `/shuffle` | Shuffle queue |
| `/filter <name>` | Apply audio filter |
| `/lyrics` | Get current song lyrics |

**Audio Filters:** `bass`, `nightcore`, `vaporwave`, `reverb`, `echo`, `8d`, `karaoke`, `distortion`, `none`

### 📋 Playlists
| Command | Description |
|---|---|
| `/playlist create <name>` | Create playlist |
| `/playlist add <name> <song>` | Add track |
| `/playlist play <name>` | Play playlist |
| `/playlist list` | List your playlists |
| `/playlist share <name>` | Make public |

### 🎨 Stickers
| Command | Description |
|---|---|
| `/q` | Quote sticker (reply to message) |
| `/q light\|dark\|amoled` | Quote with theme |
| `/s <text>` | Text sticker (default style) |
| `/s <style> <text>` | Text sticker with style |

**Sticker Styles:** `minimal`, `cyberpunk`, `anime`, `glassmorphism`, `neon`, `dark`, `telegram`, `fire`, `ocean`

### 🌸 Anime
| Command | Description |
|---|---|
| `/waifu` | Roll a waifu card |
| `/hug \| /kiss \| /pat \| /slap` | Reaction GIFs |
| `/cry \| /smile \| /blush \| /dance` | More reactions |
| `/marry` | Propose (reply to user) |
| `/divorce` | End marriage |
| `/profile` | View profile & XP |
| `/leaderboard` | Top XP rankings |

### 🤖 AI
| Command | Description |
|---|---|
| `/ask <question>` | Chat with AI |
| `/recommend` | AI music recommendations |
| `/clearchat` | Clear AI history |

### ⚙️ Admin
| Command | Description |
|---|---|
| `/stats` | Bot statistics |
| `/ban \| /unban` | User management |
| `/broadcast` | Message all chats |
| `/premium <user>` | Grant premium |
| `/sudoadd \| /sudorm` | Sudo management |
| `/adminonly` | Restrict commands to admins |
| `/djadd \| /djrm` | DJ role management |

---

## ⚙️ Configuration Reference

See `.env.example` for all available configuration options.

Key settings:
- `ASSISTANT_SESSIONS` — Comma-separated Pyrogram session strings for voice chat
- `ENABLE_AI` — Enable/disable AI features
- `STREAM_QUALITY` — `low` / `medium` / `high`
- `MAX_DURATION` — Maximum track duration in seconds
- `API_SECRET_KEY` — Dashboard authentication key

---

## 🔧 Generating Assistant Sessions

```python
from pyrogram import Client

async def main():
    async with Client("assistant", api_id=API_ID, api_hash=API_HASH) as app:
        print(await app.export_session_string())

import asyncio
asyncio.run(main())
```

Add the exported string to `ASSISTANT_SESSIONS` in your `.env`.

---

## 📊 Monitoring

- **Prometheus:** `http://localhost:9090`
- **Grafana:** `http://localhost:3000` (admin / admin)
- **Dashboard API:** `http://localhost:8080/docs`

Metrics available:
- `aurabot_active_voice_calls`
- `aurabot_tracks_played_total`
- `aurabot_commands_total`
- `aurabot_stickers_generated_total`
- `aurabot_ai_requests_total`

---

## 🧪 Testing

```bash
pytest tests/ -v --asyncio-mode=auto
```

---

## 📁 Project Structure

```
AuraBot/
├── app.py                   # Main entrypoint
├── config.py                # Pydantic settings
├── requirements.txt
│
├── core/                    # Framework layer
│   ├── assistant_manager.py # Multi-account pool
│   ├── security.py          # ACL, flood, cooldowns
│   ├── plugin_loader.py     # Auto plugin discovery
│   ├── startup.py           # Lifecycle hooks
│   ├── metrics.py           # Prometheus metrics
│   └── logger.py            # Structured logging
│
├── database/                # Data layer
│   ├── mongo.py             # Async MongoDB client
│   ├── redis.py             # Async Redis client + key helpers
│   ├── models/              # Pydantic domain models
│   └── repositories/        # CRUD abstractions
│
├── music/                   # Music engine
│   ├── player.py            # Orchestrator
│   ├── queue.py             # Redis queue manager
│   ├── extractor.py         # yt-dlp resolver
│   ├── ffmpeg.py            # FFmpeg process manager
│   └── autoplay.py          # Recommendation engine
│
├── plugins/                 # Telegram command handlers
│   ├── music/               # /play, /queue, /playlist…
│   ├── sticker/             # /q, /s
│   ├── anime/               # /waifu, reactions, marry
│   ├── ai/                  # /ask, /recommend
│   ├── admin/               # /ban, /stats, /broadcast
│   └── utility/             # Inline mode
│
├── services/                # External integrations
│   ├── spotify.py           # Spotify Web API
│   └── lyrics.py            # Multi-source lyrics
│
├── workers/                 # Background processors
│   ├── queue_worker.py      # Redis pub/sub worker
│   └── stream_worker.py     # FFmpeg health monitor
│
├── api/                     # Web dashboard
│   └── dashboard.py         # FastAPI + WebSocket
│
└── docker/                  # Deployment configs
    ├── Dockerfile
    ├── nginx.conf
    └── prometheus.yml
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built with ❤️ using Python 3.12, Pyrogram, PyTgCalls, FFmpeg, Redis, MongoDB, and FastAPI.*
