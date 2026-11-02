"""«💯 Нам 100 дней!» — the game's first hundred days.

One switch (GameConfig.anniversary_enabled), the dates (anniversary_starts_at
/ anniversary_ends_at) and every number in GameConfig.anniversary_settings
(DEFAULT_SETTINGS fills the keys an admin never touched). Four parts:

- «Мои 100 дней»: a personal recap (days with us, packs, cards, the best
  card, games and the favourite mode, coins, trades, how early the player
  came) — read-only stats of what already happened, plus a small gift for
  looking at it once.
- «Сотня»: one goal for everybody — rewarded games played during the event
  (the wallet_service.credit_coins hook). Each tier (25/50/75/100 %) pays
  every player who played at least community_min_games of them.
- The gift calendar: one gift a local day, in order (a missed day isn't
  lost, the next gift waits); the last one carries the «100 дней» badge.
- «Первые 100»: the anniversary collection (frame "gold100") and its pack —
  an admin fills them; the calendar can include the pack.

Rewards are reward_bundle_service bundles (coins / pack / card of a rarity /
badge), each taken with a unique AnniversaryClaim.ref_key under the user's
row lock, so a retried claim pays once. The community total is a SUM over
the members, cached for a few seconds — no hot counter row.
"""
import bisect
import copy
import time as _time
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.timeutil import app_timezone, ensure_aware, local_today
from app.models.anniversary import AnniversaryClaim, AnniversaryMember
from app.models.enums import CardSource, TransactionType
from app.models.game_config import GameConfig
from app.models.user import User
from app.schemas.anniversary import (
    AnniversaryCalendarDayOut,
    AnniversaryClaimOut,
    AnniversaryCommunityOut,
    AnniversaryRecapOut,
    AnniversaryStateOut,
    AnniversaryTierOut,
)
from app.services import reward_bundle_service
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import lock_user_for_update

RARITIES = ("common", "rare", "epic", "legendary", "diamond")

DEFAULT_SETTINGS: dict[str, Any] = {
    # Gift calendar: one gift a local day, in order. A gift is a bundle —
    # coins, card_rarity, pack_id; "pack": true = the event pack (pack_id
    # below), "badge": true = the «100 дней» badge (badge_id below).
    "calendar": [
        {"coins": 300},
        {"coins": 500},
        {"card_rarity": "rare"},
        {"coins": 800},
        {"card_rarity": "epic"},
        {"coins": 1500},
        {"coins": 2000, "badge": True, "pack": True},
    ],
    # «Сотня»: rewarded games of all players together.
    "community_goal": 50000,
    "community_min_games": 3,
    "community_tiers": [
        {"pct": 25, "coins": 500},
        {"pct": 50, "coins": 1000},
        {"pct": 75, "card_rarity": "epic"},
        {"pct": 100, "coins": 3000, "pack": True},
    ],
    # «Мои 100 дней»: a gift for opening the recap once.
    "recap_coins": 100,
    "claim_days": 7,
    "teaser_days": 3,
    # What the event is made of (ids set by migration 0241 / the admin).
    "badge_id": None,
    "pack_id": None,
    "collection_id": None,
}

# A fixed default window: 21.11 – 30.11 of the current year, local time.
_DEFAULT_START = (11, 21)
_DEFAULT_DAYS = 10
_CACHE_TTL = 15.0
_cache: dict[str, tuple[float, Any]] = {}


def reset_cache() -> None:
    _cache.clear()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def _config(db: AsyncSession) -> Optional[GameConfig]:
    """The config row from the identity map (never created here); reloaded
    when an earlier commit of this session expired it."""
    config = await db.get(GameConfig, 1)
    if config is not None and inspect(config).expired_attributes:
        await db.refresh(config)
    return config


def settings_of(config: GameConfig) -> dict[str, Any]:
    out = copy.deepcopy(DEFAULT_SETTINGS)
    out.update({k: v for k, v in (config.anniversary_settings or {}).items() if k in DEFAULT_SETTINGS})
    return out


def window(config: GameConfig) -> tuple[datetime, datetime]:
    if config.anniversary_starts_at and config.anniversary_ends_at:
        return ensure_aware(config.anniversary_starts_at), ensure_aware(config.anniversary_ends_at)
    start = datetime(local_today().year, *_DEFAULT_START, tzinfo=app_timezone())
    return start, start + timedelta(days=_DEFAULT_DAYS)


def is_active(config: Optional[GameConfig], now: Optional[datetime] = None) -> bool:
    if config is None or not config.anniversary_enabled:
        return False
    start, end = window(config)
    return start <= (now or _now()) < end


def claim_until(config: GameConfig) -> datetime:
    return window(config)[1] + timedelta(days=max(0, _int(settings_of(config)["claim_days"], 7)))


def event_key(config: GameConfig) -> str:
    return f"100days-{window(config)[0].astimezone(app_timezone()).year}"


def _bundle(raw: dict, s: dict) -> Bundle:
    rarity = raw.get("card_rarity")
    return Bundle(
        coins=max(0, _int(raw.get("coins"))),
        pack_id=_int(raw.get("pack_id")) or (s.get("pack_id") if raw.get("pack") else None) or None,
        card_rarity=rarity if rarity in RARITIES else None,
        badge_id=_int(raw.get("badge_id")) or (s.get("badge_id") if raw.get("badge") else None) or None,
    )


async def _member(db: AsyncSession, user_id: int, key: str, create: bool = False) -> Optional[AnniversaryMember]:
    """The caller holds the user's row lock, so creating the row can't race."""
    member = await db.get(AnniversaryMember, (user_id, key))
    if member is None and create:
        member = AnniversaryMember(user_id=user_id, event_key=key, games=0, calendar_claimed=0)
        db.add(member)
        await db.flush()
    return member


async def community_total(db: AsyncSession, key: str, fresh: bool = False) -> int:
    hit = _cache.get(key)
    if not fresh and hit is not None and _time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    total = int((await db.execute(
        select(func.coalesce(func.sum(AnniversaryMember.games), 0)).where(AnniversaryMember.event_key == key)
    )).scalar_one())
    _cache[key] = (_time.monotonic(), total)
    return total


# --- «Сотня» hook ------------------------------------------------------------------

async def count_game(db: AsyncSession, user: User, tx_type: TransactionType, amount: int) -> bool:
    """wallet_service.credit_coins hook: one rewarded game (the season-XP
    transaction types) counts towards the community goal. Reads the
    already-loaded config row, never creates it."""
    from app.services.season_pass_service import SEASON_XP_TX_TYPES

    if amount <= 0 or tx_type not in SEASON_XP_TX_TYPES:
        return False
    config = await _config(db)
    if not is_active(config) or user.game_rewards_blocked:
        return False
    member = await _member(db, user.id, event_key(config), create=True)
    member.games += 1
    member.updated_at = _now()
    db.add(member)
    return True


# --- Claims ------------------------------------------------------------------------

async def _take(
    db: AsyncSession, locked: User, key: str, kind: str, ref_key: str, bundle: Bundle, description: str,
    details: Optional[dict] = None,
) -> Optional[AnniversaryClaimOut]:
    claim = AnniversaryClaim(user_id=locked.id, event_key=key, kind=kind, ref_key=ref_key, details=details)
    try:
        async with db.begin_nested():
            db.add(claim)
            await db.flush()
    except IntegrityError:
        return None
    granted = await reward_bundle_service.grant(
        db, locked, bundle, tx_type=TransactionType.anniversary_reward, description=description,
        card_source=CardSource.game_reward, idempotency_prefix=f"anniversary-{claim.id}",
        cosmetic_source="anniversary", related_object_type="anniversary_claim", related_object_id=claim.id,
    )
    return AnniversaryClaimOut(title=description, rewards=granted, new_balance=0)


def _blocked(locked: User) -> None:
    if locked.game_rewards_blocked:
        raise ConflictError("Награды ивента для этого аккаунта отключены")


async def claim_calendar(db: AsyncSession, user: User) -> AnniversaryClaimOut:
    """Today's gift: the next one in order, once a local day."""
    from app.services.game_config_service import get_config

    config = await get_config(db)
    if not is_active(config):
        raise ConflictError("Юбилейный календарь сейчас закрыт")
    s = settings_of(config)
    key = event_key(config)
    calendar = [g for g in s["calendar"] if isinstance(g, dict)]
    locked = await lock_user_for_update(db, user.id)
    _blocked(locked)
    member = await _member(db, locked.id, key, create=True)
    today = local_today().isoformat()
    if member.calendar_last_day == today:
        raise ConflictError("Сегодняшний подарок уже твой — приходи завтра")
    if member.calendar_claimed >= len(calendar):
        raise ConflictError("Все подарки календаря уже собраны")
    n = member.calendar_claimed + 1
    out = await _take(db, locked, key, "calendar", f"{key}:calendar:{n}", _bundle(calendar[n - 1], s),
                      f"Нам 100 дней: подарок {n} из {len(calendar)}", {"day": today})
    if out is None:
        raise ConflictError("Этот подарок уже забран")
    member.calendar_claimed, member.calendar_last_day = n, today
    db.add(member)
    await db.commit()
    await db.refresh(locked)
    out.new_balance = locked.balance
    return out


def _tiers(s: dict) -> list[dict]:
    rows = [t for t in s["community_tiers"] if isinstance(t, dict) and 0 < _int(t.get("pct")) <= 100]
    return sorted(rows, key=lambda t: _int(t["pct"]))


def _tier_reached(total: int, goal: int, pct: int) -> bool:
    return goal > 0 and total * 100 >= goal * pct


async def claim_community(db: AsyncSession, user: User) -> AnniversaryClaimOut:
    """Every reached «Сотня» tier at once, for players who played enough."""
    from app.services.game_config_service import get_config

    config = await get_config(db)
    if not config.anniversary_enabled or _now() >= claim_until(config) or _now() < window(config)[0]:
        raise ConflictError("Награды «Сотни» сейчас не выдаются")
    s = settings_of(config)
    key = event_key(config)
    locked = await lock_user_for_update(db, user.id)
    _blocked(locked)
    member = await _member(db, locked.id, key)
    need = max(1, _int(s["community_min_games"]))
    if member is None or member.games < need:
        raise ConflictError(f"Сыграй хотя бы {need} наградных игр во время ивента, чтобы получить награды «Сотни»")
    total, goal = await community_total(db, key, fresh=True), _int(s["community_goal"])
    merged: Optional[AnniversaryClaimOut] = None
    for tier in _tiers(s):
        pct = _int(tier["pct"])
        if not _tier_reached(total, goal, pct):
            continue
        out = await _take(db, locked, key, "community", f"{key}:community:{pct}", _bundle(tier, s),
                          f"«Сотня»: {pct}% цели", {"pct": pct, "total": total})
        if out is None:
            continue
        merged = out if merged is None else _merge(merged, out)
    if merged is None:
        raise ConflictError("Пока нечего забирать")
    await db.commit()
    await db.refresh(locked)
    merged.new_balance = locked.balance
    return merged


def _merge(a: AnniversaryClaimOut, b: AnniversaryClaimOut) -> AnniversaryClaimOut:
    ra, rb = a.rewards, b.rewards
    ra.coins += rb.coins
    ra.cards = [*ra.cards, *rb.cards]
    ra.pack_name = ra.pack_name or rb.pack_name
    ra.badge = ra.badge or rb.badge
    a.title = f"{a.title} · {b.title}"
    return a


async def claim_recap(db: AsyncSession, user: User) -> AnniversaryClaimOut:
    from app.services.game_config_service import get_config

    config = await get_config(db)
    if not is_active(config):
        raise ConflictError("«Мои 100 дней» сейчас закрыты")
    s = settings_of(config)
    key = event_key(config)
    coins = _int(s["recap_coins"])
    if coins <= 0:
        raise ConflictError("За итог подарка нет")
    locked = await lock_user_for_update(db, user.id)
    _blocked(locked)
    out = await _take(db, locked, key, "recap", f"{key}:recap", Bundle(coins=coins), "Мои 100 дней")
    if out is None:
        raise ConflictError("Подарок за итог уже твой")
    await db.commit()
    await db.refresh(locked)
    out.new_balance = locked.balance
    return out


# --- «Мои 100 дней» ----------------------------------------------------------------

async def recap(db: AsyncSession, user: User) -> AnniversaryRecapOut:
    """What the player did since he came — all read-only."""
    from app.models.badge import UserBadge
    from app.models.card import UserCard
    from app.models.enums import TradeStatus
    from app.models.game import GameSession
    from app.models.pack import PackOpening
    from app.models.player import Player
    from app.models.trade import TradeOffer
    from app.models.transaction import CoinTransaction
    from app.models.user_activity import UserDailyActivity
    from app.services.admin_analytics_service import GAME_TYPE_LABELS, MODE_SOURCES

    hit = _cache.get(f"recap:{user.id}")
    if hit is not None and _time.monotonic() - hit[0] < 600:
        return hit[1]
    uid = user.id

    async def count(q) -> int:
        return int((await db.execute(q)).scalar_one() or 0)

    joined = ensure_aware(user.created_at)
    days_with_us = (local_today() - joined.astimezone(app_timezone()).date()).days + 1
    active_days = await count(select(func.count()).select_from(UserDailyActivity).where(UserDailyActivity.user_id == uid))
    packs = await count(select(func.count(PackOpening.id)).where(PackOpening.user_id == uid))
    cards = await count(select(func.count(UserCard.id)).where(UserCard.owner_id == uid))
    players = await count(select(func.count(func.distinct(UserCard.player_id))).where(UserCard.owner_id == uid))
    coins = await count(select(func.coalesce(func.sum(CoinTransaction.amount), 0)).where(
        CoinTransaction.user_id == uid, CoinTransaction.amount > 0,
    ))
    trades = await count(select(func.count(TradeOffer.id)).where(
        TradeOffer.status == TradeStatus.accepted, (TradeOffer.sender_id == uid) | (TradeOffer.receiver_id == uid),
    ))
    badges = await count(select(func.count(UserBadge.id)).where(UserBadge.user_id == uid))
    player_number = await count(select(func.count(User.id)).where(User.id <= uid))

    modes: dict[str, int] = {}
    for src in MODE_SOURCES:
        q = select(func.count()).select_from(src.model)
        if src.join is not None:
            q = q.join(*src.join)
        cond = src.user_cols[0] == uid
        for col in src.user_cols[1:]:
            cond = cond | (col == uid)
        n = await count(q.where(cond))
        if n:
            modes[src.label] = modes.get(src.label, 0) + n
    for game_type, n in (await db.execute(
        select(GameSession.game_type, func.count()).where(GameSession.user_id == uid).group_by(GameSession.game_type)
    )).all():
        value = getattr(game_type, "value", str(game_type))
        label = GAME_TYPE_LABELS.get(value, value)
        modes[label] = modes.get(label, 0) + int(n)
    favourite = max(modes.items(), key=lambda kv: kv[1]) if modes else None

    best = (await db.execute(
        select(Player.display_name, Player.rating, Player.rarity, Player.image_path, Player.position)
        .join(UserCard, UserCard.player_id == Player.id).where(UserCard.owner_id == uid)
        .order_by(Player.rating.desc(), Player.id).limit(1)
    )).first()

    # «Больше карточек, чем у N % игроков» (among players with any card).
    # One scan of user_cards for everybody, kept for 10 minutes.
    hit = _cache.get("owner_counts")
    if hit is None or _time.monotonic() - hit[0] >= 600:
        rows = (await db.execute(select(func.count(UserCard.id)).group_by(UserCard.owner_id))).scalars().all()
        hit = (_time.monotonic(), sorted(int(n) for n in rows))
        _cache["owner_counts"] = hit
    owner_counts: list[int] = hit[1]
    owners, fewer = len(owner_counts), bisect.bisect_left(owner_counts, cards)
    out = AnniversaryRecapOut(
        days_with_us=max(1, days_with_us), active_days=active_days, packs_opened=packs, cards=cards,
        unique_players=players, coins_earned=coins, trades=trades, badges=badges, player_number=player_number,
        games=sum(modes.values()), favourite_mode=favourite[0] if favourite else None,
        favourite_mode_games=favourite[1] if favourite else 0,
        best_card_name=best[0] if best else None, best_card_rating=best[1] if best else None,
        best_card_rarity=getattr(best[2], "value", best[2]) if best else None,
        best_card_image=best[3] if best else None,
        best_card_position=getattr(best[4], "value", best[4]) if best else None,
        cards_better_than_pct=round(fewer * 100 / owners) if owners and cards else 0,
    )
    _cache[f"recap:{user.id}"] = (_time.monotonic(), out)
    return out


def share_text(r: AnniversaryRecapOut) -> str:
    lines = [f"💯 Мои первые {r.days_with_us} дней в Victor FC", f"🎴 Паков открыто: {r.packs_opened}",
             f"🃏 Карточек: {r.cards} ({r.unique_players} разных футболистов)"]
    if r.best_card_name:
        lines.append(f"⭐ Лучшая карта: {r.best_card_name} ({r.best_card_rating})")
    if r.favourite_mode:
        lines.append(f"🎮 Любимый режим: {r.favourite_mode} — {r.favourite_mode_games} игр")
    lines.append(f"🤝 Обменов: {r.trades} · 📅 Дней в игре: {r.active_days}")
    lines.append(f"🏅 Я {r.player_number}-й игрок Victor FC! Присоединяйся 👇")
    return "\n".join(lines)


# --- State -------------------------------------------------------------------------

def _next_local_midnight(now: Optional[datetime] = None) -> datetime:
    return datetime.combine(local_today(now) + timedelta(days=1), time.min, tzinfo=app_timezone())


async def get_state(db: AsyncSession, user: User) -> AnniversaryStateOut:
    from app.services import halloween_service
    from app.services.game_config_service import get_config

    config = await get_config(db)
    start, end = window(config)
    if not config.anniversary_enabled:
        return AnniversaryStateOut(enabled=False, active=False, starts_at=start, ends_at=end)
    s = settings_of(config)
    key = event_key(config)
    now = _now()
    member = await _member(db, user.id, key)
    claimed = set((await db.execute(select(AnniversaryClaim.ref_key).where(
        AnniversaryClaim.user_id == user.id, AnniversaryClaim.event_key == key,
    ))).scalars().all())
    today = local_today(now).isoformat()

    calendar = [g for g in s["calendar"] if isinstance(g, dict)]
    done = member.calendar_claimed if member else 0
    taken_today = bool(member and member.calendar_last_day == today)
    days = []
    for i, raw in enumerate(calendar, start=1):
        status = "claimed" if i <= done else ("today" if i == done + 1 and not taken_today else "locked")
        days.append(AnniversaryCalendarDayOut(
            n=i, status=status, reward=await reward_bundle_service.describe(db, _bundle(raw, s)),
        ))

    total, goal = await community_total(db, key), _int(s["community_goal"])
    games = member.games if member else 0
    need = max(1, _int(s["community_min_games"]))
    tiers = []
    for tier in _tiers(s):
        pct = _int(tier["pct"])
        tiers.append(AnniversaryTierOut(
            pct=pct, target=goal * pct // 100, reached=_tier_reached(total, goal, pct),
            claimed=f"{key}:community:{pct}" in claimed, reward=await reward_bundle_service.describe(db, _bundle(tier, s)),
        ))
    open_for_claims = start <= now < claim_until(config)
    community_claimable = open_for_claims and games >= need and any(t.reached and not t.claimed for t in tiers)

    return AnniversaryStateOut(
        enabled=True, active=is_active(config, now), finished=now >= end, starts_at=start, ends_at=end,
        claim_until=claim_until(config), teaser_days=_int(s["teaser_days"]),
        calendar=days, calendar_claimed=done, calendar_ready=is_active(config, now) and not taken_today and done < len(calendar),
        day_resets_at=_next_local_midnight(now),
        community=AnniversaryCommunityOut(
            total=total, goal=goal, my_games=games, min_games=need, tiers=tiers, claimable=community_claimable,
        ),
        recap_coins=_int(s["recap_coins"]), recap_claimed=f"{key}:recap" in claimed,
        collection=await halloween_service._collection_out(db, user.id, s.get("collection_id")),
        pack_id=s.get("pack_id"),
    )


# --- Admin -------------------------------------------------------------------------

async def admin_stats(db: AsyncSession, config: GameConfig) -> dict[str, Any]:
    key = event_key(config)
    members = int((await db.execute(
        select(func.count(AnniversaryMember.user_id)).where(AnniversaryMember.event_key == key)
    )).scalar_one())
    by_kind = dict((await db.execute(
        select(AnniversaryClaim.kind, func.count(AnniversaryClaim.id))
        .where(AnniversaryClaim.event_key == key).group_by(AnniversaryClaim.kind)
    )).all())
    return {"members": members, "games": await community_total(db, key, fresh=True),
            "calendar_claims": int(by_kind.get("calendar", 0)), "community_claims": int(by_kind.get("community", 0)),
            "recaps": int(by_kind.get("recap", 0))}


def _valid_bundle(raw: Any, where: str) -> None:
    if not isinstance(raw, dict):
        raise ConflictError(f"{where}: нужен объект {{coins, card_rarity, pack_id, pack, badge}}")
    if _int(raw.get("coins"), 0) < 0:
        raise ConflictError(f"{where}: монеты не могут быть отрицательными")
    if raw.get("card_rarity") not in (None, "", *RARITIES):
        raise ConflictError(f"{where}: неизвестная редкость «{raw.get('card_rarity')}»")


def validate_settings(raw: dict) -> dict:
    """Admin input: known keys only, non-negative numbers, sane bundles."""
    clean: dict[str, Any] = {}
    for k, v in raw.items():
        if k not in DEFAULT_SETTINGS:
            continue
        default = DEFAULT_SETTINGS[k]
        if isinstance(default, int) or (default is None and k.endswith("_id")):
            if v in (None, "", 0) and default is None:
                clean[k] = None
                continue
            n = _int(v, -1)
            if n < 0:
                raise ConflictError(f"«{k}» должно быть неотрицательным числом")
            clean[k] = n
        elif k == "calendar":
            if not isinstance(v, list) or not v:
                raise ConflictError("Календарь — непустой список подарков")
            for i, gift in enumerate(v, start=1):
                _valid_bundle(gift, f"Подарок {i}")
            clean[k] = v
        elif k == "community_tiers":
            if not isinstance(v, list):
                raise ConflictError("Ступени «Сотни» — список {pct, …награда}")
            pcts = [_int(t.get("pct"), 0) if isinstance(t, dict) else 0 for t in v]
            if any(p <= 0 or p > 100 for p in pcts) or len(set(pcts)) != len(pcts):
                raise ConflictError("У ступеней «Сотни» pct от 1 до 100, без повторов")
            for t in v:
                _valid_bundle(t, f"Ступень {t.get('pct')}%")
            clean[k] = v
        else:
            clean[k] = v
    return clean
