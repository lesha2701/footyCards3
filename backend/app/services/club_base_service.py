"""«Клубная база»: the player's own training campus around the «Академия».
Ten buildings with levels, upgraded for coins on a build timer (Telegram
Stars finish one now). The whole base — the «Академия» wings included — has
ONE construction queue; a finished construction is completed lazily on the
next read/write, or by the bot's sweep (POST /internal/club-base/sweep),
which also notifies the player.

Buildings (effects are GameConfig.club_base_buildings lists per level,
summed by name and clamped by GameConfig.club_base_caps):

  * hq         — Штаб-квартира: every other base building is capped at its level;
  * stadium    — Стадион: coins for every home league match of «Карьера
                 тренера» (capacity and the look are cosmetic);
  * hotel      — Клубный отель: +% to that matchday income;
  * training   — Тренировочный центр: +% familiarity growth in «Карьера
                 тренера», +% XP of «Мой игрок» trainings;
  * medical    — Медцентр: −% injury chance, +fatigue recovery (career);
  * analytics  — Аналитический центр: the «Разбор соперника» / «Стандарты»
                 trainings work N% stronger (career);
  * media      — Медиацентр: +% to positive career reputation;
  * marketing  — Отдел маркетинга (финансовый департамент): sponsor coins a
                 day, +% ticket income on matchday;
  * shop       — Клубный магазин: merchandise coins a day, +% quick-sell price;
  * accounting — Бухгалтерия: −% to every construction cost (base and «Академия»).

Career effects are frozen per season (CareerParticipant.base_effects, taken
at the participant's first round), so a building finished mid-season helps
from the next season on. Coins move under the user row lock; every
operation is journaled in club_base_ledger with a unique (user_id,
idempotency_key).
"""
import math
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card_path import UserAcademy
from app.models.club_base import ClubBaseLedger, UserClubBase
from app.models.enums import NotificationType, TransactionType
from app.models.game_config import DEFAULT_CLUB_BASE_BUILDINGS, DEFAULT_CLUB_BASE_CAPS
from app.models.user import User
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update


@dataclass(frozen=True)
class Building:
    code: str
    name: str
    emoji: str
    about: str
    group: str  # "core" | "finance" — the finance department is one complex on the map
    # effect name -> text with "{value}" (the effect at a level)
    effects: dict[str, str] = field(default_factory=dict)


BUILDINGS: dict[str, Building] = {b.code: b for b in (
    Building("hq", "Штаб-квартира", "🏢", "Администрация клуба. Без неё остальные корпуса не растут.", "core",
             {"cap": "Корпуса базы до уровня {value}"}),
    Building("stadium", "Стадион", "🏟️", "Сердце базы: трибуны, крыша, подсветка — и выручка в дни матчей.", "core",
             {"matchday": "+{value} монет за домашний матч лиги «Карьеры тренера»",
              "capacity": "Вместимость {value} зрителей"}),
    Building("hotel", "Клубный отель", "🏨", "Болельщики и гости приезжают на матч с ночёвкой.", "core",
             {"matchday_pct": "+{value}% к доходу с домашних матчей"}),
    Building("training", "Тренировочный центр", "⚽", "Поля, спортзал и аналитика нагрузок.", "core",
             {"familiarity_pct": "Сыгранность в карьере растёт на {value}% быстрее",
              "my_player_xp_pct": "+{value}% опыта «Моему игроку» за тренировку"}),
    Building("medical", "Медцентр", "🩺", "Реабилитация, гидротерапия и криокамеры.", "core",
             {"injury_pct": "Травмы в карьере на {value}% реже",
              "recovery": "+{value} к восстановлению усталости между турами"}),
    Building("analytics", "Аналитический центр", "📊", "Видеоразбор соперников и стандартов.", "core",
             {"prep_pct": "Тренировки «Разбор соперника» и «Стандарты» сильнее на {value}%"}),
    Building("media", "Медиацентр", "🎙️", "Пресс-зона и клубное ТВ — о тебе говорят.", "core",
             {"rep_pct": "+{value}% к росту репутации в карьере"}),
    Building("marketing", "Отдел маркетинга", "📣", "Спонсоры, реклама и продажа билетов.", "finance",
             {"daily": "Спонсоры: +{value} монет в день",
              "matchday_pct": "Цены на билеты: +{value}% к доходу с домашних матчей"}),
    Building("shop", "Клубный магазин", "👕", "Форма и атрибутика для болельщиков.", "finance",
             {"daily": "Мерч: +{value} монет в день",
              "sell_pct": "+{value}% к цене быстрой продажи карт"}),
    Building("accounting", "Бухгалтерия", "🧮", "Считает каждую монету и экономит на стройке.", "finance",
             {"discount_pct": "Стройка на базе и в Академии дешевле на {value}%"}),
)}

# Not effects: what a level costs, takes, or only shows.
_NOT_EFFECTS = {"costs", "hours", "cap", "capacity"}

# Stadium look: seat colours are free; the rest needs the stadium level.
SEAT_COLORS = ("red", "blue", "sky", "green", "yellow", "white", "black", "purple", "orange")
ROOF_LEVEL = {"none": 0, "canopy": 2, "full": 4}
LIGHTS_LEVEL = 3
SCREEN_LEVEL = 5
DEFAULT_LOOK = {"seats": "red", "roof": "none", "lights": False, "screen": False}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- config --------------------------------------------------------------------------------------

def _building_config(config, code: str) -> dict[str, list[int]]:
    raw = (config.club_base_buildings or {}).get(code)
    if raw is None:
        raw = DEFAULT_CLUB_BASE_BUILDINGS.get(code) or {}
    return {k: [int(v) for v in (values or [])] for k, values in raw.items() if isinstance(values, list)}


def max_level(config, code: str) -> int:
    return len(_building_config(config, code).get("costs", []))


def value_at(config, code: str, name: str, level: int) -> int:
    values = _building_config(config, code).get(name, [])
    return values[level - 1] if 0 < level <= len(values) else 0


def _caps(config) -> dict[str, int]:
    return {**DEFAULT_CLUB_BASE_CAPS, **{k: int(v) for k, v in (config.club_base_caps or {}).items()}}


def validate_buildings(raw: dict) -> dict:
    """Admin input for GameConfig.club_base_buildings: known buildings only,
    costs/hours and every effect list of the same length (1..10 levels),
    non-negative integers."""
    out: dict = {}
    for code, cfg in (raw or {}).items():
        if code not in BUILDINGS:
            raise ValueError(f"неизвестный корпус «{code}»")
        if not isinstance(cfg, dict):
            raise ValueError(f"{code}: нужен объект")
        costs = cfg.get("costs") or []
        if not 1 <= len(costs) <= 10:
            raise ValueError(f"{code}: от 1 до 10 уровней")
        lists: dict[str, list[int]] = {}
        for name, values in cfg.items():
            if name not in ("costs", "hours") and name not in BUILDINGS[code].effects:
                raise ValueError(f"{code}: неизвестный эффект «{name}»")
            if not isinstance(values, list) or len(values) != len(costs):
                raise ValueError(f"{code}.{name}: нужно {len(costs)} значений — по одному на уровень")
            ints = [int(v) for v in values]
            if any(v < 0 for v in ints):
                raise ValueError(f"{code}.{name}: значения не могут быть отрицательными")
            lists[name] = ints
        out[code] = lists
    return out


# --- levels & effects -----------------------------------------------------------------------------

def _due(base: UserClubBase, now: datetime) -> bool:
    return bool(base.building_code and base.build_ends_at and ensure_aware(base.build_ends_at) <= now)


def effective_levels(base: Optional[UserClubBase], now: Optional[datetime] = None) -> dict[str, int]:
    """Building levels counting a construction that has already finished
    (read paths use this without writing)."""
    if base is None:
        return {}
    levels = {k: int(v) for k, v in (base.levels or {}).items()}
    if _due(base, now or _now()):
        levels[base.building_code] = max(levels.get(base.building_code, 0), int(base.building_to_level or 0))
    return levels


def effects_from_levels(levels: dict[str, int], config) -> dict[str, int]:
    """Every effect summed over the buildings, clamped by club_base_caps."""
    if not getattr(config, "club_base_enabled", True):
        return {}
    totals: dict[str, int] = {}
    for code in BUILDINGS:
        level = levels.get(code, 0)
        if level <= 0:
            continue
        for name, values in _building_config(config, code).items():
            if name in _NOT_EFFECTS:
                continue
            totals[name] = totals.get(name, 0) + (values[level - 1] if level <= len(values) else 0)
    caps = _caps(config)
    return {name: min(value, caps[name]) if name in caps else value for name, value in totals.items()}


def level_cap(levels: dict[str, int], config, code: str) -> int:
    """How high `code` may go now: the HQ itself up to its max, everything
    else up to the HQ's cap effect."""
    top = max_level(config, code)
    if code == "hq":
        return top
    return min(top, value_at(config, "hq", "cap", levels.get("hq", 0)))


async def user_effects(db: AsyncSession, user_id: int, config=None) -> dict[str, int]:
    """Current effects (what non-season systems use: «Мой игрок» training,
    quick sell, construction discount)."""
    config = config or await get_config(db)
    base = await db.get(UserClubBase, user_id)
    return effects_from_levels(effective_levels(base), config)


async def construction_discount_pct(db: AsyncSession, user_id: int, config=None) -> int:
    return (await user_effects(db, user_id, config)).get("discount_pct", 0)


def discounted(cost: int, discount_pct: int) -> int:
    return cost - cost * max(0, discount_pct) // 100


# --- career («Карьера тренера») ---------------------------------------------------------------------

async def career_effects(db: AsyncSession, part, config) -> dict[str, int]:
    """The base effects one career participant plays the season with: taken
    from the base the first time they are needed (the first round) and kept
    on the participant row, so later constructions wait for next season."""
    if part.base_effects is None:
        part.base_effects = await user_effects(db, part.user_id, config)
        db.add(part)
    return dict(part.base_effects or {})


def matchday_income(effects: dict) -> int:
    base = int(effects.get("matchday", 0))
    return base * (100 + int(effects.get("matchday_pct", 0))) // 100


def injury_chance(chance_pct: float, effects: dict) -> float:
    return chance_pct * (100 - int(effects.get("injury_pct", 0))) / 100


def familiarity_step(step: int, effects: dict) -> int:
    return step * (100 + int(effects.get("familiarity_pct", 0))) // 100


def prep_boost(boost: float, effects: dict) -> float:
    """«Разбор соперника» / «Стандарты»: the part above 1.0 grows by prep_pct."""
    if boost <= 1.0:
        return boost
    return 1.0 + (boost - 1.0) * (100 + int(effects.get("prep_pct", 0))) / 100


def reputation_gain(rep: int, effects: dict) -> int:
    return rep + rep * int(effects.get("rep_pct", 0)) // 100 if rep > 0 else rep


# --- income --------------------------------------------------------------------------------------

def _income_cap(rate: int, config) -> int:
    return rate * max(1, int(config.club_base_income_max_days))


def _settle_income(base: UserClubBase, rate: int, config, now: datetime) -> None:
    """Moves income earned since income_since (at `rate` coins a day) into
    income_accrued. The unpaid fraction of a coin stays in the clock."""
    if base.income_since is None:
        base.income_since = now
        return
    since = ensure_aware(base.income_since)
    if now <= since:
        return
    cap = _income_cap(rate, config)
    if rate <= 0 or base.income_accrued >= cap:
        base.income_since = now
        return
    gained = int(rate * (now - since).total_seconds() // 86400)
    base.income_accrued = min(cap, base.income_accrued + gained)
    if base.income_accrued >= cap:
        base.income_since = now
    else:
        base.income_since = since + timedelta(seconds=gained * 86400 / rate)


def pending_income(base: UserClubBase, rate: int, config, now: datetime) -> int:
    """What claiming would pay now (read-only)."""
    accrued = int(base.income_accrued or 0)
    if base.income_since is None or rate <= 0:
        return accrued
    seconds = max(0.0, (now - ensure_aware(base.income_since)).total_seconds())
    return min(_income_cap(rate, config), accrued + int(rate * seconds // 86400))


# --- construction --------------------------------------------------------------------------------

def _finish(base: UserClubBase, config) -> dict:
    """Completes the current construction. Income is settled at the old
    rate up to the moment the building was finished, then runs at the new."""
    code, level = base.building_code, int(base.building_to_level or 0)
    finished_at = ensure_aware(base.build_ends_at) if base.build_ends_at else _now()
    old_rate = effects_from_levels({k: int(v) for k, v in (base.levels or {}).items()}, config).get("daily", 0)
    _settle_income(base, old_rate, config, min(finished_at, _now()))
    levels = dict(base.levels or {})
    levels[code] = max(int(levels.get(code, 0)), level)
    base.levels = levels
    base.total_level = sum(int(v) for v in levels.values())
    base.building_code = base.building_to_level = None
    base.build_started_at = base.build_ends_at = None
    return {"building_code": code, "level": level}


def _complete_if_due(base: UserClubBase, config, now: Optional[datetime] = None) -> Optional[dict]:
    return _finish(base, config) if _due(base, now or _now()) else None


async def _get_base(db: AsyncSession, user_id: int, lock: bool) -> UserClubBase:
    query = select(UserClubBase).where(UserClubBase.user_id == user_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    base = (await db.execute(query)).scalar_one_or_none()
    if base is None:
        base = UserClubBase(user_id=user_id, levels={}, total_level=0, appearance=dict(DEFAULT_LOOK),
                            income_accrued=0, income_since=_now())
        db.add(base)
        await db.flush()
    return base


def _academy_busy(academy: Optional[UserAcademy], now: datetime) -> bool:
    return bool(academy and academy.building_code and academy.build_ends_at
                and ensure_aware(academy.build_ends_at) > now)


async def base_busy(db: AsyncSession, user_id: int) -> Optional[str]:
    """Name of the base building under construction, if any (the «Академия»
    checks this before starting one of its wings — one queue for both)."""
    base = await db.get(UserClubBase, user_id)
    if base is None or not base.building_code or not base.build_ends_at:
        return None
    if ensure_aware(base.build_ends_at) <= _now():
        return None
    return BUILDINGS[base.building_code].name if base.building_code in BUILDINGS else base.building_code


def speedup_stars(base: UserClubBase, config, now: Optional[datetime] = None) -> int:
    if not base.build_ends_at:
        return 0
    remaining = (ensure_aware(base.build_ends_at) - (now or _now())).total_seconds()
    if remaining <= 0:
        return 0
    return max(1, math.ceil(remaining / 3600) * int(config.club_base_stars_per_hour))


def art_out(config) -> dict:
    art = config.club_base_art or {}
    return {"background": art.get("background"), "buildings": dict(art.get("buildings") or {})}


def _look(base: UserClubBase, stadium_level: int) -> dict:
    """The saved look with anything the stadium level no longer allows
    switched off (admin may have shortened the level list)."""
    look = {**DEFAULT_LOOK, **(base.appearance or {})}
    if ROOF_LEVEL.get(look["roof"], 99) > stadium_level:
        look["roof"] = "none"
    look["lights"] = bool(look["lights"]) and stadium_level >= LIGHTS_LEVEL
    look["screen"] = bool(look["screen"]) and stadium_level >= SCREEN_LEVEL
    if look["seats"] not in SEAT_COLORS:
        look["seats"] = DEFAULT_LOOK["seats"]
    return look


def state_out(base: UserClubBase, academy: Optional[UserAcademy], config, now: Optional[datetime] = None) -> dict:
    from app.services import academy_service

    now = now or _now()
    levels = effective_levels(base, now)
    effects = effects_from_levels(levels, config)
    discount = effects.get("discount_pct", 0)
    building = base.building_code if base.building_code and not _due(base, now) else None
    buildings = []
    for code, b in BUILDINGS.items():
        cfg = _building_config(config, code)
        level, top, cap = levels.get(code, 0), max_level(config, code), level_cap(levels, config, code)
        effect_names = [n for n in b.effects if n in cfg]

        def texts(at: int) -> list[str]:
            return [b.effects[n].format(value=f"{value_at(config, code, n, at):,}".replace(",", " ")) for n in effect_names]

        next_cost = cfg["costs"][level] if level < top and "costs" in cfg else None
        buildings.append({
            "code": code, "name": b.name, "emoji": b.emoji, "about": b.about, "group": b.group,
            "level": level, "max_level": top, "cap_level": cap,
            "effects": texts(level) if level else [],
            "next_effects": texts(level + 1) if level < top else [],
            "next_cost": discounted(next_cost, discount) if next_cost is not None else None,
            "next_cost_full": next_cost,
            "next_hours": cfg["hours"][level] if level < top and level < len(cfg.get("hours", [])) else None,
            "locked": level < top and level >= cap,
            "building": code == building,
        })
    construction = None
    if building:
        construction = {
            "owner": "base", "building_code": building, "name": BUILDINGS[building].name,
            "emoji": BUILDINGS[building].emoji, "to_level": base.building_to_level,
            "ends_at": ensure_aware(base.build_ends_at).isoformat(),
            "remaining_seconds": max(0, int((ensure_aware(base.build_ends_at) - now).total_seconds())),
            "speedup_stars": speedup_stars(base, config, now),
        }
    elif _academy_busy(academy, now):
        wing = academy_service.WINGS.get(academy.building_code)
        construction = {
            "owner": "academy", "building_code": academy.building_code,
            "name": f"Академия: {wing.name if wing else academy.building_code}",
            "emoji": wing.emoji if wing else "🌱", "to_level": academy.building_to_level,
            "ends_at": ensure_aware(academy.build_ends_at).isoformat(),
            "remaining_seconds": max(0, int((ensure_aware(academy.build_ends_at) - now).total_seconds())),
            "speedup_stars": academy_service.speedup_stars(academy, config, now),
        }
    rate = effects.get("daily", 0)
    academy_levels = academy_service.effective_levels(academy, now)
    academy_level = sum(academy_levels.values())
    academy_max = sum(academy_service.max_level(config, c) for c in academy_service.WINGS)
    stadium_level = levels.get("stadium", 0)
    base_level = sum(levels.values())
    return {
        "enabled": bool(config.club_base_enabled),
        "level": base_level,
        "max_level": sum(max_level(config, c) for c in BUILDINGS),
        "academy_level": academy_level,
        "academy_max_level": academy_max,
        "total_level": base_level + academy_level,
        "buildings": buildings,
        "construction": construction,
        "income": {
            "daily": rate,
            "pending": pending_income(base, rate, config, now),
            "cap": _income_cap(rate, config),
            "max_days": int(config.club_base_income_max_days),
        },
        "stadium": {
            "level": stadium_level,
            "capacity": value_at(config, "stadium", "capacity", stadium_level),
            "matchday_income": matchday_income(effects),
            "look": _look(base, stadium_level),
            "seat_colors": list(SEAT_COLORS),
            "unlocks": {"roof_canopy": ROOF_LEVEL["canopy"], "roof_full": ROOF_LEVEL["full"],
                        "lights": LIGHTS_LEVEL, "screen": SCREEN_LEVEL},
        },
        "effects": effects,
        "art": art_out(config),
    }


async def get_state(db: AsyncSession, user: User) -> dict:
    """The base screen. A construction that is due is completed here (under
    the base row lock) so the level, income rate and journal are written."""
    config = await get_config(db)
    base = await db.get(UserClubBase, user.id)
    if base is not None and _due(base, _now()):
        base = await _get_base(db, user.id, lock=True)
        done = _complete_if_due(base, config)
        if done:
            db.add_all([base, _ledger_complete(user.id, done)])
            await db.commit()
    if base is None:
        base = UserClubBase(user_id=user.id, levels={}, total_level=0, appearance=dict(DEFAULT_LOOK),
                            income_accrued=0, income_since=None)
    academy = await db.get(UserAcademy, user.id)
    return state_out(base, academy, config)


def _ledger_complete(user_id: int, done: dict) -> ClubBaseLedger:
    return ClubBaseLedger(user_id=user_id, kind="complete", building_code=done["building_code"],
                          to_level=done["level"], result={})


async def _replay(db: AsyncSession, user_id: int, key: Optional[str]) -> bool:
    if not key:
        return False
    return (await db.execute(select(ClubBaseLedger.id).where(
        ClubBaseLedger.user_id == user_id, ClubBaseLedger.idempotency_key == key,
    ))).first() is not None


def _require_enabled(config) -> None:
    if not config.club_base_enabled:
        raise ConflictError("Клубная база сейчас закрыта")


async def start_upgrade(db: AsyncSession, user: User, code: str, idempotency_key: Optional[str]) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    if code not in BUILDINGS:
        raise NotFoundError("Такого корпуса нет")
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await get_state(db, user), "new_balance": locked_user.balance}
    base = await _get_base(db, user.id, lock=True)
    now = _now()
    done = _complete_if_due(base, config, now)
    if done:
        db.add(_ledger_complete(user.id, done))
    if base.building_code:
        raise ConflictError(f"Сейчас строится «{BUILDINGS[base.building_code].name}» — дождись или ускорь",
                            details={"building_code": base.building_code})
    academy = await db.get(UserAcademy, user.id)
    if _academy_busy(academy, now):
        from app.services.academy_service import WINGS

        wing = WINGS.get(academy.building_code)
        raise ConflictError(
            f"Сейчас строится «Академия: {wing.name if wing else academy.building_code}» — у базы одна бригада",
            details={"building_code": academy.building_code},
        )
    levels = {k: int(v) for k, v in (base.levels or {}).items()}
    level, top = levels.get(code, 0), max_level(config, code)
    if level >= top:
        raise ConflictError("Корпус уже на максимальном уровне")
    if level >= level_cap(levels, config, code):
        raise ConflictError("Сначала улучши штаб-квартиру" if levels.get("hq", 0) else "Сначала построй штаб-квартиру")
    cfg = _building_config(config, code)
    full_cost = cfg["costs"][level]
    cost = discounted(full_cost, effects_from_levels(levels, config).get("discount_pct", 0))
    hours = cfg["hours"][level] if level < len(cfg.get("hours", [])) else 0
    if cost:
        await debit_coins(db, locked_user, cost, TransactionType.club_base_upgrade,
                          f"Клубная база: {BUILDINGS[code].name}, уровень {level + 1}")
    base.building_code, base.building_to_level = code, level + 1
    base.build_started_at, base.build_ends_at = now, now + timedelta(hours=hours)
    finished = _finish(base, config) if hours <= 0 else None
    db.add_all([base, ClubBaseLedger(
        user_id=user.id, kind="upgrade", building_code=code, to_level=level + 1, coins_spent=cost,
        result={"hours": hours, "full_cost": full_cost, **({"finished": True} if finished else {})},
        idempotency_key=idempotency_key,
    )])
    await db.commit()
    return {**await get_state(db, user), "new_balance": locked_user.balance}


async def claim_income(db: AsyncSession, user: User, idempotency_key: Optional[str]) -> dict:
    """Sponsors + merchandise: pays what accrued (at most income_max_days)."""
    config = await get_config(db)
    _require_enabled(config)
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await get_state(db, user), "claimed": 0, "new_balance": locked_user.balance}
    base = await _get_base(db, user.id, lock=True)
    done = _complete_if_due(base, config)
    if done:
        db.add(_ledger_complete(user.id, done))
    rate = effects_from_levels({k: int(v) for k, v in (base.levels or {}).items()}, config).get("daily", 0)
    _settle_income(base, rate, config, _now())
    amount = int(base.income_accrued or 0)
    if amount <= 0:
        raise ConflictError("Пока нечего забирать — доход копится каждый день")
    base.income_accrued = 0
    paid = 0 if locked_user.game_rewards_blocked else amount
    if paid:
        await credit_coins(db, locked_user, paid, TransactionType.club_base_income,
                           "Клубная база: спонсоры и клубный магазин")
    db.add_all([base, ClubBaseLedger(
        user_id=user.id, kind="income", coins_earned=paid, result={"accrued": amount},
        idempotency_key=idempotency_key,
    )])
    await db.commit()
    return {**await get_state(db, user), "claimed": paid, "new_balance": locked_user.balance}


async def set_look(db: AsyncSession, user: User, look: dict) -> dict:
    """Stadium look — free, but roof/lights/screen need the stadium level."""
    config = await get_config(db)
    _require_enabled(config)
    base = await _get_base(db, user.id, lock=True)
    _complete_if_due(base, config)
    level = int((base.levels or {}).get("stadium", 0))
    if level <= 0:
        raise ConflictError("Сначала построй стадион")
    new = {**DEFAULT_LOOK, **(base.appearance or {})}
    if "seats" in look:
        if look["seats"] not in SEAT_COLORS:
            raise ConflictError("Такого цвета кресел нет")
        new["seats"] = look["seats"]
    if "roof" in look:
        if look["roof"] not in ROOF_LEVEL:
            raise ConflictError("Такой крыши нет")
        if ROOF_LEVEL[look["roof"]] > level:
            raise ConflictError(f"Эта крыша откроется на {ROOF_LEVEL[look['roof']]} уровне стадиона")
        new["roof"] = look["roof"]
    for key, need in (("lights", LIGHTS_LEVEL), ("screen", SCREEN_LEVEL)):
        if key in look:
            if look[key] and level < need:
                raise ConflictError(f"Откроется на {need} уровне стадиона")
            new[key] = bool(look[key])
    base.appearance = new
    db.add(base)
    await db.commit()
    return await get_state(db, user)


# --- Stars speed-up ------------------------------------------------------------------------------

SPEEDUP_PREFIX = "base:"


async def create_speedup_invoice(db: AsyncSession, user: User) -> dict:
    """Telegram Stars invoice finishing the current base construction now.
    The price (by the remaining hours) is frozen on the invoice; the invoice
    reuses StarsInvoice.academy_speedup with a "base:" prefix."""
    from app.models.pack import StarsInvoice
    from app.services.stars_payment_service import _request_telegram_invoice_link

    config = await get_config(db)
    _require_enabled(config)
    base = await db.get(UserClubBase, user.id)
    if base is None or not base.building_code or _due(base, _now()):
        raise ConflictError("Сейчас на базе ничего не строится")
    stars = speedup_stars(base, config)
    key = f"{SPEEDUP_PREFIX}{base.building_code}:{base.building_to_level}"
    token = secrets.token_urlsafe(16)
    db.add(StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, academy_speedup=key))
    await db.flush()
    link = await _request_telegram_invoice_link(
        token, "Ускорить стройку", f"Клубная база: {BUILDINGS[base.building_code].name} — уровень {base.building_to_level} сразу",
        stars,
    )
    await db.commit()
    return {"invoice_link": link, "payload_token": token, "stars_amount": stars}


async def deliver_speedup(db: AsyncSession, user: User, invoice) -> dict:
    """Called (through academy_service.deliver_speedup) by
    stars_payment_service.deliver_payment under the invoice lock. Finishes
    that exact construction; if it already finished on its own meanwhile,
    the payment is still recorded (nothing left to speed up)."""
    config = await get_config(db)
    base = await _get_base(db, user.id, lock=True)
    code, _, level = (invoice.academy_speedup or "")[len(SPEEDUP_PREFIX):].partition(":")
    finished = None
    if base.building_code == code and str(base.building_to_level) == level:
        base.build_ends_at = min(ensure_aware(base.build_ends_at), _now()) if base.build_ends_at else _now()
        finished = _finish(base, config)
    else:
        done = _complete_if_due(base, config)
        if done:
            db.add(_ledger_complete(user.id, done))
    db.add_all([base, ClubBaseLedger(
        user_id=user.id, kind="speedup", building_code=code, to_level=int(level or 0), stars_spent=invoice.stars_amount,
        result={"finished": bool(finished)}, idempotency_key=f"stars-{invoice.payload_token}",
    )])
    await db.flush()
    return {"kind": "base_speedup", "building_code": code, "finished": bool(finished)}


# --- bot sweep -----------------------------------------------------------------------------------

async def sweep_due(db: AsyncSession, limit: int = 200) -> int:
    """Completes due constructions nobody looked at and notifies their
    owners. Each base is taken with FOR UPDATE SKIP LOCKED and re-checked
    under the lock, so the sweep, a second bot replica and the player's own
    request never complete (or notify) one construction twice."""
    from app.services.notification_service import notify

    config = await get_config(db)
    now = _now()
    user_ids = (await db.execute(
        select(UserClubBase.user_id).where(UserClubBase.build_ends_at.is_not(None), UserClubBase.build_ends_at <= now)
        .order_by(UserClubBase.build_ends_at).limit(limit)
    )).scalars().all()
    completed = 0
    for user_id in user_ids:
        base = (await db.execute(
            select(UserClubBase).where(UserClubBase.user_id == user_id)
            .with_for_update(skip_locked=True).execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if base is None or not _due(base, _now()):
            await db.rollback()
            continue
        done = _finish(base, config)
        name = BUILDINGS[done["building_code"]].name if done["building_code"] in BUILDINGS else done["building_code"]
        db.add_all([base, _ledger_complete(user_id, done)])
        await notify(
            db, user_id, NotificationType.club_base_built, "Стройка завершена 🏗️",
            f"Клубная база: «{name}» — уровень {done['level']}. Можно строить дальше!",
        )
        await db.commit()
        completed += 1
    return completed


# --- admin journal -------------------------------------------------------------------------------

async def admin_ledger(db: AsyncSession, user_id: Optional[int], limit: int = 100) -> list[dict]:
    query = (select(ClubBaseLedger, User).join(User, User.id == ClubBaseLedger.user_id)
             .order_by(ClubBaseLedger.id.desc()).limit(max(1, min(limit, 500))))
    if user_id is not None:
        query = query.where(ClubBaseLedger.user_id == user_id)
    rows = (await db.execute(query)).all()
    return [{
        "id": e.id, "user_id": e.user_id, "user_name": u.full_display_name(), "kind": e.kind,
        "building_code": e.building_code,
        "building_name": BUILDINGS[e.building_code].name if e.building_code in BUILDINGS else e.building_code,
        "to_level": e.to_level, "coins_spent": e.coins_spent, "coins_earned": e.coins_earned,
        "stars_spent": e.stars_spent, "result": e.result or {}, "created_at": ensure_aware(e.created_at).isoformat(),
    } for e, u in rows]
