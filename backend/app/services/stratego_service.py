"""«Футбольное Стратего» — DB layer around stratego_engine.

Shape mirrors tactico_service: a JSON server_state per match, async friend
matches with deadlines resolved lazily by `_sweep` on reads, matchmaking via
a queue table, hourly/daily counters on User, rewards through
wallet_service with row locks.

Placement happens *before* a match (saved with the squad, see get_squad /
set_squad), so a match starts straight in play: both sides prepared their
layouts privately and independently, which is what "simultaneous setup"
needs, with no waiting phase inside the match.

Hidden information: the full layout exists only in server_state.
`_hydrate_match` is the single place a match leaves the server, and it
strips every unrevealed enemy piece down to id / position / moved.
"""
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.card import UserCard
from app.models.enums import (
    RARITY_ORDER,
    MatchResult,
    NotificationType,
    Position,
    StrategoMatchStatus,
    StrategoOpponentType,
    TransactionType,
)
from app.models.game_config import GameConfig
from app.models.player import Player
from app.models.stratego import StrategoMatch, StrategoQueueEntry
from app.models.user import User
from app.schemas.stratego import (
    StrategoCardOut,
    StrategoCombatOut,
    StrategoCombatPieceOut,
    StrategoInfoOut,
    StrategoMatchOut,
    StrategoMoveOut,
    StrategoPieceOut,
    StrategoSquadOut,
    StrategoSquadSlotOut,
)
from app.services import stratego_engine as engine
from app.services.game_config_service import get_config
from app.services.match_service import BOT_NAMES
from app.services.notification_service import notify
from app.services.player_stats_service import effective_card_stats
from app.services.wallet_service import credit_coins, lock_user_for_update

MATCHMAKING_TIMEOUT_SECONDS = 60
HISTORY_IN_RESPONSE = 20
ACTIVE_STATUSES = (StrategoMatchStatus.in_progress,)

# Which real positions fit each card role; roles absent here take any card.
ROLE_POSITIONS: dict[str, frozenset[Position]] = {
    "tackler": frozenset({Position.LB, Position.CB, Position.RB, Position.CDM}),
    "speedster": frozenset({Position.LW, Position.RW, Position.LM, Position.RM}),
    "provocateur": frozenset({Position.CM, Position.CAM, Position.CDM, Position.LM, Position.RM}),
}

_FLIP = {MatchResult.win: MatchResult.loss, MatchResult.loss: MatchResult.win, MatchResult.draw: MatchResult.draw}


# ---------------------------------------------------------------------------
# Card snapshots
# ---------------------------------------------------------------------------

def _player_info(player: Player, user_card_id: Optional[int] = None, diamond_bonus: int = 0) -> dict:
    rating, _, _ = effective_card_stats(player, diamond_bonus)
    return {
        "power": rating,
        "rarity_rank": RARITY_ORDER[player.rarity],
        "card": {
            "user_card_id": user_card_id, "player_id": player.id, "display_name": player.display_name,
            "position": player.position.value, "image_path": player.image_path,
            "rarity": player.rarity.value, "rating": rating,
        },
    }


def _card_info(card: UserCard) -> dict:
    return _player_info(card.player, card.id, card.diamond_rating_bonus)


def _sort_key(info: dict) -> tuple:
    return (-info["power"], -info["rarity_rank"], info["card"]["player_id"], info["card"]["user_card_id"] or 0)


def _fits(role: str, info: dict) -> bool:
    allowed = ROLE_POSITIONS.get(role)
    return allowed is None or Position(info["card"]["position"]) in allowed


def _auto_assign(infos: list[dict], slots: list[str], fixed: Optional[dict[str, dict]] = None) -> dict[str, dict]:
    """Fills every card slot not in `fixed` with the strongest still-unused
    card that fits the role (falling back to the strongest unused card when
    nothing fits), then makes sure the star is the strongest card picked."""
    chosen = dict(fixed or {})
    used = {id(i) for i in chosen.values()}
    pool = sorted(infos, key=_sort_key)

    def best(role: str) -> Optional[dict]:
        free = [i for i in pool if id(i) not in used]
        fitting = [i for i in free if _fits(role, i)]
        return (fitting or free or [None])[0]

    # Star first (strongest card), then the scarcest position-bound roles.
    order = ["star", "tackler", "speedster", "provocateur", *[s for s in slots if engine.role_of(s) == "regular"]]
    for slot in order:
        if slot in slots and slot not in chosen:
            pick = best(engine.role_of(slot))
            if pick is None:
                break
            chosen[slot] = pick
            used.add(id(pick))

    if "star" in chosen:
        strongest_slot = min(chosen, key=lambda s: _sort_key(chosen[s]))
        if strongest_slot != "star" and _sort_key(chosen[strongest_slot])[:2] < _sort_key(chosen["star"])[:2]:
            old_star = chosen["star"]
            chosen["star"] = chosen[strongest_slot]
            if _fits(engine.role_of(strongest_slot), old_star):
                chosen[strongest_slot] = old_star
            else:
                del chosen[strongest_slot]
                used = {id(i) for i in chosen.values()}
                pick = best(engine.role_of(strongest_slot))
                if pick is not None:
                    chosen[strongest_slot] = pick
    return chosen


# ---------------------------------------------------------------------------
# Squad & layout (pre-match preparation)
# ---------------------------------------------------------------------------

def _slot_counts(config: GameConfig) -> tuple[int, int, int]:
    return config.stratego_board_size, config.stratego_wall_count, config.stratego_regular_count


async def _usable_cards(db: AsyncSession, user_id: int) -> list[UserCard]:
    result = await db.execute(
        select(UserCard)
        .where(UserCard.owner_id == user_id, UserCard.is_locked_by_admin.is_(False))
        .options(joinedload(UserCard.player))
    )
    return list(result.unique().scalars().all())


def _layout_rng(user_id: int) -> random.Random:
    # Deterministic per user so repeated GETs of a not-yet-saved layout show
    # the same auto placement instead of reshuffling on every refetch.
    return random.Random(f"stratego-layout:{user_id}")


async def _resolve_squad(
    db: AsyncSession, user: User, board_size: int, wall_count: int, regular_count: int,
) -> tuple[dict[str, dict], dict[str, list[int]], list[dict]]:
    slots = engine.all_slots(wall_count, regular_count)
    cslots = engine.card_slots(regular_count)
    infos = [_card_info(c) for c in await _usable_cards(db, user.id)]
    by_card_id = {i["card"]["user_card_id"]: i for i in infos}

    saved = user.stratego_squad or {}
    fixed: dict[str, dict] = {}
    for slot, card_id in (saved.get("cards") or {}).items():
        info = by_card_id.get(card_id)
        if slot in cslots and info is not None and all(info is not v for v in fixed.values()):
            fixed[slot] = info
    cards = _auto_assign(infos, cslots, fixed)
    layout = engine.repair_layout(saved.get("layout"), slots, board_size, _layout_rng(user.id))
    return cards, layout, infos


def _card_out(info: dict) -> StrategoCardOut:
    return StrategoCardOut(**info["card"])


async def get_squad(db: AsyncSession, user: User) -> StrategoSquadOut:
    config = await get_config(db)
    board_size, wall_count, regular_count = _slot_counts(config)
    cards, layout, infos = await _resolve_squad(db, user, board_size, wall_count, regular_count)
    cslots = engine.card_slots(regular_count)
    return StrategoSquadOut(
        board_size=board_size,
        slots=engine.all_slots(wall_count, regular_count),
        card_slots=[
            StrategoSquadSlotOut(
                slot=s, role=engine.role_of(s),
                card=_card_out(cards[s]) if s in cards else None,
                eligible_positions=sorted(p.value for p in ROLE_POSITIONS[engine.role_of(s)])
                if engine.role_of(s) in ROLE_POSITIONS else None,
            )
            for s in cslots
        ],
        layout=layout,
        is_complete=len(cards) == len(cslots),
        cards_needed=len(cslots),
        options=[_card_out(i) for i in sorted(infos, key=_sort_key)],
    )


async def set_squad(db: AsyncSession, user: User, cards: dict[str, int], layout: dict) -> StrategoSquadOut:
    config = await get_config(db)
    board_size, wall_count, regular_count = _slot_counts(config)
    slots = engine.all_slots(wall_count, regular_count)
    cslots = engine.card_slots(regular_count)

    if set(cards) != set(cslots):
        raise ConflictError("Выбери карточку для каждой роли")
    if len(set(cards.values())) != len(cslots):
        raise ConflictError("Одна карточка не может играть две роли")
    infos = [_card_info(c) for c in await _usable_cards(db, user.id)]
    by_card_id = {i["card"]["user_card_id"]: i for i in infos}
    chosen: dict[str, dict] = {}
    for slot, card_id in cards.items():
        info = by_card_id.get(card_id)
        if info is None:
            raise ForbiddenError("Можно использовать только свои карточки")
        chosen[slot] = info
    # A card parked on a regular slot could just as well take the role, so
    # only cards bound to the star or another role count as "taken".
    bound_ids = {cid for slot, cid in cards.items() if engine.role_of(slot) != "regular"}
    for slot, info in chosen.items():
        role = engine.role_of(slot)
        if not _fits(role, info):
            others = [i for i in infos if i["card"]["user_card_id"] not in bound_ids or i is info]
            if any(_fits(role, i) for i in others):
                raise ConflictError(
                    f"Для роли «{ROLE_LABELS[role]}» нужна позиция {', '.join(sorted(p.value for p in ROLE_POSITIONS[role]))}"
                )
    star_key = _sort_key(chosen["star"])[:2]
    if any(_sort_key(i)[:2] < star_key for i in chosen.values()):
        raise ConflictError("Звездой должна быть самая сильная карточка состава")

    try:
        clean_layout = engine.validate_layout(layout, slots, board_size)
    except engine.EngineError as exc:
        raise ConflictError(str(exc))

    user.stratego_squad = {"cards": dict(cards), "layout": clean_layout}
    flag_modified(user, "stratego_squad")
    db.add(user)
    await db.commit()
    return await get_squad(db, user)


ROLE_LABELS = {
    "cup": "Кубок", "wall": "Стенка", "star": "Звезда", "tackler": "Подкатчик",
    "provocateur": "Провокатор", "speedster": "Скорость", "regular": "Игрок",
}


async def get_info(db: AsyncSession, user: User) -> StrategoInfoOut:
    config = await get_config(db)
    reset_day = local_today(user.stratego_attempts_reset_at) if user.stratego_attempts_reset_at else None
    return StrategoInfoOut(
        board_size=config.stratego_board_size, wall_count=config.stratego_wall_count,
        regular_count=config.stratego_regular_count, move_limit=config.stratego_move_limit,
        move_timeout_hours=config.stratego_move_timeout_hours,
        challenge_expiry_hours=config.stratego_challenge_expiry_hours,
        max_auto_moves=config.stratego_max_auto_moves,
        reward_win=config.stratego_reward_win, reward_draw=config.stratego_reward_draw,
        reward_loss=config.stratego_reward_loss, daily_limit=config.stratego_daily_limit,
        rewarded_today=user.stratego_rewarded_attempts_today if reset_day == local_today() else 0,
    )


# ---------------------------------------------------------------------------
# Match state construction
# ---------------------------------------------------------------------------

def _new_state(config: GameConfig) -> dict:
    board_size, wall_count, regular_count = _slot_counts(config)
    slots = engine.all_slots(wall_count, regular_count)
    if len(slots) > 2 * board_size:
        raise ConflictError("Настройки Стратего: фишек больше, чем клеток в двух рядах")
    ids = list(range(1, 2 * len(slots) + 1))
    random.shuffle(ids)
    return {
        "board_size": board_size, "wall_count": wall_count, "regular_count": regular_count,
        "move_limit": config.stratego_move_limit, "max_auto_moves": config.stratego_max_auto_moves,
        "pieces": [], "ids": {"user": ids[: len(slots)], "opponent": ids[len(slots):]},
        "turn": None, "ply": 0, "history": [], "deadline": None,
        "auto_moves": {"user": 0, "opponent": 0},
        "last_activity_at": datetime.now(timezone.utc).isoformat(),
    }


async def _add_human_side(db: AsyncSession, state: dict, side: str, user: User) -> None:
    cards, layout, _ = await _resolve_squad(db, user, state["board_size"], state["wall_count"], state["regular_count"])
    slots = engine.all_slots(state["wall_count"], state["regular_count"])
    if len(cards) < len(engine.card_slots(state["regular_count"])):
        raise ConflictError(
            f"Для Стратего нужно минимум {len(engine.card_slots(state['regular_count']))} карточек в коллекции"
        )
    state["pieces"].extend(engine.build_pieces(side, slots, cards, layout, state["board_size"], state["ids"][side]))


async def _bot_cards(db: AsyncSession, target_power: int, count: int) -> list[dict]:
    band = 8
    result = await db.execute(
        select(Player)
        .where(Player.is_active.is_(True), Player.rating.between(target_power - band, target_power + band))
        .order_by(func.random()).limit(count * 3)
    )
    players = list(result.scalars().all())
    if len(players) < count:
        result = await db.execute(select(Player).where(Player.is_active.is_(True)).order_by(func.random()).limit(count * 3))
        players = list(result.scalars().all())
    if len(players) < count:
        raise ConflictError("Not enough players available to generate a bot squad")
    return [_player_info(p) for p in players]


def _add_bot_side(state: dict, infos: list[dict], rng: random.Random) -> None:
    slots = engine.all_slots(state["wall_count"], state["regular_count"])
    cards = _auto_assign(infos, engine.card_slots(state["regular_count"]))
    layout = engine.auto_layout(slots, state["board_size"], rng)
    state["pieces"].extend(
        engine.build_pieces("opponent", slots, cards, layout, state["board_size"], state["ids"]["opponent"])
    )


def _start_play(state: dict, config: GameConfig, is_bot: bool) -> None:
    state["turn"] = random.choice(engine.SIDES)
    state.pop("ids", None)
    if not is_bot:
        state["deadline"] = (datetime.now(timezone.utc) + timedelta(hours=config.stratego_move_timeout_hours)).isoformat()


def _bot_rng(match_id: int, ply: int) -> random.Random:
    return random.Random(f"stratego-bot:{match_id}:{ply}")


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

def _ensure_hourly_reset(user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.stratego_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.stratego_hourly_attempts = 0
        user.stratego_hour_started_at = now


def _ensure_daily_reset(user: User) -> None:
    reset_day = local_today(user.stratego_attempts_reset_at) if user.stratego_attempts_reset_at else None
    if reset_day != local_today():
        user.stratego_rewarded_attempts_today = 0
        user.stratego_attempts_reset_at = datetime.now(timezone.utc)


def _hourly_limit_error(user: User, config: GameConfig) -> ConflictError:
    remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(user.stratego_hour_started_at))
    return ConflictError(
        "Hourly play limit reached for this game",
        details={"hourly_limit": config.hourly_game_limit, "retry_after_seconds": max(0, int(remaining.total_seconds()))},
    )


async def _consume_hourly_slot(db: AsyncSession, user_id: int, config: GameConfig) -> User:
    """Locks the user row, then re-checks "one active match" under that lock
    so two concurrent create/accept requests can't both start a match."""
    locked = await lock_user_for_update(db, user_id)
    if await _has_active_match(db, user_id):
        raise ConflictError(_ACTIVE_MATCH_MSG)
    _ensure_hourly_reset(locked)
    if locked.stratego_hourly_attempts >= config.hourly_game_limit:
        raise _hourly_limit_error(locked, config)
    locked.stratego_hourly_attempts += 1
    db.add(locked)
    return locked


async def _has_active_match(db: AsyncSession, user_id: int, exclude_match_id: Optional[int] = None) -> bool:
    conditions = [
        or_(StrategoMatch.user_id == user_id, StrategoMatch.opponent_user_id == user_id),
        StrategoMatch.status.in_(ACTIVE_STATUSES),
    ]
    if exclude_match_id is not None:
        conditions.append(StrategoMatch.id != exclude_match_id)
    result = await db.execute(select(StrategoMatch.id).where(*conditions).limit(1))
    return result.scalar_one_or_none() is not None


_ACTIVE_MATCH_MSG = "У тебя уже идёт матч в Стратего — доиграй его или сдайся"


# ---------------------------------------------------------------------------
# Match creation / lifecycle
# ---------------------------------------------------------------------------

async def _random_bot_name(db: AsyncSession, exclude_user_id: int) -> str:
    result = await db.execute(
        select(User)
        .where(User.is_banned.is_(False), User.is_admin.is_(False), User.id != exclude_user_id)
        .order_by(func.random()).limit(1)
    )
    candidate = result.scalar_one_or_none()
    return candidate.full_display_name() if candidate else random.choice(BOT_NAMES)


async def create_bot_match(db: AsyncSession, user: User) -> StrategoMatchOut:
    config = await get_config(db)
    if await _has_active_match(db, user.id):
        raise ConflictError(_ACTIVE_MATCH_MSG)
    state = _new_state(config)
    await _add_human_side(db, state, "user", user)
    locked = await _consume_hourly_slot(db, user.id, config)

    user_pieces = [p for p in state["pieces"] if p["role"] not in engine.IMMOBILE_ROLES]
    target = round(sum(p["power"] for p in user_pieces) / len(user_pieces))
    infos = await _bot_cards(db, target, len(engine.card_slots(state["regular_count"])))
    _add_bot_side(state, infos, random.Random())
    _start_play(state, config, is_bot=True)

    match = StrategoMatch(
        user_id=locked.id, opponent_user_id=None, opponent_name=await _random_bot_name(db, user.id),
        opponent_type=StrategoOpponentType.bot, status=StrategoMatchStatus.in_progress, server_state=state,
    )
    db.add(match)
    await db.flush()
    if state["turn"] == "opponent":
        outcome = _play_bot_turn(match, state)
        if outcome:  # practically impossible on move one, handled for completeness
            await _finish_match(db, match, state, config, outcome["winner"], outcome["reason"])
            await db.refresh(match)
            return await _hydrate_match(db, match, locked)
    match.server_state = state
    flag_modified(match, "server_state")
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, locked)


async def create_challenge(db: AsyncSession, sender: User, receiver_id: int) -> StrategoMatchOut:
    config = await get_config(db)
    if await _has_active_match(db, sender.id):
        raise ConflictError(_ACTIVE_MATCH_MSG)
    receiver = await db.get(User, receiver_id)
    if not receiver:
        raise NotFoundError("User not found")
    if receiver.id == sender.id:
        raise ConflictError("You cannot challenge yourself")
    if receiver.is_banned:
        raise ConflictError("This user is banned and cannot be challenged")

    state = _new_state(config)
    await _add_human_side(db, state, "user", sender)
    sender = await _consume_hourly_slot(db, sender.id, config)
    match = StrategoMatch(
        user_id=sender.id, opponent_user_id=receiver.id, opponent_name=receiver.full_display_name(),
        opponent_type=StrategoOpponentType.friend, status=StrategoMatchStatus.pending_accept,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=config.stratego_challenge_expiry_hours),
        server_state=state,
    )
    db.add(match)
    await db.flush()
    await notify(
        db, receiver.id, NotificationType.stratego_challenge_received,
        "Вызов в Стратего", f"{sender.full_display_name()} вызывает тебя на «Футбольное Стратего».",
        "stratego_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, sender)


async def _get_match_or_404(db: AsyncSession, match_id: int) -> StrategoMatch:
    match = await db.get(StrategoMatch, match_id)
    if not match:
        raise NotFoundError("Match not found")
    return match


async def _lock_match(db: AsyncSession, match_id: int) -> StrategoMatch:
    result = await db.execute(
        select(StrategoMatch).where(StrategoMatch.id == match_id).with_for_update().execution_options(populate_existing=True)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise NotFoundError("Match not found")
    return match


async def accept_challenge(db: AsyncSession, user: User, match_id: int) -> StrategoMatchOut:
    match = await _lock_match(db, match_id)
    if match.opponent_user_id != user.id:
        raise ForbiddenError("Only the challenged user can accept this challenge")
    if match.status != StrategoMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")
    if ensure_aware(match.expires_at) <= datetime.now(timezone.utc):
        match.status = StrategoMatchStatus.expired
        match.resolved_at = datetime.now(timezone.utc)
        db.add(match)
        await db.commit()
        raise ConflictError("This challenge has expired")
    config = await get_config(db)
    if await _has_active_match(db, user.id, exclude_match_id=match.id):
        raise ConflictError(_ACTIVE_MATCH_MSG)
    if await _has_active_match(db, match.user_id, exclude_match_id=match.id):
        raise ConflictError("Соперник сейчас играет другой матч в Стратего — попробуй позже")

    state = dict(match.server_state)
    state["pieces"] = list(state["pieces"])
    await _add_human_side(db, state, "opponent", user)
    locked = await _consume_hourly_slot(db, user.id, config)
    _start_play(state, config, is_bot=False)
    match.server_state = state
    flag_modified(match, "server_state")
    match.status = StrategoMatchStatus.in_progress
    db.add(match)
    await notify(
        db, match.user_id, NotificationType.stratego_challenge_accepted,
        "Вызов принят", f"{locked.full_display_name()} принял(а) твой вызов в Стратего.",
        "stratego_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, locked)


async def decline_challenge(db: AsyncSession, user: User, match_id: int) -> StrategoMatchOut:
    match = await _lock_match(db, match_id)
    if match.opponent_user_id != user.id:
        raise ForbiddenError("Only the challenged user can decline this challenge")
    if match.status != StrategoMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")
    match.status = StrategoMatchStatus.declined
    match.resolved_at = datetime.now(timezone.utc)
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def cancel_challenge(db: AsyncSession, user: User, match_id: int) -> StrategoMatchOut:
    match = await _lock_match(db, match_id)
    if match.user_id != user.id:
        raise ForbiddenError("Only the challenger can cancel this challenge")
    if match.status != StrategoMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")
    match.status = StrategoMatchStatus.cancelled
    match.resolved_at = datetime.now(timezone.utc)
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


# ---------------------------------------------------------------------------
# Moves
# ---------------------------------------------------------------------------

def _play_bot_turn(match: StrategoMatch, state: dict) -> Optional[dict]:
    move = engine.bot_choose_move(state, "opponent", _bot_rng(match.id, state["ply"]))
    if move is None:  # the bot side has no legal move left: it loses
        return {"winner": "user", "reason": "no_moves"}
    _, fr, fc, tr, tc = move
    return engine.apply_move(state, "opponent", fr, fc, tr, tc)


async def submit_move(
    db: AsyncSession, user: User, match_id: int, from_row: int, from_col: int, to_row: int, to_col: int,
) -> StrategoMatchOut:
    match = await _lock_match(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    if match.status != StrategoMatchStatus.in_progress:
        raise ConflictError("This match is not in progress")
    config = await get_config(db)
    side = "user" if user.id == match.user_id else "opponent"
    state = dict(match.server_state)
    n = state["board_size"]
    for v in (from_row, from_col, to_row, to_col):
        if not 0 <= v < n:
            raise ConflictError("Клетка за пределами поля")
    fr, fc = engine.from_viewer(side, from_row, from_col, n)
    tr, tc = engine.from_viewer(side, to_row, to_col, n)

    try:
        outcome = engine.apply_move(state, side, fr, fc, tr, tc)
    except engine.EngineError as exc:
        raise ConflictError(str(exc))
    state["auto_moves"] = {**state.get("auto_moves", {}), side: 0}
    now = datetime.now(timezone.utc)
    state["last_activity_at"] = now.isoformat()

    if outcome is None and match.opponent_type == StrategoOpponentType.bot:
        outcome = _play_bot_turn(match, state)
    if outcome is None and match.opponent_type != StrategoOpponentType.bot:
        state["deadline"] = (now + timedelta(hours=config.stratego_move_timeout_hours)).isoformat()

    match.server_state = state
    flag_modified(match, "server_state")
    if outcome is not None:
        await _finish_match(db, match, state, config, outcome["winner"], outcome["reason"])
    else:
        db.add(match)
        await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def forfeit_match(db: AsyncSession, user: User, match_id: int) -> StrategoMatchOut:
    match = await _lock_match(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    if match.status != StrategoMatchStatus.in_progress:
        raise ConflictError("This match is not in progress")
    config = await get_config(db)
    side = "user" if user.id == match.user_id else "opponent"
    await _finish_match(db, match, dict(match.server_state), config, engine.other_side(side), "forfeit", loser_quit=True)
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


def _reward_for(result: MatchResult, config: GameConfig) -> int:
    return {
        MatchResult.win: config.stratego_reward_win,
        MatchResult.draw: config.stratego_reward_draw,
        MatchResult.loss: config.stratego_reward_loss,
    }[result]


async def _grant_reward(db: AsyncSession, user: User, result: MatchResult, config: GameConfig, match_id: int) -> int:
    _ensure_daily_reset(user)
    if user.game_rewards_blocked or user.stratego_rewarded_attempts_today >= config.stratego_daily_limit:
        db.add(user)
        return 0
    reward = _reward_for(result, config)
    user.stratego_rewarded_attempts_today += 1
    if reward > 0:
        await credit_coins(
            db, user, reward, TransactionType.stratego_reward,
            f"Награда за матч в Стратего ({result.value})", "stratego_match", match_id,
        )
    db.add(user)
    return reward


async def _finish_match(
    db: AsyncSession, match: StrategoMatch, state: dict, config: GameConfig,
    winner: str, reason: str, loser_quit: bool = False,
) -> None:
    """`winner` is "user" | "opponent" | "draw" (canonical sides).
    `loser_quit` (forfeit / timed out) withholds the loser's consolation
    reward, so leaving is never better than playing a lost match out."""
    result = MatchResult.draw if winner == "draw" else MatchResult.win if winner == "user" else MatchResult.loss
    match.result = result
    match.win_reason = reason
    match.status = StrategoMatchStatus.finished
    match.resolved_at = datetime.now(timezone.utc)
    state["deadline"] = None
    state["turn"] = None
    state["final_strength"] = {s: engine.strength(state, s) for s in engine.SIDES}

    human_ids = [match.user_id] + ([match.opponent_user_id] if match.opponent_user_id else [])
    locked: dict[int, User] = {}
    for uid in sorted(human_ids):
        locked[uid] = await lock_user_for_update(db, uid)

    side_result = {"user": result, "opponent": _FLIP[result]}
    side_uid = {"user": match.user_id, "opponent": match.opponent_user_id}
    for side in engine.SIDES:
        uid = side_uid[side]
        if uid is None or (side == "opponent" and match.opponent_type == StrategoOpponentType.bot):
            continue
        if loser_quit and side != winner:
            reward = 0
        else:
            reward = await _grant_reward(db, locked[uid], side_result[side], config, match.id)
        if side == "user":
            match.user_reward_coins = reward
        else:
            match.opponent_reward_coins = reward

    if match.opponent_type != StrategoOpponentType.bot and match.opponent_user_id:
        labels = {MatchResult.win: "победа", MatchResult.draw: "ничья", MatchResult.loss: "поражение"}
        for side in engine.SIDES:
            await notify(
                db, side_uid[side], NotificationType.stratego_match_finished,
                "Матч в Стратего завершён", f"Итог: {labels[side_result[side]]}.",
                "stratego_match", match.id,
            )

    match.server_state = state
    flag_modified(match, "server_state")
    db.add(match)
    await db.commit()


# ---------------------------------------------------------------------------
# Lazy sweep (no scheduler — runs on reads, like tactico_service)
# ---------------------------------------------------------------------------

async def _sweep(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(StrategoMatch).where(
            StrategoMatch.status.in_((StrategoMatchStatus.in_progress, StrategoMatchStatus.pending_accept))
        )
    )
    matches = result.scalars().all()
    if not matches:
        return 0
    config = await get_config(db)
    swept = 0
    for match in matches:
        if match.status == StrategoMatchStatus.pending_accept:
            if match.expires_at and ensure_aware(match.expires_at) <= now:
                match.status = StrategoMatchStatus.expired
                match.resolved_at = now
                db.add(match)
                await db.commit()
                swept += 1
            continue

        state = dict(match.server_state or {})
        timeout = timedelta(hours=config.stratego_move_timeout_hours)
        if match.opponent_type == StrategoOpponentType.bot:
            last = state.get("last_activity_at")
            if last and ensure_aware(datetime.fromisoformat(last)) + timeout <= now:
                await _finish_match(db, match, state, config, "opponent", "timeout", loser_quit=True)
                swept += 1
            continue

        deadline = state.get("deadline")
        if not deadline or ensure_aware(datetime.fromisoformat(deadline)) > now:
            continue
        side = state["turn"]
        auto = dict(state.get("auto_moves") or {})
        if auto.get(side, 0) >= state.get("max_auto_moves", config.stratego_max_auto_moves):
            await _finish_match(db, match, state, config, engine.other_side(side), "timeout", loser_quit=True)
            swept += 1
            continue
        move = engine.bot_choose_move(state, side, _bot_rng(match.id, state["ply"]))
        if move is None:
            outcome = {"winner": engine.other_side(side), "reason": "no_moves"}
        else:
            _, fr, fc, tr, tc = move
            outcome = engine.apply_move(state, side, fr, fc, tr, tc, auto=True)
        auto[side] = auto.get(side, 0) + 1
        state["auto_moves"] = auto
        state["deadline"] = (now + timeout).isoformat()
        match.server_state = state
        flag_modified(match, "server_state")
        if outcome is not None:
            await _finish_match(db, match, state, config, outcome["winner"], outcome["reason"])
        else:
            db.add(match)
            await notify(
                db, side_uid_for(match, engine.other_side(side)), NotificationType.stratego_your_turn,
                "Твой ход в Стратего", "Соперник не успел — за него сходил автопилот. Теперь ходишь ты.",
                "stratego_match", match.id,
            )
            await db.commit()
        swept += 1
    return swept


def side_uid_for(match: StrategoMatch, side: str) -> Optional[int]:
    return match.user_id if side == "user" else match.opponent_user_id


# ---------------------------------------------------------------------------
# Reads — the only path a match leaves the server
# ---------------------------------------------------------------------------

def _combat_piece(p: dict, viewer: str) -> StrategoCombatPieceOut:
    return StrategoCombatPieceOut(
        id=p["id"], mine=p["side"] == viewer, role=p["role"], power=p["power"],
        card=StrategoCardOut(**p["card"]) if p.get("card") else None,
    )


def _piece_out(p: dict, viewer: str, n: int, reveal_all: bool) -> StrategoPieceOut:
    row, col = engine.to_viewer(viewer, p["row"], p["col"], n)
    mine = p["side"] == viewer
    if mine or p["revealed"] or reveal_all:
        return StrategoPieceOut(
            id=p["id"], mine=mine, row=row, col=col, hidden=False, revealed=p["revealed"], moved=p["moved"],
            role=p["role"], power=p["power"], card=StrategoCardOut(**p["card"]) if p.get("card") else None,
        )
    return StrategoPieceOut(id=p["id"], mine=False, row=row, col=col, hidden=True, revealed=False, moved=p["moved"])


async def _hydrate_match(db: AsyncSession, match: StrategoMatch, viewer_user: User) -> StrategoMatchOut:
    state = match.server_state or {}
    viewer = "user" if viewer_user.id == match.user_id else "opponent"
    n = state.get("board_size", 6)
    finished = match.status == StrategoMatchStatus.finished

    if viewer == "user":
        opponent_name, opponent_user_id = match.opponent_name, match.opponent_user_id
    else:
        creator = await db.get(User, match.user_id)
        opponent_name = creator.full_display_name() if creator else match.opponent_name
        opponent_user_id = match.user_id

    # While a challenge is pending the acceptor's pieces don't exist yet, and
    # the creator's must not be shown to the invitee.
    visible = [p for p in state.get("pieces", []) if p["alive"] and (match.status != StrategoMatchStatus.pending_accept or p["side"] == viewer)]
    pieces = [_piece_out(p, viewer, n, reveal_all=finished) for p in visible]
    dead = [p for p in state.get("pieces", []) if not p["alive"]]

    history = []
    for h in state.get("history", [])[-HISTORY_IN_RESPONSE:]:
        combat = h.get("combat")
        history.append(StrategoMoveOut(
            ply=h["ply"], mine=h["side"] == viewer, piece_id=h["piece_id"],
            from_cell=list(engine.to_viewer(viewer, *h["from"], n)), to_cell=list(engine.to_viewer(viewer, *h["to"], n)),
            auto=h.get("auto", False),
            combat=StrategoCombatOut(
                attacker=_combat_piece(combat["attacker"], viewer), defender=_combat_piece(combat["defender"], viewer),
                survivor=combat["survivor"],
            ) if combat else None,
        ))

    in_play = match.status == StrategoMatchStatus.in_progress
    deadline = None
    if in_play and match.opponent_type != StrategoOpponentType.bot and state.get("deadline"):
        deadline = ensure_aware(datetime.fromisoformat(state["deadline"]))
    final = state.get("final_strength") or {}
    result = match.result if viewer == "user" or match.result is None else _FLIP[match.result]

    return StrategoMatchOut(
        id=match.id, opponent_type=match.opponent_type, opponent_name=opponent_name,
        opponent_user_id=opponent_user_id, status=match.status, viewer_side=viewer,
        board_size=n, move_limit=state.get("move_limit", 0), ply=state.get("ply", 0),
        my_turn=in_play and state.get("turn") == viewer, deadline=deadline,
        my_auto_moves=(state.get("auto_moves") or {}).get(viewer, 0), max_auto_moves=state.get("max_auto_moves", 0),
        pieces=pieces,
        lost_mine=[_combat_piece(p, viewer) for p in dead if p["side"] == viewer],
        lost_opponent=[_combat_piece(p, viewer) for p in dead if p["side"] != viewer],
        history=history, result=result, win_reason=match.win_reason,
        reward_coins=match.user_reward_coins if viewer == "user" else match.opponent_reward_coins,
        my_strength=final.get(viewer) if finished else None,
        opponent_strength=final.get(engine.other_side(viewer)) if finished else None,
        created_at=match.created_at, expires_at=match.expires_at, resolved_at=match.resolved_at,
    )


async def list_matches(db: AsyncSession, user: User) -> list[StrategoMatchOut]:
    await _sweep(db)
    result = await db.execute(
        select(StrategoMatch)
        .where(or_(StrategoMatch.user_id == user.id, StrategoMatch.opponent_user_id == user.id))
        .order_by(StrategoMatch.created_at.desc()).limit(30)
    )
    return [await _hydrate_match(db, m, user) for m in result.scalars().all()]


async def get_match(db: AsyncSession, user: User, match_id: int) -> StrategoMatchOut:
    await _sweep(db)
    match = await _get_match_or_404(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    return await _hydrate_match(db, match, user)


# ---------------------------------------------------------------------------
# Matchmaking (same lazy pairing design as tactico_service)
# ---------------------------------------------------------------------------

async def start_search(db: AsyncSession, user: User) -> StrategoQueueEntry:
    if await _has_active_match(db, user.id):
        raise ConflictError(_ACTIVE_MATCH_MSG)
    result = await db.execute(
        select(StrategoQueueEntry).where(StrategoQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        reclaimable = (
            existing.matched_match_id is not None
            or datetime.now(timezone.utc) - ensure_aware(existing.created_at) > timedelta(seconds=MATCHMAKING_TIMEOUT_SECONDS)
        )
        if not reclaimable:
            raise ConflictError("Ты уже ищешь соперника")
        await db.delete(existing)
        await db.flush()

    config = await get_config(db)
    squad = await get_squad(db, user)
    if not squad.is_complete:
        raise ConflictError(f"Для Стратего нужно минимум {squad.cards_needed} карточек в коллекции")
    locked = await lock_user_for_update(db, user.id)
    _ensure_hourly_reset(locked)
    if locked.stratego_hourly_attempts >= config.hourly_game_limit:
        raise _hourly_limit_error(locked, config)
    db.add(locked)

    entry = StrategoQueueEntry(user_id=user.id)
    db.add(entry)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Ты уже ищешь соперника")
    await db.refresh(entry)
    return entry


async def get_search_status(db: AsyncSession, user: User) -> tuple[str, Optional[int]]:
    result = await db.execute(
        select(StrategoQueueEntry).where(StrategoQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    my_entry = result.scalar_one_or_none()
    if my_entry is None:
        return "not_searching", None
    if my_entry.matched_match_id is not None:
        match_id = my_entry.matched_match_id
        await db.delete(my_entry)
        await db.commit()
        return "matched", match_id
    if datetime.now(timezone.utc) - ensure_aware(my_entry.created_at) > timedelta(seconds=MATCHMAKING_TIMEOUT_SECONDS):
        await db.delete(my_entry)
        await db.commit()
        try:
            bot_match = await create_bot_match(db, user)
        except ConflictError:
            return "timeout", None
        return "matched", bot_match.id

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=MATCHMAKING_TIMEOUT_SECONDS)
    candidate_result = await db.execute(
        select(StrategoQueueEntry)
        .where(
            StrategoQueueEntry.user_id != user.id,
            StrategoQueueEntry.matched_match_id.is_(None),
            StrategoQueueEntry.created_at > cutoff,
        )
        .order_by(StrategoQueueEntry.created_at).limit(1)
        .with_for_update(skip_locked=True)
    )
    candidate = candidate_result.scalar_one_or_none()
    if candidate is None:
        await db.commit()
        return "searching", None

    config = await get_config(db)
    first_id, second_id = sorted([user.id, candidate.user_id])
    first = await lock_user_for_update(db, first_id)
    second = await lock_user_for_update(db, second_id)
    me = first if first.id == user.id else second
    them = first if first.id == candidate.user_id else second
    _ensure_hourly_reset(me)
    _ensure_hourly_reset(them)

    state = _new_state(config)
    stale: list[StrategoQueueEntry] = []
    for entry, u, side in ((my_entry, me, "user"), (candidate, them, "opponent")):
        try:
            if await _has_active_match(db, u.id) or u.stratego_hourly_attempts >= config.hourly_game_limit:
                raise ConflictError("stale")
            await _add_human_side(db, state, side, u)
        except ConflictError:
            stale.append(entry)
    if stale:
        for entry in stale:
            await db.delete(entry)
        await db.commit()
        return ("not_searching" if my_entry in stale else "searching"), None

    me.stratego_hourly_attempts += 1
    them.stratego_hourly_attempts += 1
    db.add(me)
    db.add(them)
    _start_play(state, config, is_bot=False)
    match = StrategoMatch(
        user_id=me.id, opponent_user_id=them.id, opponent_name=them.full_display_name(),
        opponent_type=StrategoOpponentType.online, status=StrategoMatchStatus.in_progress, server_state=state,
    )
    db.add(match)
    await db.flush()
    candidate.matched_match_id = match.id
    db.add(candidate)
    await db.delete(my_entry)
    await notify(
        db, them.id, NotificationType.stratego_your_turn,
        "Соперник найден!", "Начался матч в «Футбольном Стратего».", "stratego_match", match.id,
    )
    await db.commit()
    return "matched", match.id


async def cancel_search(db: AsyncSession, user: User) -> None:
    result = await db.execute(
        select(StrategoQueueEntry).where(StrategoQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Ты не ищешь соперника")
    if entry.matched_match_id is not None:
        raise ConflictError("Соперник уже найден — матч начинается")
    await db.delete(entry)
    await db.commit()
