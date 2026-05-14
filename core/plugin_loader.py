"""
AuraBot — Plugin Loader
Auto-discovers and registers all plugin routers onto the Pyrogram client.
"""

from __future__ import annotations

from pyrogram import Client

from core.logger import get_logger

log = get_logger("plugin_loader")


def load_all_plugins(app: Client) -> None:
    """
    Register every plugin router onto the Pyrogram client.
    Order matters: admin first, then music, sticker, anime, ai, utility.
    """

    # ── Admin ──────────────────────────────────────────────────────────────
    from plugins.admin.admin import admin_router
    admin_router(app)
    log.debug("Loaded: admin plugin")

    # ── Music ──────────────────────────────────────────────────────────────
    from plugins.music.play import music_router
    music_router(app)
    log.debug("Loaded: music plugin")

    from services.lyrics import lyrics_router
    lyrics_router(app)
    log.debug("Loaded: lyrics plugin")

    # ── Sticker ────────────────────────────────────────────────────────────
    from plugins.sticker.quote import sticker_router
    sticker_router(app)
    log.debug("Loaded: quote sticker plugin")

    from plugins.sticker.text_sticker import text_sticker_router
    text_sticker_router(app)
    log.debug("Loaded: text sticker plugin")

    # ── Anime ──────────────────────────────────────────────────────────────
    from plugins.anime.waifu import anime_router
    anime_router(app)
    log.debug("Loaded: anime/waifu plugin")

    # ── AI ─────────────────────────────────────────────────────────────────
    from plugins.ai.assistant import ai_router
    ai_router(app)
    log.debug("Loaded: AI assistant plugin")

    # ── Inline ─────────────────────────────────────────────────────────────
    from config import cfg
    if cfg.ENABLE_INLINE:
        from plugins.utility.inline import inline_router
        inline_router(app)
        log.debug("Loaded: inline plugin")

    log.success("All plugins loaded successfully.")
  
