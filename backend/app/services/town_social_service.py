"""«Город»: residents' quests and guests.

Quests («Задания жителей»): every local day a player with an opened town
gets GameConfig.town_social.quests_per_day small quests, each from one of
his residents (a settled one if he has any). Kinds:
  * claim      — collect the rent (town_ledger "income" rows of the day);
  * visit      — drop in on other towns (town_visits of the day);
  * like       — like someone's town;
  * play:<mode>— finish games of a mini-game (newbie_service.games_played,
                 minus the count when the quest was given).
A done quest pays quest_coins (a legendary resident's: quest_coins_legendary)
once; the row is unique per (user, day, slot), so a race never gives two.

Guests: any opened town can be visited (friends first in the list, then
random ones). One town_visits row per (visitor, owner, day) holds the like
and the gift. A like is free and counts for the town's rating. A gift costs
the guest gift_price coins, the owner gets gift_rent of them added to the
next rent collection (user_towns.gifts_pending) — the rest is burnt, so a
gift is no way to move coins between accounts; gifts_per_day a guest and
gifts_received_per_day a town.
"""
import random
from datetime import date, datetime, time, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import app_timezone, local_today
from app.models.enums import TransactionType
from app.models.town import TownLedger, TownResident, TownVisit, UserTown, UserTownQuest, UserTownResident
from app.models.user import User
from app.services import town_service
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

SOCIAL_DEFAULTS: dict[str, int] = {
    "quests_per_day": 3,
    "quest_coins": 60,
    "quest_coins_legendary": 120,
    "play_target": 2,           # games of the mode a «play» quest asks for
    "visit_target": 2,          # towns a «visit» quest asks to drop in on
    "gift_price": 300,          # what a gift costs the guest
    "gift_rent": 100,           # what the owner gets of it (the rest is burnt)
    "gifts_per_day": 3,         # gifts a guest can give a day
    "gifts_received_per_day": 5,
    "guests_listed": 12,        # towns in the guests list
}

# mode key (newbie_service.games_played) -> how a quest names it
PLAY_MODES: dict[str, str] = {
    "arena": "Card Arena",
    "game:penalty": "Пенальти",
    "game:free_kick": "Штрафной удар",
    "game:memory_sequence": "Memory Sequence",
    "game:football_hangman": "Футбольные буквы",
}
GUEST_KINDS = ("visit", "like")


def social_config(config) -> dict[str, int]:
    stored = getattr(config, "town_social", None) or {}
    out = dict(SOCIAL_DEFAULTS)
    for key, value in stored.items():
        if key in SOCIAL_DEFAULTS and isinstance(value, int) and not isinstance(value, bool):
            out[key] = max(0, value)
    out["gift_rent"] = min(out["gift_rent"], out["gift_price"])  # a gift never makes coins
    return out


def validate_social(raw: dict) -> dict:
    out: dict = {}
    for key, value in (raw or {}).items():
        if key not in SOCIAL_DEFAULTS:
            raise ValueError(f"неизвестный параметр «{key}»")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{key}: нужно целое число ≥ 0")
        out[key] = value
    if out.get("gift_rent", 0) > out.get("gift_price", SOCIAL_DEFAULTS["gift_price"]):
        raise ValueError("подарок не может приносить хозяину больше, чем стоит гостю")
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=app_timezone()).astimezone(timezone.utc)


def _owner_name(user: Optional[User]) -> str:
    if user is None:
        return "Игрок"
    return user.first_name or user.username or "Игрок"


async def _open_town(db: AsyncSession, config, user_id: int) -> UserTown:
    town = await db.get(UserTown, user_id)
    if not town_service.is_unlocked(config, town):
        raise ConflictError("Сначала открой город")
    return town


# --- quests --------------------------------------------------------------------------------------

def quest_label(kind: str, target: int) -> str:
    if kind == "claim":
        return "Собери ренту города"
    if kind == "visit":
        return f"Загляни в гости в {target} {'город' if target == 1 else 'города' if target < 5 else 'городов'}"
    if kind == "like":
        return "Поставь лайк чужому городу"
    if kind.startswith("play:"):
        times = "раза" if target % 10 in (2, 3, 4) and not 12 <= target % 100 <= 14 else "раз"
        return f"Сыграй {target} {times} в «{PLAY_MODES.get(kind[5:], kind[5:])}»"
    return kind


async def _progress(db: AsyncSession, user: User, quest: UserTownQuest) -> int:
    start = _day_start(quest.day)
    if quest.kind == "claim":
        return int((await db.execute(select(func.count()).select_from(TownLedger).where(
            TownLedger.user_id == user.id, TownLedger.kind == "income", TownLedger.created_at >= start,
        ))).scalar_one())
    if quest.kind in GUEST_KINDS:
        query = select(func.count()).select_from(TownVisit).where(TownVisit.visitor_id == user.id, TownVisit.day == quest.day)
        if quest.kind == "like":
            query = query.where(TownVisit.liked.is_(True))
        return int((await db.execute(query)).scalar_one())
    if quest.kind.startswith("play:"):
        from app.services.newbie_service import games_played

        return max(0, await games_played(db, user, quest.kind[5:]) - quest.baseline)
    return 0


async def _ensure_quests(db: AsyncSession, config, user: User, day: date) -> list[UserTownQuest]:
    rows = list((await db.execute(
        select(UserTownQuest).where(UserTownQuest.user_id == user.id, UserTownQuest.day == day).order_by(UserTownQuest.slot)
    )).scalars())
    s = social_config(config)
    if rows or s["quests_per_day"] <= 0:
        return rows
    rng = random.Random(f"{user.id}:{day.isoformat()}")
    owned = [r for r in await town_service._owned_residents(db, user.id) if r.copies > 0 and r.resident.is_active]
    settled = [r for r in owned if r.district]
    givers = settled or owned
    kinds = ["claim", rng.choice(GUEST_KINDS), f"play:{rng.choice(sorted(PLAY_MODES))}"]
    while len(kinds) < s["quests_per_day"]:
        kinds.append(f"play:{rng.choice(sorted(PLAY_MODES))}")
    from app.services.newbie_service import games_played

    for slot, kind in enumerate(kinds[:s["quests_per_day"]]):
        giver = rng.choice(givers) if givers else None
        legendary = giver is not None and giver.resident.rarity == "legendary"
        target = 1
        baseline = 0
        if kind == "visit":
            target = max(1, s["visit_target"])
        elif kind.startswith("play:"):
            target = max(1, s["play_target"])
            baseline = await games_played(db, user, kind[5:])
        rows.append(UserTownQuest(
            user_id=user.id, day=day, slot=slot, kind=kind, target=target, baseline=baseline,
            reward_coins=s["quest_coins_legendary"] if legendary else s["quest_coins"],
            resident_id=giver.resident_id if giver else None,
        ))
    try:
        db.add_all(rows)
        await db.commit()
    except IntegrityError:  # another request gave the day's quests first
        await db.rollback()
        rows = list((await db.execute(
            select(UserTownQuest).where(UserTownQuest.user_id == user.id, UserTownQuest.day == day).order_by(UserTownQuest.slot)
        )).scalars())
    return rows


async def _quest_out(db: AsyncSession, user: User, quest: UserTownQuest, residents: dict[int, TownResident]) -> dict:
    progress = min(quest.target, await _progress(db, user, quest))
    giver = residents.get(quest.resident_id) if quest.resident_id else None
    return {
        "id": quest.id, "kind": quest.kind, "label": quest_label(quest.kind, quest.target),
        "target": quest.target, "progress": progress, "reward_coins": quest.reward_coins,
        "done": progress >= quest.target, "claimed": quest.claimed_at is not None,
        "resident": {"id": giver.id, "name": giver.name, "icon": giver.icon, "image_path": giver.image_path,
                     "rarity": giver.rarity} if giver else None,
    }


async def quests(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    town_service._require_enabled(config)
    await _open_town(db, config, user.id)
    day = local_today()
    rows = await _ensure_quests(db, config, user, day)
    ids = [q.resident_id for q in rows if q.resident_id]
    residents = {r.id: r for r in (await db.execute(select(TownResident).where(TownResident.id.in_(ids)))).scalars()} if ids else {}
    return {"day": day.isoformat(), "quests": [await _quest_out(db, user, q, residents) for q in rows]}


async def claim_quest(db: AsyncSession, user: User, quest_id: int) -> dict:
    config = await get_config(db)
    town_service._require_enabled(config)
    locked_user = await lock_user_for_update(db, user.id)
    quest = (await db.execute(
        select(UserTownQuest).where(UserTownQuest.id == quest_id, UserTownQuest.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if quest is None or quest.day != local_today():
        raise NotFoundError("Это задание уже ушло — у жителей новые")
    if quest.claimed_at is not None:
        raise ConflictError("Награда уже получена")
    if await _progress(db, user, quest) < quest.target:
        raise ConflictError("Задание ещё не выполнено")
    quest.claimed_at = _now()
    paid = 0 if locked_user.game_rewards_blocked else quest.reward_coins
    if paid:
        await credit_coins(db, locked_user, paid, TransactionType.town_quest, "Город: задание жителя",
                           related_object_type="town_quest", related_object_id=quest.id)
    db.add(quest)
    await db.commit()
    return {**await quests(db, user), "paid": paid, "new_balance": locked_user.balance}


# --- guests --------------------------------------------------------------------------------------

async def _visit_row(db: AsyncSession, visitor_id: int, owner_id: int, day: date, lock: bool = False) -> TownVisit:
    query = select(TownVisit).where(TownVisit.visitor_id == visitor_id, TownVisit.owner_id == owner_id, TownVisit.day == day)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        row = TownVisit(visitor_id=visitor_id, owner_id=owner_id, day=day, liked=False, gift_coins=0)
        db.add(row)
        await db.flush()
    return row


async def _likes(db: AsyncSession, owner_id: int, day: Optional[date] = None) -> int:
    query = select(func.count()).select_from(TownVisit).where(TownVisit.owner_id == owner_id, TownVisit.liked.is_(True))
    if day is not None:
        query = query.where(TownVisit.day == day)
    return int((await db.execute(query)).scalar_one())


async def _gifts(db: AsyncSession, *, visitor_id: Optional[int] = None, owner_id: Optional[int] = None, day: date) -> int:
    query = select(func.count()).select_from(TownVisit).where(TownVisit.day == day, TownVisit.gift_coins > 0)
    if visitor_id is not None:
        query = query.where(TownVisit.visitor_id == visitor_id)
    if owner_id is not None:
        query = query.where(TownVisit.owner_id == owner_id)
    return int((await db.execute(query)).scalar_one())


async def guests(db: AsyncSession, user: User) -> dict:
    """Towns to visit: friends' first, then random opened towns."""
    from app.services.friend_service import friend_ids

    config = await get_config(db)
    town_service._require_enabled(config)
    s = social_config(config)
    day = local_today()
    friends = set(await friend_ids(db, user.id))
    opened = UserTown.unlocked_at.is_not(None) if config.town_unlock_coins > 0 else UserTown.user_id.is_not(None)
    picked: list[int] = []
    if friends:
        picked += list((await db.execute(
            select(UserTown.user_id).where(opened, UserTown.user_id.in_(friends)).limit(s["guests_listed"])
        )).scalars())
    if len(picked) < s["guests_listed"]:
        picked += list((await db.execute(
            select(UserTown.user_id).where(opened, UserTown.user_id != user.id, UserTown.user_id.not_in(picked or [0]))
            .order_by(func.random()).limit(s["guests_listed"] - len(picked))
        )).scalars())
    towns = {t.user_id: t for t in (await db.execute(select(UserTown).where(UserTown.user_id.in_(picked or [0])))).scalars()}
    owners = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(picked or [0])))).scalars()}
    houses = dict((await db.execute(
        select(town_service.UserTownHouse.user_id, func.count()).where(
            town_service.UserTownHouse.user_id.in_(picked or [0]),
            town_service.UserTownHouse.district != town_service.DECOR_DISTRICT,
        ).group_by(town_service.UserTownHouse.user_id)
    )).all())
    likes = dict((await db.execute(
        select(TownVisit.owner_id, func.count()).where(TownVisit.owner_id.in_(picked or [0]), TownVisit.liked.is_(True))
        .group_by(TownVisit.owner_id)
    )).all())
    mine = {v.owner_id: v for v in (await db.execute(
        select(TownVisit).where(TownVisit.visitor_id == user.id, TownVisit.day == day)
    )).scalars()}
    out = []
    for owner_id in picked:
        if owner_id == user.id or owner_id not in towns:
            continue
        visit = mine.get(owner_id)
        out.append({
            "user_id": owner_id, "name": towns[owner_id].name or f"Город {_owner_name(owners.get(owner_id))}",
            "owner": _owner_name(owners.get(owner_id)), "friend": owner_id in friends,
            "houses": int(houses.get(owner_id, 0)), "likes": int(likes.get(owner_id, 0)),
            "visited": visit is not None, "liked": bool(visit and visit.liked), "gifted": bool(visit and visit.gift_coins),
        })
    return {
        "towns": out,
        "gift_price": s["gift_price"], "gift_rent": s["gift_rent"],
        "gifts_left": max(0, s["gifts_per_day"] - await _gifts(db, visitor_id=user.id, day=day)),
        "likes_today": await _likes(db, user.id, day), "likes_total": await _likes(db, user.id),
    }


async def _view(db: AsyncSession, config, user: User, owner_id: int, visit: TownVisit) -> dict:
    s = social_config(config)
    day = local_today()
    town = await db.get(UserTown, owner_id)
    owner = await db.get(User, owner_id)
    houses = await town_service._houses(db, owner_id)
    places = await town_service._decor_owned(db, owner_id)
    residents = await town_service._owned_residents(db, owner_id) if config.town_residents_enabled else []
    moods = town_service.district_moods(config, town, houses, places, residents, _now())
    received = await _gifts(db, owner_id=owner_id, day=day)
    given = await _gifts(db, visitor_id=user.id, day=day)
    return {
        "user_id": owner_id, "name": town.name or f"Город {_owner_name(owner)}", "owner": _owner_name(owner),
        "districts": [
            {"code": code, "name": town_service.DISTRICT_NAMES[code], "owned": sum(1 for h in houses if h.district == code),
             "total": len(town_service.HOUSES[code]), "mood": moods[code]["mood"]}
            for code in town_service.HOUSES
        ],
        "places": sorted(places),
        "hotel": town.hotel_bought_at is not None,
        "population": sum(r.copies for r in residents if r.copies > 0 and r.resident.is_active),
        "likes_today": await _likes(db, owner_id, day), "likes_total": await _likes(db, owner_id),
        "liked": visit.liked, "gifted": visit.gift_coins > 0,
        "gift_price": s["gift_price"], "gift_rent": s["gift_rent"],
        "gifts_left": max(0, s["gifts_per_day"] - given),
        "can_gift": visit.gift_coins == 0 and given < s["gifts_per_day"] and received < s["gifts_received_per_day"]
        and s["gift_price"] > 0,
    }


async def _guest_target(db: AsyncSession, config, user: User, owner_id: int) -> None:
    town_service._require_enabled(config)
    if owner_id == user.id:
        raise ConflictError("Это твой город — гости приходят к тебе сами")
    town = await db.get(UserTown, owner_id)
    if town is None or not town_service.is_unlocked(config, town):
        raise NotFoundError("Этот город ещё закрыт")


async def visit(db: AsyncSession, user: User, owner_id: int) -> dict:
    config = await get_config(db)
    await _guest_target(db, config, user, owner_id)
    day = local_today()
    try:
        row = await _visit_row(db, user.id, owner_id, day)
        await db.commit()
    except IntegrityError:  # the same visit from a parallel request
        await db.rollback()
        row = await _visit_row(db, user.id, owner_id, day)
    return await _view(db, config, user, owner_id, row)


async def like(db: AsyncSession, user: User, owner_id: int) -> dict:
    config = await get_config(db)
    await _guest_target(db, config, user, owner_id)
    await lock_user_for_update(db, user.id)
    row = await _visit_row(db, user.id, owner_id, local_today(), lock=True)
    if row.liked:
        raise ConflictError("Сегодня ты уже ставил лайк этому городу")
    row.liked = True
    db.add(row)
    await db.commit()
    return await _view(db, config, user, owner_id, row)


async def gift(db: AsyncSession, user: User, owner_id: int) -> dict:
    """The guest pays gift_price, the owner gets gift_rent with his next rent."""
    config = await get_config(db)
    await _guest_target(db, config, user, owner_id)
    s = social_config(config)
    if s["gift_price"] <= 0:
        raise ConflictError("Подарки сейчас не дарятся")
    day = local_today()
    locked_user = await lock_user_for_update(db, user.id)
    row = await _visit_row(db, user.id, owner_id, day, lock=True)
    if row.gift_coins > 0:
        raise ConflictError("Сегодня ты уже дарил подарок этому городу")
    if await _gifts(db, visitor_id=user.id, day=day) >= s["gifts_per_day"]:
        raise ConflictError(f"Подарков на сегодня больше нет — {s['gifts_per_day']} в день")
    town = await town_service._get_town(db, owner_id)  # the owner's town row under a lock
    if await _gifts(db, owner_id=owner_id, day=day) >= s["gifts_received_per_day"]:
        raise ConflictError("Этому городу сегодня уже надарили — загляни завтра")
    await debit_coins(db, locked_user, s["gift_price"], TransactionType.town_gift, "Город: подарок в гости",
                      related_object_type="town_gift", related_object_id=owner_id)
    row.gift_coins = s["gift_rent"]
    town.gifts_pending = int(town.gifts_pending or 0) + s["gift_rent"]
    db.add_all([row, town])
    await db.commit()
    return {**await _view(db, config, user, owner_id, row), "new_balance": locked_user.balance}
