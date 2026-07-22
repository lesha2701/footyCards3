import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import local_today
from app.models.card import UserCard
from app.models.daily_reward import DailyReward
from app.models.enums import CardSource, Rarity, TransactionType
from app.models.pack import Pack, PackOpening, PackOpeningCard
from app.models.player import Player
from app.models.user import User
from app.schemas.card import UserCardOut
from app.schemas.daily_reward import DailyRewardCalendarOut, DailyRewardClaimOut, DailyRewardDayOut
from app.services.card_creation import create_user_card
from app.services.pack_service import pick_random_player, roll_rarities
from app.services.wallet_service import credit_coins, lock_user_for_update

REWARD_TABLE: dict[int, dict] = {
    1: {"coins": 50},
    2: {"coins": 75},
    3: {"coins": 100},
    4: {"coins": 125, "free_pack_slug": "basic"},
    5: {"coins": 150},
    6: {"coins": 200, "grants_random_card": True},
    7: {"coins": 300, "free_pack_slug": "premium"},
}

RANDOM_CARD_RARITY_WEIGHTS = {Rarity.common: 0.55, Rarity.rare: 0.28, Rarity.epic: 0.13, Rarity.legendary: 0.04}


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
    display_streak = next_streak if not already_claimed else next_streak

    days = []
    for day in range(1, 8):
        cfg = REWARD_TABLE[day]
        pack_name = None
        if cfg.get("free_pack_slug"):
            pack = (await db.execute(select(Pack).where(Pack.slug == cfg["free_pack_slug"]))).scalar_one_or_none()
            pack_name = pack.name if pack else cfg["free_pack_slug"]
        days.append(
            DailyRewardDayOut(
                day=day,
                coins=cfg["coins"],
                free_pack_name=pack_name,
                grants_random_card=cfg.get("grants_random_card", False),
                is_claimed=already_claimed and day == next_streak,
                is_today=(not already_claimed) and day == next_streak,
            )
        )

    return DailyRewardCalendarOut(current_streak=display_streak, already_claimed_today=already_claimed, days=days)


async def _grant_free_pack(db: AsyncSession, user: User, slug: str) -> tuple[Optional[str], Optional[UserCard]]:
    result = await db.execute(
        select(Pack).where(Pack.slug == slug).options(joinedload(Pack.rarity_probabilities))
    )
    pack = result.unique().scalar_one_or_none()
    if not pack:
        return None, None

    opening = PackOpening(
        user_id=user.id, pack_id=pack.id, price_paid=0,
        idempotency_key=f"daily-reward-{user.id}-{local_today().isoformat()}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(opening)
    await db.flush()

    rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)
    last_card = None
    for rarity in rarities:
        player = await pick_random_player(db, rarity)
        card = await create_user_card(db, user.id, player.id, CardSource.daily_reward, opening.id)
        db.add(PackOpeningCard(opening_id=opening.id, user_card_id=card.id, is_new_player=False))
        card.player = player
        last_card = card
    return pack.name, last_card


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

    cfg = REWARD_TABLE[next_streak]
    locked_user = await lock_user_for_update(db, user.id)

    reward_row = DailyReward(user_id=locked_user.id, reward_date=local_today(), streak_day=next_streak, coins_awarded=cfg["coins"])
    db.add(reward_row)
    await db.flush()

    if cfg["coins"] > 0:
        await credit_coins(
            db, locked_user, cfg["coins"], TransactionType.daily_reward,
            f"Ежедневная награда, день {next_streak}", "daily_reward", reward_row.id,
        )

    granted_pack_name = None
    granted_card = None
    if cfg.get("free_pack_slug"):
        granted_pack_name, granted_card = await _grant_free_pack(db, locked_user, cfg["free_pack_slug"])
        if granted_card:
            reward_row.random_card_id = granted_card.id
    elif cfg.get("grants_random_card"):
        granted_card = await _grant_random_card(db, locked_user)
        reward_row.random_card_id = granted_card.id

    db.add(reward_row)
    await db.commit()
    await db.refresh(locked_user)

    return DailyRewardClaimOut(
        streak_day=next_streak,
        coins_awarded=cfg["coins"],
        new_balance=locked_user.balance,
        granted_card=UserCardOut.model_validate(granted_card) if granted_card else None,
        granted_pack_name=granted_pack_name,
    )
