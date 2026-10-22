"""«Мордобой» — DB layer around mordoboi_engine.

Shape mirrors stratego_service: a JSON server_state per match, async friend
matches with per-exchange deadlines resolved lazily by `_sweep` on reads
(no scheduler), matchmaking via a queue table, hourly/daily counters on
User, rewards through wallet_service with row locks.

Simultaneous secret picks: each side's pick for the current exchange sits in
server_state["picks"] until both are in; `_hydrate_match` is the single
place a match leaves the server and it never shows the opponent's pick.

Concurrency / retries: every pick runs under the match row lock and carries
the `version` the client saw. The version only moves when the state the
client needs changes (an exchange resolves, the match starts or ends) — not
when one side's pick is merely recorded — so both boxers can pick against
the same version at the same moment. A repeated request (same action, same
version as this side's last accepted pick) returns the match unchanged.
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
    MatchResult,
    MordoboiMatchStatus,
    MordoboiOpponentType,
    NotificationType,
    TransactionType,
)
from app.models.game_config import GameConfig
from app.models.mordoboi import MordoboiMatch, MordoboiQueueEntry
from app.models.player import Player
from app.models.user import User
from app.schemas.mordoboi import (
    MordoboiBoxerOptionOut,
    MordoboiBoxerOut,
    MordoboiBoxerStatsOut,
    MordoboiCardOut,
    MordoboiExchangeOut,
    MordoboiFighterOut,
    MordoboiInfoOut,
    MordoboiMatchOut,
    MordoboiScorecardOut,
    MordoboiStatsOut,
)
from app.schemas.ranking import RankingMetric
from app.services import mordoboi_engine as engine
from app.services import ranking_service
from app.services.game_config_service import get_config
from app.services.match_service import BOT_NAMES
from app.services.notification_service import notify
from app.services.player_stats_service import card_rating_bonus, effective_card_stats
from app.services.wallet_service import credit_coins, lock_user_for_update

MATCHMAKING_TIMEOUT_SECONDS = 60
LOG_IN_RESPONSE = 40
# A friend gets at most one "твой ход" message per match this often.
NUDGE_COOLDOWN = timedelta(minutes=30)
RELATED = "mordoboi_match"

_FLIP = {MatchResult.win: MatchResult.loss, MatchResult.loss: MatchResult.win, MatchResult.draw: MatchResult.draw}
# Same base deltas as Tactico / Stratego.
_BASE_RATING_DELTA = {MatchResult.win: 3, MatchResult.loss: -1, MatchResult.draw: 1}
_RATING_MULTIPLIER = {MordoboiOpponentType.friend: 0, MordoboiOpponentType.online: 2, MordoboiOpponentType.bot: 1}

_ACTIVE_MATCH_MSG = "У тебя уже идёт бой в «Мордобое» — доиграй его или сдайся"


def _require_enabled(config: GameConfig) -> None:
    if not config.mordoboi_enabled:
        raise ConflictError("«Мордобой» сейчас недоступен", details={"reason": "disabled"})


# ---------------------------------------------------------------------------
# Boxers (cards)
# ---------------------------------------------------------------------------

def _card_snapshot(player: Player, user_card_id: Optional[int], rating: int) -> dict:
    return {
        "user_card_id": user_card_id, "player_id": player.id, "display_name": player.display_name,
        "position": player.position.value, "image_path": player.image_path,
        "rarity": player.rarity.value, "rating": rating,
    }


def _player_fighter(player: Player, config: GameConfig, user_card_id: Optional[int] = None, bonus: int = 0) -> dict:
    rating, attack, defense = effective_card_stats(player, bonus)
    stats = engine.boxer_stats(rating, attack, defense, player.position.value, config.mordoboi_base_hp)
    return engine.new_fighter(stats, _card_snapshot(player, user_card_id, rating))


def _card_fighter(card: UserCard, config: GameConfig) -> dict:
    return _player_fighter(card.player, config, card.id, card_rating_bonus(card))


async def _usable_cards(db: AsyncSession, user_id: int) -> list[UserCard]:
    result = await db.execute(
        select(UserCard)
        .where(UserCard.owner_id == user_id, UserCard.is_locked_by_admin.is_(False))
        .options(joinedload(UserCard.player))
    )
    cards = list(result.unique().scalars().all())
    cards.sort(key=lambda c: (-effective_card_stats(c.player, card_rating_bonus(c))[0], c.id))
    return cards


async def _boxer_card(db: AsyncSession, user: User) -> UserCard:
    """The saved boxer if the user still owns it, otherwise the strongest card."""
    cards = await _usable_cards(db, user.id)
    if not cards:
        raise ConflictError("Для «Мордобоя» нужна хотя бы одна карточка в коллекции")
    return next((c for c in cards if c.id == user.mordoboi_card_id), cards[0])


def _option(fighter: dict) -> MordoboiBoxerOptionOut:
    return MordoboiBoxerOptionOut(
        card=MordoboiCardOut(**fighter["card"]),
        stats=MordoboiBoxerStatsOut(**{k: fighter[k] for k in ("power", "speed", "guard", "max_hp", "max_stamina")}),
    )


async def get_boxer(db: AsyncSession, user: User) -> MordoboiBoxerOut:
    config = await get_config(db)
    cards = await _usable_cards(db, user.id)
    options = [_option(_card_fighter(c, config)) for c in cards]
    if not cards:
        return MordoboiBoxerOut(selected=None, options=[])
    chosen = next((o for o in options if o.card.user_card_id == user.mordoboi_card_id), options[0])
    return MordoboiBoxerOut(selected=chosen, options=options)


async def set_boxer(db: AsyncSession, user: User, user_card_id: int) -> MordoboiBoxerOut:
    card = await db.get(UserCard, user_card_id)
    if card is None or card.owner_id != user.id or card.is_locked_by_admin:
        raise ForbiddenError("Можно выбрать только свою карточку")
    user.mordoboi_card_id = card.id
    db.add(user)
    await db.commit()
    return await get_boxer(db, user)


async def _bot_fighter(db: AsyncSession, target_rating: int, config: GameConfig) -> dict:
    for band in (4, 10, 99):
        result = await db.execute(
            select(Player)
            .where(Player.is_active.is_(True), Player.rating.between(target_rating - band, target_rating + band))
            .order_by(func.random()).limit(1)
        )
        player = result.scalar_one_or_none()
        if player is not None:
            return _player_fighter(player, config)
    raise ConflictError("Нет доступных игроков для соперника-бота")


# ---------------------------------------------------------------------------
# Info / stats
# ---------------------------------------------------------------------------

async def get_info(db: AsyncSession, user: User) -> MordoboiInfoOut:
    config = await get_config(db)
    reset_day = local_today(user.mordoboi_attempts_reset_at) if user.mordoboi_attempts_reset_at else None
    return MordoboiInfoOut(
        enabled=config.mordoboi_enabled, rounds=config.mordoboi_rounds,
        exchanges_per_round=config.mordoboi_exchanges_per_round, base_hp=config.mordoboi_base_hp,
        reward_win=config.mordoboi_reward_win, reward_draw=config.mordoboi_reward_draw,
        reward_loss=config.mordoboi_reward_loss, reward_ko_bonus=config.mordoboi_reward_ko_bonus,
        daily_limit=config.mordoboi_daily_limit,
        rewarded_today=user.mordoboi_rewarded_attempts_today if reset_day == local_today() else 0,
        easy_reward_pct=config.mordoboi_bot_easy_reward_pct,
        move_timeout_hours=config.mordoboi_move_timeout_hours, live_move_seconds=config.mordoboi_live_move_seconds,
        challenge_expiry_hours=config.mordoboi_challenge_expiry_hours, max_auto_moves=config.mordoboi_max_auto_moves,
        stamina_cost=dict(engine.STAMINA_COST), damage=dict(engine.BASE_DAMAGE),
    )


async def get_stats(db: AsyncSession, user: User) -> MordoboiStatsOut:
    ranking = await ranking_service.get_ranking(db, RankingMetric.mordoboi_rating, user)
    return MordoboiStatsOut(mordoboi_rating=user.mordoboi_rating, mordoboi_rank=ranking.me.rank if ranking.me else None)


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

def _ensure_hourly_reset(user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.mordoboi_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.mordoboi_hourly_attempts = 0
        user.mordoboi_hour_started_at = now


def _ensure_daily_reset(user: User) -> None:
    reset_day = local_today(user.mordoboi_attempts_reset_at) if user.mordoboi_attempts_reset_at else None
    if reset_day != local_today():
        user.mordoboi_rewarded_attempts_today = 0
        user.mordoboi_attempts_reset_at = datetime.now(timezone.utc)


def _hourly_limit_error(user: User, config: GameConfig) -> ConflictError:
    remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(user.mordoboi_hour_started_at))
    return ConflictError(
        "Hourly play limit reached for this game",
        details={"hourly_limit": config.hourly_game_limit, "retry_after_seconds": max(0, int(remaining.total_seconds()))},
    )


async def _has_active_match(db: AsyncSession, user_id: int, exclude_match_id: Optional[int] = None) -> bool:
    conditions = [
        or_(MordoboiMatch.user_id == user_id, MordoboiMatch.opponent_user_id == user_id),
        MordoboiMatch.status == MordoboiMatchStatus.in_progress,
    ]
    if exclude_match_id is not None:
        conditions.append(MordoboiMatch.id != exclude_match_id)
    result = await db.execute(select(MordoboiMatch.id).where(*conditions).limit(1))
    return result.scalar_one_or_none() is not None


async def _consume_hourly_slot(db: AsyncSession, user_id: int, config: GameConfig, exclude_match_id: Optional[int] = None) -> User:
    """Locks the user row, then re-checks "one active bout" under that lock
    so two concurrent create/accept requests can't both start a match."""
    locked = await lock_user_for_update(db, user_id)
    if await _has_active_match(db, user_id, exclude_match_id):
        raise ConflictError(_ACTIVE_MATCH_MSG)
    _ensure_hourly_reset(locked)
    if locked.mordoboi_hourly_attempts >= config.hourly_game_limit:
        raise _hourly_limit_error(locked, config)
    locked.mordoboi_hourly_attempts += 1
    db.add(locked)
    return locked


# ---------------------------------------------------------------------------
# Match creation / lifecycle
# ---------------------------------------------------------------------------

def _new_state(config: GameConfig, user_fighter: dict, opponent_fighter: Optional[dict]) -> dict:
    state = engine.new_state(user_fighter, opponent_fighter, config.mordoboi_rounds, config.mordoboi_exchanges_per_round)
    state.update({
        "deadline": None, "auto_moves": {"user": 0, "opponent": 0},
        "max_auto_moves": config.mordoboi_max_auto_moves,
        "last_pick": {"user": None, "opponent": None}, "nudged_at": {},
        "last_activity_at": datetime.now(timezone.utc).isoformat(),
    })
    return state


def _move_timeout(state: dict, config: GameConfig) -> timedelta:
    if state.get("live"):
        return timedelta(seconds=config.mordoboi_live_move_seconds)
    return timedelta(hours=config.mordoboi_move_timeout_hours)


def _start_deadline(state: dict, config: GameConfig, now: Optional[datetime] = None) -> None:
    now = now or datetime.now(timezone.utc)
    state["deadline"] = (now + _move_timeout(state, config)).isoformat()


async def _random_bot_name(db: AsyncSession, exclude_user_id: int) -> str:
    result = await db.execute(
        select(User)
        .where(User.is_banned.is_(False), User.is_admin.is_(False), User.id != exclude_user_id)
        .order_by(func.random()).limit(1)
    )
    candidate = result.scalar_one_or_none()
    return candidate.full_display_name() if candidate else random.choice(BOT_NAMES)


async def create_bot_match(db: AsyncSession, user: User, difficulty: str = "hard") -> MordoboiMatchOut:
    config = await get_config(db)
    _require_enabled(config)
    if await _has_active_match(db, user.id):
        raise ConflictError(_ACTIVE_MATCH_MSG)
    me = _card_fighter(await _boxer_card(db, user), config)
    bot = await _bot_fighter(db, me["card"]["rating"], config)
    locked = await _consume_hourly_slot(db, user.id, config)
    state = _new_state(config, me, bot)
    state["difficulty"] = difficulty
    match = MordoboiMatch(
        user_id=locked.id, opponent_user_id=None, opponent_name=await _random_bot_name(db, user.id),
        opponent_type=MordoboiOpponentType.bot, status=MordoboiMatchStatus.in_progress, server_state=state,
    )
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, locked)


async def create_challenge(db: AsyncSession, sender: User, receiver_id: int) -> MordoboiMatchOut:
    config = await get_config(db)
    _require_enabled(config)
    if await _has_active_match(db, sender.id):
        raise ConflictError(_ACTIVE_MATCH_MSG)
    receiver = await db.get(User, receiver_id)
    if not receiver:
        raise NotFoundError("User not found")
    if receiver.id == sender.id:
        raise ConflictError("You cannot challenge yourself")
    if receiver.is_banned:
        raise ConflictError("This user is banned and cannot be challenged")
    me = _card_fighter(await _boxer_card(db, sender), config)
    sender = await _consume_hourly_slot(db, sender.id, config)
    match = MordoboiMatch(
        user_id=sender.id, opponent_user_id=receiver.id, opponent_name=receiver.full_display_name(),
        opponent_type=MordoboiOpponentType.friend, status=MordoboiMatchStatus.pending_accept,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=config.mordoboi_challenge_expiry_hours),
        server_state=_new_state(config, me, None),
    )
    db.add(match)
    await db.flush()
    await notify(
        db, receiver.id, NotificationType.mordoboi_challenge_received,
        "Вызов в «Мордобой»", f"{sender.full_display_name()} вызывает тебя на ринг.", RELATED, match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, sender)


async def _get_match_or_404(db: AsyncSession, match_id: int) -> MordoboiMatch:
    match = await db.get(MordoboiMatch, match_id)
    if not match:
        raise NotFoundError("Match not found")
    return match


async def _lock_match(db: AsyncSession, match_id: int, skip_locked: bool = False) -> Optional[MordoboiMatch]:
    stmt = select(MordoboiMatch).where(MordoboiMatch.id == match_id).execution_options(populate_existing=True)
    result = await db.execute(stmt.with_for_update(skip_locked=skip_locked))
    match = result.scalar_one_or_none()
    if match is None and not skip_locked:
        raise NotFoundError("Match not found")
    return match


def _expire_if_due(match: MordoboiMatch) -> bool:
    if ensure_aware(match.expires_at) <= datetime.now(timezone.utc):
        match.status = MordoboiMatchStatus.expired
        match.resolved_at = datetime.now(timezone.utc)
        return True
    return False


async def accept_challenge(db: AsyncSession, user: User, match_id: int) -> MordoboiMatchOut:
    match = await _lock_match(db, match_id)
    if match.opponent_user_id != user.id:
        raise ForbiddenError("Only the challenged user can accept this challenge")
    if match.status != MordoboiMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")
    if _expire_if_due(match):
        db.add(match)
        await db.commit()
        raise ConflictError("This challenge has expired")
    config = await get_config(db)
    _require_enabled(config)
    if await _has_active_match(db, match.user_id, exclude_match_id=match.id):
        raise ConflictError("Соперник сейчас на другом ринге — попробуй позже")
    fighter = _card_fighter(await _boxer_card(db, user), config)
    locked = await _consume_hourly_slot(db, user.id, config, exclude_match_id=match.id)

    state = dict(match.server_state)
    state["fighters"] = {**state["fighters"], "opponent": fighter}
    state["last_activity_at"] = datetime.now(timezone.utc).isoformat()
    _start_deadline(state, config)
    match.server_state = state
    flag_modified(match, "server_state")
    match.status = MordoboiMatchStatus.in_progress
    match.version += 1
    db.add(match)
    await notify(
        db, match.user_id, NotificationType.mordoboi_challenge_accepted,
        "Вызов принят", f"{locked.full_display_name()} вышел(а) на ринг — выбирай первый удар.", RELATED, match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, locked)


async def decline_challenge(db: AsyncSession, user: User, match_id: int) -> MordoboiMatchOut:
    match = await _lock_match(db, match_id)
    if match.opponent_user_id != user.id:
        raise ForbiddenError("Only the challenged user can decline this challenge")
    if match.status != MordoboiMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")
    match.status = MordoboiMatchStatus.declined
    match.resolved_at = datetime.now(timezone.utc)
    match.version += 1
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def cancel_challenge(db: AsyncSession, user: User, match_id: int) -> MordoboiMatchOut:
    match = await _lock_match(db, match_id)
    if match.user_id != user.id:
        raise ForbiddenError("Only the challenger can cancel this challenge")
    if match.status != MordoboiMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")
    match.status = MordoboiMatchStatus.cancelled
    match.resolved_at = datetime.now(timezone.utc)
    match.version += 1
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


# ---------------------------------------------------------------------------
# Picks
# ---------------------------------------------------------------------------

def _rng(match_id: int, state: dict, purpose: str) -> random.Random:
    # Seeded per match and exchange: a retried request or a re-run sweep
    # replays the same rolls instead of re-rolling them.
    return random.Random(f"mordoboi:{purpose}:{match_id}:{engine.exchange_index(state)}")


def _side_of(match: MordoboiMatch, user: User) -> str:
    if user.id == match.user_id:
        return "user"
    if user.id == match.opponent_user_id:
        return "opponent"
    raise ForbiddenError("You are not part of this match")


def _uid(match: MordoboiMatch, side: str) -> Optional[int]:
    return match.user_id if side == "user" else match.opponent_user_id


async def _nudge(db: AsyncSession, match: MordoboiMatch, state: dict, side: str, body: str) -> None:
    """«Твой ход» for a friend bout, at most once per NUDGE_COOLDOWN."""
    if match.opponent_type != MordoboiOpponentType.friend or state.get("live"):
        return
    uid = _uid(match, side)
    if uid is None:
        return
    now = datetime.now(timezone.utc)
    last = (state.get("nudged_at") or {}).get(side)
    if last and now - ensure_aware(datetime.fromisoformat(last)) < NUDGE_COOLDOWN:
        return
    state["nudged_at"] = {**(state.get("nudged_at") or {}), side: now.isoformat()}
    await notify(db, uid, NotificationType.mordoboi_your_turn, "Твой ход в «Мордобое»", body, RELATED, match.id)


def _record_pick(state: dict, side: str, action: str, version: Optional[int] = None, auto: bool = False) -> None:
    """`version` is given for a player's own pick only: it is what lets a
    retried request be recognised (see submit_pick)."""
    state["picks"] = {**state["picks"], side: {"action": action, "auto": auto}}
    if version is not None:
        state["last_pick"] = {**(state.get("last_pick") or {}), side: {"version": version, "action": action}}


async def submit_pick(db: AsyncSession, user: User, match_id: int, action: str, version: int) -> MordoboiMatchOut:
    match = await _lock_match(db, match_id)
    side = _side_of(match, user)
    state = dict(match.server_state or {})
    last = (state.get("last_pick") or {}).get(side)
    if last and last["version"] == version and last["action"] == action:
        return await _hydrate_match(db, match, user)  # a retried request — already applied
    if match.status != MordoboiMatchStatus.in_progress:
        raise ConflictError("Этот бой не идёт")
    if version != match.version:
        raise ConflictError("Бой уже ушёл вперёд — обнови экран", details={"version": match.version})
    if state["picks"].get(side) is not None:
        raise ConflictError("Ты уже выбрал действие в этом обмене")
    try:
        engine.validate_pick(state, side, action)
    except engine.EngineError as exc:
        raise ConflictError(str(exc))

    config = await get_config(db)
    now = datetime.now(timezone.utc)
    _record_pick(state, side, action, version)
    state["auto_moves"] = {**state.get("auto_moves", {}), side: 0}
    state["last_activity_at"] = now.isoformat()
    other = engine.other_side(side)
    if match.opponent_type == MordoboiOpponentType.bot:
        bot_action = engine.bot_choose(state, other, _rng(match.id, state, "bot"), state.get("difficulty", "hard"))
        _record_pick(state, other, bot_action)

    if state["picks"][other] is None:
        await _nudge(db, match, state, other, "Соперник уже выбрал удар — твоя очередь.")
        _save_state(match, state)
        db.add(match)
        await db.commit()
        await db.refresh(match)
        return await _hydrate_match(db, match, user)

    await _resolve_and_continue(db, match, state, config, now, actor=side)
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


def _save_state(match: MordoboiMatch, state: dict) -> None:
    match.server_state = state
    flag_modified(match, "server_state")


async def _resolve_and_continue(
    db: AsyncSession, match: MordoboiMatch, state: dict, config: GameConfig, now: datetime, actor: Optional[str],
) -> None:
    """Both picks are in: resolve the exchange, then finish or open the next
    one. Commits. `actor` is the side whose pick completed the exchange (it
    is on screen); the other side gets the «твой ход» nudge."""
    engine.resolve_exchange(state, _rng(match.id, state, "resolve"))
    match.version += 1
    if state["finished"]:
        await _finish_match(db, match, state, config, state["winner"], state["reason"])
        return
    if match.opponent_type != MordoboiOpponentType.bot:
        _start_deadline(state, config, now)
        for side in engine.SIDES:
            if side != actor:
                await _nudge(db, match, state, side, "Обмен сыгран — выбирай следующий удар.")
    _save_state(match, state)
    db.add(match)
    await db.commit()


async def forfeit_match(db: AsyncSession, user: User, match_id: int) -> MordoboiMatchOut:
    match = await _lock_match(db, match_id)
    side = _side_of(match, user)
    if match.status != MordoboiMatchStatus.in_progress:
        raise ConflictError("Этот бой не идёт")
    config = await get_config(db)
    state = dict(match.server_state)
    engine.finish_by(state, engine.other_side(side), "forfeit")
    match.version += 1
    await _finish_match(db, match, state, config, engine.other_side(side), "forfeit", quitters={side})
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


def _reward_for(result: MatchResult, config: GameConfig) -> int:
    return {
        MatchResult.win: config.mordoboi_reward_win,
        MatchResult.draw: config.mordoboi_reward_draw,
        MatchResult.loss: config.mordoboi_reward_loss,
    }[result]


async def _grant_reward(
    db: AsyncSession, user: User, result: MatchResult, config: GameConfig, match_id: int, pct: int, ko: bool,
) -> int:
    _ensure_daily_reset(user)
    from app.services.club_pass_service import extra_rewarded_attempts

    limit = config.mordoboi_daily_limit + await extra_rewarded_attempts(db, user.id, config)
    if user.game_rewards_blocked or user.mordoboi_rewarded_attempts_today >= limit:
        db.add(user)
        return 0
    base = _reward_for(result, config) + (config.mordoboi_reward_ko_bonus if ko and result == MatchResult.win else 0)
    reward = round(base * pct / 100)
    user.mordoboi_rewarded_attempts_today += 1
    if reward > 0:
        await credit_coins(
            db, user, reward, TransactionType.mordoboi_reward,
            f"Награда за бой в «Мордобое» ({result.value})", RELATED, match_id,
        )
    db.add(user)
    return reward


async def _finish_match(
    db: AsyncSession, match: MordoboiMatch, state: dict, config: GameConfig,
    winner: str, reason: str, quitters: frozenset[str] | set[str] = frozenset(),
) -> None:
    """`winner` is "user" | "opponent" | "draw". A side in `quitters`
    (forfeit / timed out) gets no reward at all, so leaving is never better
    than boxing a lost bout out. Commits."""
    result = MatchResult.draw if winner == "draw" else MatchResult.win if winner == "user" else MatchResult.loss
    match.result = result
    match.win_reason = reason
    match.status = MordoboiMatchStatus.finished
    match.resolved_at = datetime.now(timezone.utc)
    state["deadline"] = None

    is_bot = match.opponent_type == MordoboiOpponentType.bot
    side_uid = {"user": match.user_id, "opponent": None if is_bot else match.opponent_user_id}
    locked: dict[int, User] = {}
    for uid in sorted(u for u in side_uid.values() if u is not None):
        locked[uid] = await lock_user_for_update(db, uid)

    side_result = {"user": result, "opponent": _FLIP[result]}
    easy = state.get("difficulty") == "easy"
    multiplier = _RATING_MULTIPLIER[match.opponent_type]
    for side in engine.SIDES:
        uid = side_uid[side]
        if uid is None:
            continue
        if side in quitters:
            reward = 0
            delta = min(0, _BASE_RATING_DELTA[side_result[side]] * multiplier)
        else:
            pct = config.mordoboi_bot_easy_reward_pct if easy else 100
            reward = await _grant_reward(db, locked[uid], side_result[side], config, match.id, pct, reason == "ko")
            delta = _BASE_RATING_DELTA[side_result[side]] * multiplier
            if easy and delta > 1:
                delta = 1  # the easy bot is no rating farm (same rule as Stratego)
        locked[uid].mordoboi_rating = max(0, locked[uid].mordoboi_rating + delta)
        db.add(locked[uid])
        if side == "user":
            match.user_reward_coins, match.user_rating_delta = reward, delta
        else:
            match.opponent_reward_coins, match.opponent_rating_delta = reward, delta

    if not is_bot and match.opponent_user_id:
        labels = {MatchResult.win: "победа", MatchResult.draw: "ничья", MatchResult.loss: "поражение"}
        for side in engine.SIDES:
            await notify(
                db, side_uid[side], NotificationType.mordoboi_match_finished,
                "Бой в «Мордобое» окончен", f"Итог: {labels[side_result[side]]}.", RELATED, match.id,
            )
    _save_state(match, state)
    db.add(match)
    await db.commit()


# ---------------------------------------------------------------------------
# Lazy sweep (no scheduler — runs on reads, like stratego_service)
# ---------------------------------------------------------------------------

async def _sweep(db: AsyncSession) -> int:
    """Expires stale challenges, autopilots a side that missed its exchange
    deadline (too many in a row = lost by timeout) and closes abandoned bot
    bouts. Each match is re-read under FOR UPDATE SKIP LOCKED, so a pick
    being submitted right now — or another sweep — is simply skipped."""
    result = await db.execute(
        select(MordoboiMatch).where(
            MordoboiMatch.status.in_((MordoboiMatchStatus.in_progress, MordoboiMatchStatus.pending_accept))
        )
    )
    candidates = list(result.scalars().all())
    if not candidates:
        return 0
    config = await get_config(db)
    now = datetime.now(timezone.utc)
    due = [m.id for m in candidates if _is_due(m, config, now)]
    swept = 0
    for match_id in due:
        match = await _lock_match(db, match_id, skip_locked=True)
        if match is None or match.status not in (MordoboiMatchStatus.in_progress, MordoboiMatchStatus.pending_accept):
            await db.commit()
            continue
        if await _sweep_one(db, match, config):
            swept += 1
        else:
            await db.commit()  # release the row lock
    return swept


def _is_due(match: MordoboiMatch, config: GameConfig, now: datetime) -> bool:
    """Cheap unlocked pre-check, re-done under the lock by _sweep_one."""
    if match.status == MordoboiMatchStatus.pending_accept:
        return match.expires_at is not None and ensure_aware(match.expires_at) <= now
    state = match.server_state or {}
    if match.opponent_type == MordoboiOpponentType.bot:
        last = state.get("last_activity_at")
        return bool(last) and ensure_aware(datetime.fromisoformat(last)) + _move_timeout(state, config) <= now
    deadline = state.get("deadline")
    return bool(deadline) and ensure_aware(datetime.fromisoformat(deadline)) <= now


async def _sweep_one(db: AsyncSession, match: MordoboiMatch, config: GameConfig) -> bool:
    now = datetime.now(timezone.utc)
    if match.status == MordoboiMatchStatus.pending_accept:
        if match.expires_at and _expire_if_due(match):
            match.version += 1
            db.add(match)
            await db.commit()
            return True
        return False

    state = dict(match.server_state or {})
    timeout = _move_timeout(state, config)
    if match.opponent_type == MordoboiOpponentType.bot:
        last = state.get("last_activity_at")
        if last and ensure_aware(datetime.fromisoformat(last)) + timeout <= now:
            engine.finish_by(state, "opponent", "timeout")
            match.version += 1
            await _finish_match(db, match, state, config, "opponent", "timeout", quitters={"user"})
            return True
        return False

    deadline = state.get("deadline")
    if not deadline or ensure_aware(datetime.fromisoformat(deadline)) > now:
        return False
    late = [s for s in engine.SIDES if state["picks"].get(s) is None]
    auto = dict(state.get("auto_moves") or {})
    out = [s for s in late if auto.get(s, 0) >= state.get("max_auto_moves", config.mordoboi_max_auto_moves)]
    if out:
        winner = "draw" if len(out) == 2 else engine.other_side(out[0])
        engine.finish_by(state, winner, "timeout")
        match.version += 1
        await _finish_match(db, match, state, config, winner, "timeout", quitters=set(out))
        return True
    for side in late:
        choice = engine.bot_choose(state, side, _rng(match.id, state, f"auto-{side}"))
        _record_pick(state, side, choice, auto=True)
        auto[side] = auto.get(side, 0) + 1
    state["auto_moves"] = auto
    await _resolve_and_continue(db, match, state, config, now, actor=None)
    return True


# ---------------------------------------------------------------------------
# Reads — the only path a match leaves the server
# ---------------------------------------------------------------------------

def _fighter_out(fighter: Optional[dict], name: str) -> Optional[MordoboiFighterOut]:
    if not fighter:
        return None
    return MordoboiFighterOut(
        name=name, card=MordoboiCardOut(**fighter["card"]) if fighter.get("card") else None,
        **{k: fighter[k] for k in (
            "power", "speed", "guard", "hp", "max_hp", "stamina", "max_stamina", "landed", "damage_dealt",
        )},
    )


def _exchange_out(entry: dict, viewer: str) -> MordoboiExchangeOut:
    opp = engine.other_side(viewer)
    return MordoboiExchangeOut(
        n=entry["n"], round=entry["round"], exchange=entry["exchange"],
        my_action=entry["actions"][viewer], opponent_action=entry["actions"][opp],
        my_outcome=entry["outcome"][viewer], opponent_outcome=entry["outcome"][opp],
        my_damage=entry["damage"][viewer], opponent_damage=entry["damage"][opp],
        my_hp=entry["hp"][viewer], opponent_hp=entry["hp"][opp],
        my_auto=entry.get("auto", {}).get(viewer, False), opponent_auto=entry.get("auto", {}).get(opp, False),
        round_end=bool(entry.get("round_end")), end=entry.get("end"),
    )


async def _hydrate_match(db: AsyncSession, match: MordoboiMatch, viewer_user: User) -> MordoboiMatchOut:
    state = match.server_state or {}
    viewer = "user" if viewer_user.id == match.user_id else "opponent"
    opp = engine.other_side(viewer)
    if viewer == "user":
        opponent_name, opponent_user_id = match.opponent_name, match.opponent_user_id
    else:
        creator = await db.get(User, match.user_id)
        opponent_name = creator.full_display_name() if creator else match.opponent_name
        opponent_user_id = match.user_id

    fighters = state.get("fighters") or {}
    me = fighters.get(viewer)
    them = fighters.get(opp)
    if match.status == MordoboiMatchStatus.pending_accept and viewer == "opponent":
        them = None  # the invitee doesn't see the challenger's boxer before accepting
    in_play = match.status == MordoboiMatchStatus.in_progress
    picks = state.get("picks") or {}
    my_pick = picks.get(viewer)
    can_pick = in_play and my_pick is None and me is not None and them is not None
    deadline = None
    if in_play and match.opponent_type != MordoboiOpponentType.bot and state.get("deadline"):
        deadline = ensure_aware(datetime.fromisoformat(state["deadline"]))
    result = match.result if viewer == "user" or match.result is None else _FLIP[match.result]
    return MordoboiMatchOut(
        id=match.id, version=match.version, opponent_type=match.opponent_type, opponent_name=opponent_name,
        opponent_user_id=opponent_user_id, status=match.status, viewer_side=viewer,
        difficulty=state.get("difficulty"), live=bool(state.get("live")),
        rounds=state.get("rounds", 0), exchanges_per_round=state.get("exchanges_per_round", 0),
        round=state.get("round", 1), exchange=state.get("exchange", 1),
        me=_fighter_out(me, viewer_user.full_display_name()),
        opponent=_fighter_out(them, opponent_name),
        my_pick=my_pick["action"] if my_pick else None,
        opponent_ready=in_play and picks.get(opp) is not None,
        can_pick=can_pick,
        available_actions=engine.available_actions(me) if can_pick else [],
        deadline=deadline,
        my_auto_moves=(state.get("auto_moves") or {}).get(viewer, 0), max_auto_moves=state.get("max_auto_moves", 0),
        log=[_exchange_out(e, viewer) for e in state.get("log", [])[-LOG_IN_RESPONSE:]],
        scorecards=[MordoboiScorecardOut(mine=c[viewer], opponent=c[opp]) for c in state.get("scorecards", [])],
        result=result, win_reason=match.win_reason,
        reward_coins=match.user_reward_coins if viewer == "user" else match.opponent_reward_coins,
        rating_delta=match.user_rating_delta if viewer == "user" else match.opponent_rating_delta,
        created_at=match.created_at, expires_at=match.expires_at, resolved_at=match.resolved_at,
    )


async def list_matches(db: AsyncSession, user: User) -> list[MordoboiMatchOut]:
    await _sweep(db)
    result = await db.execute(
        select(MordoboiMatch)
        .where(or_(MordoboiMatch.user_id == user.id, MordoboiMatch.opponent_user_id == user.id))
        .order_by(MordoboiMatch.created_at.desc()).limit(30)
    )
    return [await _hydrate_match(db, m, user) for m in result.scalars().all()]


async def get_match(db: AsyncSession, user: User, match_id: int) -> MordoboiMatchOut:
    await _sweep(db)
    match = await _get_match_or_404(db, match_id)
    _side_of(match, user)
    return await _hydrate_match(db, match, user)


# ---------------------------------------------------------------------------
# Matchmaking (same lazy pairing design as stratego_service)
# ---------------------------------------------------------------------------

async def start_search(db: AsyncSession, user: User) -> MordoboiQueueEntry:
    config = await get_config(db)
    _require_enabled(config)
    if await _has_active_match(db, user.id):
        raise ConflictError(_ACTIVE_MATCH_MSG)
    result = await db.execute(
        select(MordoboiQueueEntry).where(MordoboiQueueEntry.user_id == user.id)
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

    await _boxer_card(db, user)  # fails early without a card
    locked = await lock_user_for_update(db, user.id)
    _ensure_hourly_reset(locked)
    if locked.mordoboi_hourly_attempts >= config.hourly_game_limit:
        raise _hourly_limit_error(locked, config)
    db.add(locked)
    entry = MordoboiQueueEntry(user_id=user.id)
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
        select(MordoboiQueueEntry).where(MordoboiQueueEntry.user_id == user.id)
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
        select(MordoboiQueueEntry)
        .where(
            MordoboiQueueEntry.user_id != user.id,
            MordoboiQueueEntry.matched_match_id.is_(None),
            MordoboiQueueEntry.created_at > cutoff,
        )
        .order_by(MordoboiQueueEntry.created_at).limit(1)
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

    fighters: dict[str, dict] = {}
    stale: list[MordoboiQueueEntry] = []
    for entry, u, side in ((my_entry, me, "user"), (candidate, them, "opponent")):
        try:
            if await _has_active_match(db, u.id) or u.mordoboi_hourly_attempts >= config.hourly_game_limit:
                raise ConflictError("stale")
            fighters[side] = _card_fighter(await _boxer_card(db, u), config)
        except ConflictError:
            stale.append(entry)
    if stale:
        for entry in stale:
            await db.delete(entry)
        await db.commit()
        return ("not_searching" if my_entry in stale else "searching"), None

    me.mordoboi_hourly_attempts += 1
    them.mordoboi_hourly_attempts += 1
    db.add(me)
    db.add(them)
    # Both were searching a moment ago — box it live (short deadlines).
    state = _new_state(config, fighters["user"], fighters["opponent"])
    state["live"] = True
    _start_deadline(state, config)
    match = MordoboiMatch(
        user_id=me.id, opponent_user_id=them.id, opponent_name=them.full_display_name(),
        opponent_type=MordoboiOpponentType.online, status=MordoboiMatchStatus.in_progress, server_state=state,
    )
    db.add(match)
    await db.flush()
    candidate.matched_match_id = match.id
    db.add(candidate)
    await db.delete(my_entry)
    await notify(
        db, them.id, NotificationType.mordoboi_your_turn,
        "Соперник найден!", "Начался бой в «Мордобое» — выходи на ринг.", RELATED, match.id,
    )
    await db.commit()
    return "matched", match.id


async def cancel_search(db: AsyncSession, user: User) -> None:
    result = await db.execute(
        select(MordoboiQueueEntry).where(MordoboiQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Ты не ищешь соперника")
    if entry.matched_match_id is not None:
        raise ConflictError("Соперник уже найден — бой начинается")
    await db.delete(entry)
    await db.commit()
