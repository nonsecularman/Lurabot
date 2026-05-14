"""
AuraBot — Quote Sticker Engine
Generates Telegram-style quote stickers from replied messages.
Full rendering: avatar, username, text, emoji, reply bubbles, dark/light themes.
"""

from __future__ import annotations

import asyncio
import io
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import cfg
from core.logger import get_logger

log = get_logger("sticker.quote")

STICKER_W, STICKER_H = 512, 512
PADDING = 28
BUBBLE_RADIUS = 18
AVATAR_SIZE = 48
FONT_PATH = cfg.QUOTE_FONT_PATH
EMOJI_FONT_PATH = "assets/fonts/NotoColorEmoji.ttf"


@dataclass
class QuoteTheme:
    name: str
    background: Tuple[int, int, int, int]       # RGBA
    bubble: Tuple[int, int, int, int]
    text_color: Tuple[int, int, int, int]
    name_color: Tuple[int, int, int, int]
    shadow_color: Tuple[int, int, int, int]
    reply_line: Tuple[int, int, int, int]


THEMES = {
    "dark": QuoteTheme(
        name="dark",
        background=(17, 17, 27, 220),
        bubble=(30, 30, 46, 255),
        text_color=(205, 214, 244, 255),
        name_color=(137, 180, 250, 255),
        shadow_color=(0, 0, 0, 120),
        reply_line=(89, 126, 211, 255),
    ),
    "light": QuoteTheme(
        name="light",
        background=(235, 235, 245, 220),
        bubble=(255, 255, 255, 255),
        text_color=(50, 50, 72, 255),
        name_color=(76, 110, 245, 255),
        shadow_color=(0, 0, 0, 40),
        reply_line=(76, 110, 245, 255),
    ),
    "amoled": QuoteTheme(
        name="amoled",
        background=(0, 0, 0, 255),
        bubble=(15, 15, 20, 255),
        text_color=(220, 220, 220, 255),
        name_color=(100, 160, 255, 255),
        shadow_color=(0, 0, 0, 180),
        reply_line=(100, 160, 255, 255),
    ),
}


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        path = FONT_PATH.replace(".ttf", "-Bold.ttf") if bold else FONT_PATH
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _round_image(img: Image.Image, radius: int) -> Image.Image:
    """Apply rounded corners to an RGBA image."""
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, *img.size], radius=radius, fill=255)
    result = img.copy()
    result.putalpha(mask)
    return result


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    radius: int,
    fill: Tuple,
    shadow_offset: int = 4,
    shadow_color: Optional[Tuple] = None,
) -> None:
    x1, y1, x2, y2 = xy
    if shadow_color:
        draw.rounded_rectangle(
            [x1 + shadow_offset, y1 + shadow_offset, x2 + shadow_offset, y2 + shadow_offset],
            radius=radius,
            fill=shadow_color,
        )
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)


class QuoteRenderer:
    """Renders Telegram-style quote images."""

    async def render(
        self,
        text: str,
        sender_name: str,
        avatar_bytes: Optional[bytes] = None,
        reply_to_text: Optional[str] = None,
        reply_to_name: Optional[str] = None,
        theme: str = "dark",
    ) -> bytes:
        """
        Render a quote sticker and return WEBP bytes.
        """
        return await asyncio.to_thread(
            self._render_sync,
            text,
            sender_name,
            avatar_bytes,
            reply_to_text,
            reply_to_name,
            theme,
        )

    def _render_sync(
        self,
        text: str,
        sender_name: str,
        avatar_bytes: Optional[bytes],
        reply_to_text: Optional[str],
        reply_to_name: Optional[str],
        theme_name: str,
    ) -> bytes:
        theme = THEMES.get(theme_name, THEMES["dark"])

        # Canvas
        canvas = Image.new("RGBA", (STICKER_W, STICKER_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        # Fonts
        name_font = _load_font(18, bold=True)
        text_font = _load_font(17)
        small_font = _load_font(14)

        # Layout
        x_start = PADDING
        content_width = STICKER_W - PADDING * 2

        # Bubble content measurement
        wrapped = textwrap.fill(text, width=36)
        text_bbox = draw.textbbox((0, 0), wrapped, font=text_font)
        text_h = text_bbox[3] - text_bbox[1]
        name_bbox = draw.textbbox((0, 0), sender_name, font=name_font)
        name_h = name_bbox[3] - name_bbox[1]

        reply_h = 0
        if reply_to_text:
            reply_h = 36

        bubble_h = PADDING + name_h + 8 + reply_h + text_h + PADDING
        bubble_w = content_width

        # Center vertically
        bubble_y = (STICKER_H - bubble_h) // 2
        bubble_x = AVATAR_SIZE + PADDING * 2

        # ── Background blur tint ───────────────────────────────────────────────
        bg = Image.new("RGBA", (STICKER_W, STICKER_H), theme.background)
        canvas = Image.alpha_composite(canvas, bg)
        draw = ImageDraw.Draw(canvas)

        # ── Avatar ────────────────────────────────────────────────────────────
        av_x, av_y = PADDING, bubble_y + bubble_h // 2 - AVATAR_SIZE // 2
        if avatar_bytes:
            try:
                av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                av_img = av_img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
                av_img = _round_image(av_img, AVATAR_SIZE // 2)
                canvas.paste(av_img, (av_x, av_y), av_img)
            except Exception:
                self._draw_default_avatar(draw, av_x, av_y, sender_name, theme)
        else:
            self._draw_default_avatar(draw, av_x, av_y, sender_name, theme)

        # ── Message Bubble ────────────────────────────────────────────────────
        bx1 = bubble_x
        by1 = bubble_y
        bx2 = bx1 + bubble_w - PADDING
        by2 = by1 + bubble_h

        _draw_rounded_rect(
            draw,
            (bx1, by1, bx2, by2),
            BUBBLE_RADIUS,
            theme.bubble,
            shadow_offset=3,
            shadow_color=theme.shadow_color,
        )

        # Tail indicator (left pointing)
        tail_pts = [
            (bx1, by1 + 18),
            (bx1 - 10, by1 + 28),
            (bx1, by1 + 38),
        ]
        draw.polygon(tail_pts, fill=theme.bubble)

        # ── Reply Header ──────────────────────────────────────────────────────
        cx = bx1 + PADDING
        cy = by1 + PADDING

        if reply_to_text and reply_to_name:
            draw.rectangle(
                [cx, cy, cx + 3, cy + reply_h - 4],
                fill=theme.reply_line,
            )
            draw.text((cx + 10, cy), reply_to_name, font=small_font, fill=theme.reply_line)
            preview = reply_to_text[:40] + "…" if len(reply_to_text) > 40 else reply_to_text
            draw.text(
                (cx + 10, cy + 16),
                preview,
                font=small_font,
                fill=(*theme.text_color[:3], 150),
            )
            cy += reply_h

        # ── Sender Name ───────────────────────────────────────────────────────
        draw.text((cx, cy), sender_name, font=name_font, fill=theme.name_color)
        cy += name_h + 8

        # ── Message Text ─────────────────────────────────────────────────────
        draw.multiline_text(
            (cx, cy),
            wrapped,
            font=text_font,
            fill=theme.text_color,
            spacing=4,
        )

        # ── Export as WEBP ────────────────────────────────────────────────────
        out = io.BytesIO()
        canvas.save(out, format="WEBP", quality=90, lossless=False)
        return out.getvalue()

    def _draw_default_avatar(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        name: str,
        theme: QuoteTheme,
    ) -> None:
        """Fallback: colored circle with initials."""
        colors = [
            (229, 57, 53), (244, 143, 177), (142, 36, 170),
            (3, 155, 229), (0, 137, 123), (67, 160, 71),
        ]
        color = colors[hash(name) % len(colors)]
        draw.ellipse(
            [x, y, x + AVATAR_SIZE, y + AVATAR_SIZE],
            fill=(*color, 255),
        )
        initial = (name[0] if name else "?").upper()
        font = _load_font(20, bold=True)
        bbox = draw.textbbox((0, 0), initial, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (x + (AVATAR_SIZE - tw) // 2, y + (AVATAR_SIZE - th) // 2),
            initial,
            font=font,
            fill=(255, 255, 255, 255),
        )


# Singleton
quote_renderer = QuoteRenderer()


# ── Plugin Handler ─────────────────────────────────────────────────────────────

def sticker_router(app) -> None:
    from pyrogram import Client, filters
    from pyrogram.types import Message

    @app.on_message(filters.command(["q", "quote"]))
    async def cmd_quote(client: Client, message: Message) -> None:
        replied = message.reply_to_message
        if not replied:
            await message.reply_text(
                "💬 Reply to a message with `/q` to generate a quote sticker.\n"
                "Optional: `/q dark` | `/q light` | `/q amoled`"
            )
            return

        # Extract theme from args
        args = message.command[1:]
        theme = args[0].lower() if args and args[0] in THEMES else "dark"

        # Get text
        text = replied.text or replied.caption
        if not text:
            await message.reply_text("❌ That message has no text to quote.")
            return

        sender = replied.from_user
        sender_name = sender.first_name if sender else "Unknown"
        if sender and sender.last_name:
            sender_name += f" {sender.last_name}"

        # Download avatar
        avatar_bytes: Optional[bytes] = None
        if sender:
            try:
                photos = await client.get_profile_photos(sender.id, limit=1)
                if photos.total_count:
                    buf = io.BytesIO()
                    await client.download_media(photos[0].file_id, file_name=buf)
                    avatar_bytes = buf.getvalue()
            except Exception:
                pass

        # Reply info
        reply_text = reply_name = None
        if replied.reply_to_message:
            r = replied.reply_to_message
            reply_text = r.text or r.caption or ""
            reply_name = r.from_user.first_name if r.from_user else ""

        status = await message.reply_text("🎨 Generating quote sticker...")
        try:
            webp = await quote_renderer.render(
                text=str(text),
                sender_name=sender_name,
                avatar_bytes=avatar_bytes,
                reply_to_text=reply_text,
                reply_to_name=reply_name,
                theme=theme,
            )
            sticker_buf = io.BytesIO(webp)
            sticker_buf.name = "quote.webp"
            await message.reply_sticker(sticker_buf)
            await status.delete()
        except Exception as e:
            log.error(f"Quote generation failed: {e}")
            await status.edit_text("❌ Failed to generate quote sticker.")
