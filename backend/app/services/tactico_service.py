import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card import UserCard
from app.models.enums import (
    MatchDifficulty,
    MatchResult,
    NotificationType,
    Rarity,
    TacticoMatchStatus,
    TacticoOpponentType,
    TransactionType,
)
from app.models.game_config import GameConfig
from app.models.player import Player
from app.models.tactico import TacticoMatch, TacticoSquad, TacticoSquadCard
from app.models.user import User
from app.schemas.ranking import RankingMetric
from app.schemas.tactico import TacticoCardOut, TacticoMatchOut, TacticoRoundOut, TacticoSquadOut, TacticoStatsOut
from app.services import ranking_service
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS
from app.services.match_service import BOT_NAMES
from app.services.notification_service import notify
from app.services.wallet_service import credit_coins, lock_user_for_update

SQUAD_SIZE = 11

_ATTACK_BONUS_POSITIONS = CATEGORY_POSITIONS["FWD"]
_DEFENSE_BONUS_POSITIONS = CATEGORY_POSITIONS["GK"] | CATEGORY_POSITIONS["DEF"]

_FLIP_RESULT = {MatchResult.win: MatchResult.loss, MatchResult.loss: MatchResult.win, MatchResult.draw: MatchResult.draw}
_OPPONENT_RATING_DELTA = {3: -1, -1: 3, 1: 1}


# ---------------------------------------------------------------------------
# Squad
# ---------------------------------------------------------------------------

async def _get_or_create_squad(db: AsyncSession, user_id: int) -> TacticoSquad:
    result = await db.execute(select(TacticoSquad).where(TacticoSquad.user_id == user_id))
    squad = result.scalar_one_or_none()
    if squad is None:
        squad = TacticoSquad(user_id=user_id)
        db.add(squad)
        await db.flush()
    return squad


async def get_squad(db: AsyncSession, user: User) -> TacticoSquadOut:
    config = await get_config(db)
    squad = await _get_or_create_squad(db, user.id)
    result = await db.execute(select(TacticoSquadCard).where(TacticoSquadCard.squad_id == squad.id))
    squad_cards = result.scalars().all()
    card_ids = [sc.user_card_id for sc in squad_cards]
    cards: list[UserCard] = []
    if card_ids:
        cards_result = await db.execute(
            select(UserCard).where(UserCard.id.in_(card_ids)).options(joinedload(UserCard.player))
        )
        cards = list(cards_result.unique().scalars().all())
    return TacticoSquadOut(
        is_complete=len(cards) == SQUAD_SIZE, cards=cards,
        max_legendary=config.tactico_max_legendary_cards, max_epic=config.tactico_max_epic_cards,
    )


async def set_squad(db: AsyncSession, user: User, user_card_ids: list[int]) -> TacticoSquadOut:
    config = await get_config(db)
    unique_ids = list(dict.fromkeys(user_card_ids))
    if len(unique_ids) != SQUAD_SIZE:
        raise ConflictError(f"A Tactico squad must have exactly {SQUAD_SIZE} distinct cards")

    cards_result = await db.execute(
        select(UserCard).where(UserCard.id.in_(unique_ids)).options(joinedload(UserCard.player))
    )
    cards_by_id = {c.id: c for c in cards_result.unique().scalars().all()}
    if len(cards_by_id) != len(unique_ids):
        raise NotFoundError("One or more cards not found")
    for card in cards_by_id.values():
        if card.owner_id != user.id:
            raise ForbiddenError("You can only use your own cards in your Tactico squad")
        if card.is_locked_by_admin:
            raise ConflictError(f"Card #{card.serial_number} is locked and cannot be used")

    legendary_count = sum(1 for c in cards_by_id.values() if c.player.rarity == Rarity.legendary)
    epic_count = sum(1 for c in cards_by_id.values() if c.player.rarity == Rarity.epic)
    if legendary_count > config.tactico_max_legendary_cards:
        raise ConflictError(f"Максимум {config.tactico_max_legendary_cards} легендарных карт в составе Тактико")
    if epic_count > config.tactico_max_epic_cards:
        raise ConflictError(f"Максимум {config.tactico_max_epic_cards} эпических карт в составе Тактико")

    squad = await _get_or_create_squad(db, user.id)
    old_result = await db.execute(select(TacticoSquadCard).where(TacticoSquadCard.squad_id == squad.id))
    for sc in old_result.scalars().all():
        await db.delete(sc)
    await db.flush()
    for card_id in unique_ids:
        db.add(TacticoSquadCard(squad_id=squad.id, user_card_id=card_id))

    await db.commit()
    return await get_squad(db, user)


# ---------------------------------------------------------------------------
# Stat / phase helpers
# ---------------------------------------------------------------------------

def _pick_phase() -> str:
    return random.choice(["attack", "defense"])


def _effective_stat(position: str, attack_rating: int, defense_rating: int, phase: str, bonus_pct: float) -> float:
    base = attack_rating if phase == "attack" else defense_rating
    bonus_positions = _ATTACK_BONUS_POSITIONS if phase == "attack" else _DEFENSE_BONUS_POSITIONS
    if position in {p.value for p in bonus_positions}:
        return base * (1 + bonus_pct)
    return float(base)


def _resolve_round_winner(user_snap: dict, opponent_snap: dict, phase: str, bonus_pct: float) -> str:
    user_val = _effective_stat(
        user_snap["position"], user_snap["attack_rating"], user_snap["defense_rating"], phase, bonus_pct
    )
    opp_val = _effective_stat(
        opponent_snap["position"], opponent_snap["attack_rating"], opponent_snap["defense_rating"], phase, bonus_pct
    )
    if user_val > opp_val:
        return "user"
    if opp_val > user_val:
        return "opponent"
    return "draw"


def _card_snapshot(player: Player, user_card_id: Optional[int] = None) -> dict:
    return {
        "user_card_id": user_card_id,
        "player_id": player.id,
        "display_name": player.display_name,
        "position": player.position.value,
        "image_path": player.image_path,
        "rarity": player.rarity.value,
        "rating": player.rating,
        "attack_rating": player.attack_rating if player.attack_rating is not None else player.rating,
        "defense_rating": player.defense_rating if player.defense_rating is not None else player.rating,
    }


async def _synthesize_bot_squad(db: AsyncSession, avg_user_rating: int, difficulty: MatchDifficulty, config: GameConfig) -> list[dict]:
    multiplier = {
        MatchDifficulty.easy: float(config.difficulty_easy_multiplier),
        MatchDifficulty.medium: float(config.difficulty_medium_multiplier),
        MatchDifficulty.hard: float(config.difficulty_hard_multiplier),
    }[difficulty]
    target_rating = max(1, min(99, round(avg_user_rating * multiplier)))
    band = 8
    result = await db.execute(
        select(Player)
        .where(Player.is_active.is_(True), Player.rating.between(target_rating - band, target_rating + band))
        .order_by(func.random())
        .limit(SQUAD_SIZE)
    )
    players = list(result.scalars().all())
    if len(players) < SQUAD_SIZE:
        # Not enough players in the rating band (small seed data) — widen to any active player.
        result = await db.execute(
            select(Player).where(Player.is_active.is_(True)).order_by(func.random()).limit(SQUAD_SIZE)
        )
        players = list(result.scalars().all())
    if len(players) < SQUAD_SIZE:
        raise ConflictError("Not enough players available to generate a bot squad")
    return [_card_snapshot(p) for p in players]


def _bot_pick(pool: list[dict], phase: str, difficulty: MatchDifficulty, config: GameConfig, bonus_pct: float) -> dict:
    chance = {
        MatchDifficulty.easy: float(config.tactico_bot_optimal_pick_chance_easy),
        MatchDifficulty.medium: float(config.tactico_bot_optimal_pick_chance_medium),
        MatchDifficulty.hard: float(config.tactico_bot_optimal_pick_chance_hard),
    }[difficulty]
    if random.random() < chance:
        return max(
            pool,
            key=lambda c: _effective_stat(c["position"], c["attack_rating"], c["defense_rating"], phase, bonus_pct),
        )
    return random.choice(pool)


# ---------------------------------------------------------------------------
# Round bookkeeping (operates on the plain server_state dict)
# ---------------------------------------------------------------------------

def _record_pick(state: dict, side: str, card: UserCard) -> None:
    pool = state[f"{side}_pool"]
    if card.id not in pool:
        raise ConflictError("That card is not available for this round")
    if state.get(f"{side}_pending_card_id") is not None:
        raise ConflictError("You already submitted a card for this round")
    pool.remove(card.id)
    state[f"{side}_pending_card_id"] = card.id
    state[f"{side}_pending_snapshot"] = _card_snapshot(card.player, user_card_id=card.id)


def _bot_submit(state: dict, difficulty: MatchDifficulty, config: GameConfig, bonus_pct: float) -> None:
    pool = state["opponent_pool"]
    choice = _bot_pick(pool, state["current_phase"], difficulty, config, bonus_pct)
    pool.remove(choice)
    state["opponent_pending_card_id"] = None
    state["opponent_pending_snapshot"] = choice


def _finalize_current_round(state: dict, bonus_pct: float) -> None:
    user_snap = state["user_pending_snapshot"]
    opponent_snap = state["opponent_pending_snapshot"]
    phase = state["current_phase"]
    winner = _resolve_round_winner(user_snap, opponent_snap, phase, bonus_pct)
    state["rounds"].append(
        {"index": state["current_index"], "phase": phase, "user_card": user_snap, "opponent_card": opponent_snap, "winner": winner}
    )
    state["user_pending_card_id"] = None
    state["user_pending_snapshot"] = None
    state["opponent_pending_card_id"] = None
    state["opponent_pending_snapshot"] = None
    state["current_index"] += 1
    state["current_phase"] = _pick_phase() if state["current_index"] < SQUAD_SIZE else None


def _tally(state: dict) -> tuple[int, int]:
    user_wins = sum(1 for r in state["rounds"] if r["winner"] == "user")
    opponent_wins = sum(1 for r in state["rounds"] if r["winner"] == "opponent")
    return user_wins, opponent_wins


def _relabel_round(r: dict, side: str) -> dict:
    if side == "user":
        return r
    flip = {"user": "opponent", "opponent": "user", "draw": "draw", None: None}
    return {**r, "user_card": r["opponent_card"], "opponent_card": r["user_card"], "winner": flip[r["winner"]]}


# ---------------------------------------------------------------------------
# Match creation / lifecycle
# ---------------------------------------------------------------------------

async def _has_active_match(db: AsyncSession, user_id: int, exclude_match_id: Optional[int] = None) -> bool:
    conditions = [
        or_(TacticoMatch.user_id == user_id, TacticoMatch.opponent_user_id == user_id),
        TacticoMatch.status == TacticoMatchStatus.in_progress,
    ]
    if exclude_match_id is not None:
        conditions.append(TacticoMatch.id != exclude_match_id)
    result = await db.execute(select(TacticoMatch.id).where(*conditions).limit(1))
    return result.scalar_one_or_none() is not None


async def _ensure_hourly_reset(user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.tactico_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.tactico_hourly_attempts = 0
        user.tactico_hour_started_at = now


async def _consume_hourly_slot(db: AsyncSession, user_id: int, config: GameConfig) -> User:
    locked_user = await lock_user_for_update(db, user_id)
    await _ensure_hourly_reset(locked_user)
    if locked_user.tactico_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.tactico_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.hourly_game_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.tactico_hourly_attempts += 1
    db.add(locked_user)
    return locked_user


async def create_bot_match(db: AsyncSession, user: User, difficulty: MatchDifficulty) -> TacticoMatchOut:
    config = await get_config(db)
    if await _has_active_match(db, user.id):
        raise ConflictError("У тебя уже есть матч в Тактико в процессе — заверши его или сдайся, прежде чем начать новый")
    squad = await get_squad(db, user)
    if not squad.is_complete:
        raise ConflictError(f"Build a full {SQUAD_SIZE}-card Tactico squad before playing")

    locked_user = await _consume_hourly_slot(db, user.id, config)

    avg_rating = round(sum(c.player.rating for c in squad.cards) / len(squad.cards))
    opponent_pool = await _synthesize_bot_squad(db, avg_rating, difficulty, config)

    state = {
        "rounds": [],
        "current_index": 0,
        "current_phase": _pick_phase(),
        "current_deadline": None,
        "last_activity_at": datetime.now(timezone.utc).isoformat(),
        "user_pool": [c.id for c in squad.cards],
        "opponent_pool": opponent_pool,
        "user_pending_card_id": None,
        "user_pending_snapshot": None,
        "opponent_pending_card_id": None,
        "opponent_pending_snapshot": None,
    }
    match = TacticoMatch(
        user_id=locked_user.id,
        opponent_user_id=None,
        opponent_name=random.choice(BOT_NAMES),
        opponent_type=TacticoOpponentType.bot,
        difficulty=difficulty,
        status=TacticoMatchStatus.in_progress,
        server_state=state,
    )
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, locked_user)


async def create_challenge(db: AsyncSession, sender: User, receiver_id: int) -> TacticoMatchOut:
    config = await get_config(db)
    if await _has_active_match(db, sender.id):
        raise ConflictError("У тебя уже есть матч в Тактико в процессе — заверши его или сдайся, прежде чем начать новый")
    squad = await get_squad(db, sender)
    if not squad.is_complete:
        raise ConflictError(f"Build a full {SQUAD_SIZE}-card Tactico squad before challenging a friend")

    receiver = await db.get(User, receiver_id)
    if not receiver:
        raise NotFoundError("User not found")
    if receiver.id == sender.id:
        raise ConflictError("You cannot challenge yourself")
    if receiver.is_banned:
        raise ConflictError("This user is banned and cannot be challenged")

    sender = await _consume_hourly_slot(db, sender.id, config)

    state = {
        "rounds": [],
        "current_index": 0,
        "current_phase": None,
        "current_deadline": None,
        "user_pool": [c.id for c in squad.cards],
        "opponent_pool": None,
        "user_pending_card_id": None,
        "user_pending_snapshot": None,
        "opponent_pending_card_id": None,
        "opponent_pending_snapshot": None,
    }
    match = TacticoMatch(
        user_id=sender.id,
        opponent_user_id=receiver.id,
        opponent_name=receiver.full_display_name(),
        opponent_type=TacticoOpponentType.friend,
        difficulty=None,
        status=TacticoMatchStatus.pending_accept,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=config.tactico_challenge_expiry_hours),
        server_state=state,
    )
    db.add(match)
    await db.flush()

    await notify(
        db, receiver.id, NotificationType.tactico_challenge_received,
        "Вызов в Тактико", f"{sender.full_display_name()} вызвал(а) вас на матч в Тактико.",
        "tactico_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, sender)


async def _get_match_or_404(db: AsyncSession, match_id: int) -> TacticoMatch:
    match = await db.get(TacticoMatch, match_id)
    if not match:
        raise NotFoundError("Match not found")
    return match


async def accept_challenge(db: AsyncSession, user: User, match_id: int) -> TacticoMatchOut:
    match = await _get_match_or_404(db, match_id)
    if match.opponent_user_id != user.id:
        raise ForbiddenError("Only the challenged user can accept this challenge")
    if match.status != TacticoMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")
    if ensure_aware(match.expires_at) <= datetime.now(timezone.utc):
        match.status = TacticoMatchStatus.expired
        match.resolved_at = datetime.now(timezone.utc)
        db.add(match)
        await db.commit()
        raise ConflictError("This challenge has expired")

    config = await get_config(db)
    if await _has_active_match(db, user.id, exclude_match_id=match.id):
        raise ConflictError("У тебя уже есть матч в Тактико в процессе — заверши его или сдайся, прежде чем принять вызов")
    receiver_squad = await get_squad(db, user)
    if not receiver_squad.is_complete:
        raise ConflictError(f"Build a full {SQUAD_SIZE}-card Tactico squad before accepting")

    state = dict(match.server_state)
    state["opponent_pool"] = [c.id for c in receiver_squad.cards]
    state["current_phase"] = _pick_phase()
    state["current_deadline"] = (
        datetime.now(timezone.utc) + timedelta(hours=config.tactico_round_timeout_hours)
    ).isoformat()
    match.server_state = state
    flag_modified(match, "server_state")
    match.status = TacticoMatchStatus.in_progress
    db.add(match)

    await notify(
        db, match.user_id, NotificationType.tactico_challenge_accepted,
        "Вызов принят", f"{user.full_display_name()} принял(а) ваш вызов в Тактико.",
        "tactico_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def decline_challenge(db: AsyncSession, user: User, match_id: int) -> TacticoMatchOut:
    match = await _get_match_or_404(db, match_id)
    if match.opponent_user_id != user.id:
        raise ForbiddenError("Only the challenged user can decline this challenge")
    if match.status != TacticoMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")

    match.status = TacticoMatchStatus.declined
    match.resolved_at = datetime.now(timezone.utc)
    db.add(match)
    await notify(
        db, match.user_id, NotificationType.tactico_challenge_declined,
        "Вызов отклонён", f"{user.full_display_name()} отклонил(а) ваш вызов в Тактико.",
        "tactico_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def cancel_challenge(db: AsyncSession, user: User, match_id: int) -> TacticoMatchOut:
    match = await _get_match_or_404(db, match_id)
    if match.user_id != user.id:
        raise ForbiddenError("Only the challenger can cancel this challenge")
    if match.status != TacticoMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")

    match.status = TacticoMatchStatus.cancelled
    match.resolved_at = datetime.now(timezone.utc)
    db.add(match)
    await notify(
        db, match.opponent_user_id, NotificationType.tactico_challenge_cancelled,
        "Вызов отменён", f"{user.full_display_name()} отменил(а) вызов в Тактико.",
        "tactico_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


# ---------------------------------------------------------------------------
# Round submission
# ---------------------------------------------------------------------------

async def _lock_match(db: AsyncSession, match_id: int) -> TacticoMatch:
    result = await db.execute(
        select(TacticoMatch).where(TacticoMatch.id == match_id).with_for_update().execution_options(populate_existing=True)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise NotFoundError("Match not found")
    return match


async def _load_owned_card(db: AsyncSession, user: User, user_card_id: int) -> UserCard:
    result = await db.execute(
        select(UserCard).where(UserCard.id == user_card_id).options(joinedload(UserCard.player))
    )
    card = result.unique().scalar_one_or_none()
    if not card or card.owner_id != user.id:
        raise ConflictError("That card is not available for this round")
    return card


async def submit_round(db: AsyncSession, user: User, match_id: int, user_card_id: int) -> TacticoMatchOut:
    config = await get_config(db)
    bonus_pct = float(config.tactico_phase_bonus_pct)
    match = await _lock_match(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    if match.status != TacticoMatchStatus.in_progress:
        raise ConflictError("This match is not in progress")

    side = "user" if user.id == match.user_id else "opponent"
    card = await _load_owned_card(db, user, user_card_id)

    state = dict(match.server_state)
    _record_pick(state, side, card)

    resolved = False
    if match.opponent_type == TacticoOpponentType.bot:
        state["last_activity_at"] = datetime.now(timezone.utc).isoformat()
        _bot_submit(state, match.difficulty, config, bonus_pct)
        _finalize_current_round(state, bonus_pct)
        resolved = True
    else:
        other_side = "opponent" if side == "user" else "user"
        if state.get(f"{other_side}_pending_card_id") is not None:
            _finalize_current_round(state, bonus_pct)
            resolved = True

    match.server_state = state
    flag_modified(match, "server_state")
    if resolved:
        match.user_score, match.opponent_score = _tally(state)

    if len(state["rounds"]) >= SQUAD_SIZE:
        await _finish_match(db, match, state, config)
    else:
        if resolved and match.opponent_type == TacticoOpponentType.friend:
            state["current_deadline"] = (
                datetime.now(timezone.utc) + timedelta(hours=config.tactico_round_timeout_hours)
            ).isoformat()
            match.server_state = state
            flag_modified(match, "server_state")
            other_side = "opponent" if side == "user" else "user"
            notify_user_id = match.opponent_user_id if other_side == "opponent" else match.user_id
            await notify(
                db, notify_user_id, NotificationType.tactico_your_turn,
                "Твой ход в Тактико", "Соперник сделал ход — твоя очередь выбрать карту.",
                "tactico_match", match.id,
            )
        db.add(match)
        await db.commit()

    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def _finish_match(
    db: AsyncSession, match: TacticoMatch, state: dict, config: GameConfig, forced_loser: Optional[str] = None
) -> None:
    user_wins, opponent_wins = _tally(state)

    if forced_loser == "user":
        # Forfeit (explicit or via abandonment) — always counts as a loss for
        # the forfeiting side regardless of the round tally, so leaving
        # mid-match is never a safer bet than finishing it out.
        result, user_delta = MatchResult.loss, -1
    elif forced_loser == "opponent":
        result, user_delta = MatchResult.win, 3
    elif user_wins > opponent_wins:
        result, user_delta = MatchResult.win, 3
    elif user_wins < opponent_wins:
        result, user_delta = MatchResult.loss, -1
    else:
        result, user_delta = MatchResult.draw, 1
    opponent_delta = _OPPONENT_RATING_DELTA[user_delta]
    state["opponent_rating_delta"] = opponent_delta

    match.user_score, match.opponent_score = user_wins, opponent_wins
    match.result = result
    match.rating_delta = user_delta
    match.status = TacticoMatchStatus.finished
    match.resolved_at = datetime.now(timezone.utc)

    is_friend = match.opponent_type == TacticoOpponentType.friend and match.opponent_user_id is not None
    locked_opponent: Optional[User] = None
    if is_friend:
        first_id, second_id = sorted([match.user_id, match.opponent_user_id])
        first_locked = await lock_user_for_update(db, first_id)
        second_locked = await lock_user_for_update(db, second_id)
        locked_user = first_locked if first_locked.id == match.user_id else second_locked
        locked_opponent = first_locked if first_locked.id == match.opponent_user_id else second_locked
    else:
        locked_user = await lock_user_for_update(db, match.user_id)

    locked_user.tactics_rating = max(0, locked_user.tactics_rating + user_delta)
    db.add(locked_user)

    reward = 0
    if match.opponent_type == TacticoOpponentType.bot:
        reward_base = {
            MatchResult.win: config.tactico_reward_win,
            MatchResult.draw: config.tactico_reward_draw,
            MatchResult.loss: config.tactico_reward_loss,
        }
        reward = 0 if locked_user.game_rewards_blocked else reward_base[result]
        if reward > 0:
            await credit_coins(
                db, locked_user, reward, TransactionType.tactico_reward,
                f"Награда за матч Тактико ({result.value})", "tactico_match", match.id,
            )
    match.reward_coins = reward

    if locked_opponent is not None:
        locked_opponent.tactics_rating = max(0, locked_opponent.tactics_rating + opponent_delta)
        db.add(locked_opponent)
        await notify(
            db, match.opponent_user_id, NotificationType.tactico_match_finished,
            "Матч Тактико завершён",
            f"Матч с {locked_user.full_display_name()} завершён — результат: {_FLIP_RESULT[result].value}.",
            "tactico_match", match.id,
        )
        await notify(
            db, match.user_id, NotificationType.tactico_match_finished,
            "Матч Тактико завершён",
            f"Матч с {locked_opponent.full_display_name()} завершён — результат: {result.value}.",
            "tactico_match", match.id,
        )

    match.server_state = state
    flag_modified(match, "server_state")
    db.add(match)
    await db.commit()


async def forfeit_match(db: AsyncSession, user: User, match_id: int) -> TacticoMatchOut:
    """Immediately ends an in-progress match as a loss for the forfeiting
    side. Used both by an explicit "leave match" confirmation from the
    frontend and, indirectly, by the abandonment sweep below — leaving
    mid-match is never safer than finishing it, which is the whole point."""
    match = await _lock_match(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    if match.status != TacticoMatchStatus.in_progress:
        raise ConflictError("This match is not in progress")

    config = await get_config(db)
    state = dict(match.server_state or {})
    forfeiting_side = "user" if user.id == match.user_id else "opponent"
    await _finish_match(db, match, state, config, forced_loser=forfeiting_side)
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


# ---------------------------------------------------------------------------
# Lazy timeout sweep (mirrors trade_service._expire_if_needed / expire_stale_trades)
# ---------------------------------------------------------------------------

async def _auto_play_overdue_rounds(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TacticoMatch).where(TacticoMatch.status == TacticoMatchStatus.in_progress)
    )
    matches = result.scalars().all()
    if not matches:
        return 0

    config = await get_config(db)
    bonus_pct = float(config.tactico_phase_bonus_pct)
    timeout = timedelta(hours=config.tactico_round_timeout_hours)
    swept = 0
    for match in matches:
        state = dict(match.server_state or {})

        if match.opponent_type == TacticoOpponentType.bot:
            # Bot matches have no "other side" to wait on — a match with no
            # activity for a full timeout window is simply abandoned.
            last_activity = state.get("last_activity_at")
            if last_activity and ensure_aware(datetime.fromisoformat(last_activity)) + timeout <= now:
                await _finish_match(db, match, state, config, forced_loser="user")
                swept += 1
            continue

        deadline = state.get("current_deadline")
        if not deadline or ensure_aware(datetime.fromisoformat(deadline)) > now:
            continue

        for side in ("user", "opponent"):
            if state.get(f"{side}_pending_card_id") is None and state.get(f"{side}_pool"):
                pick_id = random.choice(state[f"{side}_pool"])
                card_result = await db.execute(
                    select(UserCard).where(UserCard.id == pick_id).options(joinedload(UserCard.player))
                )
                card = card_result.unique().scalar_one_or_none()
                if card:
                    _record_pick(state, side, card)

        if state.get("user_pending_card_id") is not None and state.get("opponent_pending_card_id") is not None:
            _finalize_current_round(state, bonus_pct)
            state["current_deadline"] = (now + timedelta(hours=config.tactico_round_timeout_hours)).isoformat()
            match.user_score, match.opponent_score = _tally(state)

        match.server_state = state
        flag_modified(match, "server_state")

        if len(state["rounds"]) >= SQUAD_SIZE:
            await _finish_match(db, match, state, config)
        else:
            db.add(match)
            await db.commit()
        swept += 1
    return swept


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def get_stats(db: AsyncSession, user: User) -> TacticoStatsOut:
    ranking = await ranking_service.get_ranking(db, RankingMetric.tactics_rating, user)
    return TacticoStatsOut(
        tactics_rating=user.tactics_rating,
        tactics_rank=ranking.me.rank if ranking.me else None,
    )


async def _hydrate_match(db: AsyncSession, match: TacticoMatch, viewer: User) -> TacticoMatchOut:
    state = match.server_state or {}
    side = "user" if viewer.id == match.user_id else "opponent"

    if side == "user":
        opponent_name = match.opponent_name
        opponent_user_id = match.opponent_user_id
    else:
        challenger = await db.get(User, match.user_id)
        opponent_name = challenger.full_display_name() if challenger else match.opponent_name
        opponent_user_id = match.user_id

    rounds_out: list[TacticoRoundOut] = []
    for r in state.get("rounds", []):
        relabeled = _relabel_round(r, side)
        rounds_out.append(
            TacticoRoundOut(
                index=relabeled["index"],
                phase=relabeled["phase"],
                user_card=TacticoCardOut(**relabeled["user_card"]) if relabeled.get("user_card") else None,
                opponent_card=TacticoCardOut(**relabeled["opponent_card"]) if relabeled.get("opponent_card") else None,
                winner=relabeled.get("winner"),
            )
        )

    current_phase = state.get("current_phase") if match.status == TacticoMatchStatus.in_progress else None
    waiting_for_opponent = False
    pickable_cards: Optional[list[TacticoCardOut]] = None

    if match.status == TacticoMatchStatus.in_progress:
        if state.get(f"{side}_pending_card_id") is not None:
            waiting_for_opponent = True
        else:
            pool_ids = state.get(f"{side}_pool") or []
            if pool_ids:
                cards_result = await db.execute(
                    select(UserCard).where(UserCard.id.in_(pool_ids)).options(joinedload(UserCard.player))
                )
                cards_by_id = {c.id: c for c in cards_result.unique().scalars().all()}
                pickable_cards = [
                    TacticoCardOut(**_card_snapshot(cards_by_id[cid].player, user_card_id=cid))
                    for cid in pool_ids
                    if cid in cards_by_id
                ]

    if side == "user":
        viewer_score, other_score = match.user_score, match.opponent_score
        result_out = match.result
        reward_coins = match.reward_coins
        rating_delta = match.rating_delta
    else:
        viewer_score, other_score = match.opponent_score, match.user_score
        result_out = _FLIP_RESULT[match.result] if match.result else None
        reward_coins = 0
        rating_delta = state.get("opponent_rating_delta", 0)

    return TacticoMatchOut(
        id=match.id,
        opponent_type=match.opponent_type,
        opponent_name=opponent_name,
        opponent_user_id=opponent_user_id,
        difficulty=match.difficulty,
        status=match.status,
        viewer_side=side,
        user_score=viewer_score,
        opponent_score=other_score,
        rounds=rounds_out,
        current_phase=current_phase,
        pickable_cards=pickable_cards,
        waiting_for_opponent=waiting_for_opponent,
        result=result_out,
        reward_coins=reward_coins,
        rating_delta=rating_delta,
        created_at=match.created_at,
        expires_at=match.expires_at,
        resolved_at=match.resolved_at,
    )


async def list_matches(db: AsyncSession, user: User) -> list[TacticoMatchOut]:
    await _auto_play_overdue_rounds(db)
    result = await db.execute(
        select(TacticoMatch)
        .where(or_(TacticoMatch.user_id == user.id, TacticoMatch.opponent_user_id == user.id))
        .order_by(TacticoMatch.created_at.desc())
    )
    matches = result.scalars().all()
    return [await _hydrate_match(db, m, user) for m in matches]


async def get_match(db: AsyncSession, user: User, match_id: int) -> TacticoMatchOut:
    await _auto_play_overdue_rounds(db)
    match = await _get_match_or_404(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    return await _hydrate_match(db, match, user)
