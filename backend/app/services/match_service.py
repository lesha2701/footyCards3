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
    MatchActionRequest,
    MatchOut,
    StartMatchRequest,
)
from app.schemas.lineup import LineupOut
from app.schemas.ranking import RankingMetric
from app.services import ranking_service, task_service
from app.services.game_config_service import get_config
from app.services.lineup_service import TACTIC_MULTIPLIERS, get_active_lineup, split_strength
from app.services.match_situations import (
    ATTACK_SITUATIONS_BY_ID,
    ATTACK_SITUATIONS_BY_SHOT_TYPE,
    DEFENSE_SITUATIONS_BY_ID,
    DEFENSE_SITUATIONS_BY_SHOT_TYPE,
)
from app.services.wallet_service import credit_coins, lock_user_for_update

BOT_NAMES = [
    "ФК Северный Ветер", "Стальные Орлы", "Городские Тигры", "Речные Волки", "Атлетико Резерв",
    "Юнайтед Роботс", "ФК Комета", "Гранит Юнайтед", "Южный Роверс", "Молния СК",
]

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


def _synthesize_bot_ratings(
    user_fwd: int, user_def: int, user_gk: int, opponent_strength: int, user_strength: int
) -> tuple[int, int, int]:
    """Bots have no real lineup to read positional ratings from — reuse the
    same strength ratio `_bot_strength()` already computed (which encodes the
    difficulty multiplier + jitter) and apply it to the user's own real
    averages instead of inventing a new scale-conversion constant."""
    ratio = opponent_strength / user_strength if user_strength else 1.0

    def clamp(rating: float) -> int:
        return max(58, min(99, round(rating * ratio)))

    return clamp(user_fwd), clamp(user_def), clamp(user_gk)


def _lerp_chance(rating: int, low: float, high: float) -> float:
    r = max(58, min(99, rating))
    return high - (r - 58) / (99 - 58) * (high - low)


def _lerp_chance_positive(rating: int, low: float, high: float) -> float:
    """Same clamp/interpolation as `_lerp_chance`, but for stats where a
    HIGHER rating means a HIGHER chance — e.g. a keeper's save chance —
    rather than a lower one (miss/foul/fail chances all use `_lerp_chance`)."""
    r = max(58, min(99, rating))
    return low + (r - 58) / (99 - 58) * (high - low)


def _clamp_rating(rating: float) -> int:
    return max(58, min(99, round(rating)))


def _pick_actor(
    lineup: LineupOut, category: str, preferred_positions: tuple, exclude_ids: tuple[int, ...] = ()
) -> dict:
    cards = [s.card for s in lineup.slots if s.category == category and s.card and s.card.id not in exclude_ids]
    pool = [c for c in cards if c.player.position in preferred_positions] or cards
    if not pool:
        # Graceful fallback — squad has nobody in that exact category/position
        # combo (e.g. a tactic with no natural CAM); any outfield player can
        # still stand in rather than the moment failing to generate.
        pool = [s.card for s in lineup.slots if s.category != "GK" and s.card and s.card.id not in exclude_ids]
    card = random.choice(pool)
    return {
        "user_card_id": card.id,
        "player_id": card.player.id,
        "name": card.player.display_name,
        "rating": card.player.rating,
        "position": card.player.position.value,
    }


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
    "pass_failed": [
        ("❌ Пас твоей команды не находит адресата — атака сорвана", "❌ Пас {them} не находит адресата — атака сорвана"),
        ("❌ Неточная передача — твоя атака прерывается", "❌ Неточная передача {them} — атака прерывается"),
    ],
    # Always narrated from the "opponent" branch in practice — Tackle is only
    # offered while the user is defending, i.e. `team == "opponent"`.
    "tackle_won": [
        ("🛡️ Защитник {them} чисто отбирает мяч в подкате!", "🛡️ Точный подкат — твой защитник чисто выигрывает мяч!"),
        ("🛡️ {them} успевает выиграть мяч в подкате без фола!", "🛡️ Твой защитник вовремя подключается и забирает мяч без фола!"),
    ],
    "foul_stopped": [
        ("🟨 Фол защитника {them} останавливает вашу атаку", "🟨 Фол в подкате останавливает атаку — но без реальной угрозы воротам"),
        ("🟨 Судья фиксирует фол {them} — атака прервана", "🟨 Судья фиксирует фол твоего защитника — атака прервана вдали от штрафной"),
    ],
}


def _describe_event(event_type: str, team: str, opponent_name: str) -> str:
    mine_text, opponent_text = random.choice(_EVENT_DESCRIPTIONS[event_type])
    text = mine_text if team == "user" else opponent_text
    return text.format(them=opponent_name)


def _build_shot_moment(minute: int, team: str, shot_type: str, lineup: LineupOut, opponent_name: str) -> dict:
    moment = {"minute": minute, "kind": "shot", "team": team, "shot_type": shot_type}

    if shot_type == "empty_net":
        if team == "user":
            moment.update(
                situation_kind="breakaway_user", situation_id=None, actors={},
                description="Пустые ворота! Не отправь мяч в трибуны.", actions=["strike"],
            )
        else:
            moment.update(situation_kind="breakaway_opponent", situation_id=None, actors={}, description="", actions=[])
        return moment

    if team == "user":
        situation = random.choice(ATTACK_SITUATIONS_BY_SHOT_TYPE[shot_type])
        shooter = _pick_actor(lineup, situation.shooter_category, situation.shooter_positions)
        pass_target = _pick_actor(
            lineup, situation.pass_target_category, situation.pass_target_positions,
            exclude_ids=(shooter["user_card_id"],),
        )
        description = situation.template.format(shooter=shooter["name"], pass_target=pass_target["name"])
        moment.update(
            situation_kind="attack", situation_id=situation.id,
            actors={"shooter": shooter, "pass_target": pass_target},
            description=description, actions=["shoot", "pass"],
        )
    else:
        situation = random.choice(DEFENSE_SITUATIONS_BY_SHOT_TYPE[shot_type])
        defender = _pick_actor(lineup, situation.defender_category, situation.defender_positions)
        description = situation.template.format(defender=defender["name"], them=opponent_name)
        moment.update(
            situation_kind="defense", situation_id=situation.id, actors={"defender": defender},
            description=description, actions=["tackle", "block", "keeper"],
        )
    return moment


def _generate_moment_queue(
    user_attack: int, opponent_attack: int, config: GameConfig, lineup: LineupOut, opponent_name: str
) -> list[dict]:
    """Decides *what* happens and *when* — minute, kind (flavor/shot), team,
    and (for shots) the full situation/actors/description. Outcome rolls are
    deferred to resolution time; only identity + narration are baked in now,
    so resolution never has to trust client-supplied actor identity."""
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
            moments.append(_build_shot_moment(minute, team, shot_type, lineup, opponent_name))
        else:
            moments.append({"minute": minute, "kind": "flavor", "event_type": kind, "team": team})
    return moments


def _is_interactive(moment: dict) -> bool:
    # The only non-interactive shot is the opponent's empty-net chance
    # against the user's own goal — there's no meaningful goalkeeper choice
    # against an empty net, so it just auto-resolves via miss-chance alone.
    return moment["team"] == "user" or moment["shot_type"] != "empty_net"


def _apply_card(state: dict, user_card_id: int, is_red: bool) -> str:
    key = str(user_card_id)
    entry = state["cards"].setdefault(key, {"yellow_count": 0, "sent_off": False})
    if is_red or entry["yellow_count"] >= 1:
        entry["sent_off"] = True
        return "red"
    entry["yellow_count"] += 1
    return "yellow"


def _apply_red_card_debuff(state: dict, config: GameConfig) -> None:
    # Applied once per match — models the team playing with ten men in open
    # play as a flat aggregate effect, not a stat drop on one specific card.
    if state.get("red_card_applied"):
        return
    state["ratings"]["user_def"] = max(58, round(
        state["ratings"]["user_def"] * (1 - float(config.match_red_card_strength_penalty_pct))
    ))
    state["red_card_applied"] = True


def _resolve_shot_continuation(
    missed: bool, shot_type: str, config: GameConfig, blocker_rating: Optional[int], keeper_rating: int
) -> tuple[str, dict]:
    blocked = False
    saved = False
    if not missed and shot_type == "long_range" and blocker_rating is not None:
        blocked = random.random() < _lerp_chance(
            blocker_rating, float(config.match_defender_block_chance_min), float(config.match_defender_block_chance_max)
        )
    if not missed and not blocked:
        saved = random.random() < _lerp_chance_positive(
            keeper_rating, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max)
        )
    outcome = "shot" if missed else "blocked" if blocked else "save" if saved else "goal"
    return outcome, {"missed": missed, "blocked": blocked}


def _resolve_breakaway(moment: dict, ratings: dict, config: GameConfig, opponent_name: str) -> tuple[dict, Optional[str]]:
    team = moment["team"]
    fwd = ratings[f"{team}_fwd"]
    missed = random.random() < _lerp_chance(
        fwd, float(config.match_shot_miss_chance_min), float(config.match_shot_miss_chance_max)
    )
    outcome = "shot" if missed else "goal"
    scored_by = team if outcome == "goal" else None
    event = {
        "minute": moment["minute"], "event_type": outcome, "team": team,
        "description": _describe_event(outcome, team, opponent_name),
        "payload": {"shot_type": "empty_net", "missed": missed},
    }
    return event, scored_by


def _resolve_attack(moment: dict, action: str, state: dict, config: GameConfig, opponent_name: str) -> tuple[dict, Optional[str]]:
    ratings = state["ratings"]
    situation = ATTACK_SITUATIONS_BY_ID[moment["situation_id"]]
    shot_type = moment["shot_type"]
    shooter = moment["actors"]["shooter"]
    pass_target = moment["actors"]["pass_target"]

    if action == "shoot":
        eff_rating = _clamp_rating(shooter["rating"] + situation.bias)
        missed = random.random() < _lerp_chance(
            eff_rating, float(config.match_attack_shoot_miss_chance_min), float(config.match_attack_shoot_miss_chance_max)
        )
        outcome, extra = _resolve_shot_continuation(
            missed, shot_type, config, blocker_rating=ratings["opponent_def"], keeper_rating=ratings["opponent_gk"]
        )
        payload = {"shot_type": shot_type, "action": action, "shooter": shooter["name"], **extra}
        event = {
            "minute": moment["minute"], "event_type": outcome, "team": "user",
            "description": _describe_event(outcome, "user", opponent_name), "payload": payload,
        }
        return event, "user" if outcome == "goal" else None

    # action == "pass"
    eff_passer_rating = _clamp_rating(shooter["rating"] - situation.bias)
    pass_failed = random.random() < _lerp_chance(
        eff_passer_rating, float(config.match_pass_fail_chance_min), float(config.match_pass_fail_chance_max)
    )
    if pass_failed:
        event = {
            "minute": moment["minute"], "event_type": "pass_failed", "team": "user",
            "description": _describe_event("pass_failed", "user", opponent_name),
            "payload": {"shot_type": shot_type, "action": action, "passer": shooter["name"]},
        }
        return event, None

    missed = random.random() < _lerp_chance(
        pass_target["rating"], float(config.match_receiver_shot_miss_chance_min), float(config.match_receiver_shot_miss_chance_max)
    )
    outcome, extra = _resolve_shot_continuation(
        missed, shot_type, config, blocker_rating=ratings["opponent_def"], keeper_rating=ratings["opponent_gk"]
    )
    payload = {"shot_type": shot_type, "action": action, "shooter": pass_target["name"], "assisted_by": shooter["name"], **extra}
    event = {
        "minute": moment["minute"], "event_type": outcome, "team": "user",
        "description": _describe_event(outcome, "user", opponent_name), "payload": payload,
    }
    return event, "user" if outcome == "goal" else None


def _resolve_defense(moment: dict, action: str, state: dict, config: GameConfig, opponent_name: str) -> tuple[dict, Optional[str]]:
    ratings = state["ratings"]
    situation = DEFENSE_SITUATIONS_BY_ID[moment["situation_id"]]
    shot_type = moment["shot_type"]
    defender = moment["actors"]["defender"]

    if action == "tackle":
        foul = random.random() < _lerp_chance(
            defender["rating"], float(config.match_tackle_foul_chance_min), float(config.match_tackle_foul_chance_max)
        )
        if not foul:
            event = {
                "minute": moment["minute"], "event_type": "tackle_won", "team": "opponent",
                "description": _describe_event("tackle_won", "opponent", opponent_name),
                "payload": {"shot_type": shot_type, "action": action, "defender": defender["name"]},
            }
            return event, None

        is_red = random.random() < _lerp_chance(
            defender["rating"], float(config.match_tackle_red_chance_min), float(config.match_tackle_red_chance_max)
        )
        card = _apply_card(state, defender["user_card_id"], is_red)
        if card == "red":
            _apply_red_card_debuff(state, config)

        if "box" in situation.tags:
            eff_gk = _clamp_rating(ratings["user_gk"] - config.match_penalty_gk_rating_penalty)
            saved = random.random() < _lerp_chance_positive(
                eff_gk, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max)
            )
            outcome = "save" if saved else "goal"
            prefix = "🟥 Красная карточка, пенальти! " if card == "red" else "🟨 Жёлтая карточка, пенальти! "
            event = {
                "minute": moment["minute"], "event_type": outcome, "team": "opponent",
                "description": prefix + _describe_event(outcome, "opponent", opponent_name),
                "payload": {
                    "shot_type": shot_type, "action": action, "defender": defender["name"],
                    "card": card, "is_penalty": True,
                },
            }
            return event, "opponent" if outcome == "goal" else None

        prefix = "🟥 Красная карточка! " if card == "red" else "🟨 Жёлтая карточка. "
        event = {
            "minute": moment["minute"], "event_type": "foul_stopped", "team": "opponent",
            "description": prefix + _describe_event("foul_stopped", "opponent", opponent_name),
            "payload": {
                "shot_type": shot_type, "action": action, "defender": defender["name"],
                "card": card, "is_penalty": False,
            },
        }
        return event, None

    if action == "block":
        fail = random.random() < _lerp_chance(
            defender["rating"], float(config.match_block_fail_chance_min), float(config.match_block_fail_chance_max)
        )
        if not fail:
            event = {
                "minute": moment["minute"], "event_type": "blocked", "team": "opponent",
                "description": _describe_event("blocked", "opponent", opponent_name),
                "payload": {"shot_type": shot_type, "action": action, "defender": defender["name"], "missed": False, "blocked": True},
            }
            return event, None
        missed = random.random() < _lerp_chance(
            ratings["opponent_fwd"], float(config.match_shot_miss_chance_min), float(config.match_shot_miss_chance_max)
        )
        outcome, extra = _resolve_shot_continuation(
            missed, shot_type, config, blocker_rating=None, keeper_rating=ratings["user_gk"]
        )
        event = {
            "minute": moment["minute"], "event_type": outcome, "team": "opponent",
            "description": _describe_event(outcome, "opponent", opponent_name),
            "payload": {"shot_type": shot_type, "action": action, "defender": defender["name"], **extra},
        }
        return event, "opponent" if outcome == "goal" else None

    # action == "keeper"
    missed = random.random() < _lerp_chance(
        ratings["opponent_fwd"], float(config.match_shot_miss_chance_min), float(config.match_shot_miss_chance_max)
    )
    outcome, extra = _resolve_shot_continuation(
        missed, shot_type, config, blocker_rating=None, keeper_rating=ratings["user_gk"]
    )
    event = {
        "minute": moment["minute"], "event_type": outcome, "team": "opponent",
        "description": _describe_event(outcome, "opponent", opponent_name),
        "payload": {"shot_type": shot_type, "action": action, "defender": defender["name"], **extra},
    }
    return event, "opponent" if outcome == "goal" else None


def _resolve_action(moment: dict, action: str, state: dict, config: GameConfig, opponent_name: str) -> tuple[dict, Optional[str]]:
    situation_kind = moment["situation_kind"]
    if situation_kind.startswith("breakaway"):
        return _resolve_breakaway(moment, state["ratings"], config, opponent_name)
    if situation_kind == "attack":
        return _resolve_attack(moment, action, state, config, opponent_name)
    return _resolve_defense(moment, action, state, config, opponent_name)


def _advance(state: dict, config: GameConfig, opponent_name: str) -> list[dict]:
    """Auto-resolves flavor events (and the opponent's empty-net-vs-us case)
    from `next_index` onward, stopping as soon as an interactive shot is
    reached — that shot becomes `Match.pending_moment`."""
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
        event, scored_by = _resolve_breakaway(moment, state["ratings"], config, opponent_name)
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
        if opponent_score == 0:
            locked_user.arena_clean_sheet_wins += 1
            await task_service.evaluate_metric_progress(
                db, locked_user, "arena_clean_sheet_wins", locked_user.arena_clean_sheet_wins
            )
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
    user_gk = _category_avg(lineup, "GK")

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
        opponent_gk = _category_avg(opponent_lineup, "GK")
    else:
        opponent_fwd, opponent_def, opponent_gk = _synthesize_bot_ratings(
            user_fwd, user_def, user_gk, opponent_strength, user_strength
        )

    state = {
        "moments": _generate_moment_queue(user_attack, opponent_attack, config, lineup, opponent_name),
        "next_index": 0,
        "user_score": 0,
        "opponent_score": 0,
        "ratings": {
            "user_fwd": user_fwd, "user_def": user_def, "user_gk": user_gk,
            "opponent_fwd": opponent_fwd, "opponent_def": opponent_def, "opponent_gk": opponent_gk,
        },
        "cards": {},
        "red_card_applied": False,
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
    lineup_countries = [slot.card.player.country for slot in lineup.slots if slot.card]
    await task_service.evaluate_match_same_country(db, locked_user, lineup_countries)

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


async def resolve_action(db: AsyncSession, user: User, match_id: int, payload: MatchActionRequest) -> MatchOut:
    config = await get_config(db)
    match = await _lock_match(db, user.id, match_id)

    state = dict(match.server_state)
    moments = state["moments"]
    i = state["next_index"]
    if i >= len(moments) or moments[i]["kind"] != "shot" or not _is_interactive(moments[i]):
        raise ConflictError("No pending action for this match")
    pending = moments[i]

    if payload.expected_seq is not None and payload.expected_seq != i:
        raise ConflictError("Stale action request; the pending moment has already moved on")

    if payload.action not in pending["actions"]:
        raise ConflictError(f"Action '{payload.action}' is not available for this moment")

    event, scored_by = _resolve_action(pending, payload.action, state, config, match.opponent_name)
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
    result = await db.execute(
        select(User).where(User.is_admin.is_(False)).order_by(User.arena_rating.desc()).limit(limit)
    )
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
