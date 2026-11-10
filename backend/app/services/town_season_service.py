"""«Сезонный город»: limited decorations of the season, sold for Telegram
Stars only while their season lasts (the local calendar month) — style and
nothing else: no coins, no rent, no bonus.

Each copy carries a serial number per item («№ 37»); with
town_social.season_item_supply > 0 an item is sold out after that many.
Like the rename, availability is checked at pre-checkout (validate_invoice)
and delivery never refuses a taken payment: a second copy of an item the
player already holds is recorded in the ledger and nothing else happens.
Price: town_social.season_item_stars (0 = not sold).
"""
import secrets
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import local_today
from app.models.town import TownLedger, UserTown, UserTownSeasonItem
from app.models.user import User
from app.services import town_service
from app.services.game_config_service import get_config
from app.services.town_social_service import social_config

PREFIX = "town:season:"

SEASONS: dict[str, str] = {"winter": "Зима", "spring": "Весна", "summer": "Лето", "autumn": "Осень"}
_MONTH_SEASON = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
                 6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}

# code -> (name, emoji, season)
ITEMS: dict[str, tuple[str, str, str]] = {
    "tree": ("Новогодняя ёлка на площади", "🎄", "winter"),
    "snowman": ("Снеговик в шарфе клуба", "⛄", "winter"),
    "garland": ("Гирлянды над улицами", "✨", "winter"),
    "blossom": ("Цветущая сакура", "🌸", "spring"),
    "kites": ("Воздушные змеи над пляжем", "🪁", "spring"),
    "fireworks": ("Летний фейерверк", "🎆", "summer"),
    "icecream": ("Фургон с мороженым", "🍦", "summer"),
    "pumpkins": ("Тыквы у домов", "🎃", "autumn"),
    "leaves": ("Золотая аллея", "🍂", "autumn"),
}


def season_of(month: int) -> str:
    return _MONTH_SEASON[month]


def current_season() -> str:
    return season_of(local_today().month)


def _price(config) -> int:
    return max(0, social_config(config)["season_item_stars"])


async def _sold(db: AsyncSession, code: str) -> int:
    return int((await db.execute(
        select(func.count(UserTownSeasonItem.id)).where(UserTownSeasonItem.code == code)
    )).scalar_one())


async def owned_items(db: AsyncSession, user_id: int) -> list[dict]:
    """The player's decorations, for his map and his guests'."""
    rows = (await db.execute(
        select(UserTownSeasonItem).where(UserTownSeasonItem.user_id == user_id).order_by(UserTownSeasonItem.id)
    )).scalars().all()
    return [{"code": r.code, "name": ITEMS[r.code][0], "emoji": ITEMS[r.code][1], "serial": r.serial}
            for r in rows if r.code in ITEMS]


async def shop(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    town_service._require_enabled(config)
    s = social_config(config)
    season = current_season()
    mine = {r["code"]: r for r in await owned_items(db, user.id)}
    supply = max(0, s["season_item_supply"])
    items = []
    for code, (name, emoji, item_season) in ITEMS.items():
        if item_season != season and code not in mine:
            continue
        sold = await _sold(db, code)
        items.append({
            "code": code, "name": name, "emoji": emoji, "season": item_season,
            "on_sale": item_season == season and _price(config) > 0 and (supply == 0 or sold < supply),
            "owned": code in mine, "serial": mine[code]["serial"] if code in mine else None,
            "sold": sold, "supply": supply,
        })
    return {"season": season, "season_name": SEASONS[season], "stars": _price(config), "items": items}


async def create_invoice(db: AsyncSession, user: User, code: str) -> dict:
    from app.models.pack import StarsInvoice
    from app.services.stars_payment_service import _request_telegram_invoice_link

    config = await get_config(db)
    town_service._require_enabled(config)
    if code not in ITEMS:
        raise NotFoundError("Такого украшения нет")
    ok, reason = await _available(db, config, user.id, code)
    if not ok:
        raise ConflictError(reason)
    stars = _price(config)
    token = secrets.token_urlsafe(16)
    db.add(StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, academy_speedup=PREFIX + code))
    await db.flush()
    name, emoji, _ = ITEMS[code]
    link = await _request_telegram_invoice_link(token, f"{emoji} {name}", "Сезонное украшение города", stars)
    await db.commit()
    return {"invoice_link": link, "payload_token": token, "stars_amount": stars}


async def _available(db: AsyncSession, config, user_id: int, code: str) -> tuple[bool, str]:
    name, _, item_season = ITEMS[code]
    if not town_service.is_unlocked(config, await db.get(UserTown, user_id)):
        return False, "Сначала открой город"
    if _price(config) <= 0:
        return False, "Сезонные украшения сейчас не продаются"
    if item_season != current_season():
        return False, f"«{name}» продаётся только в свой сезон"
    held = (await db.execute(select(UserTownSeasonItem.id).where(
        UserTownSeasonItem.user_id == user_id, UserTownSeasonItem.code == code,
    ))).scalar_one_or_none()
    if held is not None:
        return False, "Это украшение у тебя уже есть"
    supply = max(0, social_config(config)["season_item_supply"])
    if supply and await _sold(db, code) >= supply:
        return False, "Все копии этого украшения уже разобраны"
    return True, ""


async def validate_invoice(db: AsyncSession, invoice) -> tuple[bool, str]:
    """pre_checkout_query: still on sale at the frozen price."""
    config = await get_config(db)
    if not config.town_enabled:
        return False, "Город сейчас закрыт"
    code = invoice.academy_speedup[len(PREFIX):]
    if code not in ITEMS:
        return False, "Unknown order"
    if _price(config) != invoice.stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    return await _available(db, config, invoice.user_id, code)


async def deliver_invoice(db: AsyncSession, user: User, invoice) -> dict:
    """Under the invoice row lock (stars_payment_service.deliver_payment);
    never refuses, the caller commits."""
    code = invoice.academy_speedup[len(PREFIX):]
    serial: Optional[int] = None
    held = (await db.execute(select(UserTownSeasonItem).where(
        UserTownSeasonItem.user_id == user.id, UserTownSeasonItem.code == code,
    ))).scalar_one_or_none()
    if held is not None:
        serial = held.serial
    elif code in ITEMS:
        for _ in range(5):  # two buyers taking the same serial: the unique index decides, retry with the next
            top = (await db.execute(
                select(func.max(UserTownSeasonItem.serial)).where(UserTownSeasonItem.code == code)
            )).scalar_one()
            try:
                async with db.begin_nested():
                    db.add(UserTownSeasonItem(user_id=user.id, code=code, serial=int(top or 0) + 1))
                serial = int(top or 0) + 1
                break
            except IntegrityError:
                continue
    db.add(TownLedger(user_id=user.id, kind="season_item", result={"code": code, "serial": serial,
                                                                    "repeat": held is not None},
                      idempotency_key=f"stars-{invoice.payload_token}"))
    await db.flush()
    return {"kind": "town_season", "code": code, "serial": serial}
