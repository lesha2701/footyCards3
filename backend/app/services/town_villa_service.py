"""«Моя вилла»: the player's own plot in his town, laid out as he likes.

The plot is an isometric grid (grid_<level> cells a side, it grows with the
villa's level). On it stand the villa itself (5 levels), the garage (0–3
levels, garage_slots_<level> cars) and whatever the player bought: cars and
yard things for coins (`coins_<code>`) or for Telegram Stars (`stars_<code>`,
the premium ones; `supply_<code>` > 0 makes an item limited, every copy
numbered). Bought things land in storage; the player places them on free
cells, turns them (w and h swapped) or puts them back (PUT layout — the whole
result is checked: owned, inside the grid, no overlaps, the villa and the
garage always stand).

«Персонал»: residents the player holds work at the villa, one a post, each
post takes residents of its professions (POSTS, matched on the title).

«Престиж» = villa level × prestige_villa_level + garage level ×
prestige_garage_level + every kind of thing owned once × prestige_<code> +
staff × prestige_staff. Every prestige_per_pct of it adds 1 % to the rent of
the town's houses, at most prestige_max_pct (town_service._income_parts) —
so the rent so far is settled before the prestige changes.

The chosen car (`car_item_id`) drives on the owner's town map. Guests see
the villa (town_social_service visits) and like it once a day
(town_visits.villa_liked); «Вилла недели» ranks villas by those likes (guests
older than town_social.week_min_account_days only) and pays
villa_week_reward_1..3 once a week — settled lazily by the first reader
under a town_weeks row keyed "V" + the ISO week.
"""
import secrets
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import local_today
from app.models.enums import TransactionType
from app.models.town import (
    TownLedger, TownResident, TownVisit, TownWeek, TownWeekResult, UserTown, UserTownResident, UserTownVilla,
    UserTownVillaItem,
)
from app.models.user import User
from app.services import town_service
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

STARS_PREFIX = "town:villa:"
MAX_VILLA_LEVEL = 5
MAX_GARAGE_LEVEL = 3
VILLA_SIZE = (3, 3)
GARAGE_SIZE = (2, 2)

# code -> (name, emoji, kind, w, h). kind: car | yard | premium.
ITEMS: dict[str, tuple[str, str, str, int, int]] = {
    "car_hatch": ("Городской хэтчбек", "🚗", "car", 1, 2),
    "car_jeep": ("Открытый джип", "🚙", "car", 1, 2),
    "car_van": ("Фургон сёрфера", "🚐", "car", 1, 2),
    "car_cabrio": ("Кабриолет 60-х", "🚘", "car", 1, 2),
    "car_sport": ("Суперкар", "🏎️", "car", 1, 2),
    "car_bus": ("Автобус команды", "🚌", "car", 1, 2),
    "car_classic": ("Золотой родстер", "🏁", "car", 1, 2),
    "pool": ("Бассейн", "🏊", "yard", 3, 2),
    "pitch_mini": ("Мини-поле", "⚽", "yard", 3, 3),
    "goal_practice": ("Ворота для тренировки", "🥅", "yard", 1, 1),
    "gazebo_bbq": ("Беседка с грилем", "🍖", "yard", 2, 2),
    "palm": ("Пальма", "🌴", "yard", 1, 1),
    "olive": ("Оливковое дерево", "🫒", "yard", 1, 1),
    "cypress": ("Кипарис", "🌲", "yard", 1, 1),
    "flowers": ("Клумба", "💐", "yard", 1, 1),
    "hedge": ("Живая изгородь", "🌿", "yard", 1, 1),
    "lamp": ("Фонарь", "🏮", "yard", 1, 1),
    "bench": ("Скамейка", "🪑", "yard", 1, 1),
    "path": ("Дорожка", "▫️", "yard", 1, 1),
    "sun_umbrella": ("Зонт с шезлонгом", "⛱️", "yard", 1, 1),
    "fountain_ball": ("Фонтан с золотым мячом", "⛲", "premium", 2, 2),
    "statue_gold": ("Золотая статуя", "🏆", "premium", 1, 1),
    "trophy_pavilion": ("Павильон трофеев", "🏛️", "premium", 2, 2),
    "helipad": ("Вертолётная площадка", "🚁", "premium", 3, 3),
    "firepit": ("Лаунж с камином", "🔥", "premium", 2, 2),
}
# One copy at most: cars and premium things (yard things — as many as fit).
_SINGLE_KINDS = ("car", "premium")

# post -> (name, emoji, title keywords)
POSTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "security": ("Охрана", "🛡️", ("полиц", "охран", "кинолог", "боксёр", "карате", "капоэйр")),
    "garden": ("Сад и газон", "🌱", ("газон", "смотритель поля", "флорист", "цвет", "садов")),
    "garage": ("Гараж", "🔧", ("механик", "таксист", "водител", "трамвай", "инженер", "курьер")),
    "kitchen": ("Кухня и бар", "🍹", ("повар", "бармен", "бариста", "мороженщ", "пекар", "лавк")),
    "party": ("Вечеринки", "🎧", ("диджей", "певиц", "танцов", "барабан", "киномеханик")),
    "health": ("Здоровье", "🩺", ("фельдшер", "ветеринар", "массаж", "врач")),
    "pool": ("Бассейн и пляж", "🛟", ("спасател", "сёрф", "парус", "водолаз")),
    "concierge": ("Дворецкий", "🎩", ("консьерж", "отел", "экскурсовод")),
}

VILLA_DEFAULTS: dict[str, int] = {
    "villa_price_2": 15000, "villa_price_3": 40000, "villa_price_4": 90000, "villa_price_5": 180000,
    "grid_1": 8, "grid_2": 9, "grid_3": 10, "grid_4": 11, "grid_5": 12,
    "garage_price_1": 8000, "garage_price_2": 25000, "garage_price_3": 60000,
    "garage_slots_1": 1, "garage_slots_2": 3, "garage_slots_3": 6,
    "prestige_villa_level": 20, "prestige_garage_level": 10, "prestige_staff": 15,
    "prestige_per_pct": 60, "prestige_max_pct": 5,
    "max_items": 120,
    "villa_week_reward_1": 2000, "villa_week_reward_2": 1000, "villa_week_reward_3": 500,
    # cars
    "coins_car_hatch": 3000, "prestige_car_hatch": 5,
    "coins_car_jeep": 6000, "prestige_car_jeep": 8,
    "coins_car_van": 9000, "prestige_car_van": 10,
    "coins_car_cabrio": 12000, "prestige_car_cabrio": 12,
    "stars_car_sport": 99, "prestige_car_sport": 25,
    "stars_car_bus": 149, "prestige_car_bus": 30,
    "stars_car_classic": 249, "prestige_car_classic": 40, "supply_car_classic": 300,
    # yard
    "coins_pool": 15000, "prestige_pool": 20,
    "coins_pitch_mini": 20000, "prestige_pitch_mini": 25,
    "coins_goal_practice": 2500, "prestige_goal_practice": 4,
    "coins_gazebo_bbq": 8000, "prestige_gazebo_bbq": 10,
    "coins_palm": 600, "prestige_palm": 1,
    "coins_olive": 800, "prestige_olive": 1,
    "coins_cypress": 600, "prestige_cypress": 1,
    "coins_flowers": 400, "prestige_flowers": 1,
    "coins_hedge": 300, "prestige_hedge": 1,
    "coins_lamp": 500, "prestige_lamp": 1,
    "coins_bench": 400, "prestige_bench": 1,
    "coins_path": 100, "prestige_path": 0,
    "coins_sun_umbrella": 700, "prestige_sun_umbrella": 1,
    # premium
    "stars_fountain_ball": 79, "prestige_fountain_ball": 25,
    "stars_statue_gold": 59, "prestige_statue_gold": 20,
    "stars_trophy_pavilion": 99, "prestige_trophy_pavilion": 30,
    "stars_helipad": 199, "prestige_helipad": 45,
    "stars_firepit": 69, "prestige_firepit": 15,
    # copies of a Stars item sold at most, each numbered (0 = no limit, no numbers)
    "supply_car_sport": 0, "supply_car_bus": 0, "supply_fountain_ball": 0, "supply_statue_gold": 0,
    "supply_trophy_pavilion": 0, "supply_helipad": 0, "supply_firepit": 0,
}


def villa_config(config) -> dict[str, int]:
    stored = getattr(config, "town_villa", None) or {}
    out = dict(VILLA_DEFAULTS)
    for key, value in stored.items():
        if key in VILLA_DEFAULTS and isinstance(value, int) and not isinstance(value, bool):
            out[key] = max(0, value)
    for level in range(1, MAX_VILLA_LEVEL + 1):  # the grid never shrinks and always holds the villa and the garage
        floor = out[f"grid_{level - 1}"] if level > 1 else 6
        out[f"grid_{level}"] = min(30, max(floor, out[f"grid_{level}"]))
    out["prestige_per_pct"] = max(1, out["prestige_per_pct"])
    return out


def validate_villa(raw: dict) -> dict:
    out: dict = {}
    for key, value in (raw or {}).items():
        if key not in VILLA_DEFAULTS:
            raise ValueError(f"неизвестный параметр «{key}»")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{key}: нужно целое число ≥ 0")
        out[key] = value
    return out


def item_price(v: dict, code: str) -> tuple[int, int]:
    """(coins, stars) — exactly one of them is > 0 for an item on sale."""
    return v.get(f"coins_{code}", 0), v.get(f"stars_{code}", 0)


def grid_size(v: dict, villa_level: int) -> int:
    return v[f"grid_{max(1, min(MAX_VILLA_LEVEL, villa_level))}"]


def garage_slots(v: dict, garage_level: int) -> int:
    return v[f"garage_slots_{garage_level}"] if garage_level > 0 else 0


def size_of(code: str) -> tuple[int, int]:
    if code == "villa":
        return VILLA_SIZE
    if code == "garage":
        return GARAGE_SIZE
    _, _, _, w, h = ITEMS[code]
    return w, h


def footprint(code: str, rot: int) -> tuple[int, int]:
    w, h = size_of(code)
    return (h, w) if rot else (w, h)


def check_layout(cells: int, items: list[tuple[int, str, Optional[int], Optional[int], int]]) -> Optional[str]:
    """None when (id, code, x, y, rot) items fit: inside the grid, no
    overlaps, the villa and the garage placed. Otherwise why not."""
    taken: dict[tuple[int, int], int] = {}
    for item_id, code, x, y, rot in items:
        if x is None or y is None:
            if code in ("villa", "garage"):
                return "Виллу и гараж нельзя убрать на склад"
            continue
        w, h = footprint(code, rot)
        if x < 0 or y < 0 or x + w > cells or y + h > cells:
            return "Предмет выходит за участок"
        for dx in range(w):
            for dy in range(h):
                if (x + dx, y + dy) in taken:
                    return "Клетки уже заняты"
                taken[(x + dx, y + dy)] = item_id
    return None


def staff_posts_for(title: Optional[str]) -> list[str]:
    lowered = (title or "").lower()
    return [post for post, (_, _, words) in POSTS.items() if any(w in lowered for w in words)]


def prestige_of(v: dict, villa: Optional[UserTownVilla], codes: set[str], staff: int) -> int:
    if villa is None:
        return 0
    return (villa.villa_level * v["prestige_villa_level"] + villa.garage_level * v["prestige_garage_level"]
            + sum(v.get(f"prestige_{c}", 0) for c in codes if c in ITEMS) + staff * v["prestige_staff"])


def prestige_pct(v: dict, prestige: int) -> int:
    return min(v["prestige_max_pct"], prestige // v["prestige_per_pct"])


# --- reading -------------------------------------------------------------------------------------

async def _villa(db: AsyncSession, user_id: int, lock: bool = False) -> Optional[UserTownVilla]:
    query = select(UserTownVilla).where(UserTownVilla.user_id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(query)).scalar_one_or_none()


async def _items(db: AsyncSession, user_id: int) -> list[UserTownVillaItem]:
    return list((await db.execute(
        select(UserTownVillaItem).where(UserTownVillaItem.user_id == user_id).order_by(UserTownVillaItem.id)
    )).scalars())


async def _staff_rows(db: AsyncSession, user_id: int, villa: Optional[UserTownVilla]) -> dict[str, TownResident]:
    """Posts whose resident the player still holds (an active one)."""
    staff = dict(villa.staff or {}) if villa is not None else {}
    ids = [int(i) for i in staff.values() if isinstance(i, int)]
    if not ids:
        return {}
    held = {r.resident_id: r.resident for r in (await db.execute(
        select(UserTownResident).where(UserTownResident.user_id == user_id, UserTownResident.resident_id.in_(ids),
                                       UserTownResident.copies > 0)
    )).scalars() if r.resident.is_active}
    return {post: held[rid] for post, rid in staff.items() if post in POSTS and rid in held}


async def prestige_for(db: AsyncSession, config, user_id: int) -> tuple[int, int]:
    """(prestige, rent %) of a player's villa — for town_service._income_parts."""
    villa = await _villa(db, user_id)
    if villa is None:
        return 0, 0
    v = villa_config(config)
    codes = {i.code for i in await _items(db, user_id)}
    staff = len(await _staff_rows(db, user_id, villa)) if config.town_residents_enabled else 0
    prestige = prestige_of(v, villa, codes, staff)
    return prestige, prestige_pct(v, prestige)


async def _sold(db: AsyncSession, code: str) -> int:
    return int((await db.execute(
        select(func.count(UserTownVillaItem.id)).where(UserTownVillaItem.code == code)
    )).scalar_one())


def _item_out(item: UserTownVillaItem, villa: UserTownVilla) -> dict:
    name, emoji, kind = ("Вилла", "🏡", "villa") if item.code == "villa" else \
        ("Гараж", "🅿️", "garage") if item.code == "garage" else ITEMS[item.code][:3]
    w, h = size_of(item.code)
    level = villa.villa_level if item.code == "villa" else villa.garage_level if item.code == "garage" else None
    return {"id": item.id, "code": item.code, "name": name, "emoji": emoji, "kind": kind, "w": w, "h": h,
            "x": item.x, "y": item.y, "rot": item.rot, "serial": item.serial, "level": level}


def _plot(v: dict, villa: UserTownVilla, items: list[UserTownVillaItem], staff: dict[str, TownResident]) -> dict:
    """What anyone may see of a villa: the grid and what stands on it."""
    known = [i for i in items if i.code in ITEMS or i.code in ("villa", "garage")]
    codes = {i.code for i in known}
    prestige = prestige_of(v, villa, codes, len(staff))
    car = next((i for i in known if i.id == villa.car_item_id and i.code in ITEMS), None)
    return {
        "villa_level": villa.villa_level, "garage_level": villa.garage_level,
        "grid": grid_size(v, villa.villa_level),
        "items": [_item_out(i, villa) for i in known],
        "car": {"id": car.id, "code": car.code, "name": ITEMS[car.code][0], "emoji": ITEMS[car.code][1]} if car else None,
        "staff": [{"post": p, "name": POSTS[p][0], "emoji": POSTS[p][1], "resident": {
            "id": r.id, "name": r.name, "title": r.title, "icon": r.icon, "image_path": r.image_path, "rarity": r.rarity,
        }} for p, r in staff.items()],
        "prestige": prestige, "prestige_pct": prestige_pct(v, prestige),
    }


def _first_free(cells: int, items: list[UserTownVillaItem], code: str) -> Optional[tuple[int, int]]:
    w, h = size_of(code)
    layout = [(i.id, i.code, i.x, i.y, i.rot) for i in items]
    for s in range(cells * 2):  # front of the plot last: try cells by x + y
        for x in range(cells):
            y = s - x
            if 0 <= y < cells and check_layout(cells, layout + [(0, code, x, y, 0)]) is None:
                return x, y
    return None


async def _ensure_villa(db: AsyncSession, config, user_id: int) -> UserTownVilla:
    """The villa row under a lock, created (with the villa on the plot) on
    the first look of an opened town."""
    villa = await _villa(db, user_id, lock=True)
    if villa is not None:
        return villa
    try:
        async with db.begin_nested():
            villa = UserTownVilla(user_id=user_id, villa_level=1, garage_level=0, staff={})
            db.add(villa)
            await db.flush()
            db.add(UserTownVillaItem(user_id=user_id, code="villa", x=1, y=1, rot=0))
            await db.flush()
    except IntegrityError:  # a parallel request made it first
        pass
    return await _villa(db, user_id, lock=True)


async def _open(db: AsyncSession, config, user_id: int) -> UserTownVilla:
    town_service._require_enabled(config)
    if not town_service.is_unlocked(config, await db.get(UserTown, user_id)):
        raise ConflictError("Сначала открой город")
    return await _ensure_villa(db, config, user_id)


async def get_villa(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    villa = await _open(db, config, user.id)
    await db.commit()
    return await _state(db, config, user, villa)


async def _state(db: AsyncSession, config, user: User, villa: UserTownVilla) -> dict:
    v = villa_config(config)
    items = await _items(db, user.id)
    staff = await _staff_rows(db, user.id, villa) if config.town_residents_enabled else {}
    owned_codes: dict[str, int] = {}
    for i in items:
        owned_codes[i.code] = owned_codes.get(i.code, 0) + 1
    cars = sum(1 for i in items if i.code in ITEMS and ITEMS[i.code][2] == "car")
    slots = garage_slots(v, villa.garage_level)
    shop = []
    for code, (name, emoji, kind, w, h) in ITEMS.items():
        coins, stars = item_price(v, code)
        supply = v.get(f"supply_{code}", 0)
        sold = await _sold(db, code) if supply else 0
        single = kind in _SINGLE_KINDS
        reason = ""
        if not coins and not stars:
            reason = "Не продаётся"
        elif single and owned_codes.get(code):
            reason = "Уже твоё"
        elif kind == "car" and cars >= slots:
            reason = "Нужно место в гараже" if slots else "Сначала построй гараж"
        elif supply and sold >= supply:
            reason = "Все копии разобраны"
        elif len(items) >= v["max_items"]:
            reason = "Склад полон"
        shop.append({
            "code": code, "name": name, "emoji": emoji, "kind": kind, "w": w, "h": h,
            "coins": coins, "stars": stars, "prestige": v.get(f"prestige_{code}", 0),
            "owned": owned_codes.get(code, 0), "supply": supply, "sold": sold,
            "can_buy": not reason, "reason": reason,
        })
    # Residents the player holds that some post takes.
    held = (await db.execute(
        select(UserTownResident).where(UserTownResident.user_id == user.id, UserTownResident.copies > 0)
    )).scalars().all() if config.town_residents_enabled else []
    candidates = [{"id": r.resident.id, "name": r.resident.name, "title": r.resident.title, "icon": r.resident.icon,
                   "image_path": r.resident.image_path, "rarity": r.resident.rarity,
                   "posts": staff_posts_for(r.resident.title)}
                  for r in held if r.resident.is_active and staff_posts_for(r.resident.title)]
    nl, ng = villa.villa_level + 1, villa.garage_level + 1
    return {
        **_plot(v, villa, items, staff),
        "user_id": user.id,
        "next_villa": {"level": nl, "price": v[f"villa_price_{nl}"], "grid": grid_size(v, nl)} if nl <= MAX_VILLA_LEVEL else None,
        "next_garage": {"level": ng, "price": v[f"garage_price_{ng}"], "slots": garage_slots(v, ng)}
        if ng <= MAX_GARAGE_LEVEL else None,
        "garage_slots": slots, "cars": cars,
        "shop": shop,
        "posts": [{"post": p, "name": n, "emoji": e} for p, (n, e, _) in POSTS.items()],
        "candidates": candidates,
        "prestige_per_pct": v["prestige_per_pct"], "prestige_max_pct": v["prestige_max_pct"],
        "max_items": v["max_items"],
        "likes_total": await _villa_likes(db, user.id),
    }


# --- actions -------------------------------------------------------------------------------------

async def _replay(db: AsyncSession, user_id: int, key: Optional[str]) -> bool:
    if not key:
        return False
    return (await db.execute(select(TownLedger.id).where(
        TownLedger.user_id == user_id, TownLedger.idempotency_key == key,
    ))).first() is not None


async def upgrade(db: AsyncSession, user: User, target: str, idempotency_key: Optional[str]) -> dict:
    """The villa's or the garage's next level for coins."""
    config = await get_config(db)
    if target not in ("villa", "garage"):
        raise NotFoundError("Такой постройки нет")
    locked_user = await lock_user_for_update(db, user.id)
    villa = await _open(db, config, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await _state(db, config, user, villa), "new_balance": locked_user.balance}
    v = villa_config(config)
    level = (villa.villa_level if target == "villa" else villa.garage_level) + 1
    if level > (MAX_VILLA_LEVEL if target == "villa" else MAX_GARAGE_LEVEL):
        raise ConflictError("Это уже последний уровень")
    price = v[f"{target}_price_{level}"]
    items = await _items(db, user.id)
    spot = None
    if target == "garage" and level == 1:
        spot = _first_free(grid_size(v, villa.villa_level), items, "garage")
        if spot is None:
            raise ConflictError("Освободи на участке место 2×2 под гараж")
    await town_service._settle_before_population_change(db, config, user.id)
    if price:
        await debit_coins(db, locked_user, price, TransactionType.town_villa,
                          f"Вилла: {'вилла' if target == 'villa' else 'гараж'}, уровень {level}",
                          related_object_type="town_villa", related_object_id=level)
    if target == "villa":
        villa.villa_level = level
    else:
        villa.garage_level = level
        if spot is not None:
            db.add(UserTownVillaItem(user_id=user.id, code="garage", x=spot[0], y=spot[1], rot=0))
    db.add_all([villa, TownLedger(user_id=user.id, kind="villa", building_code=f"{target}:{level}", coins_spent=price,
                                  result={"target": target, "level": level}, idempotency_key=idempotency_key)])
    await db.commit()
    return {**await _state(db, config, user, villa), "new_balance": locked_user.balance}


async def _available(db: AsyncSession, config, user_id: int, code: str, villa: Optional[UserTownVilla]) -> tuple[bool, str]:
    if code not in ITEMS:
        return False, "Такого предмета нет"
    if villa is None:
        return False, "Сначала открой виллу"
    v = villa_config(config)
    name, _, kind, _, _ = ITEMS[code]
    items = await _items(db, user_id)
    if len(items) >= v["max_items"]:
        return False, f"Склад полон — у виллы не больше {v['max_items']} предметов"
    if kind in _SINGLE_KINDS and any(i.code == code for i in items):
        return False, f"«{name}» уже у тебя"
    if kind == "car":
        slots = garage_slots(v, villa.garage_level)
        if sum(1 for i in items if i.code in ITEMS and ITEMS[i.code][2] == "car") >= slots:
            return False, "Нужно место в гараже — улучши гараж" if slots else "Сначала построй гараж"
    supply = v.get(f"supply_{code}", 0)
    if supply and await _sold(db, code) >= supply:
        return False, "Все копии уже разобраны"
    return True, ""


async def _grant(db: AsyncSession, user_id: int, code: str, supply: int) -> UserTownVillaItem:
    """A new thing in storage; a limited one numbered (the unique index
    decides between two buyers of the same serial)."""
    if not supply:
        item = UserTownVillaItem(user_id=user_id, code=code)
        db.add(item)
        await db.flush()
        return item
    for _ in range(5):
        top = (await db.execute(
            select(func.max(UserTownVillaItem.serial)).where(UserTownVillaItem.code == code)
        )).scalar_one()
        try:
            async with db.begin_nested():
                item = UserTownVillaItem(user_id=user_id, code=code, serial=int(top or 0) + 1)
                db.add(item)
                await db.flush()
            return item
        except IntegrityError:
            continue
    item = UserTownVillaItem(user_id=user_id, code=code)  # never refuse a paid one
    db.add(item)
    await db.flush()
    return item


async def buy_item(db: AsyncSession, user: User, code: str, idempotency_key: Optional[str]) -> dict:
    """A thing for coins, into storage."""
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    villa = await _open(db, config, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await _state(db, config, user, villa), "new_balance": locked_user.balance}
    v = villa_config(config)
    if code not in ITEMS:
        raise NotFoundError("Такого предмета нет")
    coins, stars = item_price(v, code)
    if not coins:
        raise ConflictError("Этот предмет продаётся только за ⭐" if stars else "Этот предмет не продаётся")
    ok, reason = await _available(db, config, user.id, code, villa)
    if not ok:
        raise ConflictError(reason)
    await town_service._settle_before_population_change(db, config, user.id)
    await debit_coins(db, locked_user, coins, TransactionType.town_villa, f"Вилла: {ITEMS[code][0]}",
                      related_object_type="town_villa_item")
    item = await _grant(db, user.id, code, v.get(f"supply_{code}", 0))
    db.add(TownLedger(user_id=user.id, kind="villa", building_code=code, coins_spent=coins,
                      result={"item_id": item.id}, idempotency_key=idempotency_key))
    await db.commit()
    return {**await _state(db, config, user, villa), "new_balance": locked_user.balance}


async def save_layout(db: AsyncSession, user: User, moves: list[dict]) -> dict:
    """Moves things: [{id, x, y, rot}] (x/y None = to storage). Things not
    named stay where they are; the result as a whole must fit."""
    config = await get_config(db)
    villa = await _open(db, config, user.id)
    v = villa_config(config)
    items = {i.id: i for i in await _items(db, user.id)}
    for move in moves:
        item = items.get(move.get("id"))
        if item is None:
            raise NotFoundError("Этого предмета у тебя нет")
        x, y = move.get("x"), move.get("y")
        if (x is None) != (y is None):
            raise ConflictError("Нужны обе координаты")
        item.x, item.y = x, y
        item.rot = 1 if move.get("rot") else 0
    error = check_layout(grid_size(v, villa.villa_level), [(i.id, i.code, i.x, i.y, i.rot) for i in items.values()])
    if error:
        await db.rollback()
        raise ConflictError(error)
    db.add_all(items.values())
    await db.commit()
    return await _state(db, config, user, villa)


async def choose_car(db: AsyncSession, user: User, item_id: Optional[int]) -> dict:
    config = await get_config(db)
    villa = await _open(db, config, user.id)
    if item_id is not None:
        item = await db.get(UserTownVillaItem, item_id)
        if item is None or item.user_id != user.id or item.code not in ITEMS or ITEMS[item.code][2] != "car":
            raise NotFoundError("Этой машины у тебя нет")
    villa.car_item_id = item_id
    db.add(villa)
    await db.commit()
    return await _state(db, config, user, villa)


async def set_staff(db: AsyncSession, user: User, post: str, resident_id: Optional[int]) -> dict:
    """Puts a held resident of a fitting profession on a post (off any other)
    or frees the post. The rent so far is settled at the old prestige."""
    config = await get_config(db)
    if post not in POSTS:
        raise NotFoundError("Такой должности нет")
    if not config.town_residents_enabled:
        raise ConflictError("Жители сейчас отключены")
    await lock_user_for_update(db, user.id)
    villa = await _open(db, config, user.id)
    staff = {p: r for p, r in dict(villa.staff or {}).items() if p in POSTS and p != post and r != resident_id}
    if resident_id is not None:
        row = (await db.execute(select(UserTownResident).where(
            UserTownResident.user_id == user.id, UserTownResident.resident_id == resident_id, UserTownResident.copies > 0,
        ))).scalar_one_or_none()
        if row is None or not row.resident.is_active:
            raise NotFoundError("Этого жителя у тебя нет")
        if post not in staff_posts_for(row.resident.title):
            raise ConflictError(f"{row.resident.name} не подходит на пост «{POSTS[post][0]}»")
        staff[post] = resident_id
    await town_service._settle_before_population_change(db, config, user.id)
    villa.staff = staff
    db.add(villa)
    await db.commit()
    return await _state(db, config, user, villa)


# --- Stars ---------------------------------------------------------------------------------------

async def create_invoice(db: AsyncSession, user: User, code: str) -> dict:
    from app.models.pack import StarsInvoice
    from app.services.stars_payment_service import _request_telegram_invoice_link

    config = await get_config(db)
    villa = await _open(db, config, user.id)
    if code not in ITEMS:
        raise NotFoundError("Такого предмета нет")
    _, stars = item_price(villa_config(config), code)
    if stars <= 0:
        raise ConflictError("Этот предмет не продаётся за ⭐")
    ok, reason = await _available(db, config, user.id, code, villa)
    if not ok:
        raise ConflictError(reason)
    token = secrets.token_urlsafe(16)
    db.add(StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, academy_speedup=STARS_PREFIX + code))
    await db.flush()
    name, emoji, _, _, _ = ITEMS[code]
    link = await _request_telegram_invoice_link(token, f"{emoji} {name}", "Для твоей виллы в городе", stars)
    await db.commit()
    return {"invoice_link": link, "payload_token": token, "stars_amount": stars}


async def validate_invoice(db: AsyncSession, invoice) -> tuple[bool, str]:
    config = await get_config(db)
    code = invoice.academy_speedup[len(STARS_PREFIX):]
    if code not in ITEMS:
        return False, "Unknown order"
    if item_price(villa_config(config), code)[1] != invoice.stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    return await _available(db, config, invoice.user_id, code, await _villa(db, invoice.user_id))


async def deliver_invoice(db: AsyncSession, user: User, invoice) -> dict:
    """Under the invoice row lock; never refuses a taken payment (a second
    copy of a single item only goes to the ledger). The caller commits."""
    config = await get_config(db)
    code = invoice.academy_speedup[len(STARS_PREFIX):]
    item_id = None
    repeat = True
    if code in ITEMS:
        held = (await db.execute(select(UserTownVillaItem.id).where(
            UserTownVillaItem.user_id == user.id, UserTownVillaItem.code == code,
        ))).first()
        repeat = held is not None and ITEMS[code][2] in _SINGLE_KINDS
        if not repeat:
            await _ensure_villa(db, config, user.id)
            await town_service._settle_before_population_change(db, config, user.id)
            item = await _grant(db, user.id, code, villa_config(config).get(f"supply_{code}", 0))
            item_id = item.id
    db.add(TownLedger(user_id=user.id, kind="villa", building_code=code, result={"item_id": item_id, "repeat": repeat},
                      idempotency_key=f"stars-{invoice.payload_token}"))
    await db.flush()
    return {"kind": "town_villa", "code": code, "item_id": item_id}


# --- guests and «Вилла недели» -------------------------------------------------------------------

async def _villa_likes(db: AsyncSession, owner_id: int, since: Optional[date] = None) -> int:
    query = select(func.count()).select_from(TownVisit).where(TownVisit.owner_id == owner_id, TownVisit.villa_liked.is_(True))
    if since is not None:
        query = query.where(TownVisit.day >= since)
    return int((await db.execute(query)).scalar_one())


async def guest_view(db: AsyncSession, config, owner_id: int, visit: TownVisit) -> dict:
    """Someone's villa for a guest (read-only)."""
    villa = await _villa(db, owner_id)
    if villa is None:
        raise NotFoundError("Хозяин ещё не обустроил виллу")
    v = villa_config(config)
    staff = await _staff_rows(db, owner_id, villa) if config.town_residents_enabled else {}
    from app.services.town_social_service import week_days

    monday, _ = week_days(local_today())
    return {
        **_plot(v, villa, await _items(db, owner_id), staff),
        "user_id": owner_id, "liked": visit.villa_liked,
        "likes_total": await _villa_likes(db, owner_id), "likes_week": await _villa_likes(db, owner_id, monday),
    }


async def summary(db: AsyncSession, config, owner_id: int) -> Optional[dict]:
    """A line about someone's villa for the town visit (None — no villa)."""
    villa = await _villa(db, owner_id)
    if villa is None:
        return None
    prestige, _ = await prestige_for(db, config, owner_id)
    car = await db.get(UserTownVillaItem, villa.car_item_id) if villa.car_item_id else None
    return {"villa_level": villa.villa_level, "prestige": prestige,
            "car": car.code if car is not None and car.user_id == owner_id and car.code in ITEMS else None}


def villa_week_key(day: date) -> str:
    from app.services.town_social_service import week_key

    return "V" + week_key(day)


def _week_reward(v: dict, place: int) -> int:
    return v.get(f"villa_week_reward_{place}", 0)


async def _week_scores(db: AsyncSession, config, day: date) -> list[dict]:
    from datetime import datetime, timezone

    from app.services.town_social_service import _owner_name, social_config, week_days

    s = social_config(config)
    monday, sunday = week_days(day)
    old_enough = datetime.now(timezone.utc) - timedelta(days=s["week_min_account_days"])
    rows = (await db.execute(
        select(TownVisit.owner_id, func.count()).join(User, User.id == TownVisit.visitor_id)
        .where(TownVisit.day >= monday, TownVisit.day <= sunday, TownVisit.villa_liked.is_(True),
               User.created_at <= old_enough, User.is_banned.is_(False))
        .group_by(TownVisit.owner_id)
    )).all()
    if not rows:
        return []
    owners = {u.id: u for u in (await db.execute(select(User).where(User.id.in_([r[0] for r in rows])))).scalars()}
    villas = {x.user_id: x for x in (await db.execute(
        select(UserTownVilla).where(UserTownVilla.user_id.in_([r[0] for r in rows]))
    )).scalars()}
    out = [{"user_id": oid, "owner": _owner_name(owners.get(oid)), "likes": int(n),
            "villa_level": villas[oid].villa_level}
           for oid, n in rows if oid in owners and not owners[oid].is_banned and oid in villas]
    out.sort(key=lambda r: (-r["likes"], -r["villa_level"], r["user_id"]))
    for place, row in enumerate(out, start=1):
        row["place"] = place
    return out


async def settle_villa_week(db: AsyncSession, config, day: date) -> bool:
    key = villa_week_key(day)
    if await db.get(TownWeek, key) is not None:
        return False
    v = villa_config(config)
    ranking = await _week_scores(db, config, day)
    try:
        db.add(TownWeek(week=key))
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return False
    for row in ranking[:3]:
        coins = _week_reward(v, row["place"])
        user = await lock_user_for_update(db, row["user_id"])
        paid = 0 if user.game_rewards_blocked else coins
        if paid:
            await credit_coins(db, user, paid, TransactionType.town_week, f"«Вилла недели»: {row['place']} место",
                               related_object_type="town_villa_week", related_object_id=row["place"])
        db.add(TownWeekResult(week=key, place=row["place"], user_id=row["user_id"], score=row["likes"], coins=paid))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return False
    return True


async def villa_week(db: AsyncSession, user: User) -> dict:
    from app.services.town_social_service import _owner_name, week_days

    config = await get_config(db)
    town_service._require_enabled(config)
    v = villa_config(config)
    today = local_today()
    last_day = today - timedelta(days=7)
    await settle_villa_week(db, config, last_day)
    ranking = await _week_scores(db, config, today)
    last_key = villa_week_key(last_day)
    winners = (await db.execute(
        select(TownWeekResult).where(TownWeekResult.week == last_key).order_by(TownWeekResult.place).limit(3)
    )).scalars().all()
    names = {u.id: u for u in (await db.execute(
        select(User).where(User.id.in_([w.user_id for w in winners] or [0]))
    )).scalars()}
    _, sunday = week_days(today)
    return {
        "ends_on": sunday.isoformat(),
        "rewards": [{"place": p, "coins": _week_reward(v, p)} for p in (1, 2, 3)],
        "top": [{**r, "reward": _week_reward(v, r["place"]) if r["place"] <= 3 else 0} for r in ranking[:20]],
        "me": next((r for r in ranking if r["user_id"] == user.id), None),
        "last_week": [{"place": w.place, "user_id": w.user_id, "owner": _owner_name(names.get(w.user_id)),
                       "likes": w.score, "coins": w.coins} for w in winners],
    }
