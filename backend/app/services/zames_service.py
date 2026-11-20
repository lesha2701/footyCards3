"""«Замес» — a cartoon fan brawl, one against a crowd (frontend `lib/zames`).

The fight runs on the phone, so the server can't see it. Like «Ферги Тайм»,
it only records that a run was played out and pays by what it can bound:
a base fee plus `zames_wave_coins` for every cleared wave, waves capped by
`zames_max_waves`. The client's numbers are only believed as far as the clock
allows: a wave takes at least `MIN_WAVE_SECONDS`, and nobody knocks out more
than `MAX_KNOCKOUTS_PER_WAVE` fans in one — the claim is clamped, not refused,
so a slow phone never loses a reward. The usual counters: the shared hourly cap
and a daily cap of rewarded runs; past it a run still counts, it pays nothing.
"""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.monetization import Cosmetic
from app.models.user import User
from app.schemas.game import ZamesFinishIn, ZamesFinishOut, ZamesInfoOut, ZamesStartOut
from app.services.club_pass_service import extra_rewarded_attempts
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

MODES = ("derby", "endless")
MIN_WAVE_SECONDS = 6
MAX_KNOCKOUTS_PER_WAVE = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.zames_attempts_reset_at) if user.zames_attempts_reset_at else None
    if reset_day != today:
        user.zames_rewarded_attempts_today = 0
        user.zames_attempts_reset_at = _now()
        db.add(user)


def _take_hourly_attempt(db: AsyncSession, user: User, limit: int) -> None:
    now = _now()
    started = user.zames_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.zames_hourly_attempts = 0
        user.zames_hour_started_at = now
    if user.zames_hourly_attempts >= limit:
        remaining = timedelta(hours=1) - (now - ensure_aware(user.zames_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={"hourly_limit": limit, "retry_after_seconds": max(0, int(remaining.total_seconds()))},
        )
    user.zames_hourly_attempts += 1
    db.add(user)


async def _daily_cap(db: AsyncSession, user: User, config, claim: bool) -> int:
    used = user.zames_rewarded_attempts_today if claim else None
    base = config.zames_daily_limit if claim else None
    return config.zames_daily_limit + await extra_rewarded_attempts(
        db, user.id, config, game="zames", used=used, base=base)


async def info(db: AsyncSession, user: User) -> ZamesInfoOut:
    config = await get_config(db)
    cap = await _daily_cap(db, user, config, claim=False)
    today = local_today()
    used = user.zames_rewarded_attempts_today
    if not user.zames_attempts_reset_at or local_today(user.zames_attempts_reset_at) != today:
        used = 0
    return ZamesInfoOut(
        base_coins=config.zames_base_coins, wave_coins=config.zames_wave_coins, max_waves=config.zames_max_waves,
        daily_limit=cap, rewarded_left=max(0, cap - used), best_knockouts=user.zames_best_knockouts,
        skin=await _skin(db, user),
    )


async def _skin(db: AsyncSession, user: User) -> str | None:
    """The equipped hero skin's style key (cosmetics kind "zames_hero") — the look only."""
    if not user.equipped_zames_hero_id:
        return None
    cosmetic = await db.get(Cosmetic, user.equipped_zames_hero_id)
    return cosmetic.style_key if cosmetic is not None and cosmetic.kind == "zames_hero" else None


async def start(db: AsyncSession, user: User, mode: str) -> ZamesStartOut:
    if mode not in MODES:
        raise ConflictError("Неизвестный режим")
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    _take_hourly_attempt(db, locked, config.hourly_game_limit)
    _ensure_daily_reset(db, locked)
    # Walked out of the last one: it stays unplayed.
    await db.execute(
        update(GameSession)
        .where(
            GameSession.user_id == locked.id, GameSession.game_type == GameType.zames,
            GameSession.status == GameSessionStatus.in_progress,
        )
        .values(status=GameSessionStatus.expired)
    )
    seed = random.randrange(1, 2**31 - 1)
    session = GameSession(
        user_id=locked.id, game_type=GameType.zames, status=GameSessionStatus.in_progress,
        server_state={"mode": mode, "seed": seed},
    )
    db.add(session)
    cap = await _daily_cap(db, locked, config, claim=False)
    await db.commit()
    return ZamesStartOut(session_id=session.id, seed=seed, rewarded_left=max(0, cap - locked.zames_rewarded_attempts_today))


def _believable_waves(claimed: int, elapsed: timedelta) -> int:
    return max(0, min(claimed, int(elapsed.total_seconds() // MIN_WAVE_SECONDS)))


async def finish(db: AsyncSession, user: User, session_id: int, payload: ZamesFinishIn) -> ZamesFinishOut:
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    session = (await db.execute(
        select(GameSession)
        .where(GameSession.id == session_id, GameSession.user_id == locked.id, GameSession.game_type == GameType.zames)
        .with_for_update()
    )).scalar_one_or_none()
    if session is None:
        raise NotFoundError("Замес не найден")
    state = dict(session.server_state or {})
    if session.status == GameSessionStatus.won:
        # A retried request: what the first one paid, nothing more.
        await db.commit()
        return ZamesFinishOut(
            reward_coins=session.reward_coins, new_balance=locked.balance,
            daily_cap_reached=bool(state.get("capped")), waves_paid=int(state.get("waves_paid", 0)),
            best_knockouts=locked.zames_best_knockouts, new_record=bool(state.get("new_record")),
        )
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("Этот замес уже закончился")

    elapsed = _now() - ensure_aware(session.created_at)
    waves = _believable_waves(payload.waves, elapsed)
    knockouts = min(payload.knockouts, (waves + 1) * MAX_KNOCKOUTS_PER_WAVE)
    waves_paid = min(waves, config.zames_max_waves)

    _ensure_daily_reset(db, locked)
    cap = await _daily_cap(db, locked, config, claim=True)
    capped = locked.zames_rewarded_attempts_today >= cap
    reward = 0
    if not capped and not locked.game_rewards_blocked:
        reward = config.zames_base_coins + config.zames_wave_coins * waves_paid
    if not capped:
        locked.zames_rewarded_attempts_today += 1
    if reward > 0:
        await credit_coins(
            db, locked, reward, TransactionType.game_reward,
            "Награда за Замес", related_object_type="game_session", related_object_id=session.id,
        )
    new_record = knockouts > locked.zames_best_knockouts
    if new_record:
        locked.zames_best_knockouts = knockouts
    # «won» marks a run played out, not who won it (same as «Ферги Тайм»).
    session.status = GameSessionStatus.won
    session.finished_at = _now()
    session.reward_coins = reward
    session.is_rewarded = True
    session.score = knockouts
    session.server_state = {
        **state, "waves": waves, "knockouts": knockouts, "best_combo": payload.best_combo,
        "won": payload.won, "waves_paid": waves_paid, "capped": capped, "new_record": new_record,
    }
    db.add(session)
    db.add(locked)
    await db.commit()
    await db.refresh(locked)
    return ZamesFinishOut(
        reward_coins=reward, new_balance=locked.balance, daily_cap_reached=capped,
        waves_paid=waves_paid, best_knockouts=locked.zames_best_knockouts, new_record=new_record,
    )
