import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.enums import MatchDifficulty, MatchResult, MatchStatus, TransactionType
from app.models.game_config import GameConfig
from app.models.match import Match, MatchEvent
from app.models.user import User
from app.schemas.match import (
    ArenaLeaderboardEntry,
    ArenaStatsOut,
    MatchOut,
    ShootRequest,
    StartMatchRequest,
)
from app.schemas.lineup import LineupOut
from app.schemas.ranking import RankingMetric
from app.services import ranking_service, task_service
from app.services.game_config_service import get_config
from app.services.lineup_service import TACTIC_MULTIPLIERS, get_active_lineup, split_strength
from app.services.wallet_service import credit_coins, lock_user_for_update

BOT_NAMES = [
    "ФК Северный Ветер", "Стальные Орлы", "Городские Тигры", "Речные Волки", "Атлетико Резерв",
    "Юнайтед Роботс", "ФК Комета", "Гранит Юнайтед", "Южный Роверс", "Молния СК",
]

DIRECTIONS = ("left", "center", "right")
SHOT_TYPES = ("in_box", "long_range", "empty_net")

# (flavor event_type, weight) — narrated automatically, never interactive.
_FLAVOR_WEIGHTS: list[tuple[str, int]] = [
    ("corner", 9),
    ("yellow_card", 5),
    ("red_card", 1),
    ("offside", 6),
    ("possession", 20),
]
# Reuses the old goal(7)+shot(10)+save(9) combined weight so the overall
# frequency of "a team gets a scoring chance" per moment is unchanged from
# before this rework — only what happens *within* that chance is now
# interactive and type-differentiated (in_box/long_range/empty_net).
_SHOT_CHANCE_WEIGHT = 26


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.match_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.match_hourly_attempts = 0
        user.match_hour_started_at = now
        db.add(user)


def _bot_strength(user_strength: int, difficulty: MatchDifficulty, difficulty_multiplier: dict) -> int:
    multiplier = difficulty_multiplier[difficulty]
    jitter = random.uniform(-0.05, 0.05)
    return max(1, round(user_strength * multiplier * (1 + jitter)))


def _with_jitter(strength: int) -> int:
    return max(1, round(strength * (1 + random.uniform(-0.05, 0.05))))


def _category_avg(lineup: LineupOut, category: str) -> int:
    ratings = [slot.card.player.rating for slot in lineup.slots if slot.category == category and slot.card]
    return round(sum(ratings) / len(ratings)) if ratings else 70


def _synthesize_bot_ratings(user_fwd: int, user_def: int, opponent_strength: int, user_strength: int) -> tuple[int, int]:
    """Bots have no real lineup to read positional ratings from — reuse the
    same strength ratio `_bot_strength()` already computed (which encodes the
    difficulty multiplier + jitter) and apply it to the user's own real
    averages instead of inventing a new scale-conversion constant."""
    ratio = opponent_strength / user_strength if user_strength else 1.0

    def clamp(rating: float) -> int:
        return max(58, min(99, round(rating * ratio)))

    return clamp(user_fwd), clamp(user_def)


def _lerp_chance(rating: int, low: float, high: float) -> float:
    r = max(58, min(99, rating))
    return high - (r - 58) / (99 - 58) * (high - low)


# Each event type has several (mine, opponent) phrasing pairs — a random one
# is picked per event so the commentary doesn't repeat the same line every
# time a goal/save/etc. happens, closer to a real match's varied commentary.
# `{them}` is substituted with the opponent's display name where present.
_EVENT_DESCRIPTIONS: dict[str, list[tuple[str, str]]] = {
    "goal": [
        ("⚽ Гол! Забивает твоя команда!", "⚽ Гол! Забивает {them}!"),
        ("⚽ ГОЛ! Красивый удар — твоя команда открывает счёт!", "⚽ ГОЛ! {them} наказывает за ошибку в обороне!"),
        ("⚽ Есть! Мяч влетает в сетку — гол твоей команды!", "⚽ Есть! Мяч влетает в сетку — гол {them}!"),
        ("⚽ Точный удар! Вратарь бессилен — гол твоей команды!", "⚽ Точный удар! Твой вратарь бессилен — гол {them}!"),
        ("⚽ Отличная комбинация — и гол твоей команды!", "⚽ Отличная комбинация — и гол {them}!"),
    ],
    "shot": [
        ("🎯 Твоя команда бьёт мимо ворот", "🎯 {them} бьёт мимо ворот"),
        ("🎯 Неточно! Мяч твоей команды уходит выше перекладины", "🎯 Неточно! Мяч {them} уходит выше перекладины"),
        ("🎯 Мимо! Удар твоей команды уходит за пределы поля", "🎯 Мимо! Удар {them} уходит за пределы поля"),
        ("🎯 Не повезло — твоя команда попадает в штангу", "🎯 Не повезло — {them} попадает в штангу"),
    ],
    # A save happens at the goal of the team NOT in possession, so the
    # keeper belongs to the *other* side from `team`.
    "save": [
        ("🧤 Вратарь {them} спасает!", "🧤 Твой вратарь спасает!"),
        ("🧤 Отличный сейв! Вратарь {them} тащит мёртвый мяч!", "🧤 Отличный сейв! Твой вратарь тащит мёртвый мяч!"),
        ("🧤 Вратарь {them} в прыжке переводит мяч на угловой!", "🧤 Твой вратарь в прыжке переводит мяч на угловой!"),
    ],
    "blocked": [
        ("🛡️ Защитник {them} блокирует удар твоей команды!", "🛡️ Твой защитник блокирует удар {them}!"),
        ("🛡️ Заблокировано! Защита {them} успевает в подкате!", "🛡️ Заблокировано! Твоя защита успевает в подкате!"),
        ("🛡️ Мяч срезается от защитника {them} на угловой!", "🛡️ Мяч срезается от твоего защитника на угловой!"),
    ],
    "corner": [
        ("🚩 Угловой у твоей команды", "🚩 Угловой у {them}"),
        ("🚩 Мяч отправляется на угловой в пользу твоей команды", "🚩 Мяч отправляется на угловой в пользу {them}"),
    ],
    "yellow_card": [
        ("🟨 Жёлтая карточка твоей команде", "🟨 Жёлтая карточка сопернику ({them})"),
        ("🟨 Судья показывает жёлтую твоему игроку за грубый фол", "🟨 Судья показывает жёлтую игроку {them} за грубый фол"),
    ],
    "red_card": [
        ("🟥 Красная карточка твоей команде!", "🟥 Красная карточка сопернику ({them})!"),
        ("🟥 Прямая красная! Твоя команда остаётся в меньшинстве!", "🟥 Прямая красная! {them} остаётся в меньшинстве!"),
    ],
    "offside": [
        ("🚫 Офсайд у твоей команды", "🚫 Офсайд у {them}"),
        ("🚫 Флаг поднят — офсайд у твоей команды", "🚫 Флаг поднят — офсайд у {them}"),
    ],
    "possession": [
        ("⚽ Мяч контролирует твоя команда", "⚽ Мяч контролирует {them}"),
        ("⚽ Твоя команда уверенно держит мяч", "⚽ {them} уверенно держит мяч"),
    ],
}


def _describe_event(event_type: str, team: str, opponent_name: str) -> str:
    mine_text, opponent_text = random.choice(_EVENT_DESCRIPTIONS[event_type])
    text = mine_text if team == "user" else opponent_text
    return text.format(them=opponent_name)


def _generate_moment_queue(user_attack: int, opponent_attack: int, config: GameConfig) -> list[dict]:
    """Decides *what* happens and *when* — minute, kind (flavor/shot), team,
    and (for shots) shot_type. Outcome rolls are deferred to resolution time."""
    total_attack = user_attack + opponent_attack
    user_attack_prob = user_attack / total_attack if total_attack else 0.5

    num_chances = random.randint(14, 22)
    minutes = sorted(random.sample(range(1, 90), num_chances))

    kinds = [t for t, _ in _FLAVOR_WEIGHTS] + ["shot_chance"]
    weights = [w for _, w in _FLAVOR_WEIGHTS] + [_SHOT_CHANCE_WEIGHT]

    shot_weights = [
        config.match_shot_type_in_box_weight,
        config.match_shot_type_long_range_weight,
        config.match_shot_type_empty_net_weight,
    ]

    moments: list[dict] = []
    for minute in minutes:
        team = "user" if random.random() < user_attack_prob else "opponent"
        kind = random.choices(kinds, weights=weights, k=1)[0]
        if kind == "shot_chance":
            shot_type = random.choices(list(SHOT_TYPES), weights=shot_weights, k=1)[0]
            moments.append({"minute": minute, "kind": "shot", "team": team, "shot_type": shot_type})
        else:
            moments.append({"minute": minute, "kind": "flavor", "event_type": kind, "team": team})
    return moments


def _is_interactive(moment: dict) -> bool:
    # The only non-interactive shot is the opponent's empty-net chance
    # against the user's own goal — there's no meaningful goalkeeper choice
    # against an empty net, so it just auto-resolves via miss-chance alone.
    return moment["team"] == "user" or moment["shot_type"] != "empty_net"


def _resolve_shot(
    moment: dict, ratings: dict, config: GameConfig, opponent_name: str, direction: Optional[str]
) -> tuple[dict, Optional[str]]:
    attacker = moment["team"]
    defender = "opponent" if attacker == "user" else "user"
    shot_type = moment["shot_type"]

    fwd = ratings[f"{attacker}_fwd"]
    missed = random.random() < _lerp_chance(
        fwd, float(config.match_shot_miss_chance_min), float(config.match_shot_miss_chance_max)
    )

    blocked = False
    gk_saved = False
    resolved_shot_dir: Optional[str] = None
    resolved_gk_dir: Optional[str] = None

    if not missed and shot_type == "long_range":
        deff = ratings[f"{defender}_def"]
        blocked = random.random() < _lerp_chance(
            deff, float(config.match_defender_block_chance_min), float(config.match_defender_block_chance_max)
        )

    if not missed and not blocked and shot_type in ("in_box", "long_range"):
        if attacker == "user":
            resolved_shot_dir, resolved_gk_dir = direction, random.choice(DIRECTIONS)
        else:
            resolved_shot_dir, resolved_gk_dir = random.choice(DIRECTIONS), direction
        gk_saved = resolved_shot_dir == resolved_gk_dir

    if missed:
        outcome = "shot"
    elif blocked:
        outcome = "blocked"
    elif shot_type in ("in_box", "long_range") and gk_saved:
        outcome = "save"
    else:
        outcome = "goal"

    scored_by = attacker if outcome == "goal" else None
    payload = {
        "shot_type": shot_type,
        "direction": direction,
        "resolved_shot_direction": resolved_shot_dir,
        "resolved_gk_direction": resolved_gk_dir,
        "missed": missed,
        "blocked": blocked,
    }
    event = {
        "minute": moment["minute"],
        "event_type": outcome,
        "team": attacker,
        "description": _describe_event(outcome, attacker, opponent_name),
        "payload": payload,
    }
    return event, scored_by


def _advance(state: dict, config: GameConfig, opponent_name: str) -> list[dict]:
    """Auto-resolves flavor events (and the opponent's empty-net-vs-us case)
    from `next_index` onward, stopping as soon as an interactive shot is
    reached — that shot becomes `Match.pending_shot`."""
    events: list[dict] = []
    moments = state["moments"]
    i = state["next_index"]
    while i < len(moments):
        moment = moments[i]
        if moment["kind"] == "flavor":
            events.append(
                {
                    "minute": moment["minute"],
                    "event_type": moment["event_type"],
                    "team": moment["team"],
                    "description": _describe_event(moment["event_type"], moment["team"], opponent_name),
                    "payload": None,
                }
            )
            i += 1
            continue
        if _is_interactive(moment):
            break
        event, scored_by = _resolve_shot(moment, state["ratings"], config, opponent_name, None)
        events.append(event)
        if scored_by:
            state[f"{scored_by}_score"] += 1
        i += 1
    state["next_index"] = i
    return events


def _add_events(db: AsyncSession, match: Match, events: list[dict]) -> None:
    # Adds MatchEvent rows directly via match_id rather than appending to
    # `match.events` — that relationship is lazy and touching it here (outside
    # an already-awaited load) would trigger an async lazy-load error.
    for e in events:
        db.add(
            MatchEvent(
                match_id=match.id, minute=e["minute"], event_type=e["event_type"], team=e["team"],
                description=e["description"], payload=e["payload"],
            )
        )


async def _lock_match(db: AsyncSession, user_id: int, match_id: int) -> Match:
    result = await db.execute(
        select(Match).where(Match.id == match_id).with_for_update().execution_options(populate_existing=True)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise NotFoundError("Match not found")
    if match.user_id != user_id:
        raise ForbiddenError("This match does not belong to you")
    if match.status != MatchStatus.in_progress:
        raise ConflictError("This match has already finished")
    return match


async def _finalize_match(db: AsyncSession, user: User, match: Match, state: dict, config: GameConfig) -> None:
    locked_user = await lock_user_for_update(db, user.id)
    user_score, opponent_score = state["user_score"], state["opponent_score"]
    locked_user.goals_for += user_score
    locked_user.goals_against += opponent_score

    if user_score > opponent_score:
        result, rating_delta = MatchResult.win, 3
        locked_user.matches_won += 1
    elif user_score < opponent_score:
        result, rating_delta = MatchResult.loss, -1
        locked_user.matches_lost += 1
    else:
        result, rating_delta = MatchResult.draw, 1
        locked_user.matches_drawn += 1
    locked_user.arena_rating = max(0, locked_user.arena_rating + rating_delta)

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
    reward = 0 if locked_user.game_rewards_blocked else round(
        reward_base[result] * difficulty_multiplier[match.difficulty] + user_score * 5
    )

    match.result = result
    match.reward_coins = reward
    match.rating_delta = rating_delta
    match.status = MatchStatus.finished
    db.add(match)

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.match_reward,
            f"Награда за матч Card Arena ({result.value})", related_object_type="match", related_object_id=match.id,
        )
    await db.commit()


async def start_match(db: AsyncSession, user: User, payload: StartMatchRequest) -> MatchOut:
    config = await get_config(db)
    difficulty_multiplier = {
        MatchDifficulty.easy: float(config.difficulty_easy_multiplier),
        MatchDifficulty.medium: float(config.difficulty_medium_multiplier),
        MatchDifficulty.hard: float(config.difficulty_hard_multiplier),
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

    user_strength = _with_jitter(lineup.team_strength)
    user_attack, user_defense = split_strength(user_strength, lineup.tactic)
    user_fwd, user_def = _category_avg(lineup, "FWD"), _category_avg(lineup, "DEF")

    opponent_result = await db.execute(
        select(User)
        .where(User.id != locked_user.id, User.is_banned.is_(False))
        .order_by(func.random())
        .limit(1)
    )
    opponent_user = opponent_result.scalar_one_or_none()

    opponent_name = random.choice(BOT_NAMES)
    opponent_tactic = random.choice(list(TACTIC_MULTIPLIERS))
    opponent_lineup: Optional[LineupOut] = None
    if opponent_user is not None:
        candidate_lineup = await get_active_lineup(db, opponent_user)
        if candidate_lineup.is_complete:
            opponent_lineup = candidate_lineup
            opponent_strength = _with_jitter(candidate_lineup.team_strength)
            opponent_tactic = candidate_lineup.tactic
            opponent_name = opponent_user.full_display_name()
        else:
            opponent_strength = _bot_strength(user_strength, payload.difficulty, difficulty_multiplier)
    else:
        opponent_strength = _bot_strength(user_strength, payload.difficulty, difficulty_multiplier)
    opponent_attack, opponent_defense = split_strength(opponent_strength, opponent_tactic)

    if opponent_lineup is not None:
        opponent_fwd, opponent_def = _category_avg(opponent_lineup, "FWD"), _category_avg(opponent_lineup, "DEF")
    else:
        opponent_fwd, opponent_def = _synthesize_bot_ratings(user_fwd, user_def, opponent_strength, user_strength)

    state = {
        "moments": _generate_moment_queue(user_attack, opponent_attack, config),
        "next_index": 0,
        "user_score": 0,
        "opponent_score": 0,
        "ratings": {
            "user_fwd": user_fwd, "user_def": user_def,
            "opponent_fwd": opponent_fwd, "opponent_def": opponent_def,
        },
    }

    match = Match(
        user_id=locked_user.id,
        opponent_user_id=opponent_user.id if opponent_user else None,
        opponent_name=opponent_name,
        difficulty=payload.difficulty,
        user_team_strength=user_strength,
        opponent_team_strength=opponent_strength,
        user_score=0,
        opponent_score=0,
        status=MatchStatus.in_progress,
        result=None,
        server_state=state,
        lineup_id=lineup.id,
    )
    db.add(match)
    await db.flush()

    events = _advance(state, config, match.opponent_name)
    match.server_state = state
    # `state` is the same dict object already assigned to `match.server_state`
    # above (and already flushed once) — in-place mutation of it by `_advance`
    # is invisible to SQLAlchemy's change tracking, and reassigning the same
    # object back doesn't reliably re-mark it dirty either. flag_modified()
    # forces the column into the next UPDATE regardless of object identity.
    flag_modified(match, "server_state")
    match.user_score, match.opponent_score = state["user_score"], state["opponent_score"]
    _add_events(db, match, events)

    lineup_ratings = [slot.card.player.rating for slot in lineup.slots if slot.card]
    await task_service.evaluate_match_min_rating(db, locked_user, lineup_ratings)

    if state["next_index"] >= len(state["moments"]):
        # Rare edge case: the randomly-generated queue drew zero shot chances
        # at all. Finalize immediately rather than leaving the match stuck
        # in_progress forever with nothing left to advance it.
        await _finalize_match(db, locked_user, match, state, config)
    else:
        db.add(match)
        await db.commit()

    await db.refresh(match, attribute_names=["events"])
    return MatchOut.model_validate(match)


async def resolve_shot(db: AsyncSession, user: User, match_id: int, payload: ShootRequest) -> MatchOut:
    config = await get_config(db)
    match = await _lock_match(db, user.id, match_id)

    state = dict(match.server_state)
    moments = state["moments"]
    i = state["next_index"]
    if i >= len(moments) or moments[i]["kind"] != "shot" or not _is_interactive(moments[i]):
        raise ConflictError("No pending shot for this match")
    pending = moments[i]

    if payload.expected_seq is not None and payload.expected_seq != i:
        raise ConflictError("Stale shot request; the pending shot has already moved on")

    direction: Optional[str] = None
    if pending["shot_type"] != "empty_net":
        if payload.direction not in DIRECTIONS:
            raise ConflictError("A direction is required for this shot")
        direction = payload.direction

    event, scored_by = _resolve_shot(pending, state["ratings"], config, match.opponent_name, direction)
    if scored_by:
        state[f"{scored_by}_score"] += 1
    state["next_index"] = i + 1

    new_events = [event] + _advance(state, config, match.opponent_name)

    match.server_state = state
    flag_modified(match, "server_state")
    match.user_score, match.opponent_score = state["user_score"], state["opponent_score"]
    _add_events(db, match, new_events)

    if state["next_index"] < len(moments):
        db.add(match)
        await db.commit()
    else:
        await _finalize_match(db, user, match, state, config)

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
        .where(Match.user_id == user.id, Match.status == MatchStatus.finished)
        .options(joinedload(Match.events))
        .order_by(Match.created_at.desc())
        .limit(limit)
    )
    matches = result.unique().scalars().all()
    return [MatchOut.model_validate(m) for m in matches]


async def arena_stats(db: AsyncSession, user: User) -> ArenaStatsOut:
    ranking = await ranking_service.get_ranking(db, RankingMetric.arena_rating, user)
    return ArenaStatsOut(
        matches_won=user.matches_won,
        matches_drawn=user.matches_drawn,
        matches_lost=user.matches_lost,
        arena_rating=user.arena_rating,
        arena_rank=ranking.me.rank if ranking.me else None,
    )


async def arena_leaderboard(db: AsyncSession, limit: int = 20) -> list[ArenaLeaderboardEntry]:
    result = await db.execute(select(User).order_by(User.arena_rating.desc()).limit(limit))
    users = result.scalars().all()
    return [
        ArenaLeaderboardEntry(
            user_id=u.id, display_name=u.full_display_name(), avatar_url=u.avatar_url,
            arena_rating=u.arena_rating, matches_won=u.matches_won, matches_drawn=u.matches_drawn,
            matches_lost=u.matches_lost, goal_difference=u.goals_for - u.goals_against,
            points=u.matches_won * 3 + u.matches_drawn,
        )
        for u in users
    ]
