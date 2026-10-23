"""«Менеджер»: the club's style shop, fans' merchandise and «Менеджер Pro».

Nothing here makes a club stronger.

- Style (config.manager_cosmetics): emblem shapes and symbols, kit
  patterns, share-card frames, the club colour theme and the stadium
  naming rights. An item is
  free (coins and stars both 0), sold for coins (under the user row lock,
  TransactionType.manager_cosmetic) and/or for Telegram Stars (an invoice
  through my_player_service with the purchase key "manager:<code>").
  Owned items are kept forever in manager_cosmetics. Colours are a free
  pick from PALETTE.
- Merchandise (config.manager_merch): any user buys a scarf / shirt / flag
  of ANOTHER user's club with coins — the coins are burned, the club gets
  euros (up to config.manager_merch_cap_eur a season). Euros never turn
  back into coins, so this is not a way to move coins between accounts.
  One of each item per fan and club (his collection).
- «Менеджер Pro» (Stars, config.manager_pro_days): the scout (biggest
  risers of the transfer market), the gold card frame and a PRO badge.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.enums import NotificationType, TransactionType
from app.models.manager_club import ManagerClub, ManagerCosmetic, ManagerMerch
from app.models.user import User
from app.services import wallet_service
from app.services.game_config_service import get_config
from app.services.notification_service import notify

KINDS = ("shape", "symbol", "rim", "fx", "kit", "frame", "theme", "stadium_name")
PALETTE = (
    "#1f8a4c", "#0f5132", "#c62828", "#8e0000", "#1565c0", "#0d2b6b", "#6a1b9a", "#f9a825",
    "#ef6c00", "#212121", "#f5f5f5", "#00838f", "#ad1457", "#4e342e", "#9e9e9e", "#c6e63a",
)
DEFAULT_LOOK = {
    "shape": "shield", "symbol": "⚽", "color": "#1f8a4c", "color2": "#f5f5f5",
    "kit": "plain", "kit_color": "#1f8a4c", "kit_color2": "#f5f5f5", "frame": "classic", "theme": "night", "rim": "none", "fx": "none",
}
PRO_FRAME = "frame_gold"
STADIUM_NAME_MAX = 32


def catalog(config) -> list[dict]:
    out = []
    for raw in config.manager_cosmetics or []:
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS or not raw.get("code"):
            continue
        out.append({
            "code": str(raw["code"])[:32], "kind": raw["kind"], "name": str(raw.get("name") or raw["code"])[:40],
            "value": str(raw.get("value") or "")[:32],
            "coins": max(0, int(raw.get("coins") or 0)), "stars": max(0, int(raw.get("stars") or 0)),
        })
    return out


def merch_items(config) -> list[dict]:
    out = []
    for raw in config.manager_merch or []:
        if not isinstance(raw, dict) or not raw.get("code"):
            continue
        out.append({"code": str(raw["code"])[:32], "name": str(raw.get("name") or raw["code"])[:40],
                    "emoji": str(raw.get("emoji") or "🧣")[:4],
                    "coins": max(0, int(raw.get("coins") or 0)), "eur": max(0, int(raw.get("eur") or 0))})
    return out


def _item(config, code: str) -> dict:
    item = next((i for i in catalog(config) if i["code"] == code), None)
    if item is None:
        raise NotFoundError("Такого предмета нет")
    return item


def _free(item: dict) -> bool:
    return item["coins"] == 0 and item["stars"] == 0


def is_pro(club: Optional[ManagerClub], now: Optional[datetime] = None) -> bool:
    return bool(club and club.pro_until and ensure_aware(club.pro_until) > (now or datetime.now(timezone.utc)))


async def owned(db: AsyncSession, club_id: int) -> set[str]:
    return set((await db.execute(select(ManagerCosmetic.code).where(ManagerCosmetic.club_id == club_id))).scalars().all())


def _usable(item: dict, have: set[str], pro: bool) -> bool:
    return _free(item) or item["code"] in have or (pro and item["code"] == PRO_FRAME)


def resolve_look(club: ManagerClub) -> dict:
    return {**DEFAULT_LOOK, **{k: v for k, v in (club.look or {}).items() if k in DEFAULT_LOOK}}


async def _owned_club(db: AsyncSession, user_id: int, lock: bool = False) -> ManagerClub:
    stmt = select(ManagerClub).where(ManagerClub.owner_id == user_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    club = (await db.execute(stmt)).scalar_one_or_none()
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    return club


async def club_style(db: AsyncSession, club: ManagerClub, config, now: Optional[datetime] = None) -> dict:
    from app.services.manager_service import season_key

    now = now or datetime.now(timezone.utc)
    merch_count = (await db.execute(select(func.count(ManagerMerch.id)).where(ManagerMerch.club_id == club.id))).scalar_one()
    return {
        "look": resolve_look(club), "owned_cosmetics": sorted(await owned(db, club.id)),
        "stadium_name": club.stadium_name, "pro": is_pro(club, now),
        "pro_until": club.pro_until.isoformat() if club.pro_until else None,
        "merch": {"sold": merch_count, "eur_season": club.merch_eur if club.merch_season == season_key(now) else 0,
                  "cap_eur": config.manager_merch_cap_eur},
    }


async def shop_out(db: AsyncSession, user: User, club: Optional[ManagerClub], config) -> dict:
    have = await owned(db, club.id) if club else set()
    pro = is_pro(club)
    mine = (await db.execute(
        select(ManagerMerch, ManagerClub.name).join(ManagerClub, ManagerClub.id == ManagerMerch.club_id)
        .where(ManagerMerch.user_id == user.id).order_by(ManagerMerch.id.desc()).limit(50)
    )).all()
    items = {i["code"]: i for i in merch_items(config)}
    return {
        "cosmetics": [{**i, "owned": i["code"] in have, "usable": _usable(i, have, pro)} for i in catalog(config)],
        "palette": list(PALETTE),
        "merch_items": list(items.values()),
        "my_merch": [{"club_name": name, "code": m.code, "emoji": items.get(m.code, {}).get("emoji", "🧣"),
                      "name": items.get(m.code, {}).get("name", m.code)} for m, name in mine],
        "pro_stars": config.manager_pro_stars, "pro_days": config.manager_pro_days,
    }


# --- style ---------------------------------------------------------------------------------

async def buy_cosmetic(db: AsyncSession, user: User, code: str) -> dict:
    from app.services.manager_service import get_view

    config = await get_config(db)
    item = _item(config, code)
    if item["coins"] <= 0:
        raise ConflictError("Этот предмет продаётся только за звёзды" if item["stars"] else "Он и так бесплатный")
    club = await _owned_club(db, user.id, lock=True)
    if code in await owned(db, club.id):
        raise ConflictError("Уже куплено")
    locked = await wallet_service.lock_user_for_update(db, user.id)
    await wallet_service.debit_coins(
        db, locked, item["coins"], TransactionType.manager_cosmetic, f"Стиль клуба: {item['name']}",
        related_object_type="manager_club", related_object_id=club.id,
    )
    db.add(ManagerCosmetic(club_id=club.id, code=code))
    await db.commit()
    return await get_view(db, user)


async def set_look(db: AsyncSession, user: User, look: dict) -> dict:
    from app.services.manager_service import get_view

    config = await get_config(db)
    club = await _owned_club(db, user.id, lock=True)
    have = await owned(db, club.id)
    pro = is_pro(club)
    current = resolve_look(club)
    by_kind_value = {(i["kind"], i["value"]): i for i in catalog(config)}
    for field, kind in (("shape", "shape"), ("symbol", "symbol"), ("rim", "rim"), ("fx", "fx"), ("kit", "kit"), ("frame", "frame"), ("theme", "theme")):
        if field not in look:
            continue
        item = by_kind_value.get((kind, str(look[field])))
        if item is None or not _usable(item, have, pro):
            raise ConflictError("Этот элемент ещё не куплен")
        current[field] = item["value"]
    for field in ("color", "color2", "kit_color", "kit_color2"):
        if field in look:
            if look[field] not in PALETTE:
                raise ConflictError("Такого цвета нет в палитре")
            current[field] = look[field]
    club.look = current
    await db.commit()
    return await get_view(db, user)


async def set_stadium_name(db: AsyncSession, user: User, name: Optional[str]) -> dict:
    from app.services.manager_service import get_view

    club = await _owned_club(db, user.id, lock=True)
    if "stadium_name" not in await owned(db, club.id):
        raise ForbiddenError("Сначала купи права на имя стадиона")
    name = " ".join((name or "").split())
    if name and not 3 <= len(name) <= STADIUM_NAME_MAX:
        raise ConflictError(f"Имя стадиона — от 3 до {STADIUM_NAME_MAX} символов")
    club.stadium_name = name or None
    await db.commit()
    return await get_view(db, user)


# --- merchandise -------------------------------------------------------------------------------

async def buy_merch(db: AsyncSession, user: User, club_id: int, code: str) -> dict:
    """A fan buys an item of another user's club: coins burned, euros to
    that club (up to the season cap)."""
    from app.services.manager_service import money, season_key

    config = await get_config(db)
    item = next((i for i in merch_items(config) if i["code"] == code), None)
    if item is None:
        raise NotFoundError("Такого мерча нет")
    club = (await db.execute(
        select(ManagerClub).where(ManagerClub.id == club_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if club is None:
        raise NotFoundError("Клуб не найден")
    if club.owner_id == user.id:
        raise ConflictError("Свой мерч покупать нельзя — его покупают болельщики")
    locked = await wallet_service.lock_user_for_update(db, user.id)
    key = season_key(datetime.now(timezone.utc))
    if club.merch_season != key:
        club.merch_season = key
        club.merch_eur = 0
    eur = max(0, min(item["eur"], config.manager_merch_cap_eur - club.merch_eur))
    try:
        async with db.begin_nested():
            db.add(ManagerMerch(user_id=user.id, club_id=club.id, code=code, coins=item["coins"], eur=eur))
    except IntegrityError:
        raise ConflictError("Этот предмет у тебя уже есть")
    if item["coins"]:
        await wallet_service.debit_coins(
            db, locked, item["coins"], TransactionType.manager_merch, f"Мерч «{club.name}»: {item['name']}",
            related_object_type="manager_club", related_object_id=club.id,
        )
    club.budget += eur
    club.merch_eur += eur
    await notify(
        db, club.owner_id, NotificationType.manager_event, f"Болельщик купил {item['name'].lower()} {item['emoji']}",
        f"{user.first_name or 'Болельщик'} теперь фанат «{club.name}»" + (f" · +{money(eur)} в бюджет" if eur else ""),
        related_object_type="manager_club", related_object_id=club.id,
    )
    await db.commit()
    return await club_card(db, user, club.id)


async def club_card(db: AsyncSession, user: User, club_id: int) -> dict:
    """A club's public card (from the league table): style, division,
    trophies, fans and what the viewer already bought."""
    from app.services.manager_service import _name, division_name, squad_view

    config = await get_config(db)
    club = await db.get(ManagerClub, club_id)
    if club is None:
        raise NotFoundError("Клуб не найден")
    owner = await db.get(User, club.owner_id)
    squad = await squad_view(db, club, config)
    fans = (await db.execute(select(func.count(func.distinct(ManagerMerch.user_id))).where(ManagerMerch.club_id == club.id))).scalar_one()
    bought = set((await db.execute(
        select(ManagerMerch.code).where(ManagerMerch.club_id == club.id, ManagerMerch.user_id == user.id)
    )).scalars().all())
    return {
        "id": club.id, "name": club.name, "owner_name": _name(owner), "division": club.division,
        "division_name": division_name(club.division), "titles": club.titles, "seasons_played": club.seasons_played,
        "look": resolve_look(club), "stadium_name": club.stadium_name, "pro": is_pro(club),
        "rating": squad["rating"], "fans": fans, "is_mine": club.owner_id == user.id,
        "xi": [{k: p[k] for k in ("slot", "kind", "name", "position", "rating")} for p in squad["xi"]],
        "merch": [{**i, "bought": i["code"] in bought} for i in merch_items(config)],
    }


async def popular(db: AsyncSession, limit: int = 20) -> dict:
    rows = (await db.execute(
        select(ManagerClub, func.count(func.distinct(ManagerMerch.user_id)).label("fans"))
        .join(ManagerMerch, ManagerMerch.club_id == ManagerClub.id)
        .group_by(ManagerClub.id).order_by(func.count(func.distinct(ManagerMerch.user_id)).desc(), ManagerClub.id).limit(limit)
    )).all()
    return {"clubs": [{"id": c.id, "name": c.name, "division": c.division, "fans": fans, "look": resolve_look(c)} for c, fans in rows]}


# --- «Менеджер Pro» and the scout ------------------------------------------------------------------

async def scout(db: AsyncSession, user: User) -> dict:
    """Pro: the market's biggest value risers since the last season start."""
    from app.services.manager_service import market

    club = await _owned_club(db, user.id)
    if not is_pro(club):
        raise ForbiddenError("Скаут доступен с «Менеджер Pro»")
    players = [p for p in (await market(db, user))["players"] if p.get("trend_pct") is not None]
    players.sort(key=lambda p: (-(p["trend_pct"] or 0), -p["value"]))
    return {"players": players[:15]}


# --- Telegram Stars (through my_player_service's invoice flow, key "manager:<code>") ---------------

async def stars_order(db: AsyncSession, user_id: int, code: str, config) -> tuple[str, str, str, int]:
    club = await _owned_club(db, user_id)
    if code == "pro":
        if config.manager_pro_stars <= 0:
            raise ConflictError("«Менеджер Pro» сейчас не продаётся")
        return "manager:pro", "Менеджер Pro", f"Скаут, золотая рамка и значок PRO на {config.manager_pro_days} дней", config.manager_pro_stars
    item = _item(config, code)
    if item["stars"] <= 0:
        raise ConflictError("Этот предмет за звёзды не продаётся")
    if code in await owned(db, club.id):
        raise ConflictError("Уже куплено")
    return f"manager:{code}", item["name"], f"Стиль клуба «{club.name}»: {item['name']}", item["stars"]


async def validate_stars(db: AsyncSession, invoice, config) -> tuple[bool, str]:
    code = invoice.my_player_purchase.split(":", 1)[1]
    club = (await db.execute(select(ManagerClub).where(ManagerClub.owner_id == invoice.user_id))).scalar_one_or_none()
    if club is None:
        return False, "Клуб не найден"
    if code == "pro":
        return (config.manager_pro_stars == invoice.stars_amount, "Цена изменилась — открой покупку заново")
    item = next((i for i in catalog(config) if i["code"] == code), None)
    if item is None or item["stars"] != invoice.stars_amount:
        return False, "Этот предмет больше не продаётся"
    if code in await owned(db, club.id):
        return False, "Уже куплено"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, invoice, config) -> dict:
    """Paid already — never refuses (the caller holds the invoice lock and commits)."""
    code = invoice.my_player_purchase.split(":", 1)[1]
    club = (await db.execute(
        select(ManagerClub).where(ManagerClub.owner_id == user.id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if club is None:
        return {"kind": "manager", "name": "Клуб не найден"}
    if code == "pro":
        now = datetime.now(timezone.utc)
        start = max(now, ensure_aware(club.pro_until)) if club.pro_until else now
        club.pro_until = start + timedelta(days=config.manager_pro_days)
        return {"kind": "manager_pro", "name": "Менеджер Pro"}
    if code not in await owned(db, club.id):
        db.add(ManagerCosmetic(club_id=club.id, code=code))
    item = next((i for i in catalog(config) if i["code"] == code), {"name": code})
    return {"kind": "manager_cosmetic", "name": item["name"]}
