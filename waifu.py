"""
AuraBot — Anime / Waifu System
Reaction GIFs, waifu cards, collectibles, XP, marriage system.
"""

from __future__ import annotations

import asyncio
import random
from typing import Optional

import httpx

from config import cfg
from core.logger import get_logger
from core.security import ban_check, cooldown, flood_check
from database.models import WaifuCard, WaifuRarity
from database.repositories.user_repo import user_repo

log = get_logger("anime")


# ── API Endpoints ─────────────────────────────────────────────────────────────

WAIFU_PICS = {
    "waifu": f"{cfg.WAIFU_API_BASE}/sfw/waifu",
    "hug": f"{cfg.WAIFU_API_BASE}/sfw/hug",
    "kiss": f"{cfg.WAIFU_API_BASE}/sfw/kiss",
    "pat": f"{cfg.WAIFU_API_BASE}/sfw/pat",
    "slap": f"{cfg.WAIFU_API_BASE}/sfw/slap",
    "cry": f"{cfg.WAIFU_API_BASE}/sfw/cry",
    "smile": f"{cfg.WAIFU_API_BASE}/sfw/smile",
    "blush": f"{cfg.WAIFU_API_BASE}/sfw/blush",
    "bite": f"{cfg.WAIFU_API_BASE}/sfw/bite",
    "cuddle": f"{cfg.WAIFU_API_BASE}/sfw/cuddle",
    "poke": f"{cfg.WAIFU_API_BASE}/sfw/poke",
    "wave": f"{cfg.WAIFU_API_BASE}/sfw/wave",
    "dance": f"{cfg.WAIFU_API_BASE}/sfw/dance",
}

NEKOS_BEST = {
    "waifu": f"{cfg.NEKOS_API_BASE}/waifu",
    "hug": f"{cfg.NEKOS_API_BASE}/hug",
    "kiss": f"{cfg.NEKOS_API_BASE}/kiss",
    "pat": f"{cfg.NEKOS_API_BASE}/pat",
    "cry": f"{cfg.NEKOS_API_BASE}/cry",
    "blush": f"{cfg.NEKOS_API_BASE}/blush",
}

REACTION_TEMPLATES = {
    "hug": ["{user} hugs {target} 🤗", "{user} wraps {target} in a warm hug! 🫂"],
    "kiss": ["{user} kisses {target} 💋", "{user} gives {target} a soft kiss~ 💕"],
    "pat": ["{user} pats {target}'s head 🥺", "{user} headpats {target}! ✨"],
    "slap": ["{user} slaps {target}! 👋", "{user} yeets a slap at {target} 😤"],
    "cry": ["{user} is crying 😭", "*sobs loudly* 😢"],
    "smile": ["{user} flashes a bright smile 😊", "{user} is smiling~ ☀️"],
    "blush": ["{user} is blushing 🌸", "{user}'s cheeks go red 💗"],
    "bite": ["{user} bites {target}! 😤", "{user} nom noms {target} 🍴"],
    "cuddle": ["{user} cuddles with {target} 🥰", "{user} snuggles up to {target} 💤"],
    "poke": ["{user} pokes {target}! 👆", "{user} keeps poking {target}... 😏"],
    "wave": ["{user} waves! 👋", "{user} waves goodbye~ 🌊"],
    "dance": ["{user} breaks into a dance! 💃", "{user} dances wildly 🕺"],
    "baka": ["{user} calls {target} a BAKA! 😤", "B-BAKA! {user} screams at {target} 😡"],
}

WAIFU_SERIES = [
    "Sword Art Online", "Re:Zero", "Attack on Titan", "Demon Slayer",
    "My Hero Academia", "Fullmetal Alchemist", "One Piece", "Naruto",
    "Bleach", "Hunter x Hunter", "Death Note", "Spirited Away",
    "Violet Evergarden", "Your Lie in April", "Clannad",
]

RARITY_WEIGHTS = [60, 25, 12, 3]   # common, rare, epic, legendary


async def fetch_anime_image(action: str) -> Optional[str]:
    """Fetch a GIF/image URL from waifu.pics or nekos.best."""
    url = WAIFU_PICS.get(action) or NEKOS_BEST.get(action)
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url)
            data = resp.json()
            # waifu.pics returns {"url": ...}
            # nekos.best returns {"results": [{"url": ...}]}
            return data.get("url") or data.get("results", [{}])[0].get("url")
    except Exception as e:
        log.warning(f"Anime API error for {action}: {e}")
        return None


def _get_reaction_text(action: str, sender: str, target: Optional[str] = None) -> str:
    templates = REACTION_TEMPLATES.get(action, [f"{sender} does something~ ✨"])
    tmpl = random.choice(templates)
    return tmpl.format(user=f"**{sender}**", target=f"**{target}**" if target else "everyone")


def _generate_waifu_card(user_id: int) -> WaifuCard:
    """Procedurally generate a random waifu card."""
    rarity_val = random.choices(
        [WaifuRarity.COMMON, WaifuRarity.RARE, WaifuRarity.EPIC, WaifuRarity.LEGENDARY],
        weights=RARITY_WEIGHTS,
    )[0]
    series = random.choice(WAIFU_SERIES)
    names = ["Sakura", "Rei", "Asuna", "Emilia", "Rem", "Zero Two", "Miku", "Nezuko",
             "Mikasa", "Hinata", "Nami", "Robin", "Erza", "Aqua", "Shouko"]
    name = random.choice(names)
    stats = {
        "power": random.randint(20, 100),
        "charm": random.randint(20, 100),
        "speed": random.randint(20, 100),
    }
    # Boost stats by rarity
    boost = {"common": 1, "rare": 1.3, "epic": 1.6, "legendary": 2.0}[rarity_val]
    stats = {k: min(100, int(v * boost)) for k, v in stats.items()}

    return WaifuCard(
        waifu_id=f"{user_id}_{name}_{random.randint(1000, 9999)}",
        name=name,
        series=series,
        image_url="",  # fetched dynamically
        rarity=rarity_val,
        stats=stats,
    )


# ── Plugin Handlers ────────────────────────────────────────────────────────────

def anime_router(app) -> None:
    from pyrogram import Client, filters
    from pyrogram.types import Message

    REACTION_CMDS = ["hug", "kiss", "pat", "slap", "cry", "smile", "blush",
                     "bite", "cuddle", "poke", "wave", "dance", "baka"]

    # ── /waifu ────────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["waifu"]))
    @ban_check
    @cooldown(10)
    async def cmd_waifu(client: Client, message: Message) -> None:
        uid = message.from_user.id
        name = message.from_user.first_name

        # Roll waifu
        card = _generate_waifu_card(uid)
        image_url = await fetch_anime_image("waifu") or ""
        card.image_url = image_url

        # Save to inventory
        from database.mongo import get_collection
        from datetime import datetime
        await get_collection("waifu_inventory").insert_one({
            "user_id": uid,
            "waifu": card.model_dump(),
            "obtained_at": datetime.utcnow(),
        })

        # Award XP
        _, leveled = await user_repo.add_xp(uid, 10)

        rarity_colors = {
            WaifuRarity.COMMON: "⚪",
            WaifuRarity.RARE: "🔵",
            WaifuRarity.EPIC: "🟣",
            WaifuRarity.LEGENDARY: "🌟",
        }
        text = (
            f"✨ **Waifu Rolled!**\n\n"
            f"👤 **{card.name}** — _{card.series}_\n"
            f"Rarity: {rarity_colors[card.rarity]} **{card.rarity.value.upper()}**\n\n"
            f"📊 **Stats:**\n"
            f"⚡ Power: `{card.stats['power']}`\n"
            f"💕 Charm: `{card.stats['charm']}`\n"
            f"💨 Speed: `{card.stats['speed']}`\n"
        )
        if leveled:
            text += f"\n🎉 Level up! **{name}** reached a new level!"

        if image_url:
            await message.reply_photo(image_url, caption=text)
        else:
            await message.reply_text(text)

    # ── Reaction Commands ─────────────────────────────────────────────────────
    for _action in REACTION_CMDS:
        def make_handler(action: str):
            @ban_check
            @cooldown(5)
            async def handler(client: Client, message: Message) -> None:
                sender = message.from_user.first_name if message.from_user else "Someone"
                target = None
                if message.reply_to_message and message.reply_to_message.from_user:
                    target = message.reply_to_message.from_user.first_name

                text = _get_reaction_text(action, sender, target)
                image_url = await fetch_anime_image(action)

                if image_url:
                    await message.reply_animation(image_url, caption=text)
                else:
                    await message.reply_text(text)

                # XP for interactions
                if message.from_user:
                    await user_repo.add_xp(message.from_user.id, 2)

            handler.__name__ = f"cmd_{action}"
            return handler

        app.on_message(filters.command([_action]))(make_handler(_action))

    # ── /marry ────────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["marry"]))
    @ban_check
    @cooldown(30)
    async def cmd_marry(client: Client, message: Message) -> None:
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply_text("💍 Reply to a user's message to propose!")
            return
        uid = message.from_user.id
        partner_id = message.reply_to_message.from_user.id
        if partner_id == uid:
            await message.reply_text("❌ You can't marry yourself!")
            return
        user = await user_repo.get(uid)
        if user and user.married_to:
            await message.reply_text("💔 You're already married! Divorce first.")
            return
        partner = await user_repo.get_or_create(partner_id)
        if partner.married_to:
            await message.reply_text("💔 That person is already married!")
            return
        await user_repo.marry(uid, partner_id)
        await message.reply_text(
            f"💍 **{message.from_user.first_name}** and "
            f"**{message.reply_to_message.from_user.first_name}** are now married! 🎊"
        )

    # ── /divorce ──────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["divorce"]))
    @ban_check
    @cooldown(30)
    async def cmd_divorce(client: Client, message: Message) -> None:
        uid = message.from_user.id
        user = await user_repo.get(uid)
        if not user or not user.married_to:
            await message.reply_text("❌ You're not married!")
            return
        await user_repo.divorce(uid, user.married_to)
        await message.reply_text(
            f"💔 **{message.from_user.first_name}** filed for divorce. It's official."
        )

    # ── /profile ──────────────────────────────────────────────────────────────
    @app.on_message(filters.command(["profile", "rank"]))
    @ban_check
    @cooldown(10)
    async def cmd_profile(client: Client, message: Message) -> None:
        target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
        if not target:
            return
        user = await user_repo.get_or_create(target.id, target.first_name)
        married_str = ""
        if user.married_to:
            try:
                partner = await client.get_users(user.married_to)
                married_str = f"\n💍 Married to: **{partner.first_name}**"
            except Exception:
                married_str = f"\n💍 Married (id: {user.married_to})"

        xp_needed = user.xp_for_next_level
        bar_filled = int((user.xp % xp_needed) / xp_needed * 10)
        xp_bar = "█" * bar_filled + "░" * (10 - bar_filled)

        await message.reply_text(
            f"👤 **{target.first_name}**{'s' if not target.first_name.endswith('s') else ''} Profile\n\n"
            f"🏆 Level: **{user.level}**\n"
            f"⭐ XP: `{user.xp}` / `{user.level * 100}`\n"
            f"[{xp_bar}]\n"
            f"🪙 Coins: `{user.coins}`\n"
            f"💎 Premium: {'✅' if user.is_premium else '❌'}"
            f"{married_str}"
        )

    # ── /leaderboard ──────────────────────────────────────────────────────────
    @app.on_message(filters.command(["leaderboard", "top", "lb"]))
    @ban_check
    @cooldown(15)
    async def cmd_leaderboard(client: Client, message: Message) -> None:
        leaders = await user_repo.get_leaderboard(10)
        if not leaders:
            await message.reply_text("📊 No data yet!")
            return
        medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        lines = ["**🏆 XP Leaderboard**\n"]
        for i, u in enumerate(leaders):
            lines.append(
                f"{medals[i]} **{u.full_name or f'User {u.user_id}'}** — "
                f"Lv.{u.level} · `{u.xp}` XP"
            )
        await message.reply_text("\n".join(lines))
