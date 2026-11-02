"""«⚔️ Битва фанатов» — two sides, one fight for the whole event.

One switch (GameConfig.fan_battle_enabled), the dates (fan_battle_starts_at /
fan_battle_ends_at) and every number in GameConfig.fan_battle_settings
(DEFAULT_SETTINGS fills the keys an admin never touched).

- A player picks one of two sides once (FanBattleMember) — from the moment
  the switch is on until the event ends; there is no switching.
- Rewarded games (the wallet_service.credit_coins hook, capped per day),
  claimed tasks, activity chests and the «Перебежчик» boss of «Контратака»
  bring points to the player and to his side. Fans of the side with
  noticeably fewer members get +underdog_bonus_pct % on every drop, so the
  crowd doesn't decide the fight on its own.
- Every local day is a battle: the side with more points that day wins.
  Each fan who brought at least daily_min_points that day gets the
  winners' or the losers' coins. The final: the side with more points over
  the whole event wins; its fans get more coins, the champions' badge and
  the pack, the top fans of each side a bonus.
- Personal milestones pay for the player's own points.
- Nothing is paid automatically: one claim (POST /fans/claim) takes every
  reward that is due, until claim_days after the end. Each reward is a
  FanBattleLedger row with a unique ref_key, so a retried claim pays once.

Points are SUMs over the ledger (side + day per row), never a shared
counter row, so thousands of fans finishing games at once don't queue on
one hot row; the side totals shown in the UI are cached for a few seconds.
Every mutation runs with the user row locked (lock_user_for_update); the
caller of the hooks commits.
"""
import copy
import math
import time as _time
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, inspect, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import app_timezone, ensure_aware, local_today
from app.models.badge import Badge, UserBadge
from app.models.enums import CardSource, TransactionType
from app.models.fan_battle import FanBattleLedger, FanBattleMember
from app.models.game_config import GameConfig
from app.models.pack import Pack
from app.models.user import User
from app.schemas.badge import BadgeOut
from app.schemas.fan_battle import (
    FanBattleStateOut,
    FanClaimOut,
    FanDayOut,
    FanFinalOut,
    FanMilestoneOut,
    FanSideOut,
    FanTopOut,
)
from app.services.wallet_service import credit_coins, lock_user_for_update

POINT_KINDS = ("game", "task", "chest", "boss", "admin")
MILESTONE_KINDS = ("coins", "skill_tokens", "pack", "badge")
DRAW = "draw"

DEFAULT_SETTINGS: dict[str, Any] = {
    # The two sides: code (stable — members keep it), name, emoji, colour.
    "sides": [
        {"code": "fire", "name": "Огонь", "emoji": "🔥", "color": "#f97316"},
        {"code": "ice", "name": "Лёд", "emoji": "❄️", "color": "#38bdf8"},
    ],
    # Points
    "points_per_game": 5,
    "points_games_daily_cap": 100,
    "points_per_task": 8,
    "points_per_daily_chest": 10,
    "points_per_weekly_chest": 30,
    # A side with fewer fans: once the other has at least underdog_min_members
    # and this one is underdog_gap_pct % smaller, its fans get +bonus %.
    "underdog_bonus_pct": 25,
    "underdog_gap_pct": 15,
    "underdog_min_members": 20,
    # «Перебежчик»: standing until the final whistle multiplies the game's points.
    "boss_enabled": True,
    "boss_multiplier": 3,
    # Daily battles
    "daily_min_points": 15,
    "daily_win_coins": 300,
    "daily_lose_coins": 100,
    # The final
    "final_min_points": 100,
    "final_win_coins": 3000,
    "final_lose_coins": 1000,
    "final_pack_id": None,  # the winners' pack (null = none)
    "champion_badge_id": None,  # the winners' badge (migration 0227)
    "top_n": 10,
    "top_bonus_coins": 2000,
    "claim_days": 7,
    # Personal points → rewards. A badge row without badge_id takes fan_badge_id.
    "fan_badge_id": None,
    "milestones": [
        {"points": 50, "kind": "coins", "amount": 300},
        {"points": 150, "kind": "skill_tokens", "amount": 2},
        {"points": 300, "kind": "coins", "amount": 1000},
        {"points": 600, "kind": "skill_tokens", "amount": 5},
        {"points": 1000, "kind": "badge"},
    ],
    # «Капитаны» — the event's collection (frame in the viewer's side colours).
    "collection_id": None,
    # How many days before the start the home screen shows the teaser.
    "teaser_days": 3,
}

# A fixed default window: 07.11 – 20.11 of the current year, local time.
_DEFAULT_START = (11, 7)
_DEFAULT_DAYS = 14
_CACHE_TTL = 15.0
_cache: dict[str, tuple[float, Any]] = {}


def reset_cache() -> None:
    _cache.clear()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _config(db: AsyncSession) -> Optional[GameConfig]:
    """The config row from the identity map (never created here); reloaded
    when an earlier commit of this session expired it."""
    config = await db.get(GameConfig, 1)
    if config is not None and inspect(config).expired_attributes:
        await db.refresh(config)
    return config


def settings_of(config: GameConfig) -> dict[str, Any]:
    out = copy.deepcopy(DEFAULT_SETTINGS)
    out.update({k: v for k, v in (config.fan_battle_settings or {}).items() if k in DEFAULT_SETTINGS})
    return out


def window(config: GameConfig) -> tuple[datetime, datetime]:
    if config.fan_battle_starts_at and config.fan_battle_ends_at:
        return ensure_aware(config.fan_battle_starts_at), ensure_aware(config.fan_battle_ends_at)
    year = local_today().year
    start = datetime(year, *_DEFAULT_START, tzinfo=app_timezone())
    return start, start + timedelta(days=_DEFAULT_DAYS)


def is_active(config: Optional[GameConfig], now: Optional[datetime] = None) -> bool:
    if config is None or not config.fan_battle_enabled:
        return False
    start, end = window(config)
    return start <= (now or _now()) < end


def claim_until(config: GameConfig) -> datetime:
    return window(config)[1] + timedelta(days=max(0, _int(settings_of(config)["claim_days"], 7)))


def event_key(config: GameConfig) -> str:
    return f"fans-{window(config)[0].astimezone(app_timezone()).year}"


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sides(s: dict) -> list[dict]:
    return [dict(side) for side in s["sides"]]


def _event_days(config: GameConfig) -> list[date]:
    start, end = window(config)
    first = start.astimezone(app_timezone()).date()
    last = (end - timedelta(microseconds=1)).astimezone(app_timezone()).date()
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def _winner(points: dict[str, int], codes: list[str]) -> str:
    a, b = codes
    if points.get(a, 0) == points.get(b, 0):
        return DRAW
    return a if points.get(a, 0) > points.get(b, 0) else b


def _won(side: str, winner: Optional[str]) -> bool:
    return winner == DRAW or winner == side


# --- Aggregates --------------------------------------------------------------------

async def _cached(name: str, loader, fresh: bool):
    hit = _cache.get(name)
    if not fresh and hit is not None and _time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    value = await loader()
    _cache[name] = (_time.monotonic(), value)
    return value


async def _member_counts(db: AsyncSession, key: str, fresh: bool = False) -> dict[str, int]:
    async def load():
        rows = (await db.execute(
            select(FanBattleMember.side, func.count(FanBattleMember.user_id))
            .where(FanBattleMember.event_key == key).group_by(FanBattleMember.side)
        )).all()
        return {side: int(n) for side, n in rows}

    return await _cached(f"members:{key}", load, fresh)


async def _day_totals(db: AsyncSession, key: str, fresh: bool = False) -> dict[str, dict[str, int]]:
    """{day: {side: points}} — what each side brought on each local day."""
    async def load():
        rows = (await db.execute(
            select(FanBattleLedger.day, FanBattleLedger.side, func.sum(FanBattleLedger.delta))
            .where(FanBattleLedger.event_key == key, FanBattleLedger.kind.in_(POINT_KINDS))
            .group_by(FanBattleLedger.day, FanBattleLedger.side)
        )).all()
        out: dict[str, dict[str, int]] = {}
        for day, side, total in rows:
            out.setdefault(day, {})[side] = int(total or 0)
        return out

    return await _cached(f"days:{key}", load, fresh)


def underdog_pct(s: dict, counts: dict[str, int], side: str) -> int:
    codes = [x["code"] for x in s["sides"]]
    other = next((c for c in codes if c != side), None)
    mine, theirs = counts.get(side, 0), counts.get(other, 0)
    if theirs < max(1, _int(s["underdog_min_members"])):
        return 0
    if mine * 100 <= theirs * (100 - _int(s["underdog_gap_pct"])):
        return max(0, _int(s["underdog_bonus_pct"]))
    return 0


async def _member(db: AsyncSession, user_id: int, key: str) -> Optional[FanBattleMember]:
    return await db.get(FanBattleMember, (user_id, key))


# --- Points ------------------------------------------------------------------------

async def add_points(
    db: AsyncSession, user: User, base: int, kind: str, *, ref_key: Optional[str] = None,
    config: Optional[GameConfig] = None, details: Optional[dict] = None,
) -> int:
    """Credits points to a row-locked `user`'s side while the event runs.
    Returns what was added (0 when off, no side, blocked, or the ref_key was
    used)."""
    config = config or await _config(db)
    if base <= 0 or not is_active(config) or user.game_rewards_blocked:
        return 0
    key = event_key(config)
    member = await _member(db, user.id, key)
    if member is None:
        return 0
    s = settings_of(config)
    bonus = underdog_pct(s, await _member_counts(db, key), member.side)
    amount = math.ceil(base * (100 + bonus) / 100)
    entry = FanBattleLedger(
        user_id=user.id, event_key=key, side=member.side, day=local_today().isoformat(), kind=kind, delta=amount,
        ref_key=ref_key, details=({**(details or {}), "bonus_pct": bonus} if bonus else details),
    )
    if ref_key is not None:
        try:
            async with db.begin_nested():
                db.add(entry)
                await db.flush()
        except IntegrityError:
            return 0
    else:
        db.add(entry)
    member.points += amount
    member.updated_at = _now()
    db.add(member)
    return amount


async def grant_game_points(db: AsyncSession, user: User, tx_type: TransactionType, amount: int) -> int:
    """wallet_service.credit_coins hook: a rewarded game (the season-XP
    transaction types) brings points, up to the daily cap. Reads the
    already-loaded config row, never creates it."""
    from app.services.season_pass_service import SEASON_XP_TX_TYPES

    if amount <= 0 or tx_type not in SEASON_XP_TX_TYPES:
        return 0
    config = await _config(db)
    if not is_active(config) or user.game_rewards_blocked:
        return 0
    s = settings_of(config)
    per_game, cap = _int(s["points_per_game"]), _int(s["points_games_daily_cap"])
    if per_game <= 0:
        return 0
    member = await _member(db, user.id, event_key(config))
    if member is None:
        return 0
    today = local_today().isoformat()
    if member.games_day != today:
        member.games_day, member.games_points_today = today, 0
    give = per_game if cap <= 0 else max(0, min(per_game, cap - member.games_points_today))
    if give <= 0:
        db.add(member)
        return 0
    member.games_points_today += give  # the cap counts base points, before the underdog bonus
    return await add_points(db, user, give, "game", config=config, details={"tx": tx_type.value})


async def grant_task_points(db: AsyncSession, user: User, user_task_id: int, period_key: Optional[str]) -> int:
    config = await _config(db)
    if not is_active(config):
        return 0
    return await add_points(
        db, user, _int(settings_of(config)["points_per_task"]), "task",
        ref_key=f"task:{user_task_id}:{period_key or '-'}", config=config,
    )


async def grant_chest_points(db: AsyncSession, user: User, period: str, period_key: str, index: int) -> int:
    config = await _config(db)
    if not is_active(config):
        return 0
    s = settings_of(config)
    amount = _int(s["points_per_weekly_chest" if period == "weekly" else "points_per_daily_chest"])
    return await add_points(db, user, amount, "chest", ref_key=f"chest:{period}:{period_key}:{index}", config=config)


# --- «Перебежчик» ------------------------------------------------------------------

BOSS_CODE = "turncoat"


def kontra_boss(config: Optional[GameConfig]) -> Optional[dict]:
    """The event's «Контратака» boss while the event runs, else None."""
    if not is_active(config) or not settings_of(config).get("boss_enabled", True):
        return None
    from app.services.kontra_catalog import FAN_BATTLE_BOSS

    return dict(FAN_BATTLE_BOSS, abilities=list(FAN_BATTLE_BOSS["abilities"]))


async def grant_boss_bonus(db: AsyncSession, user: User, battle_id: int, state: dict) -> int:
    """×boss_multiplier of the game's points for a win over the
    «Перебежчик». `user` is row-locked by kontra_service._finish."""
    from app.services.halloween_service import boss_won

    if (state.get("boss") or {}).get("code") != BOSS_CODE or not boss_won(state):
        return 0
    config = await _config(db)
    if not is_active(config):
        return 0
    s = settings_of(config)
    extra = _int(s["points_per_game"]) * max(0, _int(s["boss_multiplier"], 1) - 1)
    return await add_points(db, user, extra, "boss", ref_key=f"kontra-boss:{battle_id}", config=config)


# --- Joining -----------------------------------------------------------------------

async def join(db: AsyncSession, user: User, side: str) -> FanBattleStateOut:
    from app.services.game_config_service import get_config

    config = await get_config(db)
    if not config.fan_battle_enabled or _now() >= window(config)[1]:
        raise ConflictError("Битва фанатов сейчас не идёт")
    s = settings_of(config)
    if side not in [x["code"] for x in s["sides"]]:
        raise NotFoundError("Такой стороны нет")
    key = event_key(config)
    locked = await lock_user_for_update(db, user.id)
    member = await _member(db, locked.id, key)
    if member is not None:
        if member.side == side:
            return await get_state(db, locked)
        raise ConflictError("Сторону выбирают один раз — ты уже за другую команду")
    db.add(FanBattleMember(user_id=locked.id, event_key=key, side=side, points=0, games_points_today=0))
    await db.commit()
    _cache.pop(f"members:{key}", None)
    return await get_state(db, locked)


# --- Rewards -----------------------------------------------------------------------

def _milestones(s: dict) -> list[dict]:
    out = []
    for raw in s.get("milestones") or []:
        if not isinstance(raw, dict) or raw.get("kind") not in MILESTONE_KINDS or _int(raw.get("points")) <= 0:
            continue
        item = dict(raw)
        if item["kind"] == "badge":
            item["badge_id"] = item.get("badge_id") or s.get("fan_badge_id")
        out.append(item)
    return sorted(out, key=lambda m: _int(m["points"]))


def _milestone_title(item: dict, badge: Optional[Badge], pack: Optional[Pack]) -> str:
    kind, amount = item["kind"], _int(item.get("amount"))
    if kind == "coins":
        return f"{amount:,} монет".replace(",", " ")
    if kind == "skill_tokens":
        return f"{max(1, amount)} жет. навыка"
    if kind == "pack":
        return f"Пак «{pack.name}»" if pack else "Пак"
    return f"Значок «{badge.name}»" if badge else "Значок"


async def _top(db: AsyncSession, key: str, side: str, limit: int) -> list[tuple[int, int]]:
    rows = (await db.execute(
        select(FanBattleMember.user_id, FanBattleMember.points)
        .where(FanBattleMember.event_key == key, FanBattleMember.side == side, FanBattleMember.points > 0)
        .order_by(FanBattleMember.points.desc(), FanBattleMember.joined_at, FanBattleMember.user_id)
        .limit(limit)
    )).all()
    return [(int(u), int(p)) for u, p in rows]


async def _rank(db: AsyncSession, member: FanBattleMember) -> Optional[int]:
    if member.points <= 0:
        return None
    ahead = (await db.execute(select(func.count(FanBattleMember.user_id)).where(
        FanBattleMember.event_key == member.event_key, FanBattleMember.side == member.side,
        or_(
            FanBattleMember.points > member.points,
            and_(FanBattleMember.points == member.points, or_(
                FanBattleMember.joined_at < member.joined_at,
                and_(FanBattleMember.joined_at == member.joined_at, FanBattleMember.user_id < member.user_id),
            )),
        ),
    ))).scalar_one()
    return int(ahead) + 1


async def _my_days(db: AsyncSession, user_id: int, key: str) -> dict[str, int]:
    rows = (await db.execute(
        select(FanBattleLedger.day, func.sum(FanBattleLedger.delta)).where(
            FanBattleLedger.user_id == user_id, FanBattleLedger.event_key == key,
            FanBattleLedger.kind.in_(POINT_KINDS),
        ).group_by(FanBattleLedger.day)
    )).all()
    return {day: int(n or 0) for day, n in rows}


async def _claimed(db: AsyncSession, user_id: int, key: str) -> set[str]:
    rows = (await db.execute(select(FanBattleLedger.ref_key).where(
        FanBattleLedger.user_id == user_id, FanBattleLedger.event_key == key,
        FanBattleLedger.kind.in_(("daily", "milestone", "final")),
    ))).scalars().all()
    return {r for r in rows if r}


def _finished_day(day: date, config: GameConfig, now: datetime) -> bool:
    return day < local_today(now) or now >= window(config)[1]


async def _final_totals(db: AsyncSession, key: str, fresh: bool) -> dict[str, int]:
    totals: dict[str, int] = {}
    for per_side in (await _day_totals(db, key, fresh)).values():
        for side, n in per_side.items():
            totals[side] = totals.get(side, 0) + n
    return totals


async def _due(db: AsyncSession, config: GameConfig, member: FanBattleMember, fresh: bool) -> dict[str, Any]:
    """Everything the player has earned so far, claimed or not."""
    s = settings_of(config)
    key = member.event_key
    now = _now()
    codes = [x["code"] for x in s["sides"]]
    totals = await _day_totals(db, key, fresh)
    mine = await _my_days(db, member.user_id, key)
    claimed = await _claimed(db, member.user_id, key)
    min_points = _int(s["daily_min_points"])

    days = []
    for day in _event_days(config):
        if day > local_today(now):
            break
        iso = day.isoformat()
        finished = _finished_day(day, config, now)
        points = {c: totals.get(iso, {}).get(c, 0) for c in codes}
        winner = _winner(points, codes) if finished else None
        my_points = mine.get(iso, 0)
        coins = 0
        if finished and my_points >= max(1, min_points):
            coins = _int(s["daily_win_coins"] if _won(member.side, winner) else s["daily_lose_coins"])
        days.append({"day": day, "iso": iso, "finished": finished, "points": points, "winner": winner,
                     "my_points": my_points, "coins": coins, "ref": f"{key}:daily:{iso}"})

    milestones = []
    for item in _milestones(s):
        ref = f"{key}:milestone:{_int(item['points'])}"
        milestones.append({**item, "ref": ref, "reached": member.points >= _int(item["points"])})

    final = None
    if now >= window(config)[1]:
        winner = _winner(await _final_totals(db, key, fresh), codes)
        top_n = _int(s["top_n"])
        top_ids = [u for u, _ in await _top(db, key, member.side, top_n)] if top_n > 0 else []
        eligible = member.points >= max(1, _int(s["final_min_points"]))
        won = _won(member.side, winner)
        coins = _int(s["final_win_coins"] if won else s["final_lose_coins"]) if eligible else 0
        in_top = eligible and member.user_id in top_ids
        if in_top:
            coins += _int(s["top_bonus_coins"])
        final = {
            "ref": f"{key}:final", "winner": winner, "eligible": eligible, "coins": coins,
            "rank": top_ids.index(member.user_id) + 1 if in_top else None,
            "pack_id": s.get("final_pack_id") if eligible and won else None,
            "badge_id": s.get("champion_badge_id") if eligible and won else None,
        }
    return {"days": days, "milestones": milestones, "final": final, "claimed": claimed}


def _claimable(due: dict, config: GameConfig) -> int:
    if _now() >= claim_until(config):
        return 0
    claimed = due["claimed"]
    n = sum(1 for d in due["days"] if d["coins"] > 0 and d["ref"] not in claimed)
    n += sum(1 for m in due["milestones"] if m["reached"] and m["ref"] not in claimed)
    final = due["final"]
    if final and final["eligible"] and final["ref"] not in claimed:
        n += 1
    return n


async def _random_skill_code(db: AsyncSession) -> str:
    from app.services.card_skill_service import pack_token_drop_table, pick_pack_token

    table = await pack_token_drop_table(db)
    if not table:
        raise ConflictError("Жетоны навыков сейчас недоступны")
    return pick_pack_token(table)[0]


async def claim(db: AsyncSession, user: User) -> FanClaimOut:
    """Takes every reward that is due — daily battles, milestones, the final
    — in one transaction under the user's row lock. Each one is a ledger
    row with a unique ref_key; a retry finds them taken and pays nothing."""
    from app.services.card_skill_service import grant_tokens
    from app.services.collection_service import grant_collection_rewards_for_new_cards
    from app.services.game_config_service import get_config
    from app.services.pack_service import grant_bonus_pack_opening
    from app.services.reward_bundle_service import grant_badge

    config = await get_config(db)
    if not config.fan_battle_enabled or _now() >= claim_until(config):
        raise ConflictError("Награды «Битвы фанатов» уже не выдаются")
    key = event_key(config)
    locked = await lock_user_for_update(db, user.id)
    if locked.game_rewards_blocked:
        raise ConflictError("Награды ивента для этого аккаунта отключены")
    member = await _member(db, locked.id, key)
    if member is None:
        raise ConflictError("Сначала выбери сторону")
    due = await _due(db, config, member, fresh=True)
    claimed = due["claimed"]
    out = FanClaimOut(claimed=0, new_balance=locked.balance)
    today = local_today().isoformat()

    async def take(kind: str, ref: str, details: dict) -> Optional[FanBattleLedger]:
        entry = FanBattleLedger(user_id=locked.id, event_key=key, side=member.side, day=today, kind=kind, delta=0,
                                ref_key=ref, details=details)
        try:
            async with db.begin_nested():
                db.add(entry)
                await db.flush()
        except IntegrityError:
            return None
        out.claimed += 1
        return entry

    async def pay_coins(amount: int, entry: FanBattleLedger, description: str) -> None:
        if amount > 0:
            await credit_coins(db, locked, amount, TransactionType.fan_battle_reward, description,
                               "fan_battle_ledger", entry.id)
            out.coins += amount

    async def pay_pack(pack_id: Optional[int], entry: FanBattleLedger) -> None:
        pack = await db.get(Pack, pack_id) if pack_id else None
        if pack is None:
            return
        opened = await grant_bonus_pack_opening(db, locked, pack.id, idempotency_prefix=f"fan-battle-{entry.id}",
                                                source=CardSource.game_reward)
        if opened is not None:
            await grant_collection_rewards_for_new_cards(db, locked, [c.card.player.id for c in opened.cards])
            out.pack_names.append(opened.pack.name)
            out.cards.extend(c.card for c in opened.cards)

    async def pay_badge(badge_id: Optional[int]) -> None:
        if badge_id:
            badge = await grant_badge(db, locked, badge_id)
            if badge is not None:
                out.badges.append(BadgeOut.model_validate(badge))

    for day in due["days"]:
        if day["coins"] <= 0 or day["ref"] in claimed:
            continue
        entry = await take("daily", day["ref"], {"day": day["iso"], "winner": day["winner"], "coins": day["coins"]})
        if entry is not None:
            won = _won(member.side, day["winner"])
            await pay_coins(day["coins"], entry, f"Битва фанатов: {'победа' if won else 'бой'} дня {day['iso']}")
            out.titles.append(f"{'Победа' if won else 'Бой'} {day['day'].strftime('%d.%m')}")

    for item in due["milestones"]:
        if not item["reached"] or item["ref"] in claimed:
            continue
        entry = await take("milestone", item["ref"], {"points": item["points"], "kind": item["kind"]})
        if entry is None:
            continue
        kind = item["kind"]
        if kind == "coins":
            await pay_coins(_int(item.get("amount")), entry, f"Битва фанатов: {item['points']} очков")
        elif kind == "skill_tokens":
            code = item.get("skill_code") or await _random_skill_code(db)
            amount = max(1, _int(item.get("amount"), 1))
            await grant_tokens(db, locked, code, amount, "grant_event", related_object_type="fan_battle_ledger",
                               related_object_id=entry.id, reason="Битва фанатов")
            out.skill_tokens.append({"code": code, "amount": amount})
        elif kind == "pack":
            await pay_pack(item.get("pack_id"), entry)
        else:
            await pay_badge(item.get("badge_id"))
        out.titles.append(f"{item['points']} очков")

    final = due["final"]
    if final and final["eligible"] and final["ref"] not in claimed:
        entry = await take("final", final["ref"], {k: v for k, v in final.items() if k != "ref"})
        if entry is not None:
            await pay_coins(final["coins"], entry, "Битва фанатов: финал")
            await pay_pack(final["pack_id"], entry)
            await pay_badge(final["badge_id"])
            out.titles.append("Финал")

    if out.claimed == 0:
        raise ConflictError("Пока нечего забирать")
    await db.commit()
    await db.refresh(locked)
    out.new_balance = locked.balance
    return out


# --- State -------------------------------------------------------------------------

def _next_local_midnight(now: Optional[datetime] = None) -> datetime:
    return datetime.combine(local_today(now) + timedelta(days=1), time.min, tzinfo=app_timezone())


async def get_state(db: AsyncSession, user: User) -> FanBattleStateOut:
    from app.services import halloween_service
    from app.services.game_config_service import get_config

    config = await get_config(db)
    start, end = window(config)
    if not config.fan_battle_enabled:
        return FanBattleStateOut(enabled=False, active=False, starts_at=start, ends_at=end)
    s = settings_of(config)
    key = event_key(config)
    now = _now()
    active = is_active(config, now)
    counts = await _member_counts(db, key)
    totals = await _day_totals(db, key)
    today = local_today(now).isoformat()
    sides = []
    for side in _sides(s):
        code = side["code"]
        sides.append(FanSideOut(
            code=code, name=str(side.get("name") or code), emoji=str(side.get("emoji") or ""),
            color=str(side.get("color") or "#a3a3a3"), members=counts.get(code, 0),
            points=sum(day.get(code, 0) for day in totals.values()), today_points=totals.get(today, {}).get(code, 0),
            underdog_bonus_pct=underdog_pct(s, counts, code),
        ))
    names: dict[int, str] = {}
    top_rows = {side.code: await _top(db, key, side.code, 5) for side in sides}
    ids = [u for rows in top_rows.values() for u, _ in rows]
    if ids:
        names = dict((await db.execute(select(User.id, User.first_name).where(User.id.in_(ids)))).all())
    top = {code: [FanTopOut(user_id=u, name=names.get(u) or f"#{u}", points=p) for u, p in rows]
           for code, rows in top_rows.items()}

    boss = kontra_boss(config)
    state = FanBattleStateOut(
        enabled=True, active=active, finished=now >= end, starts_at=start, ends_at=end,
        claim_until=claim_until(config), can_join=now < end, teaser_days=_int(s["teaser_days"]), sides=sides, top=top,
        points_per_game=_int(s["points_per_game"]), games_daily_cap=_int(s["points_games_daily_cap"]),
        points_per_task=_int(s["points_per_task"]), points_per_daily_chest=_int(s["points_per_daily_chest"]),
        points_per_weekly_chest=_int(s["points_per_weekly_chest"]),
        boss_name=boss["name"] if boss else None, boss_multiplier=_int(s["boss_multiplier"], 1),
        daily_min_points=_int(s["daily_min_points"]), daily_win_coins=_int(s["daily_win_coins"]),
        daily_lose_coins=_int(s["daily_lose_coins"]), day_resets_at=_next_local_midnight(now),
        final_win_coins=_int(s["final_win_coins"]), final_lose_coins=_int(s["final_lose_coins"]),
        final_min_points=_int(s["final_min_points"]), top_n=_int(s["top_n"]),
        top_bonus_coins=_int(s["top_bonus_coins"]),
        collection=await halloween_service._collection_out(db, user.id, s.get("collection_id")),
    )
    member = await _member(db, user.id, key)
    milestone_badges = {m.get("badge_id") for m in _milestones(s) if m["kind"] == "badge" and m.get("badge_id")}
    milestone_packs = {m.get("pack_id") for m in _milestones(s) if m["kind"] == "pack" and m.get("pack_id")}
    badges = {b.id: b for b in (await db.execute(select(Badge).where(
        Badge.id.in_([*milestone_badges, s.get("champion_badge_id") or 0])
    ))).scalars()}
    packs = {p.id: p for p in (await db.execute(select(Pack).where(
        Pack.id.in_([*milestone_packs, s.get("final_pack_id") or 0])
    ))).scalars()}

    due = await _due(db, config, member, fresh=False) if member else None
    claimed = due["claimed"] if due else set()
    for item in (due["milestones"] if due else _milestones(s)):
        badge = badges.get(item.get("badge_id")) if item["kind"] == "badge" else None
        pack = packs.get(item.get("pack_id")) if item["kind"] == "pack" else None
        state.milestones.append(FanMilestoneOut(
            points=_int(item["points"]), kind=item["kind"], amount=_int(item.get("amount")),
            title=_milestone_title(item, badge, pack), reached=bool(item.get("reached")),
            claimed=item.get("ref") in claimed, badge=BadgeOut.model_validate(badge) if badge else None,
            pack_name=pack.name if pack else None,
        ))
    if due is None:
        return state

    state.my_side = member.side
    state.my_points = member.points
    state.my_rank = await _rank(db, member)
    state.games_points_today = member.games_points_today if member.games_day == today else 0
    state.days = [FanDayOut(day=d["day"], finished=d["finished"], points=d["points"], winner=d["winner"],
                            my_points=d["my_points"], reward_coins=d["coins"], claimed=d["ref"] in claimed)
                  for d in due["days"]]
    state.my_today_points = next((d["my_points"] for d in due["days"] if d["iso"] == today), 0)
    final = due["final"]
    if final:
        badge = badges.get(final["badge_id"]) if final["badge_id"] else None
        pack = packs.get(final["pack_id"]) if final["pack_id"] else None
        state.final = FanFinalOut(
            winner=final["winner"], my_rank=final["rank"], eligible=final["eligible"], coins=final["coins"],
            pack_name=pack.name if pack else None, badge=BadgeOut.model_validate(badge) if badge else None,
            claimed=final["ref"] in claimed,
        )
    state.claimable = _claimable(due, config)
    return state


# --- Admin -------------------------------------------------------------------------

async def admin_stats(db: AsyncSession, config: GameConfig) -> dict[str, Any]:
    key = event_key(config)
    counts = await _member_counts(db, key, fresh=True)
    totals = await _final_totals(db, key, fresh=True)
    claims = (await db.execute(select(func.count(FanBattleLedger.id)).where(
        FanBattleLedger.event_key == key, FanBattleLedger.kind.in_(("daily", "milestone", "final")),
    ))).scalar_one()
    coins = (await db.execute(select(func.coalesce(func.sum(FanBattleLedger.delta), 0)).where(
        FanBattleLedger.event_key == key, FanBattleLedger.kind.in_(POINT_KINDS),
    ))).scalar_one()
    return {"members": counts, "points": totals, "points_total": int(coins), "claims": int(claims)}


def validate_settings(raw: dict) -> dict:
    """Admin input: known keys only, non-negative numbers, two sides, sane milestones."""
    clean: dict[str, Any] = {}
    for k, v in raw.items():
        if k not in DEFAULT_SETTINGS:
            continue
        default = DEFAULT_SETTINGS[k]
        if isinstance(default, bool):
            clean[k] = bool(v)
        elif isinstance(default, int) or (default is None and k.endswith("_id")):
            if v in (None, "", 0) and default is None:
                clean[k] = None
                continue
            n = _int(v, -1)
            if n < 0:
                raise ConflictError(f"«{k}» должно быть неотрицательным числом")
            clean[k] = n
        elif k == "sides":
            if not isinstance(v, list) or len(v) != 2 or any(
                not isinstance(x, dict) or not str(x.get("code") or "").strip() or len(str(x["code"])) > 16
                or not str(x.get("name") or "").strip() for x in v
            ):
                raise ConflictError("Сторон ровно две: {code (до 16 символов), name, emoji, color}")
            if v[0]["code"] == v[1]["code"]:
                raise ConflictError("Коды сторон должны различаться")
            clean[k] = v
        elif k == "milestones":
            if not isinstance(v, list) or any(
                not isinstance(m, dict) or m.get("kind") not in MILESTONE_KINDS or _int(m.get("points"), 0) <= 0
                for m in v
            ):
                raise ConflictError("Рубежи — список {points > 0, kind: coins/skill_tokens/pack/badge, amount}")
            if len({_int(m["points"]) for m in v}) != len(v):
                raise ConflictError("Очки рубежей повторяются")
            clean[k] = v
        else:
            clean[k] = v
    for k in ("underdog_bonus_pct", "underdog_gap_pct"):
        if k in clean and clean[k] > 100:
            raise ConflictError(f"«{k}» — от 0 до 100")
    return clean

