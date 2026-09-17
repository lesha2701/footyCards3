import random
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import local_today
from app.models.card import UserCard
from app.models.daily_reward import DailyReward, DailyRewardOption
from app.models.enums import CardSource, Rarity, TransactionType
from app.models.pack import Pack, PackOpening, PackOpeningCard
from app.models.player import Player
from app.models.user import User
from app.schemas.card import UserCardOut
from app.schemas.daily_reward import DailyRewardCalendarOut, DailyRewardClaimOut, DailyRewardDayOut
from app.services.card_creation import create_user_card
from app.services.collection_service import grant_collection_rewards_for_new_cards
from app.services.pack_service import pick_random_player, roll_rarities
from app.services.wallet_service import credit_coins, lock_user_for_update

# Default candidate pool seeded the first time daily_reward_options is read
# and found empty (same lazy-singleton-row pattern as game_config_service's
# GameConfig) — an escalating spread of amounts around this feature's old
# fixed per-day value, keeping each day's special grant (pack/random card)
# on every candidate so a day's "identity" (e.g. "day 4 gives a pack") stays
# recognizable regardless of which candidate gets rolled. Admins can freely
# diverge from this after the fact via the admin panel.
DEFAULT_DAILY_REWARD_OPTIONS: dict[int, list[dict]] = {
    1: [{"coins": c} for c in (40, 45, 50, 55, 60)],
    2: [{"coins": c} for c in (65, 70, 75, 80, 90)],
    3: [{"coins": c} for c in (85, 95, 100, 110, 120)],
    4: [{"coins": c, "free_pack_slug": "basic"} for c in (110, 120, 125, 135, 150)],
    5: [{"coins": c} for c in (130, 140, 150, 160, 175)],
    6: [{"coins": c, "grants_random_card": True} for c in (175, 190, 200, 215, 230)],
    7: [{"coins": c, "free_pack_slug": "premium"} for c in (260, 280, 300, 325, 350)],
}

RANDOM_CARD_RARITY_WEIGHTS = {Rarity.common: 0.55, Rarity.rare: 0.28, Rarity.epic: 0.13, Rarity.legendary: 0.04}


async def _ensure_default_options(db: AsyncSession) -> None:
    count = (await db.execute(select(func.count(DailyRewardOption.id)))).scalar_one()
    if count > 0:
        return
    for day, options in DEFAULT_DAILY_REWARD_OPTIONS.items():
        for index, cfg in enumerate(options, start=1):
            db.add(
                DailyRewardOption(
                    day=day, option_index=index, coins=cfg["coins"],
                    free_pack_slug=cfg.get("free_pack_slug"), grants_random_card=cfg.get("grants_random_card", False),
                )
            )
    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent requests both saw an empty table — the loser just
        # discards its own attempt and reads back what the winner inserted.
        await db.rollback()


async def get_day_options(db: AsyncSession) -> dict[int, list[DailyRewardOption]]:
    await _ensure_default_options(db)
    result = await db.execute(
        select(DailyRewardOption).order_by(DailyRewardOption.day, DailyRewardOption.option_index)
    )
    by_day: dict[int, list[DailyRewardOption]] = {day: [] for day in range(1, 8)}
    for option in result.scalars().all():
        by_day.setdefault(option.day, []).append(option)
    return by_day


def _cycle_start_date(today: date, streak_day: int) -> date:
    """The reward_date of this cycle's day-1 claim, derived (not looked up)
    from today's date and the current cycle position — valid because a
    cycle is always a run of consecutive calendar days (see
    _compute_next_streak: any gap resets streak_day to 1, i.e. starts a new
    cycle whose day-1 date IS today)."""
    return today - timedelta(days=streak_day - 1)


def _resolve_option(user_id: int, cycle_start: date, day: int, candidates: list[DailyRewardOption]) -> DailyRewardOption:
    """Deterministically "randomly" picks this user's reward for `day`
    within the cycle that started on `cycle_start` — deterministic so that
    re-fetching the calendar (or claiming, moments after previewing it)
    always resolves to the same candidate for as long as the cycle lasts,
    with no extra state to persist: the same (user_id, cycle_start, day)
    always seeds the same pick, and a new cycle (new cycle_start) reseeds
    every day's pick at once, exactly the "new random set each cycle"
    behavior asked for. random.Random(str) is used instead of Python's
    built-in hash() because hash() is randomized per-process (PYTHONHASHSEED)
    and would pick differently across requests/workers."""
    if not candidates:
        # Defensive only — _ensure_default_options always seeds every day;
        # this only guards a day an admin has since emptied out entirely.
        return DailyRewardOption(day=day, option_index=0, coins=0)
    rng = random.Random(f"{user_id}:{cycle_start.isoformat()}:{day}")
    return candidates[rng.randrange(len(candidates))]


async def _latest_reward(db: AsyncSession, user_id: int) -> Optional[DailyReward]:
    result = await db.execute(
        select(DailyReward).where(DailyReward.user_id == user_id).order_by(DailyReward.reward_date.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def _compute_next_streak(db: AsyncSession, user_id: int) -> tuple[int, bool]:
    today = local_today()
    latest = await _latest_reward(db, user_id)
    if latest and latest.reward_date == today:
        return latest.streak_day, True
    if latest and latest.reward_date == today - timedelta(days=1):
        next_streak = latest.streak_day + 1
        if next_streak > 7:
            next_streak = 1
        return next_streak, False
    return 1, False


async def get_calendar(db: AsyncSession, user: User) -> DailyRewardCalendarOut:
    next_streak, already_claimed = await _compute_next_streak(db, user.id)
    today = local_today()
    cycle_start = _cycle_start_date(today, next_streak)
    day_options = await get_day_options(db)

    days = []
    for day in range(1, 8):
        opt = _resolve_option(user.id, cycle_start, day, day_options[day])
        pack_name = None
        if opt.free_pack_slug:
            pack = (await db.execute(select(Pack).where(Pack.slug == opt.free_pack_slug))).scalar_one_or_none()
            pack_name = pack.name if pack else opt.free_pack_slug
        days.append(
            DailyRewardDayOut(
                day=day,
                coins=opt.coins,
                free_pack_name=pack_name,
                grants_random_card=opt.grants_random_card,
                is_claimed=already_claimed and day == next_streak,
                is_today=(not already_claimed) and day == next_streak,
            )
        )

    return DailyRewardCalendarOut(current_streak=next_streak, already_claimed_today=already_claimed, days=days)


async def _grant_free_pack(
    db: AsyncSession, user: User, slug: str
) -> tuple[Optional[str], Optional[UserCard], list[int]]:
    result = await db.execute(
        select(Pack).where(Pack.slug == slug).options(joinedload(Pack.rarity_probabilities))
    )
    pack = result.unique().scalar_one_or_none()
    if not pack:
        return None, None, []

    opening = PackOpening(
        user_id=user.id, pack_id=pack.id, price_paid=0,
        idempotency_key=f"daily-reward-{user.id}-{local_today().isoformat()}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(opening)
    await db.flush()

    rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)
    last_card = None
    player_ids: list[int] = []
    for rarity in rarities:
        player = await pick_random_player(db, rarity)
        card = await create_user_card(db, user.id, player.id, CardSource.daily_reward, opening.id)
        db.add(PackOpeningCard(opening_id=opening.id, user_card_id=card.id, user_coach_card_id=None, is_new=False))
        card.player = player
        last_card = card
        player_ids.append(player.id)
    return pack.name, last_card, player_ids


async def _grant_random_card(db: AsyncSession, user: User) -> UserCard:
    rarity = random.choices(
        list(RANDOM_CARD_RARITY_WEIGHTS.keys()), weights=list(RANDOM_CARD_RARITY_WEIGHTS.values()), k=1
    )[0]
    player = await pick_random_player(db, rarity)
    card = await create_user_card(db, user.id, player.id, CardSource.daily_reward)
    card.player = player
    return card


async def claim_daily_reward(db: AsyncSession, user: User) -> DailyRewardClaimOut:
    next_streak, already_claimed = await _compute_next_streak(db, user.id)
    if already_claimed:
        raise ConflictError("Daily reward already claimed today")

    today = local_today()
    cycle_start = _cycle_start_date(today, next_streak)
    day_options = await get_day_options(db)
    opt = _resolve_option(user.id, cycle_start, next_streak, day_options[next_streak])

    locked_user = await lock_user_for_update(db, user.id)

    reward_row = DailyReward(user_id=locked_user.id, reward_date=today, streak_day=next_streak, coins_awarded=opt.coins)
    db.add(reward_row)
    await db.flush()

    if opt.coins > 0:
        await credit_coins(
            db, locked_user, opt.coins, TransactionType.daily_reward,
            f"Ежедневная награда, день {next_streak}", "daily_reward", reward_row.id,
        )

    granted_pack_name = None
    granted_card = None
    touched_player_ids: list[int] = []
    if opt.free_pack_slug:
        granted_pack_name, granted_card, touched_player_ids = await _grant_free_pack(
            db, locked_user, opt.free_pack_slug
        )
        if granted_card:
            reward_row.random_card_id = granted_card.id
    elif opt.grants_random_card:
        granted_card = await _grant_random_card(db, locked_user)
        reward_row.random_card_id = granted_card.id
        touched_player_ids = [granted_card.player_id]

    if touched_player_ids:
        await grant_collection_rewards_for_new_cards(db, locked_user, touched_player_ids)

    db.add(reward_row)
    await db.commit()
    await db.refresh(locked_user)

    return DailyRewardClaimOut(
        streak_day=next_streak,
        coins_awarded=opt.coins,
        new_balance=locked_user.balance,
        granted_card=UserCardOut.model_validate(granted_card) if granted_card else None,
        granted_pack_name=granted_pack_name,
    )
