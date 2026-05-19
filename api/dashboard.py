"""
AuraBot — FastAPI Dashboard
REST API + WebSocket backend for the web management dashboard.
"""

from __future__ import annotations

import asyncio
import time
from typing import List

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from config import cfg
from core.logger import get_logger
from core.assistant_manager import assistant_manager
from database.mongo import count_documents, find_many
from database.redis import queue_peek, queue_len
from music.player import player
from music.queue import music_queue
from workers.stream_worker import stream_worker

log = get_logger("api.dashboard")


# ── Pydantic Models ───────────────────────────────────────────

class PlaybackAction(BaseModel):
    action: str


class VolumeBody(BaseModel):
    volume: int


# ── App Setup ─────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="AuraBot Dashboard API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.API_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_routes(app)
    return app


# ── Auth ──────────────────────────────────────────────────────

security = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:

    if credentials.credentials != cfg.API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return credentials.credentials


# ── WebSocket Manager ─────────────────────────────────────────

class ConnectionManager:

    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, data: dict):

        dead = []

        for ws in self.connections:
            try:
                await ws.send_json(data)

            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()


# ── Routes ────────────────────────────────────────────────────

def _register_routes(app: FastAPI) -> None:

    # ── Health ────────────────────────────────────────────────
    @app.get("/health")
    async def health():

        return {
            "status": "ok",
            "timestamp": time.time(),
        }

    # ── Stats ─────────────────────────────────────────────────
    @app.get("/api/stats", dependencies=[Depends(verify_token)])
    async def get_stats():

        total_users = await count_documents("users")
        total_chats = await count_documents("chats")
        total_plays = await count_documents("play_history")

        return {
            "users": total_users,
            "chats": total_chats,
            "total_plays": total_plays,
            "active_calls": len(player._active),
            "active_streams": stream_worker.active_count(),
            "assistants": assistant_manager.status(),
        }

    # ── Assistants ────────────────────────────────────────────
    @app.get("/api/assistants", dependencies=[Depends(verify_token)])
    async def get_assistants():

        return assistant_manager.status()

    # ── Queue ─────────────────────────────────────────────────
    @app.get("/api/queue/{chat_id}", dependencies=[Depends(verify_token)])
    async def get_queue(chat_id: int):

        state = await music_queue.get_state(chat_id)
        tracks = await queue_peek(chat_id, 20)

        return {
            "chat_id": chat_id,
            "current": (
                state.current.model_dump()
                if state and state.current
                else None
            ),
            "queue_length": await queue_len(chat_id),
            "tracks": tracks,
            "loop": state.loop if state else "none",
            "volume": state.volume if state else 100,
            "is_playing": state.is_playing if state else False,
            "is_paused": state.is_paused if state else False,
        }

    # ── Playback Control ──────────────────────────────────────
    @app.post("/api/playback/{chat_id}",
              dependencies=[Depends(verify_token)])
    async def control_playback(
        chat_id: int,
        body: PlaybackAction,
    ):

        actions = {
            "pause": player.pause,
            "resume": player.resume,
            "skip": player.skip,
            "stop": player.stop_session,
        }

        fn = actions.get(body.action)

        if not fn:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action: {body.action}",
            )

        await fn(chat_id)

        await ws_manager.broadcast({
            "type": "playback_action",
            "chat_id": chat_id,
            "action": body.action,
        })

        return {"ok": True}

    # ── Volume Control ────────────────────────────────────────
    @app.post("/api/volume/{chat_id}",
              dependencies=[Depends(verify_token)])
    async def set_volume(
        chat_id: int,
        body: VolumeBody,
    ):

        await player.set_volume(chat_id, body.volume)

        return {
            "ok": True,
            "volume": body.volume,
        }

    # ── Users ─────────────────────────────────────────────────
    @app.get("/api/users", dependencies=[Depends(verify_token)])
    async def list_users(
        limit: int = 50,
        skip: int = 0,
    ):

        docs = await find_many(
            "users",
            {},
            sort=[("xp", -1)],
            limit=limit,
            skip=skip,
        )

        total = await count_documents("users")

        return {
            "total": total,
            "users": docs,
        }

    @app.get("/api/users/{user_id}",
             dependencies=[Depends(verify_token)])
    async def get_user(user_id: int):

        from database.repositories.user_repo import user_repo

        user = await user_repo.get(user_id)

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        return user.model_dump()

    # ── Play History ──────────────────────────────────────────
    @app.get("/api/history", dependencies=[Depends(verify_token)])
    async def play_history(limit: int = 50):

        docs = await find_many(
            "play_history",
            {},
            sort=[("played_at", -1)],
            limit=limit,
        )

        return {"history": docs}

    # ── Streams ───────────────────────────────────────────────
    @app.get("/api/streams", dependencies=[Depends(verify_token)])
    async def get_streams():

        return stream_worker.status()

    # ── WebSocket ─────────────────────────────────────────────
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):

        await ws_manager.connect(ws)

        log.info(f"WebSocket client connected: {ws.client}")

        try:
            while True:

                stats = {
                    "type": "status_update",
                    "active_calls": len(player._active),
                    "active_streams": stream_worker.active_count(),
                    "timestamp": time.time(),
                }

                await ws.send_json(stats)

                await asyncio.sleep(5)

        except WebSocketDisconnect:

            ws_manager.disconnect(ws)

            log.info(
                f"WebSocket client disconnected: {ws.client}"
            )

    # ── Metrics ───────────────────────────────────────────────
    @app.get("/metrics")
    async def metrics():

        from prometheus_client import (
            generate_latest,
            CONTENT_TYPE_LATEST,
        )

        from fastapi.responses import Response

        data = generate_latest()

        return Response(
            content=data,
            media_type=CONTENT_TYPE_LATEST,
        )


# ── Export App ────────────────────────────────────────────────

dashboard_app = create_app()
