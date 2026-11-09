"""«Город»: the player's own town by the sea, next to the «Клубная база».

Five districts of twelve houses each (the drawn pictures and tap zones live
in frontend/src/lib/town.ts — the codes here must match). A house is bought
once for coins and kept forever; it pays its district's rent every day.

Numbers are GameConfig (never hardcoded): town_districts {district: {price,
rent}}, town_price_growth_pct — every house already owned anywhere in the
town makes the next one that much dearer (so the first houses are cheap and
a whole town is a long goal), town_income_max_hours — unclaimed rent stops
growing after that, so the town wants a visit a day.

Rent is settled like the base's finance department: `income_accrued` up to
`income_since`, settled at the old rate before every purchase, the unpaid
fraction of a coin stays in the clock. Coins move under the user row lock;
every operation is journaled in town_ledger with a unique (user_id,
idempotency_key), and a house is unique per (user, district, building).

The town opens once for town_unlock_coins coins (0 = open to everyone) and
can be renamed for Telegram Stars (town_rename_stars): a StarsInvoice with
academy_speedup = "town:rename" (the same column the base's Stars purchases
use); the ordered name waits in a town_ledger row "rename_order" keyed by
the invoice, so two invoices never mix names.

The «Отель» is bought once for town_hotel_price coins; it pays
town_hotel_rent_per_100_cards a day for every 100 cards the player holds
now (up to town_hotel_max_cards) — selling cards lowers it.

«Жители города» are cards of their own (TownResident, drawn by the admin
like «Музы»), dropped by packs with resident_drop_chance (the «Жители»
packs: 1.0) and sold one by one in the shop (CardOffer.resident_id). Every
copy held is one inhabitant paying town_resident_rent coins a day; a spare
copy sells for town_resident_spare_coins[rarity]. A resident with a bonus
(meant for the rare legendary ones) adds it once, whatever the copies:
  * rent_pct    — +N% to the houses' rent;
  * hotel_pct   — +N% to the hotel's rent;
  * daily_coins — +N coins a day to the town's rent.
Per kind the bonuses add up, capped by town_resident_bonus_max_pct and
town_resident_max_daily_coins. Residents count only in an opened town.

Closed places on the map (DECOR: a pier, a park with a fountain, the
legend's island) stay dimmed until bought once for coins
(GameConfig.town_decor {code: {price, rent_pct}}); a bought place lights
up on the map and adds its rent_pct % to the houses' rent. It is kept as
a user_town_houses row of the pseudo-district "decor", so the same
unique key guards it; it never counts as a house.
"""
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card import UserCard
from app.models.enums import Rarity, TransactionType
from app.models.game_config import DEFAULT_TOWN_DECOR, DEFAULT_TOWN_DISTRICTS, DEFAULT_TOWN_RESIDENT_SPARE_COINS
from app.models.town import TownLedger, TownResident, UserTown, UserTownHouse, UserTownResident
from app.models.user import User
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

DISTRICT_NAMES: dict[str, str] = {
    "center": "Центр",
    "favela": "Фавелы",
    "beach": "Пляж",
    "mountains": "Горы",
    "business": "Бизнес-район",
}

HOUSES: dict[str, dict[str, str]] = {
    "center": {
        "town_hall": "Ратуша", "museum": "Музей футбола", "hotel_tower": "Отель «Башня»", "market": "Крытый рынок",
        "cinema": "Кинотеатр", "barber": "Барбершоп", "sports_bar": "Спорт-бар", "bakery": "Пекарня",
        "bank": "Банк", "boot_shop": "Бутсы", "newspaper": "Редакция газеты", "apartments": "Жилой дом",
    },
    "favela": {
        "church": "Церковь", "community": "Общинный центр", "guesthouse": "Гостевой дом", "boxing": "Боксёрский зал",
        "samba": "Самба-клуб", "barber": "Барбершоп", "bar": "Угловой бар", "street_food": "Уличная еда",
        "studio": "Музыкальная студия", "mural": "Дом с муралом", "shop": "Лавка", "garden": "Дом с садом",
    },
    "beach": {
        "white_villa": "Белая вилла", "pink_villa": "Розовая вилла", "hotel": "Бутик-отель", "penthouse": "Пентхаус",
        "surf": "Серф-школа", "seafood": "Рыбный ресторан", "ice_cream": "Мороженое", "lighthouse": "Маяк",
        "yacht_club": "Яхт-клуб", "beach_bar": "Бар на сваях", "volley": "Пляжная хижина", "coconut": "Кокосы",
    },
    "mountains": {
        "chalet": "Большое шале", "hut": "Горная хижина", "spa": "Спа-отель", "cable_car": "Канатная дорога",
        "observatory": "Обсерватория", "glass_villa": "Стеклянная вилла", "guesthouse": "Каменный дом",
        "cabin": "Бревенчатый домик", "dairy": "Сыроварня", "farm": "Ферма", "restaurant": "Ресторан у озера",
        "fishing": "Рыбацкий дом",
    },
    "business": {
        "hotel": "Гранд-отель", "twist": "Витая башня", "tv_tower": "Телебашня", "sky_office": "Офис с садом",
        "tower": "Офисная башня", "bank_tower": "Банк", "law": "Юристы", "sponsors": "Офис спонсоров",
        "agents": "Футбольные агенты", "exchange": "Биржа", "cars": "Автосалон", "congress": "Конгресс-центр",
    },
}

# Closed places on the town map (frontend lib/town.ts DECOR_ZONES — the codes must match).
DECOR_DISTRICT = "decor"
DECOR: dict[str, str] = {"pier": "Пирс с колесом обозрения", "park": "Парк с фонтаном", "island": "Остров легенды"}

RARITIES = ("common", "rare", "epic", "legendary")
_RARITY_ORDER = {r: i for i, r in enumerate(RARITIES)}
# code -> label ("{v}" = the value); "none" = no bonus, only the daily coin(s).
RESIDENT_BONUSES: dict[str, str] = {
    "none": "",
    "rent_pct": "+{v}% к ренте домов",
    "hotel_pct": "+{v}% к доходу отеля",
    "daily_coins": "+{v} монет в день",
    # Outside the town: «Мой игрок» XP (my_player_service.xp_bonus_pct), the
    # daily rewarded attempts of every mini-game (club_pass_service.
    # extra_rewarded_attempts) and the build time of «Клубная база» and the
    # «Академия» (club_base_service / academy_service start_upgrade).
    "xp_pct": "+{v}% к опыту игрока",
    "game_attempts": "+{v} к попыткам игр",
    "build_pct": "−{v}% времени стройки",
}
_PCT_BONUSES = ("rent_pct", "hotel_pct", "xp_pct", "build_pct")
_NO_EFFECTS = {"population": 0, "rent": 0, **{k: 0 for k in RESIDENT_BONUSES if k != "none"}}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- config --------------------------------------------------------------------------------------

def districts_config(config) -> dict[str, dict[str, int]]:
    """{district: {"price", "rent"}} — the admin values over the defaults."""
    raw = config.town_districts or {}
    out = {}
    for code, default in DEFAULT_TOWN_DISTRICTS.items():
        values = {**default, **(raw.get(code) or {})}
        out[code] = {"price": max(0, int(values["price"])), "rent": max(0, int(values["rent"]))}
    return out


def validate_districts(raw: dict) -> dict:
    """Admin input for GameConfig.town_districts: known districts only,
    non-negative integer price and rent."""
    out: dict = {}
    for code, values in (raw or {}).items():
        if code not in DISTRICT_NAMES:
            raise ValueError(f"неизвестный район «{code}»")
        if not isinstance(values, dict):
            raise ValueError(f"{code}: ожидаются цена и рента")
        row = {}
        for key in ("price", "rent"):
            value = values.get(key, DEFAULT_TOWN_DISTRICTS[code][key])
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{code}.{key}: нужно целое число ≥ 0")
            row[key] = value
        out[code] = row
    return out


def decor_config(config) -> dict[str, dict[str, int]]:
    """{place: {"price", "rent_pct"}} — the admin values over the defaults."""
    raw = getattr(config, "town_decor", None) or {}
    out = {}
    for code, default in DEFAULT_TOWN_DECOR.items():
        values = {**default, **(raw.get(code) or {})}
        out[code] = {"price": max(0, int(values["price"])), "rent_pct": max(0, int(values["rent_pct"]))}
    return out


def validate_decor(raw: dict) -> dict:
    """Admin input for GameConfig.town_decor: known places, integers ≥ 0."""
    out: dict = {}
    for code, values in (raw or {}).items():
        if code not in DECOR:
            raise ValueError(f"неизвестное место «{code}»")
        if not isinstance(values, dict):
            raise ValueError(f"{code}: ожидаются цена и %")
        row = {}
        for key in ("price", "rent_pct"):
            value = values.get(key, DEFAULT_TOWN_DECOR[code][key])
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{code}.{key}: нужно целое число ≥ 0")
            row[key] = value
        out[code] = row
    return out


def decor_pct(config, owned: set[str]) -> int:
    """+% to the houses' rent from the places bought."""
    places = decor_config(config)
    return sum(places[c]["rent_pct"] for c in owned if c in places)


def validate_spare_coins(raw: dict) -> dict:
    """Admin input for GameConfig.town_resident_spare_coins: {rarity: coins ≥ 0}."""
    out: dict = {}
    for rarity, value in (raw or {}).items():
        if rarity not in RARITIES:
            raise ValueError(f"неизвестная редкость «{rarity}»")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{rarity}: нужно целое число ≥ 0")
        out[rarity] = value
    return out


def house_price(config, district: str, owned_total: int) -> int:
    """The price of the next house in `district` when `owned_total` houses
    are already owned anywhere in the town, rounded to 10 coins."""
    base = districts_config(config)[district]["price"]
    growth = max(0, int(config.town_price_growth_pct))
    return int(round(base * (100 + growth * owned_total) / 100 / 10)) * 10


def rent_rate(config, houses: list[UserTownHouse]) -> int:
    """Coins a day the owned houses pay."""
    rents = districts_config(config)
    return sum(rents[h.district]["rent"] for h in houses if h.district in rents)


def hotel_rent(config, cards: int) -> int:
    """Coins a day the hotel pays for `cards` cards held."""
    counted = min(max(0, cards), max(0, int(config.town_hotel_max_cards)))
    return max(0, int(config.town_hotel_rent_per_100_cards)) * counted // 100


def is_unlocked(config, town: Optional[UserTown]) -> bool:
    return int(config.town_unlock_coins) <= 0 or (town is not None and town.unlocked_at is not None)


def spare_coins(config, rarity: str) -> int:
    values = {**DEFAULT_TOWN_RESIDENT_SPARE_COINS, **(config.town_resident_spare_coins or {})}
    return max(0, int(values.get(rarity, 0) or 0))


def bonus_label(bonus: str, value: int) -> str:
    template = RESIDENT_BONUSES.get(bonus, "")
    return template.format(v=value) if template and value > 0 else ""


async def _card_count(db: AsyncSession, user_id: int) -> int:
    return int((await db.execute(select(func.count(UserCard.id)).where(UserCard.owner_id == user_id))).scalar_one())


async def _owned_residents(db: AsyncSession, user_id: int) -> list[UserTownResident]:
    return list((await db.execute(
        select(UserTownResident).where(UserTownResident.user_id == user_id).order_by(UserTownResident.id)
    )).unique().scalars())


def resident_effects(config, owned: list[UserTownResident]) -> dict:
    """Population and what the residents add to the town's income."""
    live = [r for r in owned if r.resident.is_active and r.copies > 0]
    population = sum(r.copies for r in live)
    sums = {k: 0 for k in RESIDENT_BONUSES if k != "none"}
    for row in live:
        if row.resident.bonus in sums:
            sums[row.resident.bonus] += max(0, int(row.resident.bonus_value))
    pct_cap = max(0, int(config.town_resident_bonus_max_pct))
    return {
        **sums,
        "population": population,
        "rent": population * max(0, int(config.town_resident_rent)),
        **{k: min(sums[k], pct_cap) for k in _PCT_BONUSES},
        # The build time never drops below a tenth.
        "build_pct": min(sums["build_pct"], pct_cap, 90),
        "daily_coins": min(sums["daily_coins"], max(0, int(config.town_resident_max_daily_coins))),
    }


async def user_bonus(db: AsyncSession, user_id: int, kind: str, config=None) -> int:
    """One resident bonus outside the town (xp_pct, game_attempts, build_pct)."""
    config = config or await get_config(db)
    if not config.town_residents_enabled:
        return 0
    return int(resident_effects(config, await _owned_residents(db, user_id)).get(kind, 0))


def build_hours(hours, build_pct: int):
    """A construction time shortened by the residents' build_pct, in whole minutes."""
    if not hours or build_pct <= 0:
        return hours
    return round(hours * 60 * (100 - build_pct) / 100) / 60


async def _income_parts(db: AsyncSession, config, user_id: int, town: Optional[UserTown], houses) -> dict:
    """Coins a day by source: houses (with the residents' and the places' +%),
    hotel, residents (with their bonuses)."""
    effects = resident_effects(config, await _owned_residents(db, user_id)) if config.town_residents_enabled else \
        dict(_NO_EFFECTS)
    cards = await _card_count(db, user_id)
    hotel_owned = town is not None and town.hotel_bought_at is not None
    places = await _decor_owned(db, user_id)
    places_pct = decor_pct(config, places)
    houses_rent = rent_rate(config, houses) * (100 + effects["rent_pct"] + places_pct) // 100
    hotel = hotel_rent(config, cards) * (100 + effects["hotel_pct"]) // 100
    residents = effects["rent"] + effects["daily_coins"]
    return {
        "houses": houses_rent, "hotel": hotel if hotel_owned else 0, "hotel_if_owned": hotel,
        "residents": residents, "cards": cards, "hotel_owned": hotel_owned, "effects": effects,
        "places": places, "places_pct": places_pct,
        "total": houses_rent + (hotel if hotel_owned else 0) + residents,
    }


async def _rate(db: AsyncSession, config, user_id: int, town: Optional[UserTown], houses) -> int:
    return (await _income_parts(db, config, user_id, town, houses))["total"]


# --- income --------------------------------------------------------------------------------------

def _income_cap(rate: int, config) -> int:
    return rate * max(1, int(config.town_income_max_hours)) // 24


def _settle_income(town: UserTown, rate: int, config, now: datetime) -> None:
    """Moves rent earned since income_since (at `rate` coins a day) into
    income_accrued. The unpaid fraction of a coin stays in the clock."""
    if town.income_since is None:
        town.income_since = now
        return
    since = ensure_aware(town.income_since)
    if now <= since:
        return
    cap = _income_cap(rate, config)
    if rate <= 0 or town.income_accrued >= cap:
        town.income_since = now
        return
    gained = int(rate * (now - since).total_seconds() // 86400)
    town.income_accrued = min(cap, town.income_accrued + gained)
    if town.income_accrued >= cap:
        town.income_since = now
    else:
        town.income_since = since + timedelta(seconds=gained * 86400 / rate)


def pending_income(town: Optional[UserTown], rate: int, config, now: datetime) -> int:
    """What collecting would pay now (read-only)."""
    if town is None:
        return 0
    accrued = int(town.income_accrued or 0)
    if town.income_since is None or rate <= 0:
        return accrued
    seconds = max(0.0, (now - ensure_aware(town.income_since)).total_seconds())
    return min(_income_cap(rate, config), accrued + int(rate * seconds // 86400))


# --- state ---------------------------------------------------------------------------------------

async def _houses(db: AsyncSession, user_id: int) -> list[UserTownHouse]:
    return list((await db.execute(
        select(UserTownHouse).where(UserTownHouse.user_id == user_id, UserTownHouse.district != DECOR_DISTRICT)
        .order_by(UserTownHouse.id)
    )).scalars())


async def _decor_owned(db: AsyncSession, user_id: int) -> set[str]:
    return set((await db.execute(
        select(UserTownHouse.building_code).where(UserTownHouse.user_id == user_id, UserTownHouse.district == DECOR_DISTRICT)
    )).scalars())


async def _get_town(db: AsyncSession, user_id: int) -> UserTown:
    """The town row under a lock, created on the first write."""
    query = select(UserTown).where(UserTown.user_id == user_id).with_for_update().execution_options(populate_existing=True)
    town = (await db.execute(query)).scalar_one_or_none()
    if town is None:
        town = UserTown(user_id=user_id, income_accrued=0, income_since=_now())
        db.add(town)
        await db.flush()
    return town


async def get_state(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    houses = await _houses(db, user.id)
    town = await db.get(UserTown, user.id)
    now = _now()
    unlocked = is_unlocked(config, town)
    parts = await _income_parts(db, config, user.id, town, houses)
    rate = parts["total"] if unlocked else 0
    effects = parts["effects"]
    rents = districts_config(config)
    owned_total = len(houses)
    return {
        "enabled": bool(config.town_enabled),
        "unlocked": unlocked,
        "unlock_coins": max(0, int(config.town_unlock_coins)),
        "rename_stars": max(0, int(config.town_rename_stars)),
        "name": town.name if town is not None else None,
        "hotel": {
            "owned": parts["hotel_owned"],
            "price": max(0, int(config.town_hotel_price)),
            "cards": parts["cards"],
            "max_cards": max(0, int(config.town_hotel_max_cards)),
            "rent_per_100_cards": max(0, int(config.town_hotel_rent_per_100_cards)),
            "rent": parts["hotel_if_owned"],
        },
        "residents": {
            "enabled": bool(config.town_residents_enabled),
            "population": effects["population"],
            "rent_per_resident": max(0, int(config.town_resident_rent)),
            "rent": parts["residents"],
            "rent_pct": effects["rent_pct"],
            "hotel_pct": effects["hotel_pct"],
            "daily_coins": effects["daily_coins"],
        },
        "decor": [
            {"code": code, "name": DECOR[code], "price": v["price"], "rent_pct": v["rent_pct"],
             "owned": code in parts["places"]}
            for code, v in decor_config(config).items()
        ],
        "decor_pct": parts["places_pct"],
        "houses": [{"district": h.district, "code": h.building_code} for h in houses],
        "owned_total": owned_total,
        "total_houses": sum(len(v) for v in HOUSES.values()),
        "price_growth_pct": int(config.town_price_growth_pct),
        "districts": [
            {
                "code": code,
                "name": DISTRICT_NAMES[code],
                "rent": rents[code]["rent"] * (100 + effects["rent_pct"] + parts["places_pct"]) // 100,
                "next_price": house_price(config, code, owned_total),
                "owned": sum(1 for h in houses if h.district == code),
                "total": len(HOUSES[code]),
            }
            for code in HOUSES
        ],
        "income": {
            "rate_per_day": rate,
            "pending": pending_income(town, rate, config, now) if unlocked else 0,
            "cap": _income_cap(rate, config),
            "max_hours": int(config.town_income_max_hours),
        },
    }


# --- actions -------------------------------------------------------------------------------------

def _require_enabled(config) -> None:
    if not config.town_enabled:
        raise ConflictError("Город сейчас закрыт")


def _require_open(config, town: UserTown) -> None:
    if not is_unlocked(config, town):
        raise ConflictError("Сначала открой город")


async def _replay(db: AsyncSession, user_id: int, key: Optional[str]) -> bool:
    if not key:
        return False
    return (await db.execute(select(TownLedger.id).where(
        TownLedger.user_id == user_id, TownLedger.idempotency_key == key,
    ))).first() is not None


async def unlock(db: AsyncSession, user: User, idempotency_key: Optional[str]) -> dict:
    """Opens the town once for town_unlock_coins coins."""
    config = await get_config(db)
    _require_enabled(config)
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await get_state(db, user), "new_balance": locked_user.balance}
    town = await _get_town(db, user.id)
    if is_unlocked(config, town):
        raise ConflictError("Город уже открыт")
    price = max(0, int(config.town_unlock_coins))
    if price:
        await debit_coins(db, locked_user, price, TransactionType.town_unlock, "Город: открытие")
    town.unlocked_at = _now()
    town.income_since = town.unlocked_at
    town.income_accrued = 0
    db.add_all([town, TownLedger(user_id=user.id, kind="unlock", coins_spent=price, result={},
                                 idempotency_key=idempotency_key)])
    await db.commit()
    return {**await get_state(db, user), "new_balance": locked_user.balance}


async def buy_house(db: AsyncSession, user: User, district: str, code: str, idempotency_key: Optional[str]) -> dict:
    """Buys one house for coins. The rent so far is settled at the old rate,
    so the new house pays from the moment it is bought."""
    config = await get_config(db)
    _require_enabled(config)
    name = HOUSES.get(district, {}).get(code)
    if name is None:
        raise NotFoundError("Такого дома в городе нет")
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await get_state(db, user), "new_balance": locked_user.balance}
    town = await _get_town(db, user.id)
    _require_open(config, town)
    houses = await _houses(db, user.id)
    if any(h.district == district and h.building_code == code for h in houses):
        raise ConflictError("Этот дом уже твой")
    price = house_price(config, district, len(houses))
    _settle_income(town, await _rate(db, config, user.id, town, houses), config, _now())
    if price:
        await debit_coins(db, locked_user, price, TransactionType.town_house,
                          f"Город: {name} ({DISTRICT_NAMES[district]})")
    db.add_all([
        town,
        UserTownHouse(user_id=user.id, district=district, building_code=code, price_paid=price),
        TownLedger(user_id=user.id, kind="buy", district=district, building_code=code, coins_spent=price,
                   result={"owned_before": len(houses)}, idempotency_key=idempotency_key),
    ])
    await db.commit()
    return {**await get_state(db, user), "new_balance": locked_user.balance}


async def buy_decor(db: AsyncSession, user: User, code: str, idempotency_key: Optional[str]) -> dict:
    """Opens a closed place on the map once for coins; from now on it adds
    its rent_pct to the houses' rent (rent so far settled at the old rate)."""
    config = await get_config(db)
    _require_enabled(config)
    if code not in DECOR:
        raise NotFoundError("Такого места в городе нет")
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await get_state(db, user), "new_balance": locked_user.balance}
    town = await _get_town(db, user.id)
    _require_open(config, town)
    if code in await _decor_owned(db, user.id):
        raise ConflictError("Это место уже твоё")
    _settle_income(town, await _rate(db, config, user.id, town, await _houses(db, user.id)), config, _now())
    price = decor_config(config)[code]["price"]
    if price:
        await debit_coins(db, locked_user, price, TransactionType.town_house, f"Город: {DECOR[code]}")
    db.add_all([
        town,
        UserTownHouse(user_id=user.id, district=DECOR_DISTRICT, building_code=code, price_paid=price),
        TownLedger(user_id=user.id, kind="decor", district=DECOR_DISTRICT, building_code=code, coins_spent=price,
                   result={}, idempotency_key=idempotency_key),
    ])
    await db.commit()
    return {**await get_state(db, user), "new_balance": locked_user.balance}


async def claim_income(db: AsyncSession, user: User, idempotency_key: Optional[str]) -> dict:
    """Collects the rent (at most town_income_max_hours of it)."""
    config = await get_config(db)
    _require_enabled(config)
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await get_state(db, user), "claimed": 0, "new_balance": locked_user.balance}
    town = await _get_town(db, user.id)
    _require_open(config, town)
    _settle_income(town, await _rate(db, config, user.id, town, await _houses(db, user.id)), config, _now())
    amount = int(town.income_accrued or 0)
    if amount <= 0:
        raise ConflictError("Пока нечего забирать — рента копится каждый час")
    town.income_accrued = 0
    paid = 0 if locked_user.game_rewards_blocked else amount
    if paid:
        await credit_coins(db, locked_user, paid, TransactionType.town_income, "Город: рента")
    db.add_all([town, TownLedger(user_id=user.id, kind="income", coins_earned=paid, result={"accrued": amount},
                                 idempotency_key=idempotency_key)])
    await db.commit()
    return {**await get_state(db, user), "claimed": paid, "new_balance": locked_user.balance}


async def buy_hotel(db: AsyncSession, user: User, idempotency_key: Optional[str]) -> dict:
    """Buys the «Отель» once for coins; it pays for the cards held from now on."""
    config = await get_config(db)
    _require_enabled(config)
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await get_state(db, user), "new_balance": locked_user.balance}
    town = await _get_town(db, user.id)
    _require_open(config, town)
    if town.hotel_bought_at is not None:
        raise ConflictError("Отель уже твой")
    houses = await _houses(db, user.id)
    now = _now()
    _settle_income(town, await _rate(db, config, user.id, town, houses), config, now)
    price = max(0, int(config.town_hotel_price))
    if price:
        await debit_coins(db, locked_user, price, TransactionType.town_house, "Город: Отель")
    town.hotel_bought_at = now
    db.add_all([town, TownLedger(user_id=user.id, kind="hotel", coins_spent=price,
                                 result={"cards": await _card_count(db, user.id)}, idempotency_key=idempotency_key)])
    await db.commit()
    return {**await get_state(db, user), "new_balance": locked_user.balance}


async def _settle_before_population_change(db: AsyncSession, config, user_id: int) -> None:
    """Rent so far is settled at the old population before it changes (an
    opened town only). Caller holds the user lock."""
    town = await db.get(UserTown, user_id)
    if town is None or not is_unlocked(config, town):
        return
    town = await _get_town(db, user_id)
    _settle_income(town, await _rate(db, config, user_id, town, await _houses(db, user_id)), config, _now())
    db.add(town)


# --- residents -----------------------------------------------------------------------------------

def resident_out(resident: TownResident, config, owned: Optional[UserTownResident] = None) -> dict:
    """A resident card; the same card fields as muse_service.muse_out, so the
    pack reveal and the shop draw both the same way."""
    rent = max(0, int(config.town_resident_rent))
    bonus = bonus_label(resident.bonus, resident.bonus_value)
    rent_label = f"+{rent} {'монета' if rent == 1 else 'монет'} в день" if rent else ""
    return {
        "id": resident.id, "name": resident.name, "title": resident.title, "description": resident.description,
        "icon": resident.icon, "image_path": resident.image_path, "rarity": resident.rarity,
        "bonus": resident.bonus, "bonus_value": resident.bonus_value, "bonus_label": bonus,
        "effect_label": " · ".join(x for x in (rent_label, bonus) if x) or "Житель города",
        "owned": owned is not None and owned.copies > 0, "copies": owned.copies if owned else 0,
        "spare_coins": spare_coins(config, resident.rarity),
    }


async def album(db: AsyncSession, user: User) -> dict:
    """«Жители»: every active resident (owned or not), the population and
    what the residents add to the town."""
    config = await get_config(db)
    residents = (await db.execute(
        select(TownResident).where(TownResident.is_active.is_(True))
        .order_by(TownResident.sort_order, TownResident.id)
    )).scalars().all()
    owned_rows = await _owned_residents(db, user.id)
    owned = {r.resident_id: r for r in owned_rows}
    effects = resident_effects(config, owned_rows)
    ordered = sorted(residents, key=lambda r: (-_RARITY_ORDER.get(r.rarity, 0), r.sort_order, r.id))
    return {
        "enabled": bool(config.town_residents_enabled),
        "residents": [resident_out(r, config, owned.get(r.id)) for r in ordered],
        "owned_count": sum(1 for r in residents if owned.get(r.id) and owned[r.id].copies > 0),
        "total_count": len(residents),
        "population": effects["population"],
        "rent_per_resident": max(0, int(config.town_resident_rent)),
        "bonuses": {k: effects[k] for k in RESIDENT_BONUSES if k != "none"},
        "caps": {"pct": int(config.town_resident_bonus_max_pct), "daily_coins": int(config.town_resident_max_daily_coins)},
    }


async def sell_spare(db: AsyncSession, user: User, resident_id: int, count: int = 1) -> dict:
    """Sells spare copies (one copy of the resident always stays)."""
    config = await get_config(db)
    if not config.town_residents_enabled:
        raise ConflictError("Жители сейчас недоступны")
    locked = await lock_user_for_update(db, user.id)
    row = (await db.execute(
        select(UserTownResident).where(UserTownResident.user_id == user.id, UserTownResident.resident_id == resident_id)
        .with_for_update(of=UserTownResident).execution_options(populate_existing=True)
    )).unique().scalar_one_or_none()
    if row is None:
        raise NotFoundError("Этого жителя у тебя нет")
    count = max(1, count)
    if row.copies - 1 < count:
        raise ConflictError("Лишних копий этого жителя нет")
    await _settle_before_population_change(db, config, user.id)
    price = spare_coins(config, row.resident.rarity) * count
    row.copies -= count
    db.add_all([row, TownLedger(user_id=user.id, kind="resident_sale", coins_earned=price,
                                result={"resident_id": resident_id, "count": count})])
    if price:
        await credit_coins(db, locked, price, TransactionType.town_resident_sale,
                           f"Житель «{row.resident.name}»: лишняя копия",
                           related_object_type="town_resident", related_object_id=resident_id)
    await db.commit()
    await db.refresh(locked)
    view = await album(db, locked)
    view["sold_coins"] = price
    view["new_balance"] = locked.balance
    return view


# --- packs, shop and admin grants ----------------------------------------------------------------

async def droppable(db: AsyncSession) -> list[TownResident]:
    """The pack's drop pool: active, droppable residents with a weight."""
    return list((await db.execute(select(TownResident).where(
        TownResident.is_active.is_(True), TownResident.is_pack_droppable.is_(True), TownResident.drop_weight > 0,
    ))).scalars())


def pick_random_resident(pool: list[TownResident], rarity: Rarity) -> Optional[TownResident]:
    """A resident of the slot's rarity (diamond → legendary) by drop weight;
    if none has that rarity, the closest rarity below, then above."""
    if not pool:
        return None
    wanted = _RARITY_ORDER.get("legendary" if rarity == Rarity.diamond else rarity.value, 0)
    by_distance = sorted({_RARITY_ORDER.get(r.rarity, 0) for r in pool}, key=lambda t: (abs(t - wanted), t > wanted))
    tier = [r for r in pool if _RARITY_ORDER.get(r.rarity, 0) == by_distance[0]]
    return random.choices(tier, weights=[r.drop_weight for r in tier], k=1)[0]


async def grant(db: AsyncSession, user_id: int, resident: TownResident, source: str) -> tuple[UserTownResident, bool]:
    """Adds one copy of a resident (one more inhabitant). The rent so far is
    settled at the old population first. Caller holds the user lock, commits."""
    config = await get_config(db)
    await _settle_before_population_change(db, config, user_id)
    row = (await db.execute(
        select(UserTownResident).where(UserTownResident.user_id == user_id, UserTownResident.resident_id == resident.id)
        .with_for_update(of=UserTownResident).execution_options(populate_existing=True)
    )).unique().scalar_one_or_none()
    if row is not None:
        row.copies += 1
        db.add(row)
        await db.flush()
        return row, False
    row = UserTownResident(user_id=user_id, resident_id=resident.id, copies=1, source=source)
    row.resident = resident
    db.add(row)
    await db.flush()
    return row, True


def admin_resident_out(resident: TownResident) -> dict:
    return {
        "id": resident.id, "name": resident.name, "title": resident.title, "description": resident.description,
        "icon": resident.icon, "image_path": resident.image_path, "rarity": resident.rarity,
        "bonus": resident.bonus, "bonus_value": resident.bonus_value,
        "bonus_label": bonus_label(resident.bonus, resident.bonus_value),
        "drop_weight": resident.drop_weight, "is_pack_droppable": resident.is_pack_droppable,
        "is_active": resident.is_active, "sort_order": resident.sort_order,
    }


async def admin_catalog(db: AsyncSession) -> dict:
    residents = (await db.execute(select(TownResident).order_by(TownResident.sort_order, TownResident.id))).scalars().all()
    counts = dict((await db.execute(
        select(UserTownResident.resident_id, func.coalesce(func.sum(UserTownResident.copies), 0))
        .group_by(UserTownResident.resident_id)
    )).all())
    return {
        "rarities": list(RARITIES),
        "bonuses": [{"code": code, "label": (label or "Без бонуса").format(v="N")} for code, label in RESIDENT_BONUSES.items()],
        "residents": [{**admin_resident_out(r), "copies_held": int(counts.get(r.id, 0))} for r in residents],
    }


async def admin_save(db: AsyncSession, data: dict, resident_id: Optional[int] = None) -> dict:
    if data.get("rarity") is not None and data["rarity"] not in RARITIES:
        raise ConflictError(f"Неизвестная редкость: {data['rarity']}")
    if data.get("bonus") is not None and data["bonus"] not in RESIDENT_BONUSES:
        raise ConflictError(f"Неизвестный бонус: {data['bonus']}")
    if resident_id is None:
        row = TownResident(**data)
        db.add(row)
    else:
        row = await db.get(TownResident, resident_id)
        if row is None:
            raise NotFoundError("Житель не найден")
        for key, value in data.items():
            setattr(row, key, value)
    await db.flush()
    await db.refresh(row)
    return admin_resident_out(row)


async def admin_grant(db: AsyncSession, resident_id: int, user_id: int) -> dict:
    resident = await db.get(TownResident, resident_id)
    if resident is None:
        raise NotFoundError("Житель не найден")
    if await db.get(User, user_id) is None:
        raise NotFoundError("Пользователь не найден")
    await lock_user_for_update(db, user_id)
    row, is_new = await grant(db, user_id, resident, "admin")
    return {"user_town_resident_id": row.id, "copies": row.copies, "is_new": is_new}


# --- Telegram Stars: renaming the town -----------------------------------------------------------

STARS_PREFIX = "town:"
_RENAME = "town:rename"
_NAME_RE = re.compile(r"^[0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё .'«»-]*$")
_BANNED_IN_NAME = ("http", "t.me", "www", "footycards")


def clean_name(raw: str) -> str:
    """A town name: 2–24 letters, digits, spaces and . ' - « », no links."""
    name = " ".join((raw or "").split())
    if not 2 <= len(name) <= 24:
        raise ConflictError("Название — от 2 до 24 символов")
    lowered = name.lower()
    if not _NAME_RE.match(name) or any(bad in lowered for bad in _BANNED_IN_NAME):
        raise ConflictError("В названии можно только буквы, цифры, пробелы и . ' - « »")
    return name


async def create_rename_invoice(db: AsyncSession, user: User, raw_name: str) -> dict:
    """Telegram Stars invoice for a new town name; the name is kept in a
    "rename_order" ledger row keyed by this invoice."""
    import secrets

    from app.models.pack import StarsInvoice
    from app.services.stars_payment_service import _request_telegram_invoice_link

    config = await get_config(db)
    _require_enabled(config)
    stars = int(config.town_rename_stars)
    if stars <= 0:
        raise ConflictError("Переименование сейчас не продаётся")
    if not is_unlocked(config, await db.get(UserTown, user.id)):
        raise ConflictError("Сначала открой город")
    name = clean_name(raw_name)
    token = secrets.token_urlsafe(16)
    db.add(StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, academy_speedup=_RENAME))
    await db.flush()
    link = await _request_telegram_invoice_link(token, "Название города", f"Город получит имя «{name}»", stars)
    db.add(TownLedger(user_id=user.id, kind="rename_order", result={"name": name}, idempotency_key=f"order-{token}"))
    await db.commit()
    return {"invoice_link": link, "payload_token": token, "stars_amount": stars}


async def validate_stars_invoice(db: AsyncSession, invoice) -> tuple[bool, str]:
    """pre_checkout_query: still buyable at the frozen price."""
    config = await get_config(db)
    if not config.town_enabled:
        return False, "Город сейчас закрыт"
    if invoice.academy_speedup != _RENAME:
        return False, "Unknown order"
    if not is_unlocked(config, await db.get(UserTown, invoice.user_id)):
        return False, "Сначала открой город"
    if int(config.town_rename_stars) != invoice.stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    return True, ""


async def deliver_stars_invoice(db: AsyncSession, user: User, invoice) -> dict:
    """Called by stars_payment_service.deliver_payment under the invoice row
    lock (idempotent there). The payment is taken, so it never refuses; the
    caller commits."""
    town = await _get_town(db, user.id)
    order = (await db.execute(select(TownLedger).where(
        TownLedger.user_id == user.id, TownLedger.idempotency_key == f"order-{invoice.payload_token}",
    ))).scalar_one_or_none()
    name = (order.result or {}).get("name") if order is not None else None
    if name:
        town.name = name
    db.add_all([town, TownLedger(user_id=user.id, kind="rename", result={"name": name},
                                 idempotency_key=f"stars-{invoice.payload_token}")])
    await db.flush()
    return {"kind": "town_rename", "name": name}
