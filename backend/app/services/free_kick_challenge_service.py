"""«Испытание дня» in the 3D free kick: every player gets the same
`free_kick_challenge_kicks` positions and a target in the goal for each,
derived from the local date — one attempt a day (the unique entry row),
outside the hourly/daily caps of the series. A goal inside the target
scores 50-100 points by how close to its centre, any other goal 10; coins
per target hit plus a bonus for all of them, paid when the last kick is
taken. The day's leaderboard is the entries ordered by score.

Each swipe is replayed with the Python port of the client's engine
(free_kick_3d_engine), as in the series — nothing the client says about
the outcome is trusted."""
import math
import random
from datetime import date, datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.free_kick_challenge import FreeKickChallengeEntry
from app.models.game import GameSession
from app.models.user import User
from app.services import free_kick_3d_engine as engine
from app.services import my_player_service
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

MODE_CHALLENGE = "challenge"
# Same pause before a swipe counts as in the series.
MIN_KICK_MS = 350
# A target forgiving enough for a human swipe (a few ms of tempo moves a
# long curler by half a metre), kept clear of the posts and the bar.
TARGET_RADIUS = 0.7
GOAL_POINTS = 10
LEADERBOARD_SIZE = 20


def day_kicks(day: date, count: int) -> list[dict]:
    """The day's positions (engine seeds) and targets (centre on the goal
    plane and radius, m) — the same for every player."""
    rnd = random.Random(f"free-kick-challenge:{day.isoformat()}")
    kicks = []
    for _ in range(count):
        side = rnd.choice((-1, 1))
        kicks.append({
            "seed": rnd.randrange(1, 2**31 - 1),
            "x": round(side * rnd.uniform(0.6, engine.GOAL_HALF_WIDTH - 0.85), 2),
            "y": round(rnd.uniform(0.6, engine.GOAL_HEIGHT - 0.7), 2),
            "r": TARGET_RADIUS,
        })
    return kicks


def score_kick(result: engine.ShotResult, target: dict) -> tuple[int, bool]:
    """Points for one replayed shot and whether it went in the target."""
    if result.outcome != "goal":
        return 0, False
    x, y, _ = result.end_position
    d = math.hypot(x - target["x"], y - target["y"])
    if d <= target["r"]:
        return 50 + round(50 * (1 - d / target["r"])), True
    return GOAL_POINTS, False


def _targets_out(kicks: list[dict]) -> list[dict]:
    return [{"x": k["x"], "y": k["y"], "r": k["r"]} for k in kicks]


async def _entry(db: AsyncSession, user_id: int, day: date) -> FreeKickChallengeEntry | None:
    return (await db.execute(
        select(FreeKickChallengeEntry).where(FreeKickChallengeEntry.user_id == user_id, FreeKickChallengeEntry.day == day)
    )).scalar_one_or_none()


async def _rank(db: AsyncSession, entry: FreeKickChallengeEntry) -> int:
    better = await db.scalar(select(func.count()).select_from(FreeKickChallengeEntry).where(
        FreeKickChallengeEntry.day == entry.day,
        or_(
            FreeKickChallengeEntry.score > entry.score,
            and_(FreeKickChallengeEntry.score == entry.score, FreeKickChallengeEntry.id < entry.id),
        ),
    ))
    return int(better or 0) + 1


async def overview(db: AsyncSession, user: User) -> dict:
    """Today's challenge: the rules' numbers, the player's attempt and the
    leaderboard."""
    config = await get_config(db)
    day = local_today()
    rows = (await db.execute(
        select(FreeKickChallengeEntry, User)
        .join(User, User.id == FreeKickChallengeEntry.user_id)
        .where(FreeKickChallengeEntry.day == day)
        .order_by(FreeKickChallengeEntry.score.desc(), FreeKickChallengeEntry.id)
        .limit(LEADERBOARD_SIZE)
    )).all()
    mine = await _entry(db, user.id, day)
    players = await db.scalar(select(func.count()).select_from(FreeKickChallengeEntry).where(FreeKickChallengeEntry.day == day))
    return {
        "day": day,
        "total_kicks": config.free_kick_challenge_kicks,
        "coins_per_hit": config.free_kick_challenge_coins_per_hit,
        "perfect_bonus": config.free_kick_challenge_perfect_bonus,
        "players": int(players or 0),
        "my": None if mine is None else {
            "score": mine.score, "hits": mine.hits, "rank": await _rank(db, mine),
            "finished": mine.finished_at is not None, "reward_coins": mine.reward_coins,
        },
        "top": [
            {
                "rank": i + 1, "name": u.full_display_name(), "score": e.score, "hits": e.hits,
                "finished": e.finished_at is not None, "is_me": u.id == user.id,
            }
            for i, (e, u) in enumerate(rows)
        ],
    }


def _start_out(session: GameSession, state: dict, gear: dict) -> dict:
    index = state["current_kick_index"]
    return {
        "session_id": session.id,
        "rating": state["player_rating"],
        "total_kicks": len(state["kicks"]),
        "kick": {"kick_index": index, "seed": state["kicks"][index]["seed"]},
        "targets": _targets_out(state["kicks"]),
        "score": state["score"],
        "hits": state["hits"],
        **gear,
    }


async def start(db: AsyncSession, user: User) -> dict:
    """Begins today's attempt — or picks it up where it was left (an app
    closed mid-way); a finished one can't be played again."""
    config = await get_config(db)
    day = local_today()
    gear = await my_player_service.game_gear(db, user.id)
    entry = await _entry(db, user.id, day)
    if entry is not None:
        session = await db.get(GameSession, entry.session_id) if entry.session_id else None
        if entry.finished_at is not None or session is None or session.status != GameSessionStatus.in_progress:
            raise ConflictError("Сегодняшнее испытание уже сыграно — приходи завтра")
        return _start_out(session, dict(session.server_state), gear)

    now = datetime.now(timezone.utc).isoformat()
    kicks = [{**k, "issued_at": None, "outcome": None, "points": None, "hit": None} for k in day_kicks(day, max(1, config.free_kick_challenge_kicks))]
    kicks[0]["issued_at"] = now
    state = {
        "mode": MODE_CHALLENGE, "day": day.isoformat(), "player_rating": config.free_kick_challenge_rating,
        "kicks": kicks, "current_kick_index": 0, "score": 0, "hits": 0,
    }
    session = GameSession(user_id=user.id, game_type=GameType.free_kick, status=GameSessionStatus.in_progress, server_state=state)
    db.add(session)
    await db.flush()
    db.add(FreeKickChallengeEntry(user_id=user.id, day=day, session_id=session.id))
    try:
        await db.commit()
    except IntegrityError:
        # A second start raced this one: the unique (user, day) row won.
        await db.rollback()
        raise ConflictError("Испытание уже начато")
    await db.refresh(session)
    return _start_out(session, state, gear)


async def shoot(db: AsyncSession, user: User, session_id: int, swipe) -> dict:
    config = await get_config(db)
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.free_kick:
        raise NotFoundError("Game session not found")
    if session.user_id != user.id:
        raise ForbiddenError("This session does not belong to you")
    # Two concurrent swipes on one kick: the second waits here and sees it taken.
    await db.refresh(session, with_for_update=True)
    state = dict(session.server_state)
    if state.get("mode") != MODE_CHALLENGE:
        raise ConflictError("Not a challenge session")
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    kicks = [dict(k) for k in state["kicks"]]
    index = state["current_kick_index"]
    kick = kicks[index]
    issued = ensure_aware(datetime.fromisoformat(kick["issued_at"]))
    if (datetime.now(timezone.utc) - issued).total_seconds() * 1000 < MIN_KICK_MS:
        raise ConflictError("Too fast — take your time to aim")

    result = engine.simulate_shot(
        engine.create_setup(kick["seed"], state["player_rating"]),
        engine.Swipe(swipe.dx, swipe.dy, swipe.curve, swipe.duration_ms),
    )
    points, hit = score_kick(result, kick)
    kick.update(outcome=result.outcome, points=points, hit=hit)
    state["score"] += points
    state["hits"] += int(hit)

    entry = await _entry(db, user.id, date.fromisoformat(state["day"]))
    entry.score = state["score"]
    entry.hits = state["hits"]

    next_kick = None
    reward = 0
    new_balance = None
    if index + 1 < len(kicks):
        state["current_kick_index"] = index + 1
        kicks[index + 1]["issued_at"] = datetime.now(timezone.utc).isoformat()
        next_kick = {"kick_index": index + 1, "seed": kicks[index + 1]["seed"]}
    else:
        locked_user = await lock_user_for_update(db, user.id)
        reward = state["hits"] * config.free_kick_challenge_coins_per_hit
        if state["hits"] == len(kicks):
            reward += config.free_kick_challenge_perfect_bonus
        if locked_user.game_rewards_blocked:
            reward = 0
        if reward > 0:
            await credit_coins(
                db, locked_user, reward, TransactionType.game_reward,
                "Испытание дня в Штрафном", related_object_type="game_session", related_object_id=session.id,
            )
        now = datetime.now(timezone.utc)
        session.status = GameSessionStatus.won
        session.finished_at = now
        session.reward_coins = reward
        # Paid here: the series' claim endpoint must not pay it again.
        session.is_rewarded = True
        entry.reward_coins = reward
        entry.finished_at = now
        new_balance = locked_user.balance

    state["kicks"] = kicks
    session.server_state = state
    db.add(session)
    db.add(entry)
    await db.commit()
    return {
        "outcome": result.outcome, "hit": hit, "points": points, "score": state["score"], "hits": state["hits"],
        "is_finished": next_kick is None, "next_kick": next_kick, "reward_coins": reward, "new_balance": new_balance,
        "rank": await _rank(db, entry) if next_kick is None else None,
    }
