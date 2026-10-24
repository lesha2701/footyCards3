"""«Топ недели»: every Monday the top places of each ranking (the boards of
the «Рейтинг» page plus this week's games, Stars and referrals) get the
reward of their place — coins, a pack, a frame (GameConfig.weekly_top_*,
one reward_bundle per place). Each win is a WeeklyTopAward the player sees
as a popup, one per ranking taken.

There is no scheduler of its own: the bot calls /internal/weekly-top/settle
every few minutes and the Mini App settles lazily on GET /weekly-top/awards.
The WeeklyTopRun primary key makes a week settle exactly once. Standings
(ratings, collection sizes) are read when the week is settled — a few
minutes into Monday; the weekly boards count the closed week itself.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CardSource, NotificationType, TransactionType
from app.models.game_config import GameConfig
from app.models.monetization import Cosmetic
from app.models.user import User
from app.models.weekly_top import WeeklyTopAward, WeeklyTopRun
from app.schemas.ranking import RankingMetric
from app.schemas.weekly_top import WeeklyTopAwardOut, WeeklyTopInfoOut, WeeklyTopPlaceOut
from app.services import ranking_service, reward_bundle_service
from app.services.club_league_service import week_bounds, week_start_for
from app.services.game_config_service import get_config
from app.services.notification_service import notify
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import lock_user_for_update

logger = logging.getLogger(__name__)

METRIC_LABELS: dict[RankingMetric, str] = {
    RankingMetric.arena_rating: "Рейтинг Arena",
    RankingMetric.tactics_rating: "Рейтинг Тактико",
    RankingMetric.penalty_rating: "Рейтинг Пенальти",
    RankingMetric.stratego_rating: "Рейтинг Стратего",
    RankingMetric.stratego_puzzles: "Задачи Стратего",
    RankingMetric.mordoboi_rating: "Рейтинг Мордобоя",
    RankingMetric.kontra_rating: "Арена Контратаки",
    RankingMetric.league_rating: "Рейтинг лиги",
    RankingMetric.matches_won: "Победы",
    RankingMetric.cards_count: "Карт в коллекции",
    RankingMetric.unique_players: "Уникальных игроков",
    RankingMetric.referral_count: "Рефералов",
    RankingMetric.base_level: "Уровень базы",
    RankingMetric.academy_level: "Уровень Академии",
    RankingMetric.academy_prestige: "Престиж Академии",
    RankingMetric.games_week: "Игр за неделю",
    RankingMetric.stars_week: "Звёзд за неделю",
    RankingMetric.referrals_week: "Рефералов за неделю",
}

# Used when the admin hasn't set a ladder (or set fewer places than the top
# size): coins only, falling with the place.
DEFAULT_COINS = (5000, 3500, 2500, 1800, 1500, 1200, 1000, 800, 600, 500)


def metrics_for(config: GameConfig) -> list[RankingMetric]:
    chosen = {m for m in (config.weekly_top_metrics or []) if m in RankingMetric.__members__}
    return [m for m in RankingMetric if not chosen or m.value in chosen]


def bundle_for(config: GameConfig, rank: int) -> Bundle:
    ladder = config.weekly_top_rewards or []
    if rank <= len(ladder) and isinstance(ladder[rank - 1], dict):
        row = ladder[rank - 1]
        return Bundle(
            coins=int(row.get("coins") or 0), pack_id=row.get("pack_id"), card_rarity=row.get("card_rarity"),
            badge_id=row.get("badge_id"), cosmetic_id=row.get("cosmetic_id"),
        )
    return Bundle(coins=DEFAULT_COINS[min(rank, len(DEFAULT_COINS)) - 1])


def last_closed_week(now: Optional[datetime] = None) -> date:
    return week_start_for(now) - timedelta(days=7)


async def settle(db: AsyncSession, week_start: date) -> int:
    """Pays the week's tops once; returns how many places were paid (0 when
    the week was already settled or the feature is off). Commits."""
    config = await get_config(db)
    if not config.weekly_top_enabled:
        return 0
    try:
        async with db.begin_nested():
            run = WeeklyTopRun(week_start=week_start)
            db.add(run)
            await db.flush()
    except IntegrityError:
        await db.rollback()
        return 0

    size = max(1, min(config.weekly_top_size or 10, 100))
    paid = 0
    for metric in metrics_for(config):
        winners = await ranking_service.top_rows(db, metric, size, week_start)
        for rank, (user, value) in enumerate(winners, start=1):
            await _award(db, config, week_start, metric, rank, user.id, value)
            paid += 1
    run.winners = paid
    db.add(run)
    await db.commit()
    if paid:
        logger.info("Weekly top %s settled: %s places paid", week_start, paid)
    return paid


async def _award(
    db: AsyncSession, config: GameConfig, week_start: date, metric: RankingMetric, rank: int, user_id: int, value: int,
) -> None:
    locked = await lock_user_for_update(db, user_id)
    label = METRIC_LABELS.get(metric, metric.value)
    award = WeeklyTopAward(week_start=week_start, metric=metric.value, rank=rank, user_id=user_id, value=value, rewards={})
    db.add(award)
    await db.flush()
    granted = await reward_bundle_service.grant(
        db, locked, bundle_for(config, rank), tx_type=TransactionType.weekly_top_reward,
        description=f"Топ недели: {label}, {rank}-е место", card_source=CardSource.task,
        idempotency_prefix=f"weekly-top-{week_start}-{metric.value}-{rank}", cosmetic_source="weekly_top",
        related_object_type="weekly_top_award", related_object_id=award.id,
    )
    award.rewards = {
        "coins": granted.coins, "pack_name": granted.pack_name, "cards": len(granted.cards),
        "cosmetic_name": granted.cosmetic.name if granted.cosmetic else None,
        "cosmetic_style": granted.cosmetic.style_key if granted.cosmetic else None,
    }
    db.add(award)
    await notify(
        db, user_id, NotificationType.weekly_top, f"🏆 {rank}-е место недели!",
        f"«{label}»: ты в топе недели. Награда уже у тебя — открой игру, чтобы посмотреть.",
        related_object_type="weekly_top_award", related_object_id=award.id,
    )


async def settle_due(db: AsyncSession) -> int:
    """Settles the last closed week if nobody has yet (cheap when done)."""
    week = last_closed_week()
    if await db.get(WeeklyTopRun, week) is not None:
        return 0
    return await settle(db, week)


def _award_out(a: WeeklyTopAward, balance: int = 0) -> WeeklyTopAwardOut:
    metric = RankingMetric(a.metric) if a.metric in RankingMetric.__members__ else None
    r = a.rewards or {}
    return WeeklyTopAwardOut(
        id=a.id, week_start=a.week_start, metric=a.metric,
        metric_label=METRIC_LABELS.get(metric, a.metric) if metric else a.metric,
        rank=a.rank, value=a.value, coins=int(r.get("coins") or 0), pack_name=r.get("pack_name"),
        cards=int(r.get("cards") or 0), cosmetic_name=r.get("cosmetic_name"), cosmetic_style=r.get("cosmetic_style"),
        balance=balance,
    )


async def pending(db: AsyncSession, user: User) -> list[WeeklyTopAwardOut]:
    try:
        await settle_due(db)
    except Exception:  # noqa: BLE001 - a failed settlement must not break the app's start-up call
        logger.exception("Weekly top lazy settlement failed")
        await db.rollback()
    rows = (await db.execute(
        select(WeeklyTopAward).where(WeeklyTopAward.user_id == user.id, WeeklyTopAward.seen_at.is_(None))
        .order_by(WeeklyTopAward.rank, WeeklyTopAward.id)
    )).scalars().all()
    if not rows:
        return []
    balance = (await db.execute(select(User.balance).where(User.id == user.id))).scalar_one()
    return [_award_out(a, balance) for a in rows]


async def mark_seen(db: AsyncSession, user: User, ids: list[int]) -> int:
    rows = (await db.execute(
        select(WeeklyTopAward).where(
            WeeklyTopAward.user_id == user.id, WeeklyTopAward.id.in_(ids or [0]), WeeklyTopAward.seen_at.is_(None),
        )
    )).scalars().all()
    now = datetime.now(timezone.utc)
    for a in rows:
        a.seen_at = now
        db.add(a)
    await db.commit()
    return len(rows)


async def info(db: AsyncSession) -> WeeklyTopInfoOut:
    """What the places pay this week and when the week closes."""
    config = await get_config(db)
    size = max(1, min(config.weekly_top_size or 10, 100))
    places = []
    for rank in range(1, size + 1):
        bundle = bundle_for(config, rank)
        described = await reward_bundle_service.describe(db, bundle)
        cosmetic = await db.get(Cosmetic, bundle.cosmetic_id) if bundle.cosmetic_id else None
        places.append(WeeklyTopPlaceOut(
            rank=rank, coins=bundle.coins, pack_name=described.pack_name,
            cosmetic_name=cosmetic.name if cosmetic else None, cosmetic_style=cosmetic.style_key if cosmetic else None,
        ))
    _, ends_at = week_bounds(week_start_for())
    return WeeklyTopInfoOut(
        enabled=config.weekly_top_enabled, size=size, ends_at=ends_at, places=places,
        metrics=[m.value for m in metrics_for(config)],
        starting_values={m.value: v for m in RankingMetric if (v := ranking_service.starting_value(m))},
    )
