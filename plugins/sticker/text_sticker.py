"""
AuraBot — Text to Sticker Engine
/s command: converts text to stylized WEBP sticker with multiple themes.
"""

from __future__ import annotations

import asyncio
import io
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import cfg
from core.logger import get_logger

log = get_logger("sticker.text")

W, H = 512, 512


@dataclass
class StickerStyle:
    name: str
    bg_colors: List[Tuple[int, int, int]]   # gradient stops
    text_color: Tuple[int, int, int, int]
    font_size: int = 52
    shadow: bool = True
    glow: bool = False
    border: bool = False
    border_color: Tuple[int, int, int, int] = (255, 255, 255, 200)


STYLES: dict[str, StickerStyle] = {
    "minimal": StickerStyle(
        name="minimal",
        bg_colors=[(20, 20, 30), (40, 40, 60)],
        text_color=(240, 240, 255, 255),
        shadow=False,
    ),
    "cyberpunk": StickerStyle(
        name="cyberpunk",
        bg_colors=[(5, 0, 20), (20, 5, 60), (0, 30, 60)],
        text_color=(0, 255, 200, 255),
        glow=True,
        border=True,
        border_color=(0, 255, 200, 180),
    ),
    "anime": StickerStyle(
        name="anime",
        bg_colors=[(255, 182, 193), (255, 105, 180), (138, 43, 226)],
        text_color=(255, 255, 255, 255),
        shadow=True,
        font_size=54,
    ),
    "glassmorphism": StickerStyle(
        name="glassmorphism",
        bg_colors=[(70, 130, 180), (100, 100, 200), (50, 200, 200)],
        text_color=(255, 255, 255, 255),
        shadow=True,
        border=True,
        border_color=(255, 255, 255, 100),
    ),
    "neon": StickerStyle(
        name="neon",
        bg_colors=[(0, 0, 0), (10, 0, 30)],
        text_color=(255, 50, 255, 255),
        glow=True,
        border=True,
        border_color=(255, 50, 255, 200),
    ),
    "dark": StickerStyle(
        name="dark",
        bg_colors=[(15, 15, 25), (25, 25, 40)],
        text_color=(200, 200, 220, 255),
        shadow=True,
    ),
    "telegram": StickerStyle(
        name="telegram",
        bg_colors=[(31, 136, 229), (20, 102, 200)],
        text_color=(255, 255, 255, 255),
        shadow=True,
    ),
    "fire": StickerStyle(
        name="fire",
        bg_colors=[(40, 5, 0), (120, 30, 0), (200, 80, 0)],
        text_color=(255, 220, 50, 255),
        glow=True,
        shadow=True,
    ),
    "ocean": StickerStyle(
        name="ocean",
        bg_colors=[(0, 20, 60), (0, 60, 120), (0, 100, 160)],
        text_color=(100, 220, 255, 255),
        shadow=True,
        border=True,
        border_color=(100, 220, 255, 150),
    ),
}


def _linear_gradient(img: Image.Image, colors: List[Tuple[int, int, int]]) -> Image.Image:
    """Apply a multi-stop linear gradient to an RGBA image."""
    w, h = img.size
    draw = ImageDraw.Draw(img)
    n = len(colors) - 1
    for y in range(h):
        t = y / h
        segment = min(int(t * n), n - 1)
        local_t = (t * n) - segment
        c1, c2 = colors[segment], colors[segment + 1]
        r = int(c1[0] + (c2[0] - c1[0]) * local_t)
        g = int(c1[1] + (c2[1] - c1[1]) * local_t)
        b = int(c1[2] + (c2[2] - c1[2]) * local_t)
        draw.line([(0, y), (w, y)], fill=(r, g, b, 255))
    return img


def _add_noise(img: Image.Image, intensity: int = 12) -> Image.Image:
    """Add subtle grain for texture."""
    import random
    noise = Image.new("RGBA", img.size)
    px = noise.load()
    for y in range(img.height):
        for x in range(img.width):
            v = random.randint(-intensity, intensity)
            px[x, y] = (max(0, min(255, v)), max(0, min(255, v)), max(0, min(255, v)), 20)
    return Image.alpha_composite(img, noise)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(cfg.STICKER_FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _fit_text(text: str, max_width: int, initial_size: int = 52) -> Tuple[ImageFont.FreeTypeFont, str]:
    """Auto-shrink font until text fits."""
    import textwrap
    for size in range(initial_size, 14, -2):
        font = _load_font(size)
        wrapped = textwrap.fill(text, width=max(8, 24 - (initial_size - size) // 4))
        dummy = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(dummy)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        tw = bbox[2] - bbox[0]
        if tw <= max_width:
            return font, wrapped
    return _load_font(14), textwrap.fill(text, width=30)


class TextStickerRenderer:

    async def render(self, text: str, style: str = "telegram") -> bytes:
        return await asyncio.to_thread(self._render_sync, text, style)

    def _render_sync(self, text: str, style_name: str) -> bytes:
        style = STYLES.get(style_name, STYLES["telegram"])
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        # ── Background Gradient ───────────────────────────────────────────────
        bg = Image.new("RGBA", (W, H))
        _linear_gradient(bg, style.bg_colors)

        # Glassmorphism overlay
        if style_name == "glassmorphism":
            overlay = bg.filter(ImageFilter.GaussianBlur(15))
            glass = Image.new("RGBA", (W, H), (255, 255, 255, 40))
            overlay = Image.alpha_composite(overlay, glass)
            bg = overlay

        canvas = Image.alpha_composite(canvas, bg)

        # Subtle noise texture
        canvas = _add_noise(canvas, intensity=8)

        draw = ImageDraw.Draw(canvas)

        # ── Text Layout ───────────────────────────────────────────────────────
        font, wrapped = _fit_text(text, W - 60, style.font_size)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=8)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (W - tw) // 2
        ty = (H - th) // 2

        # ── Glow Effect ───────────────────────────────────────────────────────
        if style.glow:
            glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow_layer)
            gd.multiline_text(
                (tx, ty), wrapped, font=font,
                fill=(*style.text_color[:3], 80), spacing=8,
            )
            for r in [8, 12, 16]:
                blurred = glow_layer.filter(ImageFilter.GaussianBlur(r))
                canvas = Image.alpha_composite(canvas, blurred)

        # ── Shadow ────────────────────────────────────────────────────────────
        if style.shadow:
            shadow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow_layer)
            sd.multiline_text(
                (tx + 3, ty + 4), wrapped, font=font,
                fill=(0, 0, 0, 160), spacing=8,
            )
            blurred_shadow = shadow_layer.filter(ImageFilter.GaussianBlur(4))
            canvas = Image.alpha_composite(canvas, blurred_shadow)

        # ── Border / Stroke ───────────────────────────────────────────────────
        if style.border:
            for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
                draw.multiline_text(
                    (tx + dx, ty + dy), wrapped, font=font,
                    fill=style.border_color, spacing=8,
                )

        # ── Main Text ─────────────────────────────────────────────────────────
        draw.multiline_text(
            (tx, ty), wrapped, font=font,
            fill=style.text_color, spacing=8, align="center",
        )

        # ── Corner Accent (cyberpunk / neon) ──────────────────────────────────
        if style_name in ("cyberpunk", "neon"):
            accent = style.text_color[:3]
            for corner_x, corner_y, dx, dy in [
                (16, 16, 1, 1), (W - 16, 16, -1, 1),
                (16, H - 16, 1, -1), (W - 16, H - 16, -1, -1),
            ]:
                draw.line(
                    [(corner_x, corner_y), (corner_x + dx * 30, corner_y)],
                    fill=(*accent, 200), width=2,
                )
                draw.line(
                    [(corner_x, corner_y), (corner_x, corner_y + dy * 30)],
                    fill=(*accent, 200), width=2,
                )

        # ── Export ────────────────────────────────────────────────────────────
        out = io.BytesIO()
        canvas.save(out, format="WEBP", quality=92)
        return out.getvalue()


text_sticker_renderer = TextStickerRenderer()


# ── Plugin Handler ─────────────────────────────────────────────────────────────

def text_sticker_router(app) -> None:
    from pyrogram import Client, filters
    from pyrogram.types import Message

    style_names = "|".join(STYLES.keys())

    @app.on_message(filters.command(["s", "sticker"]))
    async def cmd_text_sticker(client: Client, message: Message) -> None:
        args = message.command[1:]
        if not args:
            await message.reply_text(
                "✨ **Text Sticker Generator**\n\n"
                "Usage: `/s <text>`\n"
                "With style: `/s <style> <text>`\n\n"
                f"**Styles:** `{'`, `'.join(STYLES.keys())}`"
            )
            return

        style = "telegram"
        text_parts = args

        if args[0].lower() in STYLES:
            style = args[0].lower()
            text_parts = args[1:]

        text = " ".join(text_parts).strip()
        if not text:
            await message.reply_text("❌ Provide some text after the style.")
            return
        if len(text) > 200:
            await message.reply_text("❌ Text too long. Max 200 characters.")
            return

        status = await message.reply_text("🎨 Creating sticker...")
        try:
            webp = await text_sticker_renderer.render(text, style)
            buf = io.BytesIO(webp)
            buf.name = "sticker.webp"
            await message.reply_sticker(buf)
            await status.delete()
        except Exception as e:
            log.error(f"Text sticker error: {e}")
            await status.edit_text("❌ Failed to generate sticker.")
