"""
AuraBot — AI Service & Plugin
Conversational AI assistant, music recommendations, and lyric generation.
Supports OpenAI and Anthropic backends.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from config import cfg
from core.logger import get_logger
from core.security import ban_check, cooldown, flood_check

log = get_logger("ai")


class AIService:
    """Unified AI backend supporting OpenAI and Anthropic."""

    def __init__(self) -> None:
        self._openai = None
        self._anthropic = None

    def _ensure_openai(self):
        if self._openai is None:
            import openai
            self._openai = openai.AsyncOpenAI(api_key=cfg.OPENAI_API_KEY)
        return self._openai

    def _ensure_anthropic(self):
        if self._anthropic is None:
            import anthropic
            self._anthropic = anthropic.AsyncAnthropic(api_key=cfg.ANTHROPIC_API_KEY)
        return self._anthropic

    async def chat(
        self,
        prompt: str,
        system: str = "You are AuraBot, a friendly and helpful Telegram assistant.",
        history: Optional[List[dict]] = None,
    ) -> str:
        """Send a chat message and return the response."""
        if cfg.ANTHROPIC_API_KEY:
            return await self._anthropic_chat(prompt, system, history)
        if cfg.OPENAI_API_KEY:
            return await self._openai_chat(prompt, system, history)
        return "⚠️ No AI API keys configured."

    async def _openai_chat(
        self, prompt: str, system: str, history: Optional[List[dict]]
    ) -> str:
        client = self._ensure_openai()
        messages = [{"role": "system", "content": system}]
        if history:
            messages.extend(history[-6:])  # keep last 3 turns
        messages.append({"role": "user", "content": prompt})
        try:
            response = await client.chat.completions.create(
                model=cfg.AI_MODEL,
                messages=messages,
                max_tokens=cfg.AI_MAX_TOKENS,
                temperature=0.8,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            log.error(f"OpenAI error: {e}")
            return "❌ AI service error. Please try again."

    async def _anthropic_chat(
        self, prompt: str, system: str, history: Optional[List[dict]]
    ) -> str:
        client = self._ensure_anthropic()
        messages = []
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": prompt})
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=cfg.AI_MAX_TOKENS,
                system=system,
                messages=messages,
            )
            return response.content[0].text.strip()
        except Exception as e:
            log.error(f"Anthropic error: {e}")
            return "❌ AI service error. Please try again."

    async def recommend_music(self, history: List[str], count: int = 5) -> List[str]:
        """Generate music recommendations based on listen history."""
        if not history:
            return []
        history_str = ", ".join(history[-10:])
        prompt = (
            f"Based on these recently played songs: {history_str}\n\n"
            f"Recommend {count} similar songs the user might enjoy. "
            f"Reply with only a numbered list of 'Artist - Song Title' pairs."
        )
        system = "You are a music recommendation expert. Reply concisely with only the list requested."
        raw = await self.chat(prompt, system=system)
        # Parse numbered list
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        recs = []
        for line in lines:
            # Remove numbering
            parts = line.split(". ", 1)
            if len(parts) == 2:
                recs.append(parts[1])
            elif line:
                recs.append(line)
        return recs[:count]

    async def generate_playlist_name(self, tracks: List[str]) -> str:
        """Generate a creative playlist name from track list."""
        sample = ", ".join(tracks[:5])
        prompt = f"Generate a short, creative playlist name for songs like: {sample}. Reply with ONLY the name."
        return await self.chat(prompt, system="You name playlists creatively. Reply with just the name, no quotes.")

    async def analyze_mood(self, track_title: str, artist: str) -> str:
        """Analyze the mood/vibe of a track."""
        prompt = f"In 2-3 words, describe the mood/vibe of '{track_title}' by {artist}."
        return await self.chat(prompt, system="You analyze music mood concisely.")

    async def generate_dj_message(self, track: str) -> str:
        """Generate a hype DJ announcement for a track."""
        prompt = f"Write a 1-sentence energetic DJ announcement for playing '{track}'. Keep it fun and under 100 chars."
        return await self.chat(prompt, system="You are an energetic DJ making announcements.")


# Session history per user (in-memory, resets on restart)
_ai_sessions: dict[int, List[dict]] = {}
AI_MAX_HISTORY = 20

ai_service = AIService()


def ai_router(app) -> None:
    from pyrogram import Client, filters
    from pyrogram.types import Message

    # ── /ai or /ask ───────────────────────────────────────────────────────────
    @app.on_message(filters.command(["ai", "ask", "chat"]))
    @ban_check
    @flood_check
    @cooldown(5)
    async def cmd_ai(client: Client, message: Message) -> None:
        if not cfg.ENABLE_AI:
            await message.reply_text("❌ AI features are disabled.")
            return
        query = " ".join(message.command[1:]).strip()
        if not query:
            await message.reply_text(
                "🤖 **AuraBot AI**\n\n"
                "Usage: `/ask <your question>`\n\n"
                "_Powered by advanced AI. Ask me anything!_"
            )
            return
        uid = message.from_user.id
        status = await message.reply_text("🤔 Thinking...")
        history = _ai_sessions.get(uid, [])
        try:
            response = await ai_service.chat(query, history=history)
            # Update history
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": response})
            _ai_sessions[uid] = history[-AI_MAX_HISTORY:]
            await status.edit_text(f"🤖 {response}")
        except Exception as e:
            log.error(f"AI chat error: {e}")
            await status.edit_text("❌ AI is unavailable right now.")

    # ── /recommend ────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["recommend", "rec"]))
    @ban_check
    @cooldown(30)
    async def cmd_recommend(client: Client, message: Message) -> None:
        if not cfg.ENABLE_AI:
            return
        uid = message.from_user.id
        status = await message.reply_text("🎵 Analyzing your listening history...")
        from database.mongo import get_collection
        docs = await get_collection("play_history").find(
            {"user_id": uid}
        ).sort("played_at", -1).limit(15).to_list(length=15)
        if not docs:
            await status.edit_text("❌ No listening history yet. Play some music first!")
            return
        history = [f"{d.get('title', '')} by {d.get('artist', '')}" for d in docs]
        recs = await ai_service.recommend_music(history)
        if not recs:
            await status.edit_text("❌ Could not generate recommendations.")
            return
        lines = ["🎵 **AI Music Recommendations**\n"]
        for i, rec in enumerate(recs, 1):
            lines.append(f"`{i}.` {rec}")
        lines.append("\n_Click a song name to play it with /play_")
        await status.edit_text("\n".join(lines))

    # ── /clearchat ────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["clearchat", "resetai"]))
    @ban_check
    async def cmd_clear_chat(client: Client, message: Message) -> None:
        uid = message.from_user.id
        _ai_sessions.pop(uid, None)
        await message.reply_text("🧹 AI conversation history cleared.")
      
