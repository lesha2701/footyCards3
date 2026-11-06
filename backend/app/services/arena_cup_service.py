"""«Кубок выходных» Card Arena: a knockout run open on the configured days,
one per week. The ladder isn't touched: rounds are bots of a growing strength
(GameConfig.arena_cup_round_strength_pct) and pay by the round."""
import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.arena_cup import ArenaCupRun
from app.models.enums import TransactionType
from app.models.user import User
from app.services.arena_ladder_service import BOT_NAMES
from app.services.wallet_service import credit_coins


def week_key(now: Optional[datetime] = None) -> str:
    year, week, _ = (now or datetime.now(timezone.utc)).isocalendar()
    return f"{year}-W{week:02d}"


def is_open(config, now: Optional[datetime] = None) -> bool:
    if not config.arena_cup_enabled:
        return False
    return (now or datetime.now(timezone.utc)).weekday() in (config.arena_cup_weekdays or [])


def _rewards(config) -> list[int]:
    return [int(v) for v in (config.arena_cup_round_rewards or [])]


async def _run(db: AsyncSession, user_id: int, key: str) -> Optional[ArenaCupRun]:
    return await db.scalar(select(ArenaCupRun).where(ArenaCupRun.user_id == user_id, ArenaCupRun.week_key == key))


async def status(db: AsyncSession, user: User, config) -> dict:
    key = week_key()
    run = await _run(db, user.id, key)
    rewards = _rewards(config)
    strength = [int(v) for v in (config.arena_cup_round_strength_pct or [])]
    won = run.rounds_won if run else 0
    champions = await db.scalar(
        select(func.count(ArenaCupRun.id)).where(ArenaCupRun.week_key == key, ArenaCupRun.status == "champion")
    )
    return {
        "open": is_open(config),
        "enabled": bool(config.arena_cup_enabled),
        "total_rounds": len(rewards),
        "rounds_won": won,
        "status": run.status if run else "none",
        "rewards": rewards,
        "next_strength_pct": strength[won] if won < len(strength) else None,
        "champions": int(champions or 0),
    }


async def begin_round(db: AsyncSession, user: User, config) -> dict:
    """The next round's opponent; refuses a closed cup or a finished run."""
    if not is_open(config):
        raise ConflictError("Кубок открыт только в выходные")
    key = week_key()
    run = await _run(db, user.id, key)
    if run is None:
        run = ArenaCupRun(user_id=user.id, week_key=key)
        db.add(run)
        await db.flush()
    if run.status != "active":
        raise ConflictError("Кубок этой недели для тебя уже закончен")
    strengths = [int(v) for v in (config.arena_cup_round_strength_pct or [100])]
    index = min(run.rounds_won, len(strengths) - 1)
    return {
        "user_id": None, "name": random.choice(BOT_NAMES), "avatar_url": None, "points": user.arena_points,
        "bot_ratio": strengths[index] / 100,
        "bot_style": random.choice(("attacking", "possession", "defensive", "counter")),
        "bot_formation": random.choice(("4-3-3", "4-4-2", "4-2-3-1", "3-5-2", "5-3-2", "3-4-3")),
        "cup": {"run_id": run.id, "round": run.rounds_won + 1},
    }


async def settle(db: AsyncSession, locked_user: User, cup: dict, won: bool, config) -> dict:
    """The round's outcome; the caller commits. Returns what it paid."""
    run = await db.scalar(select(ArenaCupRun).where(ArenaCupRun.id == cup["run_id"]).with_for_update())
    rewards = _rewards(config)
    index = int(cup["round"]) - 1
    if run is None or run.status != "active" or run.rounds_won != index:
        return {"coins": 0, "status": run.status if run else "lost", "round": cup["round"]}
    coins = 0
    if won:
        run.rounds_won += 1
        coins = rewards[index] if index < len(rewards) else 0
        if coins > 0 and not locked_user.game_rewards_blocked:
            await credit_coins(
                db, locked_user, coins, TransactionType.arena_cup_reward,
                f"Кубок выходных: раунд {cup['round']}", related_object_type="arena_cup", related_object_id=run.id,
            )
        else:
            coins = 0
        if run.rounds_won >= len(rewards):
            run.status = "champion"
    else:
        run.status = "lost"
    db.add(run)
    return {"coins": coins, "status": run.status, "round": cup["round"], "rounds_won": run.rounds_won}
