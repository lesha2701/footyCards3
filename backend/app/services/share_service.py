"""«Поделиться в Telegram»: a player shares one of their own moments — a
legendary/diamond card they own, an Arena match they won, a trophy they
hold, their «Мой игрок» card — as an image with a «Играть» button carrying
their referral link.

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
KINDS = ("card", "match", "trophy", "my_player", "trade_wishes")


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


async def _my_player(db: AsyncSession, user: User) -> tuple[str, str]:
    from app.services import my_player_service
    from app.services.game_config_service import get_config

    config = await get_config(db)
    mp = await my_player_service.get_my_player(db, user.id) if config.my_player_enabled else None
    if mp is None:
        raise NotFoundError("Сначала создай своего игрока")
    out = my_player_service.player_out(mp, config)
    level = my_player_service.level_info(user.my_player_xp or 0, config)[0]
    image = share_card_service.render_my_player(
        name=out["name"], number=out["number"], position=out["position"], rating=out["rating"],
        attack=out["attack_rating"], defense=out["defense_rating"], level=level,
        tier=out["tier"], tier_label=out["tier_label"], appearance=out["appearance"],
        bot_username=settings.telegram_bot_username,
    )
    fingerprint = f"{out['name']}|{out['number']}|{out['position']}|{out['rating']}|{out['attributes']}|{level}|{out['tier']}|{sorted(out['appearance'].items())}"
    path = _store(image, "my_player", mp.id, fingerprint)
    return path, f"Мой игрок {out['name']}: рейтинг {out['rating']}, {out['tier_label'].lower()}! ⚽ Создай своего в Victor FC"


def trade_link(user: User) -> str:
    """Opens the bot, which answers with «Предложить обмен» → /trades/new?to=<id>."""
    return f"https://t.me/{settings.telegram_bot_username}?start=trade_{user.id}"


async def _trade_wishes(db: AsyncSession, user: User) -> str:
    """«Ищу / Отдаю» from the «Поиск обменов» lists, as plain text."""
    from app.services import trade_finder_service
    from app.services.game_config_service import get_config

    wishes = await trade_finder_service.list_wishes(db, user, await get_config(db))
    if not wishes["wants"] and not wishes["gives"]:
        raise ConflictError("Сначала добавь карточки в «Ищу» или «Отдаю»")

    def names(players) -> str:
        shown = ", ".join(f"{p.display_name} ({p.rating})" for p in players[:8])
        return shown + (f" и ещё {len(players) - 8}" if len(players) > 8 else "")

    lines = ["🔄 Ищу обмен в Victor FC"]
    if wishes["wants"]:
        lines.append(f"🔎 Ищу: {names(wishes['wants'])}")
    if wishes["gives"]:
        lines.append(f"🎁 Отдаю: {names(wishes['gives'])}")
    lines.append("Жми «Предложить обмен» — откроется обмен со мной 👇")
    return "\n".join(lines)


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


async def _save_prepared_text(user: User, text: str, link: str) -> Optional[str]:
    """Text-only prepared message with a «Предложить обмен» button; None on failure."""
    body = {
        "user_id": user.telegram_id,
        "result": {
            "type": "article",
            "id": uuid.uuid4().hex,
            "title": "Ищу обмен",
            "input_message_content": {"message_text": text},
            "reply_markup": {"inline_keyboard": [[{"text": "🔄 Предложить обмен", "url": link}]]},
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
    if kind == "trade_wishes":
        text = await _trade_wishes(db, user)
        link = trade_link(user)
        prepared_id = await _save_prepared_text(user, text, link) if _can_prepare_messages() else None
        return {
            "prepared_message_id": prepared_id,
            "image_url": None,
            "caption": text,
            "link": link,
            "share_url": f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text, safe='')}",
        }
    if kind == "card":
        path, caption = await _card(db, user, object_id)
    elif kind == "match":
        path, caption = await _match(db, user, object_id)
    elif kind == "trophy":
        path, caption = await _trophy(db, user, object_id)
    elif kind == "my_player":
        path, caption = await _my_player(db, user)
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
