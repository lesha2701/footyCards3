"""«Академия» building: five wings a user upgrades with coins on a build
timer (Telegram Stars finish a construction now). One construction at a
time; a finished one is completed lazily on the next read/write. Effects
only touch «Академия» cards:

  * scout    — +percentage points to the «Академия» card chance of every
               slot in the «Академия» pack; unlocks a free scouting report
               every few days (a chance of an «Академия» card, else coins);
  * training — +% path experience for every «Академия» card;
  * dorm     — +free Card Arena attempts a day for every «Академия» card;
  * staff    — −% of every stage task target (rounded up, min 1);
  * hall     — +slots in the profile showcase.

Academy level = the sum of wing levels (leaderboard «Уровень Академии»).
Costs, build hours, effects, Stars per hour and the scouting report are
GameConfig.academy_* (lists per level). Coins and cards move under the user
row lock; every operation is journaled in academy_ledger with a unique
(user_id, idempotency_key).
"""
import math
import random
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card_path import AcademyLedger, UserAcademy
from app.models.enums import CardSource, Rarity, TransactionType
from app.models.user import User
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update


@dataclass(frozen=True)
class Wing:
    code: str
    name: str
    emoji: str
    about: str
    effect_text: str  # "{value}" = the effect at a level


WINGS: dict[str, Wing] = {w.code: w for w in (
    Wing("scout", "Скаутский отдел", "🔭", "Ищет таланты: больше карт «Академии» в её паке и бесплатный скаутский отчёт.",
         "+{value}% к шансу карты «Академии» в каждом слоте пака «Академия»"),
    Wing("training", "Тренировочная база", "🏋️", "Игроки «Академии» растут быстрее.",
         "+{value}% опыта картам «Академии»"),
    Wing("dorm", "Интернат", "🛏️", "Молодые игроки живут при клубе и больше тренируются.",
         "+{value} бесплатн. попыт. Арены в день каждой карте «Академии»"),
    Wing("staff", "Тренерский штаб", "📋", "Опытные наставники ускоряют переход между этапами.",
         "Цели заданий этапов меньше на {value}%"),
    Wing("hall", "Зал славы", "🏛️", "Место для ваших Икон и легенд.",
         "+{value} мест в витрине профиля"),
)}

SHOWCASE_BASE = 3


def _wing_config(config, code: str) -> dict:
    raw = (config.academy_buildings or {}).get(code) or {}
    return {k: [int(v) for v in (raw.get(k) or [])] for k in ("costs", "hours", "effect")}


def max_level(config, code: str) -> int:
    return len(_wing_config(config, code)["costs"])


def effect_at(config, code: str, level: int) -> int:
    values = _wing_config(config, code)["effect"]
    return values[level - 1] if 0 < level <= len(values) else 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def effective_levels(academy: Optional[UserAcademy], now: Optional[datetime] = None) -> dict[str, int]:
    """Wing levels counting a construction that has already finished (read
    paths use this without writing)."""
    if academy is None:
        return {}
    levels = {k: int(v) for k, v in (academy.levels or {}).items()}
    if academy.building_code and academy.build_ends_at and ensure_aware(academy.build_ends_at) <= (now or _now()):
        levels[academy.building_code] = max(levels.get(academy.building_code, 0), int(academy.building_to_level or 0))
    return levels


def effects_from_levels(levels: dict[str, int], config) -> dict[str, int]:
    if not getattr(config, "academy_enabled", True):
        return {code: 0 for code in WINGS}
    return {code: effect_at(config, code, levels.get(code, 0)) for code in WINGS}


async def user_effects(db: AsyncSession, user_id: int, config) -> dict[str, int]:
    academy = await db.get(UserAcademy, user_id)
    return effects_from_levels(effective_levels(academy), config)


def _complete_if_due(academy: UserAcademy, now: Optional[datetime] = None) -> Optional[dict]:
    if not academy.building_code or not academy.build_ends_at:
        return None
    if ensure_aware(academy.build_ends_at) > (now or _now()):
        return None
    return _finish(academy)


def _finish(academy: UserAcademy) -> dict:
    code, level = academy.building_code, int(academy.building_to_level or 0)
    levels = dict(academy.levels or {})
    levels[code] = max(int(levels.get(code, 0)), level)
    academy.levels = levels
    academy.total_level = sum(int(v) for v in levels.values())
    academy.building_code = academy.building_to_level = None
    academy.build_started_at = academy.build_ends_at = None
    return {"building_code": code, "level": level}


async def _get_academy(db: AsyncSession, user_id: int, lock: bool) -> UserAcademy:
    query = select(UserAcademy).where(UserAcademy.user_id == user_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    academy = (await db.execute(query)).scalar_one_or_none()
    if academy is None:
        academy = UserAcademy(user_id=user_id, levels={}, total_level=0)
        db.add(academy)
        await db.flush()
    return academy


def speedup_stars(academy: UserAcademy, config, now: Optional[datetime] = None) -> int:
    if not academy.build_ends_at:
        return 0
    remaining = (ensure_aware(academy.build_ends_at) - (now or _now())).total_seconds()
    if remaining <= 0:
        return 0
    return max(1, math.ceil(remaining / 3600) * int(config.academy_stars_per_hour))


def _scout(config, level: int) -> dict:
    raw = config.academy_scout_report or {}

    def at(key: str) -> int:
        values = [int(v) for v in (raw.get(key) or [])]
        return values[level - 1] if 0 < level <= len(values) else 0

    return {"chance_pct": at("chance_pct"), "cooldown_days": at("cooldown_days"), "consolation_coins": at("consolation_coins")}


def state_out(academy: UserAcademy, config, academy_cards: int = 0, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    levels = effective_levels(academy, now)
    building = academy.building_code if academy.building_code and academy.build_ends_at and \
        ensure_aware(academy.build_ends_at) > now else None
    wings = []
    for code, wing in WINGS.items():
        cfg = _wing_config(config, code)
        level, top = levels.get(code, 0), len(cfg["costs"])
        wings.append({
            "code": code, "name": wing.name, "emoji": wing.emoji, "about": wing.about,
            "level": level, "max_level": top,
            "effect": wing.effect_text.format(value=effect_at(config, code, level)) if level else None,
            "next_effect": wing.effect_text.format(value=effect_at(config, code, level + 1)) if level < top else None,
            "next_cost": cfg["costs"][level] if level < top else None,
            "next_hours": cfg["hours"][level] if level < top and level < len(cfg["hours"]) else None,
            "building": code == building,
        })
    scout_level = levels.get("scout", 0)
    scout = _scout(config, scout_level) if scout_level else None
    next_report_at = None
    if scout and academy.scout_report_at:
        next_report_at = ensure_aware(academy.scout_report_at) + timedelta(days=scout["cooldown_days"])
    return {
        "enabled": bool(config.academy_enabled),
        "level": sum(levels.values()),
        "max_level": sum(max_level(config, c) for c in WINGS),
        "wings": wings,
        "construction": {
            "building_code": building, "to_level": academy.building_to_level,
            "ends_at": ensure_aware(academy.build_ends_at).isoformat(),
            "remaining_seconds": max(0, int((ensure_aware(academy.build_ends_at) - now).total_seconds())),
            "speedup_stars": speedup_stars(academy, config, now),
        } if building else None,
        "scout_report": {
            "chance_pct": scout["chance_pct"], "consolation_coins": scout["consolation_coins"],
            "cooldown_days": scout["cooldown_days"],
            "available": next_report_at is None or next_report_at <= now,
            "next_at": next_report_at.isoformat() if next_report_at and next_report_at > now else None,
        } if scout else None,
        "effects": effects_from_levels(levels, config),
        "showcase_slots": SHOWCASE_BASE + effect_at(config, "hall", levels.get("hall", 0)),
        "academy_cards": academy_cards,
    }


async def _academy_cards(db: AsyncSession, user_id: int) -> int:
    from sqlalchemy import func

    from app.models.card import UserCard
    from app.models.player import Player

    return int((await db.execute(
        select(func.count(UserCard.id)).join(Player, Player.id == UserCard.player_id)
        .where(UserCard.owner_id == user_id, Player.path_talent_code.is_not(None))
    )).scalar_one())


async def _academy_card_list(db: AsyncSession, user_id: int) -> list[dict]:
    """The user's «Академия» cards for the academy screen, furthest along first."""
    from sqlalchemy.orm import joinedload

    from app.models.card import UserCard
    from app.models.player import Player
    from app.schemas.card import UserCardOut

    rows = (await db.execute(
        select(UserCard).join(Player, Player.id == UserCard.player_id).options(joinedload(UserCard.player))
        .where(UserCard.owner_id == user_id, Player.path_talent_code.is_not(None))
        .order_by(UserCard.path_stage.desc(), UserCard.path_level.desc(), UserCard.prestige.desc(), UserCard.id)
        .limit(60)
    )).unique().scalars().all()
    return [UserCardOut.model_validate(c).model_dump(mode="json") for c in rows]


async def get_state(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    academy = await db.get(UserAcademy, user.id)
    if academy is None:
        academy = UserAcademy(user_id=user.id, levels={}, total_level=0)
    cards = await _academy_card_list(db, user.id)
    return {**state_out(academy, config, len(cards)), "cards": cards}


async def _replay(db: AsyncSession, user_id: int, key: Optional[str]) -> bool:
    if not key:
        return False
    return (await db.execute(select(AcademyLedger.id).where(
        AcademyLedger.user_id == user_id, AcademyLedger.idempotency_key == key,
    ))).first() is not None


async def start_upgrade(db: AsyncSession, user: User, code: str, idempotency_key: Optional[str]) -> dict:
    config = await get_config(db)
    if not config.academy_enabled:
        raise ConflictError("Академия сейчас закрыта")
    if code not in WINGS:
        raise NotFoundError("Такого корпуса нет")
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await get_state(db, user), "new_balance": locked_user.balance}
    academy = await _get_academy(db, user.id, lock=True)
    _complete_if_due(academy)
    if academy.building_code:
        raise ConflictError(f"Сейчас строится «{WINGS[academy.building_code].name}» — дождись или ускорь",
                            details={"building_code": academy.building_code})
    cfg = _wing_config(config, code)
    level = int((academy.levels or {}).get(code, 0))
    if level >= len(cfg["costs"]):
        raise ConflictError("Корпус уже на максимальном уровне")
    cost = cfg["costs"][level]
    hours = cfg["hours"][level] if level < len(cfg["hours"]) else 0
    if cost:
        await debit_coins(db, locked_user, cost, TransactionType.academy_upgrade,
                          f"Академия: {WINGS[code].name}, уровень {level + 1}")
    now = _now()
    academy.building_code, academy.building_to_level = code, level + 1
    academy.build_started_at, academy.build_ends_at = now, now + timedelta(hours=hours)
    finished = _finish(academy) if hours <= 0 else None
    db.add_all([academy, AcademyLedger(
        user_id=user.id, kind="upgrade", building_code=code, to_level=level + 1, coins_spent=cost,
        result={"hours": hours, **({"finished": True} if finished else {})}, idempotency_key=idempotency_key,
    )])
    await db.commit()
    return {**await get_state(db, user), "new_balance": locked_user.balance}


async def create_speedup_invoice(db: AsyncSession, user: User) -> dict:
    """Telegram Stars invoice finishing the current construction now. The
    price (by the remaining hours) is frozen on the invoice."""
    from app.models.pack import StarsInvoice
    from app.services.stars_payment_service import _request_telegram_invoice_link

    config = await get_config(db)
    if not config.academy_enabled:
        raise ConflictError("Академия сейчас закрыта")
    academy = await db.get(UserAcademy, user.id)
    if academy is None or not academy.building_code or _complete_if_due(academy) is not None:
        if academy is not None:
            db.add(academy)
            await db.commit()
        raise ConflictError("Сейчас ничего не строится")
    stars = speedup_stars(academy, config)
    key = f"{academy.building_code}:{academy.building_to_level}"
    token = secrets.token_urlsafe(16)
    db.add(StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, academy_speedup=key))
    await db.flush()
    link = await _request_telegram_invoice_link(
        token, "Ускорить стройку", f"Академия: {WINGS[academy.building_code].name} — уровень {academy.building_to_level} сразу",
        stars,
    )
    await db.commit()
    return {"invoice_link": link, "payload_token": token, "stars_amount": stars}


async def deliver_speedup(db: AsyncSession, user: User, invoice) -> dict:
    """Called by stars_payment_service.deliver_payment under the invoice
    lock. Finishes that exact construction; if it already finished on its
    own meanwhile, the payment is still recorded (nothing left to speed up)."""
    academy = await _get_academy(db, user.id, lock=True)
    code, _, level = (invoice.academy_speedup or "").partition(":")
    finished = None
    if academy.building_code == code and str(academy.building_to_level) == level:
        finished = _finish(academy)
    else:
        _complete_if_due(academy)
    db.add_all([academy, AcademyLedger(
        user_id=user.id, kind="speedup", building_code=code, to_level=int(level or 0), stars_spent=invoice.stars_amount,
        result={"finished": bool(finished)}, idempotency_key=f"stars-{invoice.payload_token}",
    )])
    await db.flush()
    return {"kind": "academy_speedup", "building_code": code, "finished": bool(finished)}


async def claim_scout_report(db: AsyncSession, user: User, idempotency_key: Optional[str]) -> dict:
    """Free scouting report: a chance of an «Академия» card (the same pool as
    the «Академия» pack), coins otherwise. Every few days, by scout level."""
    from app.models.card import UserCard
    from app.services.card_creation import create_user_card
    from app.services.pack_service import path_pool_ready, pick_random_player

    config = await get_config(db)
    if not config.academy_enabled:
        raise ConflictError("Академия сейчас закрыта")
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await get_state(db, user), "report": None, "new_balance": locked_user.balance}
    academy = await _get_academy(db, user.id, lock=True)
    _complete_if_due(academy)
    level = int((academy.levels or {}).get("scout", 0))
    if level <= 0:
        raise ConflictError("Сначала построй скаутский отдел")
    scout = _scout(config, level)
    now = _now()
    if academy.scout_report_at and ensure_aware(academy.scout_report_at) + timedelta(days=scout["cooldown_days"]) > now:
        raise ConflictError("Следующий скаутский отчёт ещё не готов")
    report: dict = {}
    if random.random() * 100 < scout["chance_pct"] and await path_pool_ready(db):
        player = await pick_random_player(db, Rarity.diamond, "path")
        card: UserCard = await create_user_card(db, user.id, player.id, CardSource.game_reward)
        report = {"card_id": card.id, "player_id": player.id, "player_name": player.display_name}
    else:
        coins = scout["consolation_coins"]
        if coins and not locked_user.game_rewards_blocked:
            await credit_coins(db, locked_user, coins, TransactionType.academy_scout_reward, "Академия: скаутский отчёт")
        report = {"coins": coins}
    academy.scout_report_at = now
    db.add_all([academy, AcademyLedger(
        user_id=user.id, kind="report", building_code="scout", to_level=level, result=report,
        idempotency_key=idempotency_key,
    )])
    await db.commit()
    return {**await get_state(db, user), "report": report, "new_balance": locked_user.balance}
