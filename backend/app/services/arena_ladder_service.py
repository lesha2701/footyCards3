"""Card Arena divisions: Elo-like arena points, numbered divisions with a
promotion shield, first-reach rewards and the opponent search.

Arena points are separate from User.arena_rating (+3/+1/-1 per match),
which keeps feeding the overall «Лига» unchanged. Division N is index N-1
of GameConfig.arena_division_* (parallel lists, thresholds ascending from
0), so the ladder is tuned from the admin panel without a deploy.

Only the player who plays the match moves: the opponent's points are read,
never written (the opponent isn't online — their squad is borrowed).
"""
import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MatchResult, TransactionType
from app.models.user import User
from app.services.wallet_service import credit_coins

BOT_NAMES = [
    "ФК Северный Ветер", "Стальные Орлы", "Городские Тигры", "Речные Волки", "Атлетико Резерв",
    "Юнайтед Роботс", "ФК Комета", "Гранит Юнайтед", "Южный Роверс", "Молния СК",
]

_SCORE = {MatchResult.win: 1.0, MatchResult.draw: 0.5, MatchResult.loss: 0.0}


def thresholds(config) -> list[int]:
    values = [int(v) for v in (config.arena_division_min_points or [0])]
    return values or [0]


def _at(values, index: int, default: int) -> int:
    values = list(values or [])
    return int(values[index]) if 0 <= index < len(values) else default


def division_of(points: int, config) -> int:
    """1-based division for `points` (the highest threshold reached)."""
    division = 1
    for i, minimum in enumerate(thresholds(config)):
        if points >= minimum:
            division = i + 1
    return division


def division_info(user: User, config) -> dict:
    mins = thresholds(config)
    division = division_of(user.arena_points, config)
    next_min = mins[division] if division < len(mins) else None
    return {
        "division": division,
        "total_divisions": len(mins),
        "points": user.arena_points,
        "min_points": mins[division - 1],
        "next_min_points": next_min,
        "shield_matches": user.arena_shield_matches,
        "coin_pct": coin_pct(division, config),
        "next_reward_coins": _at(config.arena_division_reward_coins, division, 0) if next_min is not None else None,
    }


def coin_pct(division: int, config) -> int:
    return _at(config.arena_division_coin_pct, division - 1, 100)


def expected_score(points: int, opponent_points: int, config) -> float:
    scale = max(50, int(config.arena_points_scale))
    return 1 / (1 + 10 ** ((opponent_points - points) / scale))


def points_change(points: int, opponent_points: int, result: MatchResult, config) -> int:
    k = max(1, int(config.arena_points_k))
    return round(k * (_SCORE[result] - expected_score(points, opponent_points, config)))


def points_preview(points: int, opponent_points: int, config) -> dict:
    return {r.value: points_change(points, opponent_points, r, config) for r in MatchResult}


async def apply_result(db: AsyncSession, locked_user: User, opponent_points: int, result: MatchResult, config) -> dict:
    """Moves the (already row-locked) user on the ladder and grants the
    first-reach reward of every division newly reached. The caller commits.
    Returns the audit dict stored as server_state["ladder"]."""
    before = locked_user.arena_points
    division_before = division_of(before, config)
    delta = points_change(before, opponent_points, result, config)
    after = max(0, before + delta)

    shield_used = False
    shield = locked_user.arena_shield_matches
    if shield > 0:
        floor = thresholds(config)[division_before - 1]
        if after < floor:
            after, shield_used = floor, True
        shield -= 1

    division_after = division_of(after, config)
    promoted = division_after > division_before
    if promoted:
        shield = max(0, int(config.arena_shield_matches))

    locked_user.arena_points = after
    locked_user.arena_shield_matches = shield

    rewards: list[dict] = []
    if division_after > locked_user.arena_best_division:
        for division in range(locked_user.arena_best_division + 1, division_after + 1):
            coins = _at(config.arena_division_reward_coins, division - 1, 0)
            if coins > 0 and not locked_user.game_rewards_blocked:
                await credit_coins(
                    db, locked_user, coins, TransactionType.arena_division_reward,
                    f"Card Arena: дивизион {division}", related_object_type="arena_division",
                    related_object_id=division,
                )
                rewards.append({"division": division, "coins": coins})
        locked_user.arena_best_division = division_after
    db.add(locked_user)

    return {
        "points_before": before,
        "points_after": after,
        "delta": after - before,
        "division_before": division_before,
        "division_after": division_after,
        "promoted": promoted,
        "relegated": division_after < division_before,
        "shield_used": shield_used,
        "shield_left": shield,
        "rewards": rewards,
    }


async def find_opponent(db: AsyncSession, user: User, config) -> dict:
    """Picks the next opponent: a real Arena player within the matchmaking
    window of arena points (closest first among a random sample), else any
    real player (bootstrap — their name/squad, your points), else a bot of
    your strength. The result is stored on the user until that match is
    played, so a re-roll can't fish for an easier one."""
    window = max(0, int(config.arena_matchmaking_window))
    base = select(User).where(User.id != user.id, User.is_banned.is_(False), User.is_admin.is_(False))
    near = (
        await db.execute(
            base.where(
                User.arena_last_strength.is_not(None),
                User.arena_points.between(user.arena_points - window, user.arena_points + window),
            ).order_by(func.random()).limit(5)
        )
    ).scalars().all()
    if not near:
        near = (
            await db.execute(
                base.where(User.arena_last_strength.is_not(None))
                .order_by(func.abs(User.arena_points - user.arena_points)).limit(5)
            )
        ).scalars().all()
    if not near:
        near = (await db.execute(base.order_by(func.random()).limit(5))).scalars().all()

    pending: dict
    if near:
        opponent = random.choice(list(near))
        pending = {
            "user_id": opponent.id,
            "name": opponent.full_display_name(),
            "avatar_url": opponent.avatar_url,
            "points": opponent.arena_points if opponent.arena_last_strength is not None else user.arena_points,
        }
    else:
        pending = {"user_id": None, "name": random.choice(BOT_NAMES), "avatar_url": None, "points": user.arena_points}
    # A bot stand-in (also used if the real opponent's squad turns out to be
    # incomplete): strength relative to yours, its own random style.
    pending["bot_ratio"] = round(random.uniform(0.9, 1.1), 3)
    pending["bot_style"] = random.choice(("attacking", "possession", "defensive", "counter"))
    pending["found_at"] = datetime.now(timezone.utc).isoformat()
    return pending


async def leaderboard(db: AsyncSession, limit: int = 20) -> list[User]:
    result = await db.execute(
        select(User).where(User.is_admin.is_(False), User.is_banned.is_(False))
        .order_by(User.arena_points.desc(), User.matches_won.desc(), User.id).limit(limit)
    )
    return list(result.scalars().all())


async def points_rank(db: AsyncSession, user: User) -> Optional[int]:
    if user.arena_last_strength is None and user.arena_points == 0:
        return None
    higher = await db.scalar(
        select(func.count(User.id)).where(
            User.is_admin.is_(False), User.is_banned.is_(False), User.arena_points > user.arena_points,
        )
    )
    return int(higher or 0) + 1
