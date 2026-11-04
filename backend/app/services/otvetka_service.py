"""«Ответка»: a match of `EPISODES` episodes at match minutes, drawn at random
from everything the game has (a penalty, a free kick, one on one, 2 на 1, 3 на
2, пас в разрез, навес) within `LIMITS`. The player plays each; the opponent
answers it, and only then is its answer known. A draw goes to a penalty
shoot-out, sudden death.

The opponent is a bot and is called one. Its answers are rolled at the start
and stay in `server_state`: nothing the client gets before it has played an
episode carries that episode's answer.

The client sends only the input of each episode (a timeline, or a swipe for a
set piece); it is replayed here with the Python ports of the client's engines,
so the outcome, the score and the coins are the server's alone. The usual
counters: the shared hourly cap of matches and a daily cap of rewarded ones —
past it the player keeps playing for nothing.
"""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.user import User
from app.schemas.game import (
    OtvetkaClaimOut,
    OtvetkaEpisodeOut,
    OtvetkaEpisodeRequest,
    OtvetkaResultOut,
    OtvetkaStartOut,
)
from app.services import free_kick_3d_engine as shot_engine
from app.services import my_player_service
from app.services import one_on_one_engine as engine
from app.services import team_attack_engine as team_engine
from app.services.club_pass_service import extra_rewarded_attempts
from app.services.free_kick_3d_engine import Swipe
from app.services.game_config_service import get_config
from app.services.one_on_one_service import ELAPSED_SLACK_MS, _own_card
from app.services.wallet_service import credit_coins, lock_user_for_update

EPISODES = 10
# Episodes of each kind in a match: (at least, at most).
LIMITS: dict[str, tuple[int, int]] = {
    "penalty": (1, 2),
    "free_kick": (1, 2),
    "one_on_one": (1, 3),
    "two_v_one": (1, 3),
    "three_v_two": (1, 3),
    "through_ball": (1, 3),
    "cross": (1, 3),
}
SET_PIECES = ("penalty", "free_kick")
# A swipe needs a human moment, as in the free kick.
MIN_KICK_MS = 350

_rnd = random.SystemRandom()


def plan_kinds(rnd: random.Random) -> list[str]:
    """The match's episodes in order: each kind's minimum, the rest at random
    among those under their maximum, shuffled."""
    kinds = [kind for kind, (least, _) in LIMITS.items() for _ in range(least)]
    while len(kinds) < EPISODES:
        kinds.append(rnd.choice([kind for kind, (_, most) in LIMITS.items() if kinds.count(kind) < most]))
    rnd.shuffle(kinds)
    return kinds


def plan_minutes(rnd: random.Random) -> list[int]:
    """One minute in each equal stretch of the 90: ascending, spread out."""
    stretch = 90 // EPISODES
    return [i * stretch + rnd.randint(1, stretch) for i in range(EPISODES)]


def _seed() -> int:
    return _rnd.randrange(1, 2**31 - 1)


def _roll_answer(config, kind: str) -> bool:
    pct = config.otvetka_bot_penalty_pct if kind == "penalty" else config.otvetka_bot_goal_pct
    return _rnd.randrange(100) < pct


def _episode(config, kind: str, minute: int | None) -> dict:
    return {
        "kind": kind, "minute": minute, "seed": _seed(), "issued_at": None,
        "outcome": None, "opponent_goal": _roll_answer(config, kind),
    }


def _issue(episode: dict) -> dict:
    return {**episode, "issued_at": datetime.now(timezone.utc).isoformat()}


def _episode_out(index: int, episode: dict) -> OtvetkaEpisodeOut:
    return OtvetkaEpisodeOut(episode_index=index, kind=episode["kind"], minute=episode["minute"], seed=episode["seed"])


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.otvetka_attempts_reset_at) if user.otvetka_attempts_reset_at else None
    if reset_day != today:
        user.otvetka_rewarded_attempts_today = 0
        user.otvetka_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _take_hourly_attempt(db: AsyncSession, user: User, limit: int) -> None:
    now = datetime.now(timezone.utc)
    started = user.otvetka_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.otvetka_hourly_attempts = 0
        user.otvetka_hour_started_at = now
    if user.otvetka_hourly_attempts >= limit:
        remaining = timedelta(hours=1) - (now - ensure_aware(user.otvetka_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={"hourly_limit": limit, "retry_after_seconds": max(0, int(remaining.total_seconds()))},
        )
    user.otvetka_hourly_attempts += 1
    db.add(user)


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.otvetka:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


def _replay(episode: dict, rating: int, payload: OtvetkaEpisodeRequest) -> tuple[str, int]:
    """The episode's outcome and its length in ticks (0 for a set piece)."""
    kind = episode["kind"]
    if kind in SET_PIECES:
        if payload.swipe is None:
            raise ConflictError("This episode is a set piece")
        q = payload.swipe
        setup = (
            shot_engine.create_penalty_setup(episode["seed"], rating) if kind == "penalty"
            else shot_engine.create_setup(episode["seed"], rating)
        )
        return shot_engine.simulate_shot(setup, Swipe(q.dx, q.dy, q.curve, q.duration_ms)).outcome, 0
    if payload.swipe is not None:
        raise ConflictError("This episode is played, not kicked")
    shot = payload.shot
    base = dict(
        controls=[(c[0], c[1], c[2]) for c in payload.controls],
        feint=(payload.feint.tick, payload.feint.dir) if payload.feint else None,
        shot=(shot.tick, Swipe(shot.dx, shot.dy, shot.curve, shot.duration_ms)) if shot else None,
    )
    if kind == "one_on_one":
        end = engine.replay_episode(engine.create_episode(episode["seed"], rating), engine.Timeline(**base))
    else:
        passes = [(p.tick, (p.target, p.mode, p.power)) for p in payload.passes]
        end = team_engine.replay_team(
            team_engine.create_team_episode(kind, episode["seed"], rating), team_engine.TeamTimeline(**base, passes=passes),
        )
    return end.outcome, end.tick


async def start(db: AsyncSession, user: User, user_card_id: int) -> OtvetkaStartOut:
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    await _take_hourly_attempt(db, locked, config.hourly_game_limit)
    await _ensure_daily_reset(db, locked)
    card = await _own_card(db, locked, user_card_id)

    kinds = plan_kinds(_rnd)
    minutes = plan_minutes(_rnd)
    episodes = [_episode(config, kind, minute) for kind, minute in zip(kinds, minutes)]
    episodes[0] = _issue(episodes[0])
    session = GameSession(
        user_id=locked.id, game_type=GameType.otvetka, status=GameSessionStatus.in_progress,
        server_state={
            "player_rating": card.player.rating, "episodes": episodes, "current_index": 0,
            "my_score": 0, "opponent_score": 0, "shootout_my": 0, "shootout_opponent": 0,
            "goals_coins": 0,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return OtvetkaStartOut(
        session_id=session.id, rating=card.player.rating, total_episodes=EPISODES, opponent="Бот",
        goal_coins=config.otvetka_goal_coins, win_coins=config.otvetka_win_coins, loss_coins=config.otvetka_loss_coins,
        episode=_episode_out(0, episodes[0]), **await my_player_service.game_gear(db, locked.id),
    )


async def play_episode(db: AsyncSession, user: User, session_id: int, payload: OtvetkaEpisodeRequest) -> OtvetkaResultOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    # Two concurrent submissions of one episode: the second waits here and sees it taken.
    await db.refresh(session, with_for_update=True)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    state = dict(session.server_state)
    episodes = list(state["episodes"])
    index = state["current_index"]
    episode = dict(episodes[index])
    if episode["outcome"] is not None:
        raise ConflictError("This episode has already been played")

    outcome, ticks = _replay(episode, state["player_rating"], payload)
    issued = ensure_aware(datetime.fromisoformat(episode["issued_at"]))
    elapsed_ms = (datetime.now(timezone.utc) - issued).total_seconds() * 1000
    if elapsed_ms < max(MIN_KICK_MS, ticks * engine.TICK * 1000 - ELAPSED_SLACK_MS):
        raise ConflictError("Too fast — this episode couldn't have been played yet")

    goal = outcome == "goal"
    answer = episode["opponent_goal"]
    shootout = index >= EPISODES
    coins = 0
    if shootout:
        state["shootout_my"] += int(goal)
        state["shootout_opponent"] += int(answer)
    else:
        state["my_score"] += int(goal)
        state["opponent_score"] += int(answer)
        coins = config.otvetka_goal_coins if goal else 0
        state["goals_coins"] += coins
    episodes[index] = {**episode, "outcome": outcome, "timeline": payload.model_dump()}

    # Past the 90 minutes it ends on the score, or in sudden death on a round
    # that split them.
    level = state["my_score"] == state["opponent_score"]
    over = index + 1 >= EPISODES and (not level or (shootout and goal != answer))
    next_out = None
    result = None
    if over:
        won = state["my_score"] > state["opponent_score"] or (level and goal)
        result = "win" if won else "loss"
        session.status = GameSessionStatus.won if won else GameSessionStatus.lost
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = state["goals_coins"] + (config.otvetka_win_coins if won else config.otvetka_loss_coins)
    else:
        if index + 1 >= EPISODES:
            episodes.append(_episode(config, "penalty", None))
        episodes[index + 1] = _issue(episodes[index + 1])
        state["current_index"] = index + 1
        next_out = _episode_out(index + 1, episodes[index + 1])

    state["episodes"] = episodes
    session.server_state = state
    db.add(session)
    await db.commit()
    return OtvetkaResultOut(
        outcome=outcome, opponent_goal=answer, my_score=state["my_score"], opponent_score=state["opponent_score"],
        shootout_my=state["shootout_my"], shootout_opponent=state["shootout_opponent"],
        coins_this_episode=coins, total_coins=state["goals_coins"], is_finished=over, result=result,
        reward_coins=session.reward_coins if over else None, next_episode=next_out,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> OtvetkaClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status not in (GameSessionStatus.won, GameSessionStatus.lost):
        raise ConflictError("Session is still in progress")

    locked = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked)
    daily_cap_reached = locked.otvetka_rewarded_attempts_today >= config.otvetka_daily_limit + await extra_rewarded_attempts(
        db, locked.id, config
    )

    reward = 0 if (locked.game_rewards_blocked or daily_cap_reached) else session.reward_coins
    session.is_rewarded = True
    if not daily_cap_reached:
        locked.otvetka_rewarded_attempts_today += 1
    if reward > 0:
        await credit_coins(
            db, locked, reward, TransactionType.game_reward,
            "Награда за Ответку", related_object_type="game_session", related_object_id=session.id,
        )
    db.add(session)
    await db.commit()
    await db.refresh(locked)
    return OtvetkaClaimOut(reward_coins=reward, new_balance=locked.balance)
