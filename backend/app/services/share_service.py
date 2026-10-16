"""«Поделиться в Telegram»: a player shares one of their own moments — a
legendary/diamond card they own, an Arena match they won, a trophy they
hold — as an image with a «Играть» button carrying their referral link.

Ownership is checked here; the image is rendered on the server
(share_card_service) from the player's own data, never uploaded by the
client. With a real bot and a public HTTPS app URL the image goes out as a
Telegram prepared inline message (Bot API savePreparedInlineMessage →
WebApp.shareMessage); otherwise — dev, old clients — the client falls back
to t.me/share/url with the same caption and link. Referral rewards are
unchanged: still granted only on the invitee's first genuine paid pack.
"""
import hashlib
import logging
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import UserCard
from app.models.enums import MatchResult, Rarity
from app.models.match import Match
from app.models.trophy import UserTrophy
from app.models.user import User
from app.services import share_card_service
from app.services.image_service import STATIC_DIR
from app.services.player_stats_service import card_rating_bonus

logger = logging.getLogger(__name__)
settings = get_settings()

SHARE_DIR = STATIC_DIR / "share"
SHAREABLE_RARITIES = {Rarity.legendary, Rarity.diamond}
KINDS = ("card", "match", "trophy")


def referral_link(user: User) -> str:
    return f"https://t.me/{settings.telegram_bot_username}?start=ref_{user.telegram_id}"


def _static_path(relative: Optional[str]) -> Optional[Path]:
    if not relative:
        return None
    full = (STATIC_DIR / relative).resolve()
    return full if STATIC_DIR.resolve() in full.parents and full.is_file() else None


def _store(image: bytes, kind: str, object_id: int, fingerprint: str) -> str:
    """Write once per distinct content; returns the path under /static."""
    digest = hashlib.sha1(fingerprint.encode()).hexdigest()[:12]
    name = f"{kind}_{object_id}_{digest}.jpg"
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    target = SHARE_DIR / name
    if not target.exists():
        target.write_bytes(image)
    return f"share/{name}"


async def _card(db: AsyncSession, user: User, card_id: int) -> tuple[str, str]:
    card = (await db.execute(
        select(UserCard).where(UserCard.id == card_id).options(selectinload(UserCard.player))
    )).scalar_one_or_none()
    if card is None or card.owner_id != user.id:
        raise NotFoundError("Карточка не найдена")
    player = card.player
    if player.rarity not in SHAREABLE_RARITIES:
        raise ConflictError("Поделиться можно легендарной или бриллиантовой карточкой")
    rating = min(99, player.rating + card_rating_bonus(card))
    rarity = player.rarity.value
    position = getattr(player.position, "value", str(player.position))
    image = share_card_service.render_card(
        name=player.display_name, rating=rating, position=position, rarity=rarity,
        image=_static_path(player.image_path), bot_username=settings.telegram_bot_username,
    )
    path = _store(image, "card", card.id, f"{player.display_name}|{rating}|{rarity}|{player.image_path}")
    label = "бриллиант" if rarity == "diamond" else "легенда"
    return path, f"Мне выпала {label}: {player.display_name}, рейтинг {rating}! ⚽ Собирай карточки в Victor FC"


async def _match(db: AsyncSession, user: User, match_id: int) -> tuple[str, str]:
    match = await db.get(Match, match_id)
    if match is None or match.user_id != user.id:
        raise NotFoundError("Матч не найден")
    if match.result != MatchResult.win:
        raise ConflictError("Поделиться можно только победой")
    name = user.full_display_name()
    image = share_card_service.render_match_win(
        user_score=match.user_score, opponent_score=match.opponent_score, player_name=name,
        bot_username=settings.telegram_bot_username,
    )
    path = _store(image, "match", match.id, f"{match.user_score}:{match.opponent_score}|{name}")
    return path, f"Победа {match.user_score}:{match.opponent_score} в Card Arena! ⚽ Сыграй против меня в Victor FC"


async def _trophy(db: AsyncSession, user: User, trophy_id: int) -> tuple[str, str]:
    trophy = (await db.execute(
        select(UserTrophy).where(UserTrophy.id == trophy_id)
    )).scalar_one_or_none()
    if trophy is None or trophy.user_id != user.id:
        raise NotFoundError("Трофей не найден")
    d = trophy.trophy
    image = share_card_service.render_trophy(
        name=d.name, description=d.description or "", image=_static_path(d.image_path),
        bot_username=settings.telegram_bot_username,
    )
    path = _store(image, "trophy", trophy.id, f"{d.name}|{d.description}|{d.image_path}")
    return path, f"Новый трофей: «{d.name}»! 🏆 Собирай карточки в Victor FC"


def _can_prepare_messages() -> bool:
    """Telegram must be able to download the photo (public HTTPS) and the
    bot must be real — neither holds in local dev."""
    return settings.mini_app_url.startswith("https://") and settings.telegram_bot_token not in ("", "0:DEV")


async def _save_prepared_message(user: User, photo_url: str, caption: str, link: str) -> Optional[str]:
    """Bot API savePreparedInlineMessage; None on any failure (the client
    then falls back to a plain share link). Split out for tests."""
    body = {
        "user_id": user.telegram_id,
        "result": {
            "type": "photo",
            "id": uuid.uuid4().hex,
            "photo_url": photo_url,
            "thumbnail_url": photo_url,
            "caption": f"{caption}\n{link}",
            "reply_markup": {"inline_keyboard": [[{"text": "⚽ Играть в Victor FC", "url": link}]]},
        },
        "allow_user_chats": True,
        "allow_group_chats": True,
        "allow_channel_chats": True,
    }
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/savePreparedInlineMessage"
    try:
        async with httpx.AsyncClient(timeout=10, proxy=settings.telegram_proxy_url or None) as client:
            data = (await client.post(url, json=body)).json()
    except (httpx.HTTPError, ValueError):
        logger.warning("savePreparedInlineMessage request failed", exc_info=True)
        return None
    if not data.get("ok"):
        logger.warning("savePreparedInlineMessage rejected: %s", data.get("description"))
        return None
    return data["result"]["id"]


async def prepare_share(db: AsyncSession, user: User, kind: str, object_id: int) -> dict:
    if kind == "card":
        path, caption = await _card(db, user, object_id)
    elif kind == "match":
        path, caption = await _match(db, user, object_id)
    elif kind == "trophy":
        path, caption = await _trophy(db, user, object_id)
    else:
        raise NotFoundError("Нечем поделиться")

    link = referral_link(user)
    image_url = f"/static/{path}"
    prepared_id = None
    if _can_prepare_messages():
        prepared_id = await _save_prepared_message(user, f"{settings.mini_app_url.rstrip('/')}{image_url}", caption, link)
    return {
        "prepared_message_id": prepared_id,
        "image_url": image_url,
        "caption": caption,
        "link": link,
        "share_url": f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(caption, safe='')}",
    }
