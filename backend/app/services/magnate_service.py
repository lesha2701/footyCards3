"""«Футбольный магнат» — DB layer around magnate_engine.

Same shape as stratego_service: the game lives in MagnateMatch.server_state,
seats in MagnateSeat, hourly/daily counters on User, rewards through
wallet_service under row locks.

Concurrency: every change happens under `SELECT … FOR UPDATE` of the match
row and bumps `version`; actions may carry the version the client saw and
are rejected when it is stale. Overdue work (lobby timer, turn timer, the
overall time limit) is advanced by `_advance`, which takes the row with
SKIP LOCKED and re-checks `next_deadline_at` under the lock — so the lazy
sweep on reads and the bot's background loop (POST /internal/magnate/sweep)
can both run at any time without double-processing a deadline.
"""
import copy
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.enums import TransactionType
from app.models.game_config import GameConfig
from app.models.magnate import MagnateMatch, MagnateSeat
from app.models.user import User
from app.schemas.magnate import (
    MagnateCellOut,
    MagnateGroupOut,
    MagnateInfoOut,
    MagnateLogOut,
    MagnateMatchBriefOut,
    MagnateMatchOut,
    MagnatePlayerOut,
    MagnateRollOut,
    MagnateRoomPreviewOut,
)
from app.services import magnate_engine as engine
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

SEATS = 4
ACTIVE_STATUSES = ("lobby", "in_progress")
LOG_IN_RESPONSE = 30
SWEEP_BATCH = 100
BOT_NAMES = ["Бот Бернабеу", "Бот Сан-Сиро", "Бот Энфилд", "Бот Маракана", "Бот Вестфален", "Бот Камп Ноу"]
_ACTIVE_MSG = "У тебя уже есть партия в «Футбольном магнате» — доиграй её или выйди"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def board_for(config: GameConfig) -> dict:
    return config.magnate_board or engine.DEFAULT_BOARD


def cards_for(config: GameConfig) -> dict:
    return config.magnate_cards or engine.DEFAULT_CARDS


def _settings(config: GameConfig) -> dict:
    return {
        "start_money": config.magnate_start_money, "pass_start_bonus": config.magnate_pass_start_bonus,
        "jail_fine": config.magnate_jail_fine, "max_jail_turns": config.magnate_max_jail_turns,
        "fine_amount": config.magnate_fine_amount, "building_sell_pct": config.magnate_building_sell_pct,
        "max_rounds": config.magnate_max_rounds, "stadium_rents": list(config.magnate_stadium_rents),
        "bot_buy_reserve": config.magnate_bot_buy_reserve, "bot_build_reserve": config.magnate_bot_build_reserve,
    }


# ---------------------------------------------------------------------------
# Limits (same counters as every mini-game, see game_limits_service)
# ---------------------------------------------------------------------------

def _ensure_hourly_reset(user: User) -> None:
    started = user.magnate_hour_started_at
    if started is None or _now() - ensure_aware(started) >= timedelta(hours=1):
        user.magnate_hourly_attempts = 0
        user.magnate_hour_started_at = _now()


def _ensure_daily_reset(user: User) -> None:
    reset_day = local_today(user.magnate_attempts_reset_at) if user.magnate_attempts_reset_at else None
    if reset_day != local_today():
        user.magnate_rewarded_attempts_today = 0
        user.magnate_attempts_reset_at = _now()


async def _active_match_id(db: AsyncSession, user_id: int) -> Optional[int]:
    result = await db.execute(
        select(MagnateMatch.id)
        .join(MagnateSeat, MagnateSeat.match_id == MagnateMatch.id)
        .where(
            MagnateSeat.user_id == user_id, MagnateSeat.replaced_by_bot.is_(False),
            MagnateMatch.status.in_(ACTIVE_STATUSES),
        )
        .order_by(MagnateMatch.id.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def _take_slot(db: AsyncSession, user_id: int, config: GameConfig) -> User:
    """Locks the user, re-checks "one active table" under that lock (so two
    concurrent joins can't both succeed) and spends an hourly play."""
    locked = await lock_user_for_update(db, user_id)
    if await _active_match_id(db, user_id) is not None:
        raise ConflictError(_ACTIVE_MSG)
    _ensure_hourly_reset(locked)
    if locked.magnate_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (_now() - ensure_aware(locked.magnate_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={"hourly_limit": config.hourly_game_limit, "retry_after_seconds": max(0, int(remaining.total_seconds()))},
        )
    locked.magnate_hourly_attempts += 1
    db.add(locked)
    return locked


async def _refund_slots(db: AsyncSession, user_ids: list[int]) -> None:
    """Gives back the hourly play of people whose table never started."""
    for uid in sorted(set(user_ids)):
        user = await lock_user_for_update(db, uid)
        if user.magnate_hourly_attempts > 0:
            user.magnate_hourly_attempts -= 1
            db.add(user)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

async def _lock_match(db: AsyncSession, match_id: int) -> MagnateMatch:
    result = await db.execute(
        select(MagnateMatch).where(MagnateMatch.id == match_id).with_for_update().execution_options(populate_existing=True)
    )
    match = result.scalar_one_or_none()
    if match is None:
        raise NotFoundError("Партия не найдена")
    return match


async def _seats(db: AsyncSession, match_id: int) -> list[MagnateSeat]:
    result = await db.execute(
        select(MagnateSeat).where(MagnateSeat.match_id == match_id).order_by(MagnateSeat.seat)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


def _my_seat(seats: list[MagnateSeat], user_id: int) -> Optional[MagnateSeat]:
    return next((s for s in seats if s.user_id == user_id), None)


def _humans(seats: list[MagnateSeat]) -> list[MagnateSeat]:
    return [s for s in seats if s.user_id is not None and not s.is_bot]


async def _add_seat(db: AsyncSession, match: MagnateMatch, user: User, seats: list[MagnateSeat]) -> MagnateSeat:
    taken = {s.seat for s in seats}
    free = [i for i in range(SEATS) if i not in taken]
    if not free:
        raise ConflictError("За столом нет свободных мест")
    seat = MagnateSeat(match_id=match.id, seat=free[0], user_id=user.id, name=user.full_display_name(), is_bot=False)
    db.add(seat)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Не удалось занять место — попробуй ещё раз")
    seats.append(seat)
    return seat


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def _bump(match: MagnateMatch, state: Optional[dict] = None) -> None:
    if state is not None:
        match.server_state = state
        flag_modified(match, "server_state")
    match.version += 1


async def _start(db: AsyncSession, match: MagnateMatch, config: GameConfig, now: datetime) -> None:
    """Fills empty seats with bots, builds the engine state and plays any
    bot turns up to the first human decision."""
    seats = await _seats(db, match.id)
    used = {s.name for s in seats}
    names = [n for n in BOT_NAMES if n not in used]
    random.shuffle(names)
    taken = {s.seat for s in seats}
    for i in range(SEATS):
        if i not in taken:
            db.add(MagnateSeat(match_id=match.id, seat=i, user_id=None, name=names.pop(), is_bot=True))
    await db.flush()
    seats = await _seats(db, match.id)
    humans = len(_humans(seats))
    try:
        state = engine.new_state(
            board_for(config), cards_for(config), _settings(config),
            [{"name": s.name, "is_bot": s.is_bot, "user_id": s.user_id} for s in seats],
            seed=secrets.token_hex(8),
        )
    except (engine.EngineError, KeyError, TypeError) as exc:
        raise ConflictError(f"Настройки «Футбольного магната» некорректны: {exc}")
    state["ends_at"] = (now + timedelta(minutes=config.magnate_time_limit_minutes)).isoformat()
    state["turn_seconds"] = config.magnate_turn_seconds
    state["max_missed"] = config.magnate_max_missed_turns
    # A table with a single human — vs-bots mode, or a lobby nobody else
    # joined — pays the reduced vs-bots rewards.
    state["reward_pct"] = config.magnate_bot_reward_pct if humans <= 1 else 100
    match.status = "in_progress"
    match.started_at = now
    await _settle(db, match, state, config, now)


def _has_active_human(state: dict) -> bool:
    return any(not p["is_bot"] and not p["bankrupt"] for p in state["players"])


async def _settle(db: AsyncSession, match: MagnateMatch, state: dict, config: GameConfig, now: datetime) -> None:
    """After any change: let bots move, apply the time limit, set the next
    deadline (or finish and pay out). Bumps the version."""
    if not state["finished"] and not _has_active_human(state):
        engine.finish(state, "abandoned")
    engine.run_bots(state)
    ends_at = ensure_aware(datetime.fromisoformat(state["ends_at"]))
    if not state["finished"] and now >= ends_at:
        engine.finish(state, "time")
    if not state["finished"] and not _has_active_human(state):
        engine.finish(state, "abandoned")
    if state["finished"]:
        state["deadline"] = None
        match.next_deadline_at = None
        await _finish(db, match, state, config, now)
    else:
        deadline = now + timedelta(seconds=state["turn_seconds"])
        state["deadline"] = deadline.isoformat()
        match.next_deadline_at = min(deadline, ends_at)
    _bump(match, state)
    db.add(match)


def _place_reward(config: GameConfig, place: int, pct: int) -> int:
    rewards = list(config.magnate_place_rewards or [])
    if place - 1 >= len(rewards):
        return 0
    return max(0, round(rewards[place - 1] * pct / 100))


async def _finish(db: AsyncSession, match: MagnateMatch, state: dict, config: GameConfig, now: datetime) -> None:
    """Places for every seat; coins for humans still at the table, within
    their daily rewarded limit. Runs once: the match row is locked and its
    status flips to finished here."""
    order = engine.standings(state)
    seats = {s.seat: s for s in await _seats(db, match.id)}
    paid_humans = sorted(
        s.user_id for s in seats.values() if s.user_id is not None and not s.is_bot and not s.replaced_by_bot
    )
    locked = {uid: await lock_user_for_update(db, uid) for uid in paid_humans}
    for place, seat_no in enumerate(order, start=1):
        row = seats[seat_no]
        row.place = place
        state["players"][seat_no]["place"] = place
        user = locked.get(row.user_id) if row.user_id is not None else None
        if user is not None and not row.replaced_by_bot:
            _ensure_daily_reset(user)
            reward = 0
            from app.services.club_pass_service import extra_rewarded_attempts

            limit = config.magnate_daily_limit + await extra_rewarded_attempts(db, user.id, config)
            if not user.game_rewards_blocked and user.magnate_rewarded_attempts_today < limit:
                user.magnate_rewarded_attempts_today += 1
                reward = _place_reward(config, place, state.get("reward_pct", 100))
                if reward > 0:
                    await credit_coins(
                        db, user, reward, TransactionType.magnate_reward,
                        f"«Футбольный магнат»: {place}-е место", "magnate_match", match.id,
                    )
            if place == 1:
                user.magnate_wins += 1
            row.reward_coins = reward
            state["players"][seat_no]["reward_coins"] = reward
            db.add(user)
        db.add(row)
    match.status = "finished"
    match.finished_at = now
    match.finish_reason = state["finish_reason"]


async def _cancel_lobby(db: AsyncSession, match: MagnateMatch, seats: list[MagnateSeat]) -> None:
    await _refund_slots(db, [s.user_id for s in _humans(seats)])
    match.status = "cancelled"
    match.finished_at = _now()
    match.next_deadline_at = None
    _bump(match)
    db.add(match)


async def _process_due(db: AsyncSession, match: MagnateMatch, config: GameConfig, now: datetime) -> None:
    """The match row is locked and its next_deadline_at has passed."""
    if match.status == "lobby":
        seats = await _seats(db, match.id)
        humans = _humans(seats)
        if not humans or (match.mode == "private" and len(humans) < 2):
            await _cancel_lobby(db, match, seats)
        else:
            await _start(db, match, config, now)
        return
    state = copy.deepcopy(match.server_state)
    ends_at = ensure_aware(datetime.fromisoformat(state["ends_at"]))
    deadline = state.get("deadline")
    if now < ends_at and deadline and now >= ensure_aware(datetime.fromisoformat(deadline)):
        seat = state["turn"]
        p = state["players"][seat]
        p["missed"] += 1
        engine.log(state, seat, f"{p['name']} не успел — ход сыграл автопилот", "auto")
        engine.play_turn_for(state, seat)
        if not p["is_bot"] and p["missed"] >= state.get("max_missed", 2):
            p["is_bot"] = True
            p["left"] = True
            engine.log(state, seat, f"{p['name']} пропустил {p['missed']} хода подряд — за него играет бот", "auto")
            row = next((s for s in await _seats(db, match.id) if s.seat == seat), None)
            if row is not None:
                row.replaced_by_bot = True
                db.add(row)
    await _settle(db, match, state, config, now)


async def _advance(db: AsyncSession, match_id: int) -> bool:
    """Processes one overdue deadline of one match, if there is one and no
    one else holds the row right now. Commits only when it did something."""
    now = _now()
    result = await db.execute(
        select(MagnateMatch)
        .where(
            MagnateMatch.id == match_id, MagnateMatch.status.in_(ACTIVE_STATUSES),
            MagnateMatch.next_deadline_at.is_not(None), MagnateMatch.next_deadline_at <= now,
        )
        .with_for_update(skip_locked=True).execution_options(populate_existing=True)
    )
    match = result.scalar_one_or_none()
    if match is None:
        return False
    config = await get_config(db)
    await _process_due(db, match, config, now)
    await db.commit()
    return True


async def sweep_due(db: AsyncSession, limit: int = SWEEP_BATCH) -> int:
    """Background tick (bot scheduler → POST /internal/magnate/sweep): one
    step for every match whose lobby/turn/time deadline has passed. Keeps
    tables moving when every player has closed the app."""
    result = await db.execute(
        select(MagnateMatch.id)
        .where(
            MagnateMatch.status.in_(ACTIVE_STATUSES),
            MagnateMatch.next_deadline_at.is_not(None), MagnateMatch.next_deadline_at <= _now(),
        )
        .order_by(MagnateMatch.next_deadline_at).limit(limit)
    )
    advanced = 0
    for match_id in list(result.scalars().all()):
        if await _advance(db, match_id):
            advanced += 1
    return advanced


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

async def create_bot_match(db: AsyncSession, user: User) -> MagnateMatchOut:
    config = await get_config(db)
    locked = await _take_slot(db, user.id, config)
    match = MagnateMatch(mode="bot", status="lobby", creator_id=locked.id)
    db.add(match)
    await db.flush()
    await _add_seat(db, match, locked, [])
    await _start(db, match, config, _now())
    await db.commit()
    return await _hydrate(db, match, locked)


async def join_public_lobby(db: AsyncSession, user: User) -> MagnateMatchOut:
    config = await get_config(db)
    now = _now()
    locked = await _take_slot(db, user.id, config)
    result = await db.execute(
        select(MagnateMatch)
        .where(MagnateMatch.mode == "public", MagnateMatch.status == "lobby", MagnateMatch.next_deadline_at > now)
        .order_by(MagnateMatch.created_at).limit(5)
        .with_for_update(skip_locked=True).execution_options(populate_existing=True)
    )
    target, seats = None, []
    for candidate in result.scalars().all():
        candidate_seats = await _seats(db, candidate.id)
        if len(candidate_seats) < SEATS:
            target, seats = candidate, candidate_seats
            break
    if target is None:
        target = MagnateMatch(
            mode="public", status="lobby", creator_id=locked.id,
            next_deadline_at=now + timedelta(seconds=config.magnate_lobby_wait_seconds),
        )
        db.add(target)
        await db.flush()
    await _add_seat(db, target, locked, seats)
    if len(seats) >= SEATS:
        await _start(db, target, config, now)
    else:
        _bump(target)
        db.add(target)
    await db.commit()
    return await _hydrate(db, target, locked)


async def create_room(db: AsyncSession, user: User) -> MagnateMatchOut:
    config = await get_config(db)
    locked = await _take_slot(db, user.id, config)
    match = MagnateMatch(
        mode="private", status="lobby", creator_id=locked.id, invite_code=secrets.token_hex(4),
        next_deadline_at=_now() + timedelta(minutes=config.magnate_room_wait_minutes),
    )
    db.add(match)
    await db.flush()
    await _add_seat(db, match, locked, [])
    await db.commit()
    return await _hydrate(db, match, locked)


async def _room_by_code(db: AsyncSession, code: str, lock: bool = False) -> MagnateMatch:
    query = select(MagnateMatch).where(MagnateMatch.invite_code == code, MagnateMatch.mode == "private")
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    match = (await db.execute(query)).scalar_one_or_none()
    if match is None:
        raise NotFoundError("Комната не найдена")
    return match


async def preview_room(db: AsyncSession, user: User, code: str) -> MagnateRoomPreviewOut:
    match = await _room_by_code(db, code)
    await _advance(db, match.id)
    match = await _room_by_code(db, code)
    seats = await _seats(db, match.id)
    creator = await db.get(User, match.creator_id) if match.creator_id else None
    return MagnateRoomPreviewOut(
        id=match.id, invite_code=code, creator_name=creator.full_display_name() if creator else "Игрок",
        status=match.status, players=[s.name for s in seats], is_member=_my_seat(seats, user.id) is not None,
    )


async def join_room(db: AsyncSession, user: User, code: str) -> MagnateMatchOut:
    config = await get_config(db)
    now = _now()
    match = await _room_by_code(db, code, lock=True)
    seats = await _seats(db, match.id)
    if _my_seat(seats, user.id) is not None:
        return await _hydrate(db, match, user)
    if match.status != "lobby" or (match.next_deadline_at and ensure_aware(match.next_deadline_at) <= now):
        raise ConflictError("Эта комната уже закрыта")
    if len(seats) >= SEATS:
        raise ConflictError("В комнате нет свободных мест")
    locked = await _take_slot(db, user.id, config)
    await _add_seat(db, match, locked, seats)
    if len(seats) >= SEATS:
        await _start(db, match, config, now)
    else:
        _bump(match)
        db.add(match)
    await db.commit()
    return await _hydrate(db, match, locked)


async def start_room(db: AsyncSession, user: User, match_id: int) -> MagnateMatchOut:
    """The room's creator starts early; bots take the empty seats."""
    config = await get_config(db)
    match = await _lock_match(db, match_id)
    if match.mode != "private" or match.creator_id != user.id:
        raise ForbiddenError("Начать партию может только создатель комнаты")
    if match.status != "lobby":
        raise ConflictError("Партия уже началась или закрыта")
    await _start(db, match, config, _now())
    await db.commit()
    return await _hydrate(db, match, user)


async def leave_match(db: AsyncSession, user: User, match_id: int) -> Optional[MagnateMatchOut]:
    """Lobby: frees the seat (and the hourly play) — returns None, the
    player is no longer at the table (a private room's creator closes the
    whole room instead). In a running match: a bot takes over the seat for
    the rest of the game and the player gets no reward."""
    config = await get_config(db)
    match = await _lock_match(db, match_id)
    seats = await _seats(db, match.id)
    mine = _my_seat(seats, user.id)
    if mine is None or mine.replaced_by_bot:
        raise ForbiddenError("Ты не играешь за этим столом")
    if match.status == "lobby":
        if match.mode == "private" and match.creator_id == user.id:
            await _cancel_lobby(db, match, seats)
        else:
            await _refund_slots(db, [user.id])
            await db.delete(mine)
            seats.remove(mine)
            if not _humans(seats):
                await _cancel_lobby(db, match, seats)
            else:
                _bump(match)
                db.add(match)
            await db.commit()
            return None
        await db.commit()
        return await _hydrate(db, match, user)
    if match.status != "in_progress":
        raise ConflictError("Партия уже завершена")
    state = copy.deepcopy(match.server_state)
    p = state["players"][mine.seat]
    p["is_bot"] = True
    p["left"] = True
    engine.log(state, mine.seat, f"{p['name']} покинул партию — за него играет бот", "auto")
    mine.replaced_by_bot = True
    db.add(mine)
    await _settle(db, match, state, config, _now())
    await db.commit()
    return await _hydrate(db, match, user)


async def act(
    db: AsyncSession, user: User, match_id: int, action: str, cell: Optional[int], version: Optional[int],
) -> MagnateMatchOut:
    match = await _lock_match(db, match_id)
    seats = await _seats(db, match.id)
    mine = _my_seat(seats, user.id)
    if mine is None or mine.replaced_by_bot:
        raise ForbiddenError("Ты не играешь за этим столом")
    if match.status != "in_progress":
        raise ConflictError("Партия не идёт")
    if version is not None and version != match.version:
        raise ConflictError("Состояние партии уже изменилось — обнови экран", details={"version": match.version})
    config = await get_config(db)
    state = copy.deepcopy(match.server_state)
    try:
        engine.apply_action(state, mine.seat, action, cell)
    except engine.EngineError as exc:
        raise ConflictError(str(exc))
    state["players"][mine.seat]["missed"] = 0
    await _settle(db, match, state, config, _now())
    await db.commit()
    return await _hydrate(db, match, user)


async def get_match(db: AsyncSession, user: User, match_id: int) -> MagnateMatchOut:
    await _advance(db, match_id)
    result = await db.execute(
        select(MagnateMatch).where(MagnateMatch.id == match_id).execution_options(populate_existing=True)
    )
    match = result.scalar_one_or_none()
    if match is None:
        raise NotFoundError("Партия не найдена")
    return await _hydrate(db, match, user)


async def list_matches(db: AsyncSession, user: User) -> list[MagnateMatchBriefOut]:
    result = await db.execute(
        select(MagnateMatch, MagnateSeat)
        .join(MagnateSeat, MagnateSeat.match_id == MagnateMatch.id)
        .where(MagnateSeat.user_id == user.id)
        .order_by(MagnateMatch.created_at.desc(), MagnateMatch.id.desc()).limit(20)
    )
    rows = result.all()
    counts: dict[int, int] = {}
    if rows:
        count_result = await db.execute(
            select(MagnateSeat.match_id, func.count(MagnateSeat.id))
            .where(MagnateSeat.match_id.in_([m.id for m, _ in rows])).group_by(MagnateSeat.match_id)
        )
        counts = dict(count_result.all())
    return [
        MagnateMatchBriefOut(
            id=m.id, mode=m.mode, status=m.status, players=counts.get(m.id, 0), my_place=s.place,
            reward_coins=s.reward_coins, left=s.replaced_by_bot, created_at=m.created_at, finished_at=m.finished_at,
        )
        for m, s in rows
    ]


async def get_info(db: AsyncSession, user: User) -> MagnateInfoOut:
    config = await get_config(db)
    reset_day = local_today(user.magnate_attempts_reset_at) if user.magnate_attempts_reset_at else None
    return MagnateInfoOut(
        start_money=config.magnate_start_money, pass_start_bonus=config.magnate_pass_start_bonus,
        jail_fine=config.magnate_jail_fine, fine_amount=config.magnate_fine_amount,
        max_rounds=config.magnate_max_rounds, time_limit_minutes=config.magnate_time_limit_minutes,
        turn_seconds=config.magnate_turn_seconds, max_missed_turns=config.magnate_max_missed_turns,
        lobby_wait_seconds=config.magnate_lobby_wait_seconds, room_wait_minutes=config.magnate_room_wait_minutes,
        place_rewards=list(config.magnate_place_rewards or []), bot_reward_pct=config.magnate_bot_reward_pct,
        daily_limit=config.magnate_daily_limit,
        rewarded_today=user.magnate_rewarded_attempts_today if reset_day == local_today() else 0,
        wins=user.magnate_wins, active_match_id=await _active_match_id(db, user.id),
    )


# ---------------------------------------------------------------------------
# Serialisation — no seed, deck order or RNG counter ever leaves the server
# ---------------------------------------------------------------------------

def _cells_out(board_cells: list[dict], state: Optional[dict]) -> list[MagnateCellOut]:
    out = []
    for i, c in enumerate(board_cells):
        owner = state["owner"][i] if state else None
        out.append(MagnateCellOut(
            index=i, type=c["type"], name=c["name"], group=c.get("group"), price=c.get("price"),
            rent=c.get("rent"), build_cost=c.get("build_cost"), short=c.get("short"), colors=c.get("colors"),
            amount=c.get("amount"), owner_seat=owner,
            level=state["level"][i] if state else 0,
            current_rent=engine.rent_for(state, i) if state and owner is not None else 0,
        ))
    return out


def _iso(value: Optional[str]) -> Optional[datetime]:
    return ensure_aware(datetime.fromisoformat(value)) if value else None


async def _hydrate(db: AsyncSession, match: MagnateMatch, viewer: User) -> MagnateMatchOut:
    seats = await _seats(db, match.id)
    mine = _my_seat(seats, viewer.id)
    if mine is None:
        raise ForbiddenError("Ты не играешь за этим столом")
    state = match.server_state if match.status in ("in_progress", "finished") else None
    base = dict(
        id=match.id, mode=match.mode, status=match.status, version=match.version,
        invite_code=match.invite_code, is_creator=match.creator_id == viewer.id, my_seat=mine.seat,
        server_now=_now(), finish_reason=match.finish_reason, my_place=mine.place, my_reward=mine.reward_coins,
        created_at=match.created_at, started_at=match.started_at, finished_at=match.finished_at,
    )
    if state is None:
        config = await get_config(db)
        board = board_for(config)
        return MagnateMatchOut(
            **base,
            players=[
                MagnatePlayerOut(seat=s.seat, name=s.name, is_bot=s.is_bot, is_me=s.user_id == viewer.id)
                for s in seats
            ],
            groups=[MagnateGroupOut(**g) for g in board["groups"]], cells=_cells_out(board["cells"], None),
            lobby_deadline=ensure_aware(match.next_deadline_at) if match.status == "lobby" and match.next_deadline_at else None,
            max_rounds=config.magnate_max_rounds, turn_seconds=config.magnate_turn_seconds,
        )

    seat_rows = {s.seat: s for s in seats}
    in_play = match.status == "in_progress"
    me = state["players"][mine.seat]
    my_turn = in_play and state["turn"] == mine.seat and not mine.replaced_by_bot
    players = []
    for p in state["players"]:
        row = seat_rows.get(p["seat"])
        players.append(MagnatePlayerOut(
            seat=p["seat"], name=p["name"], is_bot=p["is_bot"], is_me=p["seat"] == mine.seat, left=p["left"],
            cash=p["cash"], pos=p["pos"], in_jail=p["in_jail"], jail_cards=p["jail_cards"],
            skip_turns=p.get("skip_turns", 0),
            bankrupt=p["bankrupt"], capital=engine.capital(state, p["seat"]), missed=p["missed"],
            place=row.place if row else None, reward_coins=row.reward_coins if row else 0,
        ))
    last_roll = state.get("last_roll")
    return MagnateMatchOut(
        **base,
        players=players,
        groups=[MagnateGroupOut(**g) for g in state["groups"]],
        cells=_cells_out(state["cells"], state),
        turn=state["turn"] if in_play else None, phase=state["phase"], my_turn=my_turn,
        pending_cell=(state.get("pending") or {}).get("cell") if in_play else None,
        build_options=engine.build_options(state, mine.seat) if my_turn and state["phase"] in ("roll", "end") else [],
        can_pay_bail=my_turn and state["phase"] == "roll" and me["in_jail"] and me["cash"] >= state["settings"]["jail_fine"],
        can_use_card=my_turn and state["phase"] == "roll" and me["in_jail"] and me["jail_cards"] > 0,
        jail_fine=state["settings"]["jail_fine"], stadium_rents=list(state["settings"].get("stadium_rents") or []),
        round=state["round"], max_rounds=state["settings"]["max_rounds"], turn_seconds=state.get("turn_seconds", 0),
        deadline=_iso(state.get("deadline")) if in_play else None, ends_at=_iso(state.get("ends_at")),
        last_roll=MagnateRollOut(**last_roll) if last_roll else None,
        log=[MagnateLogOut(**e) for e in state["log"][-LOG_IN_RESPONSE:]],
    )
