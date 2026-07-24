import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.enums import MatchDifficulty, MatchResult, TransactionType
from app.models.match import Match, MatchEvent
from app.models.user import User
from app.schemas.match import ArenaLeaderboardEntry, ArenaStatsOut, MatchOut, StartMatchRequest
from app.services import task_service
from app.services.game_config_service import get_config
from app.services.lineup_service import get_active_lineup
from app.services.wallet_service import credit_coins, lock_user_for_update

BOT_NAMES = [
    "ФК Северный Ветер", "Стальные Орлы", "Городские Тигры", "Речные Волки", "Атлетико Резерв",
    "Юнайтед Роботс", "ФК Комета", "Гранит Юнайтед", "Южный Роверс", "Молния СК",
]


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.match_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.match_hourly_attempts = 0
        user.match_hour_started_at = now
        db.add(user)


async def _ensure_energy_reset(db: AsyncSession, user: User, max_energy: int) -> None:
    today = local_today()
    reset_day = local_today(user.match_energy_reset_at) if user.match_energy_reset_at else None
    if reset_day != today:
        user.match_energy = max_energy
        user.match_energy_reset_at = datetime.now(timezone.utc)
        db.add(user)


def _bot_strength(user_strength: int, difficulty: MatchDifficulty, difficulty_multiplier: dict) -> int:
    multiplier = difficulty_multiplier[difficulty]
    jitter = random.uniform(-0.05, 0.05)
    return max(1, round(user_strength * multiplier * (1 + jitter)))


def _with_jitter(strength: int) -> int:
    return max(1, round(strength * (1 + random.uniform(-0.05, 0.05))))


def _simulate_events(user_strength: int, opponent_strength: int) -> tuple[list[dict], int, int]:
    total = user_strength + opponent_strength
    user_attack_prob = user_strength / total if total else 0.5

    num_chances = random.randint(9, 15)
    minutes = sorted(random.sample(range(1, 90), num_chances))

    events: list[dict] = []
    user_score = 0
    opponent_score = 0

    for minute in minutes:
        team = "user" if random.random() < user_attack_prob else "opponent"
        roll = random.random()
        if roll < 0.28:
            is_goal = random.random() < 0.55
            if is_goal:
                if team == "user":
                    user_score += 1
                else:
                    opponent_score += 1
                events.append(
                    {"minute": minute, "event_type": "goal", "team": team, "description": "⚽ Гол!"}
                )
            else:
                events.append(
                    {"minute": minute, "event_type": "shot", "team": team, "description": "🎯 Удар мимо ворот"}
                )
        elif roll < 0.5:
            events.append(
                {"minute": minute, "event_type": "chance", "team": team, "description": "🔥 Опасный момент у ворот"}
            )
        elif roll < 0.58:
            events.append(
                {"minute": minute, "event_type": "yellow_card", "team": team, "description": "🟨 Жёлтая карточка"}
            )
        else:
            events.append(
                {"minute": minute, "event_type": "possession", "team": team, "description": "⚽ Контроль мяча"}
            )

    events.sort(key=lambda e: e["minute"])
    return events, user_score, opponent_score


async def start_match(db: AsyncSession, user: User, payload: StartMatchRequest) -> MatchOut:
    config = await get_config(db)
    difficulty_multiplier = {
        MatchDifficulty.easy: float(config.difficulty_easy_multiplier),
        MatchDifficulty.medium: float(config.difficulty_medium_multiplier),
        MatchDifficulty.hard: float(config.difficulty_hard_multiplier),
    }
    reward_base = {
        MatchResult.win: config.match_reward_win,
        MatchResult.draw: config.match_reward_draw,
        MatchResult.loss: config.match_reward_loss,
    }

    lineup = await get_active_lineup(db, user)
    if not lineup.is_complete:
        raise ConflictError("Complete your starting XI (4-3-3) before playing a match")

    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.match_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.match_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.hourly_game_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.match_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_energy_reset(db, locked_user, config.match_daily_energy)
    if locked_user.match_energy < 1:
        raise ConflictError("No match energy left today")

    user_strength = _with_jitter(lineup.team_strength)

    opponent_result = await db.execute(
        select(User)
        .where(User.id != locked_user.id, User.is_banned.is_(False))
        .order_by(func.random())
        .limit(1)
    )
    opponent_user = opponent_result.scalar_one_or_none()

    opponent_name = random.choice(BOT_NAMES)
    if opponent_user is not None:
        opponent_lineup = await get_active_lineup(db, opponent_user)
        if opponent_lineup.is_complete:
            opponent_strength = _with_jitter(opponent_lineup.team_strength)
            opponent_name = opponent_user.full_display_name()
        else:
            opponent_strength = _bot_strength(user_strength, payload.difficulty, difficulty_multiplier)
    else:
        opponent_strength = _bot_strength(user_strength, payload.difficulty, difficulty_multiplier)

    events, user_score, opponent_score = _simulate_events(user_strength, opponent_strength)

    if user_score > opponent_score:
        result = MatchResult.win
        locked_user.matches_won += 1
        rating_delta = 15 + max(0, (opponent_strength - user_strength) // 10)
    elif user_score < opponent_score:
        result = MatchResult.loss
        locked_user.matches_lost += 1
        rating_delta = -12 - max(0, (user_strength - opponent_strength) // 10)
    else:
        result = MatchResult.draw
        locked_user.matches_drawn += 1
        rating_delta = 2

    locked_user.arena_rating = max(0, locked_user.arena_rating + rating_delta)
    locked_user.match_energy -= 1

    reward = 0 if locked_user.game_rewards_blocked else round(
        reward_base[result] * difficulty_multiplier[payload.difficulty] + user_score * 5
    )

    match = Match(
        user_id=locked_user.id,
        opponent_user_id=opponent_user.id if opponent_user else None,
        opponent_name=opponent_name,
        difficulty=payload.difficulty,
        user_team_strength=user_strength,
        opponent_team_strength=opponent_strength,
        user_score=user_score,
        opponent_score=opponent_score,
        result=result,
        reward_coins=reward,
        rating_delta=rating_delta,
        lineup_id=lineup.id,
    )
    db.add(match)
    await db.flush()

    for e in events:
        db.add(MatchEvent(match_id=match.id, minute=e["minute"], event_type=e["event_type"], team=e["team"], description=e["description"]))

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.match_reward,
            f"Награда за матч Card Arena ({result.value})", related_object_type="match", related_object_id=match.id,
        )

    lineup_ratings = [slot.card.player.rating for slot in lineup.slots if slot.card]
    await task_service.evaluate_match_min_rating(db, locked_user, lineup_ratings)

    await db.commit()
    await db.refresh(match, attribute_names=["events"])

    return MatchOut.model_validate(match)


async def get_match(db: AsyncSession, user: User, match_id: int) -> MatchOut:
    result = await db.execute(select(Match).where(Match.id == match_id).options(joinedload(Match.events)))
    match = result.unique().scalar_one_or_none()
    if not match:
        raise NotFoundError("Match not found")
    if match.user_id != user.id:
        raise ForbiddenError("This match does not belong to you")
    return MatchOut.model_validate(match)


async def match_history(db: AsyncSession, user: User, limit: int = 20) -> list[MatchOut]:
    result = await db.execute(
        select(Match)
        .where(Match.user_id == user.id)
        .options(joinedload(Match.events))
        .order_by(Match.created_at.desc())
        .limit(limit)
    )
    matches = result.unique().scalars().all()
    return [MatchOut.model_validate(m) for m in matches]


async def arena_stats(db: AsyncSession, user: User) -> ArenaStatsOut:
    config = await get_config(db)
    await _ensure_energy_reset(db, user, config.match_daily_energy)
    await db.commit()
    return ArenaStatsOut(
        matches_won=user.matches_won,
        matches_drawn=user.matches_drawn,
        matches_lost=user.matches_lost,
        arena_rating=user.arena_rating,
        match_energy=user.match_energy,
        max_energy=config.match_daily_energy,
    )


async def arena_leaderboard(db: AsyncSession, limit: int = 20) -> list[ArenaLeaderboardEntry]:
    result = await db.execute(select(User).order_by(User.arena_rating.desc()).limit(limit))
    users = result.scalars().all()
    return [
        ArenaLeaderboardEntry(
            user_id=u.id, display_name=u.full_display_name(), avatar_url=u.avatar_url,
            arena_rating=u.arena_rating, matches_won=u.matches_won,
        )
        for u in users
    ]
