import random
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.card import UserCard
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.user import User
from app.schemas.game import (
    FreeKick3DShotRequest,
    Penalty3DDive,
    Penalty3DKickOut,
    Penalty3DResultOut,
    Penalty3DStartOut,
    PenaltyClaimOut,
    PenaltyForfeitOut,
    PenaltyKickOut,
    PenaltyStartOut,
    PenaltyStatsOut,
)
from app.schemas.ranking import RankingMetric
from app.services import free_kick_3d_engine as engine
from app.services import league_service, my_player_service, ranking_service, task_service
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update
from app.services.club_pass_service import extra_rewarded_attempts

# 3x2 grid: which third of the goal (left/center/right) and which half
# (top/bottom) the shot/dive targets. Shared with PvP (see penalty_match_service.py).
PENALTY_ZONES = ("top_left", "top_center", "top_right", "bottom_left", "bottom_center", "bottom_right")
REGULATION_KICKS = 10  # 5 rounds x 2 kicks
MODE_3D = "3d"
# A kick answered faster than this after it was issued is refused: a swipe
# (or a bot's run-up, then a dive) takes a human moment.
MIN_3D_ACTION_MS = 350


def player_miss_chance(rating: int) -> float:
    r = max(58, min(99, rating))
    return 0.30 - (r - 58) / (99 - 58) * (0.30 - 0.05)


def placement_chance(rating: int, max_pct: int) -> float:
    """vs the bot: how often a shot into the corner the keeper picked still
    goes in — 0 at rating 58, `max_pct`% at 99 (GameConfig)."""
    r = max(58, min(99, rating))
    return (r - 58) / (99 - 58) * max(0, max_pct) / 100


def _resolve_shot(miss_chance: float, shot_zone: str, dive_zone: str) -> str:
    """A single blind shot vs. a single blind dive: 'goal', 'saved', or
    'miss'. The shooter's own miss chance is rolled first (independent of
    zones) — only if they don't miss do the zones get compared. Shared by
    the bot mode below and by PvP (which reuses this exact rule, just with
    a real dive instead of a random one)."""
    if random.random() < miss_chance:
        return "miss"
    return "saved" if shot_zone == dive_zone else "goal"


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.penalty_attempts_reset_at) if user.penalty_attempts_reset_at else None
    if reset_day != today:
        user.penalty_rewarded_attempts_today = 0
        user.penalty_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.penalty_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.penalty_hourly_attempts = 0
        user.penalty_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User, user_card_id: int) -> PenaltyStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.penalty_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.penalty_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.hourly_game_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.penalty_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)

    result = await db.execute(
        select(UserCard).where(UserCard.id == user_card_id).options(joinedload(UserCard.player))
    )
    card = result.unique().scalar_one_or_none()
    if not card:
        raise NotFoundError("Card not found")
    if card.owner_id != locked_user.id:
        raise ForbiddenError("You can only use your own cards")

    session = GameSession(
        user_id=locked_user.id, game_type=GameType.penalty, status=GameSessionStatus.in_progress,
        server_state={
            "selected_card_id": card.id, "player_rating": card.player.rating,
            "rounds": [], "player_score": 0, "bot_score": 0, "kicks_taken": 0, "sudden_death": False,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return PenaltyStartOut(session_id=session.id, player_rating=card.player.rating, first_kicker="player")


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.penalty:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


def _current_kicker(state: dict) -> str:
    return "player" if state["kicks_taken"] % 2 == 0 else "bot"


async def _apply_finish(db: AsyncSession, user: User, session: GameSession, state: dict, result: str, config) -> int:
    """Shared by a natural finish (resolve_kick) and an explicit forfeit:
    marks the session finished with the given result, applies the same
    +3/-1 penalty_rating delta Tactico uses (clamped at 0), and returns the
    raw delta so the caller can report it."""
    state["result"] = result
    session.server_state = state
    session.status = GameSessionStatus.won
    session.finished_at = datetime.now(timezone.utc)
    session.reward_coins = {
        "win": config.penalty_reward_win, "loss": config.penalty_reward_loss,
    }[result]
    rating_delta = 3 if result == "win" else -1
    locked_user = await lock_user_for_update(db, user.id)
    locked_user.penalty_rating = max(0, locked_user.penalty_rating + rating_delta)
    db.add(locked_user)
    await league_service.sync_league_rewards_for_user(db, locked_user)
    await task_service.evaluate_penalty_win_max_rating(db, user, state["player_rating"], result == "win")
    return rating_delta


async def resolve_kick(db: AsyncSession, user: User, session_id: int, direction: str) -> PenaltyKickOut:
    if direction not in PENALTY_ZONES:
        raise ConflictError("Invalid direction")

    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    state = dict(session.server_state)
    if state.get("mode") == MODE_3D:
        raise ConflictError("This is a 3D penalty session")
    kicker = _current_kicker(state)

    if kicker == "player":
        bot_dir = random.choice(PENALTY_ZONES)
        outcome = _resolve_shot(player_miss_chance(state["player_rating"]), direction, bot_dir)
        # A strong card can place it past a keeper who guessed right.
        beat_keeper = outcome == "saved" and random.random() < placement_chance(
            state["player_rating"], config.penalty_placement_max_pct,
        )
        if beat_keeper:
            outcome = "goal"
        if outcome == "goal":
            state["player_score"] += 1
        round_entry = {
            "kicker": "player", "player_direction": direction, "bot_direction": bot_dir, "outcome": outcome,
        }
    else:
        bot_shot_dir = random.choice(PENALTY_ZONES)
        outcome = _resolve_shot(float(config.penalty_bot_miss_chance), bot_shot_dir, direction)
        if outcome == "goal":
            state["bot_score"] += 1
        round_entry = {
            "kicker": "bot", "player_direction": direction, "bot_direction": bot_shot_dir, "outcome": outcome,
        }

    state["rounds"] = list(state["rounds"]) + [round_entry]
    state["kicks_taken"] += 1

    is_finished = False
    result: str | None = None
    rating_delta: int | None = None
    if state["kicks_taken"] >= REGULATION_KICKS and state["kicks_taken"] % 2 == 0:
        if state["player_score"] != state["bot_score"]:
            is_finished = True
        else:
            state["sudden_death"] = True

    session.server_state = state
    if is_finished:
        result = "win" if state["player_score"] > state["bot_score"] else "loss"
        # rating_delta is the raw, unclamped delta actually applied to
        # penalty_rating (the clamp only matters when a fresh user is
        # already at 0 and loses) — returned as-is so the frontend can show
        # "+3"/"-1" after the match, same as the PvP match page already does.
        rating_delta = await _apply_finish(db, user, session, state, result, config)

    db.add(session)
    await db.commit()

    next_kicker = None if is_finished else _current_kicker(state)
    return PenaltyKickOut(
        session_id=session.id, kicker=kicker, outcome=outcome,
        player_direction=direction, bot_direction=round_entry["bot_direction"],
        player_score=state["player_score"], bot_score=state["bot_score"],
        next_kicker=next_kicker, is_finished=is_finished, result=result, rating_delta=rating_delta,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> PenaltyClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.won:
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    daily_cap_reached = locked_user.penalty_rewarded_attempts_today >= config.penalty_daily_limit + await extra_rewarded_attempts(
        db, locked_user.id, config
    )

    reward = 0 if (locked_user.game_rewards_blocked or daily_cap_reached) else session.reward_coins
    session.is_rewarded = True
    if not daily_cap_reached:
        locked_user.penalty_rewarded_attempts_today += 1

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.game_reward,
            "Награда за Пенальти", related_object_type="game_session", related_object_id=session.id,
        )
    db.add(session)
    await db.commit()
    await db.refresh(locked_user)

    return PenaltyClaimOut(reward_coins=reward, new_balance=locked_user.balance, result=session.server_state["result"])


async def forfeit_session(db: AsyncSession, user: User, session_id: int) -> PenaltyForfeitOut:
    """Immediately ends an in-progress session as a loss for the player,
    regardless of the partial score — leaving mid-match is never a safer
    bet than finishing it out, same rule Tactico's forfeit enforces. Called
    from the frontend's leave-confirmation dialog (matchGuardStore)."""
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session is not in progress")

    state = dict(session.server_state)
    rating_delta = await _apply_finish(db, user, session, state, "loss", config)
    db.add(session)
    await db.commit()

    return PenaltyForfeitOut(
        session_id=session.id, player_score=state["player_score"], bot_score=state["bot_score"],
        result="loss", rating_delta=rating_delta,
    )


async def get_stats(db: AsyncSession, user: User) -> PenaltyStatsOut:
    ranking = await ranking_service.get_ranking(db, RankingMetric.penalty_rating, user)
    return PenaltyStatsOut(
        penalty_rating=user.penalty_rating,
        penalty_rank=ranking.me.rank if ranking.me else None,
    )


# ---------------------------------------------------------------------------
# «Пенальти» in 3D — the bot shootout. Same rules, counters, rating, reward
# and forfeit as the classic one (_apply_finish, claim_reward,
# forfeit_session); each kick is a seed the server picks, and the outcome is
# the server's own replay with free_kick_3d_engine: the player's swipe
# against the bot keeper, or the bot's strike against the player's dive.
# ---------------------------------------------------------------------------

def _new_3d_kick(index: int) -> dict:
    return {
        "kicker": "player" if index % 2 == 0 else "bot",
        "seed": secrets.randbelow(2**31 - 1) + 1,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "outcome": None,
    }


def _kick_out(index: int, kick: dict) -> Penalty3DKickOut:
    return Penalty3DKickOut(kick_index=index, kicker=kick["kicker"], seed=kick["seed"])


async def start_3d(db: AsyncSession, user: User, user_card_id: int) -> Penalty3DStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.penalty_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.penalty_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={"hourly_limit": config.hourly_game_limit, "retry_after_seconds": max(0, int(remaining.total_seconds()))},
        )
    locked_user.penalty_hourly_attempts += 1
    db.add(locked_user)
    await _ensure_daily_reset(db, locked_user)

    card = (await db.execute(
        select(UserCard).where(UserCard.id == user_card_id).options(joinedload(UserCard.player))
    )).unique().scalar_one_or_none()
    if not card:
        raise NotFoundError("Card not found")
    if card.owner_id != locked_user.id:
        raise ForbiddenError("You can only use your own cards")

    first = _new_3d_kick(0)
    session = GameSession(
        user_id=locked_user.id, game_type=GameType.penalty, status=GameSessionStatus.in_progress,
        server_state={
            "mode": MODE_3D, "selected_card_id": card.id, "player_rating": card.player.rating,
            "kicks": [first], "rounds": [], "player_score": 0, "bot_score": 0, "kicks_taken": 0, "sudden_death": False,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    mp = await my_player_service.get_my_player(db, locked_user.id)
    celebration = my_player_service.cosmetics_of(mp)["celebration"] if mp else None
    return Penalty3DStartOut(session_id=session.id, rating=card.player.rating, kick=_kick_out(0, first), celebration=celebration)


async def _lock_3d_kick(db: AsyncSession, user: User, session_id: int, kicker: str) -> tuple[GameSession, dict, dict]:
    session = await _get_session(db, user.id, session_id)
    # Two concurrent answers to one kick: the second waits here and sees it taken.
    await db.refresh(session, with_for_update=True)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")
    state = dict(session.server_state)
    if state.get("mode") != MODE_3D:
        raise ConflictError("Not a 3D penalty session")
    kick = dict(state["kicks"][state["kicks_taken"]])
    if kick["kicker"] != kicker:
        raise ConflictError("It's not this side's kick")
    if kick["outcome"] is not None:
        raise ConflictError("This kick has already been taken")
    issued = ensure_aware(datetime.fromisoformat(kick["issued_at"]))
    if (datetime.now(timezone.utc) - issued).total_seconds() * 1000 < MIN_3D_ACTION_MS:
        raise ConflictError("Too fast — take your time")
    return session, state, kick


async def _settle_3d(
    db: AsyncSession, user: User, session: GameSession, state: dict, kick: dict, outcome: str, bot_kind: str | None,
) -> Penalty3DResultOut:
    config = await get_config(db)
    index = state["kicks_taken"]
    kicks = list(state["kicks"])
    kicks[index] = {**kick, "outcome": outcome}
    if outcome == "goal":
        state["player_score" if kick["kicker"] == "player" else "bot_score"] += 1
    state["rounds"] = list(state["rounds"]) + [{"kicker": kick["kicker"], "outcome": outcome}]
    state["kicks_taken"] = index + 1

    is_finished = False
    if state["kicks_taken"] >= REGULATION_KICKS and state["kicks_taken"] % 2 == 0:
        if state["player_score"] != state["bot_score"]:
            is_finished = True
        else:
            state["sudden_death"] = True

    result = None
    rating_delta = None
    next_out = None
    if is_finished:
        state["kicks"] = kicks
        result = "win" if state["player_score"] > state["bot_score"] else "loss"
        rating_delta = await _apply_finish(db, user, session, state, result, config)
    else:
        nxt = _new_3d_kick(state["kicks_taken"])
        kicks.append(nxt)
        state["kicks"] = kicks
        next_out = _kick_out(state["kicks_taken"], nxt)
        session.server_state = state
    db.add(session)
    await db.commit()
    return Penalty3DResultOut(
        kicker=kick["kicker"], outcome=outcome, bot_kind=bot_kind,
        player_score=state["player_score"], bot_score=state["bot_score"],
        is_finished=is_finished, result=result, rating_delta=rating_delta, next_kick=next_out,
    )


async def shoot_3d(db: AsyncSession, user: User, session_id: int, swipe: FreeKick3DShotRequest) -> Penalty3DResultOut:
    """The player's penalty: their swipe against the bot keeper."""
    session, state, kick = await _lock_3d_kick(db, user, session_id, "player")
    shot = engine.simulate_shot(
        engine.create_penalty_setup(kick["seed"], state["player_rating"]),
        engine.Swipe(swipe.dx, swipe.dy, swipe.curve, swipe.duration_ms),
    )
    outcome = "save" if shot.outcome == "save" else "goal" if shot.outcome == "goal" else "miss"
    return await _settle_3d(db, user, session, state, kick, outcome, None)


async def save_3d(db: AsyncSession, user: User, session_id: int, dive: Penalty3DDive | None) -> Penalty3DResultOut:
    """The bot's penalty: its strike against the player's dive (or none)."""
    session, state, kick = await _lock_3d_kick(db, user, session_id, "bot")
    d = engine.Dive(dive.x, dive.y, dive.reaction_ms) if dive else None
    kind, bot_swipe = engine.penalty_bot_shot(kick["seed"], d)
    shot = engine.simulate_shot(engine.player_keeper_setup(kick["seed"], d), bot_swipe)
    outcome = "save" if shot.outcome == "save" else "goal" if shot.outcome == "goal" else "miss"
    return await _settle_3d(db, user, session, state, kick, outcome, kind)
