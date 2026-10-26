import json
import math
import random
from types import SimpleNamespace
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.enums import BingoGoalType, MatchDifficulty, MatchResult, MatchStatus, TransactionType
from app.models.game_config import GameConfig
from app.models.match import Match, MatchEvent
from app.models.user import User
from app.schemas.match import (
    ArenaDivisionOut,
    ArenaLeaderboardEntry,
    ArenaLineCompareOut,
    ArenaPreviewOut,
    ArenaStatsOut,
    MatchActionRequest,
    MatchOut,
    StartMatchRequest,
)
from app.schemas.lineup import LineupOut
from app.services import (
    arena_ladder_service,
    arena_tactics,
    bingo_service,
    chemistry_service,
    league_service,
    path_match_service,
    task_service,
)
from app.services.card_skill_effects import SNAPSHOT_VERSION, effect_for_card, effect_of, skill_roll
from app.services.game_config_service import get_config
from app.services.lineup_service import get_active_lineup, split_strength
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
    # Neighbour-link chemistry (only present while GameConfig.chemistry_enabled
    # is on) adds each card's own bonus to its match rating here as well, so
    # the moment rolls see the same chemistry the team strength does; the
    # result is frozen into server_state["ratings"] at kickoff. getattr: FUT
    # Draft passes its own lineup stand-in (no chemistry, no slot_code).
    chemistry = getattr(lineup, "chemistry", None)
    bonus = {p.slot_code: p.rating_bonus for p in chemistry.players} if chemistry is not None and chemistry.enabled else {}
    ratings = [
        chemistry_service.boosted_rating(slot.card.player.rating, bonus.get(slot.slot_code, 0) if bonus else 0)
        for slot in lineup.slots if slot.category == category and slot.card
    ]
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


def _fit_goal_to_score(event: dict, scored_by: str, state: dict) -> None:
    """Card Arena: a goal text saying "открывает счёт" only on the opener
    (the score is already updated for this goal); otherwise what the goal
    did to the score. No random numbers."""
    from app.services.tournament_match_engine import OPENER_PHRASE, score_phrase

    text = event.get("description") or ""
    if event.get("event_type") != "goal" or OPENER_PHRASE not in text:
        return
    other = "opponent" if scored_by == "user" else "user"
    phrase = score_phrase(state[f"{scored_by}_score"], state[f"{other}_score"])
    event["description"] = text.replace(OPENER_PHRASE, phrase)


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
    user_attack: int, opponent_attack: int, config: GameConfig, lineup: LineupOut, opponent_name: str,
    balance: Optional[dict] = None,
) -> list[dict]:
    """Decides *what* happens and *when* — minute, kind (flavor/shot), team,
    and (for shots) the full situation/actors/description. Outcome rolls are
    deferred to resolution time; only identity + narration are baked in now,
    so resolution never has to trust client-supplied actor identity.

    Card Arena passes `balance` (arena_tactics.compute_balance): the moment
    share and each side's chance frequency then follow attack vs defense.
    Without it (FUT Draft) the old linear attack share and fixed weights."""
    if balance is not None:
        user_attack_prob = float(balance["share"])
    else:
        total_attack = user_attack + opponent_attack
        user_attack_prob = user_attack / total_attack if total_attack else 0.5

    num_chances = random.randint(14, 22)
    minutes = sorted(random.sample(range(1, 90), num_chances))

    kinds = [t for t, _ in _FLAVOR_WEIGHTS] + ["shot_chance"]
    flavor_weights = [w for _, w in _FLAVOR_WEIGHTS]
    team_weights = {
        team: flavor_weights + [int(balance[f"{team}_shot_weight"]) if balance is not None else _SHOT_CHANCE_WEIGHT]
        for team in ("user", "opponent")
    }

    shot_weights = [
        config.match_shot_type_in_box_weight,
        config.match_shot_type_long_range_weight,
        config.match_shot_type_empty_net_weight,
    ]

    moments: list[dict] = []
    for minute in minutes:
        team = "user" if random.random() < user_attack_prob else "opponent"
        kind = random.choices(kinds, weights=team_weights[team], k=1)[0]
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
    missed: bool, shot_type: str, config: GameConfig, blocker_rating: Optional[int], keeper_rating: int,
    keeper_effect: Optional[dict] | list = None, notes: Optional[list] = None,
    save_pp: int = 0, save_player: Optional[str] = None, equipment_notes: Optional[list] = None,
) -> tuple[str, dict]:
    """save_pp: the defending keeper's «Экипировка» save bonus (user side in
    Card Arena), +N pp to the save chance, capped at 98%; noted in
    `equipment_notes` only when a save roll actually happens."""
    blocked = False
    saved = False
    if not missed and shot_type == "long_range" and blocker_rating is not None:
        blocked = random.random() < _lerp_chance(
            blocker_rating, float(config.match_defender_block_chance_min), float(config.match_defender_block_chance_max)
        )
    if not missed and not blocked:
        save_base = _lerp_chance_positive(
            keeper_rating, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max)
        )
        if save_pp > 0 and save_base < _SAVE_CEILING:
            save_base = min(_SAVE_CEILING, save_base + save_pp / 100)
            if equipment_notes is not None:
                equipment_notes.append({"player": save_player, "effect": "save_pp", "bonus_pp": save_pp})
        saved, save_notes = skill_roll(
            save_base,
            [(e, 1, e.get("player")) for e in (keeper_effect if isinstance(keeper_effect, list) else [keeper_effect]) if e],
        )
        if notes is not None:
            notes.extend(save_notes)
    outcome = "shot" if missed else "blocked" if blocked else "save" if saved else "goal"
    return outcome, {"missed": missed, "blocked": blocked}


def _edge(state: dict) -> int:
    """Card Arena: rating points the strength gap adds to every user roll and
    takes from every opponent roll (frozen at kickoff; 0 for FUT Draft and
    matches started before the balance rework)."""
    return int((state.get("balance") or {}).get("edge", 0))


def _skills(state: dict) -> dict:
    # Absent/None for matches started before skills existed or while the
    # mechanic was off — every lookup below then resolves to "no effect".
    return state.get("skills") or {}


def _card_effect(state: dict, actor: dict, code: str) -> Optional[dict]:
    return effect_of(_skills(state).get("cards", {}).get(str(actor.get("user_card_id"))), code)


# «Экипировка» in Card Arena: situations where the ball carrier has to beat a
# man (clean through on the keeper, a run down the flank) — the thing's
# «обыгрыш» bonus lowers the chance his action fails there.
_DRIBBLE_TAGS = frozenset({"one_on_one", "flank"})
_NO_TAGS = SimpleNamespace(tags=())
_EQUIPMENT_FLOOR = 0.02
_SAVE_CEILING = 0.98


def _equipment_adjusted(state: dict, actor: dict, base: float, situation, *, own: str, notes: list) -> float:
    """The actor's frozen «Экипировка» boosts (state["equipment"]) applied to
    one failure chance (shot miss, pass failure, tackle foul, failed block)
    the way the tournament engine applies them: minus N percentage points,
    never below 2%. `own`: the boost of this action (shot_pp / pass_pp /
    tackle_pp); the dribble bonus adds to a shot or a pass only in
    _DRIBBLE_TAGS situations. Without boosts the chance is returned
    untouched, so the roll draws exactly as before."""
    boosts = (state.get("equipment") or {}).get(str(actor.get("user_card_id"))) or {}
    parts = []
    if boosts.get(own):
        parts.append((own, int(boosts[own])))
    if own in ("shot_pp", "pass_pp") and boosts.get("dribble_pp") and _DRIBBLE_TAGS & set(situation.tags):
        parts.append(("dribble_pp", int(boosts["dribble_pp"])))
    total = sum(pp for _, pp in parts)
    if total <= 0 or base <= _EQUIPMENT_FLOOR:
        return base
    notes.extend({"player": actor.get("name"), "effect": effect, "bonus_pp": pp} for effect, pp in parts)
    return max(_EQUIPMENT_FLOOR, base - total / 100)


def _user_save_pp(state: dict) -> tuple[int, Optional[str]]:
    """The user keeper's frozen «Экипировка» save bonus (pp) and his name."""
    gk = state.get("equipment_gk") or {}
    boosts = (state.get("equipment") or {}).get(str(gk.get("id"))) or {}
    return int(boosts.get("save_pp") or 0), gk.get("name")


def _with_equipment_notes(payload: dict, notes: list) -> dict:
    if notes:
        payload["equipment"] = notes
    return payload


def _keeper_effect(state: dict, side: str, code: str = "reflexes") -> Optional[dict]:
    return effect_of(_skills(state).get(f"{side}_gk"), code)


def _keeper_effects(state: dict, side: str, one_on_one: bool) -> list:
    """Save-roll adjustments for a side's keeper: reflexes always, plus
    one_on_one when the attacker is clean through. A keeper holds a single
    skill, so at most one of these is ever active."""
    codes = ["reflexes"] + (["one_on_one"] if one_on_one else [])
    return [effect for code in codes if (effect := _keeper_effect(state, side, code))]


def _with_skill_notes(payload: dict, notes: list) -> dict:
    # Skill notes and «Академия» talent notes may share one list (a
    # talent note carries an "emoji" key); each kind gets its own key.
    talents = [n for n in notes if "emoji" in n]
    skills = [n for n in notes if "emoji" not in n]
    if skills:
        payload["skills"] = skills
    return _with_talent_notes(payload, talents)


def _with_talent_notes(payload: dict, notes: list) -> dict:
    if notes:
        payload["talents"] = payload.get("talents", []) + notes
    return payload


def _resolve_breakaway(
    moment: dict, ratings: dict, config: GameConfig, opponent_name: str, edge: int = 0,
) -> tuple[dict, Optional[str]]:
    team = moment["team"]
    fwd = ratings[f"{team}_fwd"] + (edge if team == "user" else -edge)
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

    notes: list = []
    equipment_notes: list = []
    minute = moment["minute"]
    one_on_one = "one_on_one" in situation.tags
    edge = _edge(state)
    if action == "shoot":
        # «Академия» talents act on the card's rating before the skill roll.
        shooter_rating = path_match_service.arena_actor_rating(
            state, shooter, minute, "shooter", notes, one_on_one=one_on_one,
        )
        eff_rating = _clamp_rating(shooter_rating + situation.bias + edge)
        missed, shot_notes = skill_roll(
            _equipment_adjusted(
                state, shooter,
                _lerp_chance(
                    eff_rating, float(config.match_attack_shoot_miss_chance_min), float(config.match_attack_shoot_miss_chance_max)
                ),
                situation, own="shot_pp", notes=equipment_notes,
            ),
            [(_card_effect(state, shooter, "sniper"), -1, shooter["name"])],
        )
        notes.extend(shot_notes)
        outcome, extra = _resolve_shot_continuation(
            missed, shot_type, config, blocker_rating=ratings["opponent_def"] - edge,
            keeper_rating=ratings["opponent_gk"] - edge,
            keeper_effect=_keeper_effects(state, "opponent", "one_on_one" in situation.tags), notes=notes,
        )
        payload = _with_equipment_notes(_with_skill_notes({
            "shot_type": shot_type, "action": action, "shooter": shooter["name"],
            "shooter_id": shooter.get("user_card_id"), **extra,
        }, notes), equipment_notes)
        event = {
            "minute": moment["minute"], "event_type": outcome, "team": "user",
            "description": _describe_event(outcome, "user", opponent_name), "payload": payload,
        }
        return event, "user" if outcome == "goal" else None

    # action == "pass"
    passer_rating = path_match_service.arena_actor_rating(state, shooter, minute, "passer", notes)
    eff_passer_rating = _clamp_rating(passer_rating - situation.bias + edge)
    pass_failed, pass_notes = skill_roll(
        _equipment_adjusted(
            state, shooter,
            _lerp_chance(eff_passer_rating, float(config.match_pass_fail_chance_min), float(config.match_pass_fail_chance_max)),
            situation, own="pass_pp", notes=equipment_notes,
        ),
        # A passer has one skill: playmaker on any pass, or crosser when the
        # pass is a cross/cut-back from the flank.
        [(_card_effect(state, shooter, "playmaker"), -1, shooter["name"])]
        + ([(_card_effect(state, shooter, "crosser"), -1, shooter["name"])] if "flank" in situation.tags else []),
    )
    notes.extend(pass_notes)
    if pass_failed:
        event = {
            "minute": moment["minute"], "event_type": "pass_failed", "team": "user",
            "description": _describe_event("pass_failed", "user", opponent_name),
            "payload": _with_equipment_notes(
                _with_skill_notes({"shot_type": shot_type, "action": action, "passer": shooter["name"]}, notes), equipment_notes,
            ),
        }
        return event, None

    receiver_rating = path_match_service.arena_actor_rating(
        state, pass_target, minute, "shooter", notes, one_on_one=one_on_one,
    ) + edge
    # The receiver finishes the pass: only his shot accuracy counts (the
    # «обыгрыш» was the passer's, above).
    missed, shot_notes = skill_roll(
        _equipment_adjusted(
            state, pass_target,
            _lerp_chance(
                receiver_rating, float(config.match_receiver_shot_miss_chance_min), float(config.match_receiver_shot_miss_chance_max)
            ),
            _NO_TAGS, own="shot_pp", notes=equipment_notes,
        ),
        [(_card_effect(state, pass_target, "sniper"), -1, pass_target["name"])],
    )
    notes.extend(shot_notes)
    outcome, extra = _resolve_shot_continuation(
        missed, shot_type, config, blocker_rating=ratings["opponent_def"] - edge,
        keeper_rating=ratings["opponent_gk"] - edge,
        keeper_effect=_keeper_effects(state, "opponent", "one_on_one" in situation.tags), notes=notes,
    )
    payload = _with_equipment_notes(_with_skill_notes(
        {"shot_type": shot_type, "action": action, "shooter": pass_target["name"], "assisted_by": shooter["name"],
         "shooter_id": pass_target.get("user_card_id"), "assist_id": shooter.get("user_card_id"), **extra},
        notes,
    ), equipment_notes)
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
    minute = moment["minute"]
    one_on_one = "one_on_one" in situation.tags
    talent_notes: list = []
    edge = _edge(state)

    last_line = _card_effect(state, defender, "last_line") if "breakaway" in situation.tags else None
    equipment_notes: list = []
    save_pp, save_player = _user_save_pp(state)
    if action in ("tackle", "block"):
        # The defender plays this roll himself (not the keeper's «keeper» action).
        defender_rating = path_match_service.arena_actor_rating(state, defender, minute, "defender", talent_notes) + edge
    if action == "tackle":
        foul, tackle_notes = skill_roll(
            _equipment_adjusted(
                state, defender,
                _lerp_chance(defender_rating, float(config.match_tackle_foul_chance_min), float(config.match_tackle_foul_chance_max)),
                _NO_TAGS, own="tackle_pp", notes=equipment_notes,
            ),
            [(last_line, -1, defender["name"])],
        )
        if not foul:
            event = {
                "minute": moment["minute"], "event_type": "tackle_won", "team": "opponent",
                "description": _describe_event("tackle_won", "opponent", opponent_name),
                "payload": _with_equipment_notes(_with_talent_notes(
                    _with_skill_notes({"shot_type": shot_type, "action": action, "defender": defender["name"]}, tackle_notes),
                    talent_notes,
                ), equipment_notes),
            }
            return event, None

        is_red = random.random() < _lerp_chance(
            defender_rating, float(config.match_tackle_red_chance_min), float(config.match_tackle_red_chance_max)
        )
        card = _apply_card(state, defender["user_card_id"], is_red)
        if card == "red":
            _apply_red_card_debuff(state, config)

        if "box" in situation.tags:
            keeper_bonus = path_match_service.arena_keeper_bonus(state, minute, talent_notes, penalty=True)
            eff_gk = _clamp_rating(ratings["user_gk"] + keeper_bonus + edge - config.match_penalty_gk_rating_penalty)
            keeper = _keeper_effect(state, "user")
            penalty_base = _lerp_chance_positive(
                eff_gk, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max)
            )
            if save_pp > 0 and penalty_base < _SAVE_CEILING:
                penalty_base = min(_SAVE_CEILING, penalty_base + save_pp / 100)
                equipment_notes.append({"player": save_player, "effect": "save_pp", "bonus_pp": save_pp})
            saved, save_notes = skill_roll(penalty_base, [(keeper, 1, keeper.get("player") if keeper else None)])
            outcome = "save" if saved else "goal"
            prefix = "🟥 Красная карточка, пенальти! " if card == "red" else "🟨 Жёлтая карточка, пенальти! "
            event = {
                "minute": moment["minute"], "event_type": outcome, "team": "opponent",
                "description": prefix + _describe_event(outcome, "opponent", opponent_name),
                "payload": _with_equipment_notes(_with_talent_notes(_with_skill_notes({
                    "shot_type": shot_type, "action": action, "defender": defender["name"],
                    "card": card, "is_penalty": True,
                }, save_notes), talent_notes), equipment_notes),
            }
            return event, "opponent" if outcome == "goal" else None

        prefix = "🟥 Красная карточка! " if card == "red" else "🟨 Жёлтая карточка. "
        event = {
            "minute": moment["minute"], "event_type": "foul_stopped", "team": "opponent",
            "description": prefix + _describe_event("foul_stopped", "opponent", opponent_name),
            "payload": _with_equipment_notes({
                "shot_type": shot_type, "action": action, "defender": defender["name"],
                "card": card, "is_penalty": False,
            }, equipment_notes),
        }
        return event, None

    if action == "block":
        # On a cross / corner ("aerial" situations) the block IS the defender's
        # aerial duel — the defender's own aerial_master lowers the fail chance.
        aerial = _card_effect(state, defender, "aerial_master") if "aerial" in situation.tags else None
        fail, block_notes = skill_roll(
            _equipment_adjusted(
                state, defender,
                _lerp_chance(defender_rating, float(config.match_block_fail_chance_min), float(config.match_block_fail_chance_max)),
                _NO_TAGS, own="tackle_pp", notes=equipment_notes,
            ),
            # A defender has one skill: aerial_master on crosses, last_line
            # when he's the last man against a breakaway.
            [(aerial, -1, defender["name"]), (last_line, -1, defender["name"])],
        )
        if not fail:
            event = {
                "minute": moment["minute"], "event_type": "blocked", "team": "opponent",
                "description": _describe_event("blocked", "opponent", opponent_name),
                "payload": _with_equipment_notes(_with_talent_notes(_with_skill_notes(
                    {"shot_type": shot_type, "action": action, "defender": defender["name"], "missed": False, "blocked": True},
                    block_notes,
                ), talent_notes), equipment_notes),
            }
            return event, None
        missed = random.random() < _lerp_chance(
            ratings["opponent_fwd"] - edge, float(config.match_shot_miss_chance_min), float(config.match_shot_miss_chance_max)
        )
        notes: list = []
        keeper_notes: list = []
        keeper_rating = ratings["user_gk"] + edge + path_match_service.arena_keeper_bonus(
            state, minute, keeper_notes, one_on_one=one_on_one,
        )
        outcome, extra = _resolve_shot_continuation(
            missed, shot_type, config, blocker_rating=None, keeper_rating=keeper_rating,
            keeper_effect=_keeper_effects(state, "user", "one_on_one" in situation.tags), notes=notes,
            save_pp=save_pp, save_player=save_player, equipment_notes=equipment_notes,
        )
        if outcome in ("save", "goal"):  # the keeper's talent only counts if he had a save to make
            talent_notes.extend(keeper_notes)
        event = {
            "minute": moment["minute"], "event_type": outcome, "team": "opponent",
            "description": _describe_event(outcome, "opponent", opponent_name),
            "payload": _with_equipment_notes(_with_talent_notes(
                _with_skill_notes({"shot_type": shot_type, "action": action, "defender": defender["name"], **extra}, notes),
                talent_notes,
            ), equipment_notes),
        }
        return event, "opponent" if outcome == "goal" else None

    # action == "keeper"
    missed = random.random() < _lerp_chance(
        ratings["opponent_fwd"] - edge, float(config.match_shot_miss_chance_min), float(config.match_shot_miss_chance_max)
    )
    notes = []
    keeper_notes: list = []
    keeper_rating = ratings["user_gk"] + edge + path_match_service.arena_keeper_bonus(
        state, minute, keeper_notes, one_on_one=one_on_one,
    )
    outcome, extra = _resolve_shot_continuation(
        missed, shot_type, config, blocker_rating=None, keeper_rating=keeper_rating,
        keeper_effect=_keeper_effects(state, "user", "one_on_one" in situation.tags), notes=notes,
        save_pp=save_pp, save_player=save_player, equipment_notes=equipment_notes,
    )
    if outcome in ("save", "goal"):  # the keeper's talent only counts if he had a save to make
        talent_notes.extend(keeper_notes)
    event = {
        "minute": moment["minute"], "event_type": outcome, "team": "opponent",
        "description": _describe_event(outcome, "opponent", opponent_name),
        "payload": _with_equipment_notes(_with_talent_notes(
            _with_skill_notes({"shot_type": shot_type, "action": action, "defender": defender["name"], **extra}, notes),
            talent_notes,
        ), equipment_notes),
    }
    return event, "opponent" if outcome == "goal" else None


def _resolve_action(moment: dict, action: str, state: dict, config: GameConfig, opponent_name: str) -> tuple[dict, Optional[str]]:
    situation_kind = moment["situation_kind"]
    if situation_kind.startswith("breakaway"):
        return _resolve_breakaway(moment, state["ratings"], config, opponent_name, _edge(state))
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
        event, scored_by = _resolve_breakaway(moment, state["ratings"], config, opponent_name, _edge(state))
        events.append(event)
        if scored_by:
            state[f"{scored_by}_score"] += 1
            _fit_goal_to_score(event, scored_by, state)
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


async def _finalize_match(
    db: AsyncSession, user: User, match: Match, state: dict, config: GameConfig,
    forced_result: Optional[MatchResult] = None,
) -> None:
    locked_user = await lock_user_for_update(db, user.id)
    user_score, opponent_score = state["user_score"], state["opponent_score"]
    locked_user.goals_for += user_score
    locked_user.goals_against += opponent_score

    if forced_result is not None:
        # Forfeit — always counts as a loss for the forfeiting side
        # regardless of the score so far, same rule Tactico/Penalty's
        # forfeit enforces: leaving mid-match is never a safer bet than
        # finishing it out.
        result = forced_result
    elif user_score > opponent_score:
        result = MatchResult.win
    elif user_score < opponent_score:
        result = MatchResult.loss
    else:
        result = MatchResult.draw

    rating_delta = {MatchResult.win: 3, MatchResult.loss: -1, MatchResult.draw: 1}[result]
    if result == MatchResult.win:
        locked_user.matches_won += 1
        if opponent_score == 0:
            locked_user.arena_clean_sheet_wins += 1
            await task_service.evaluate_metric_progress(
                db, locked_user, "arena_clean_sheet_wins", locked_user.arena_clean_sheet_wins
            )
    elif result == MatchResult.loss:
        locked_user.matches_lost += 1
    else:
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
    division_pct = arena_ladder_service.coin_pct(
        arena_ladder_service.division_of(locked_user.arena_points, config), config,
    )
    reward = 0 if locked_user.game_rewards_blocked else round(
        reward_base[result] * difficulty_multiplier[match.difficulty] * division_pct / 100 + user_score * 5
    )
    # «Экипировка»: coin talismans of the lineup, frozen at kickoff, on a win only.
    coins_pct = int((match.server_state or {}).get("equipment_coins_pct") or 0)
    if reward > 0 and result == MatchResult.win and coins_pct > 0:
        reward = round(reward * (100 + coins_pct) / 100)

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

    # «Академия»: experience only for a finished, rewarded match (a
    # forfeit never counts), in the same transaction as the reward.
    if forced_result is None:
        await path_match_service.arena_after_match(
            db, locked_user.id, match, state, result.value, rewarded=reward > 0, config=config,
        )

    # Divisions: a forfeit moves the ladder like any loss.
    state["ladder"] = await arena_ladder_service.apply_result(
        db, locked_user, int(state.get("opponent_points", locked_user.arena_points)), result, config,
    )
    events = (await db.execute(select(MatchEvent).where(MatchEvent.match_id == match.id))).scalars().all()
    state["report"] = build_report(match, state, list(events), result, forfeited=forced_result is not None)
    match.server_state = state
    flag_modified(match, "server_state")

    await league_service.sync_league_rewards_for_user(db, locked_user)
    await db.commit()

    # Bingo of the Week: one finished Card Arena match counts once.
    await bingo_service.increment_goal(db, BingoGoalType.arena_matches_played, 1)


_USER_CHANCE_EVENTS = {"goal", "shot", "save", "blocked", "pass_failed"}
_OPPONENT_CHANCE_EVENTS = {"goal", "shot", "save", "blocked", "tackle_won", "foul_stopped"}


def _pct_diff(a: float, b: float) -> int:
    return round(abs(a / b - 1) * 100) if b else 0


def _tilt_text(formation: str) -> str:
    attack, _defense = arena_tactics.FORMATION_SHIFT.get(formation, (0, 0))
    if attack > 0:
        return "атакующая"
    if attack < 0:
        return "оборонительная"
    return "сбалансированная"


def build_report(match: Match, state: dict, events: list, result: MatchResult, forfeited: bool) -> Optional[dict]:
    """The «Разбор матча»: chances before kickoff, both line-ups, the style
    matchup, how the chances went, and a one-line verdict with its reasons.
    None for matches started before the balance rework (no frozen balance)."""
    balance = state.get("balance")
    if not balance:
        return None
    chances = state.get("chances") or win_chances(balance["strength_ratio"])
    lines = state.get("lines") or {"user": {}, "opponent": {}}
    user_score, opponent_score = state.get("user_score", 0), state.get("opponent_score", 0)

    user_chances = sum(1 for e in events if e.team == "user" and e.event_type in _USER_CHANCE_EVENTS)
    opponent_chances = sum(1 for e in events if e.team == "opponent" and e.event_type in _OPPONENT_CHANCE_EVENTS)
    opponent_keeper_saves = sum(1 for e in events if e.team == "user" and e.event_type == "save")
    user_keeper_saves = sum(1 for e in events if e.team == "opponent" and e.event_type == "save")
    red_card = any(c.get("sent_off") for c in (state.get("cards") or {}).values())

    win_pct, loss_pct = chances["win"], chances["loss"]
    if forfeited:
        verdict = "Матч прерван — засчитано техническое поражение."
    elif result == MatchResult.win:
        verdict = (
            f"Закономерная победа фаворита (≈{win_pct}% на победу)." if win_pct >= 60
            else "Победа в равной игре." if win_pct >= 35
            else f"Сенсация! Победа при шансах всего ≈{win_pct}%."
        )
    elif result == MatchResult.draw:
        verdict = (
            f"Фаворит не дожал: ничья при ≈{win_pct}% на победу." if win_pct >= 60
            else f"Ценная ничья против фаворита (у него было ≈{loss_pct}%)." if loss_pct >= 60
            else "Ничья в равной игре."
        )
    else:
        verdict = (
            f"Обидное поражение фаворита (≈{win_pct}% на победу) — так бывает редко." if win_pct >= 60
            else "Поражение в равной игре." if loss_pct < 60
            else f"Соперник был сильнее: у него было ≈{loss_pct}% на победу."
        )

    reasons: list[str] = []
    user_strength, opponent_strength = match.user_team_strength, match.opponent_team_strength
    ratio = user_strength / opponent_strength if opponent_strength else 1.0
    if ratio >= 1.03:
        reasons.append(f"Ваш состав сильнее на {_pct_diff(user_strength, opponent_strength)}% ({user_strength} против {opponent_strength}).")
    elif ratio <= 0.97:
        reasons.append(f"Состав соперника сильнее на {_pct_diff(opponent_strength, user_strength)}% ({opponent_strength} против {user_strength}).")
    else:
        reasons.append(f"Составы почти равны ({user_strength} против {opponent_strength}).")

    if balance["matchup"] != "neutral":
        sign = "+" if balance["matchup"] == "win" else "−"
        reasons.append(
            arena_tactics.matchup_text(balance["user_style"], balance["opponent_style"])
            + f" ({sign}{balance['matchup_bonus_pct']}% к силе)."
        )

    user_formation = balance.get("user_formation", "4-3-3")
    opponent_formation = balance.get("opponent_formation", "4-3-3")
    if user_formation != opponent_formation:
        reasons.append(
            f"Схемы: ваша {arena_tactics.formation_label(user_formation)}"
            f" ({_tilt_text(user_formation)}), у соперника {arena_tactics.formation_label(opponent_formation)}"
            f" ({_tilt_text(opponent_formation)})."
        )

    gaps = [
        (lines["opponent"].get(key, 0) - lines["user"].get(key, 0), label, key)
        for key, label in _LINES if key in lines["user"] and key in lines["opponent"]
    ]
    worst = max(gaps, default=None)
    best = min(gaps, default=None)
    if worst is not None and worst[0] >= 3:
        reasons.append(f"{worst[1]} соперника сильнее: {lines['opponent'][worst[2]]} против {lines['user'][worst[2]]}.")
    if best is not None and best[0] <= -3:
        reasons.append(f"Ваша линия «{best[1]}» сильнее: {lines['user'][best[2]]} против {lines['opponent'][best[2]]}.")

    if not forfeited:
        reasons.append(f"Моменты: у вас {user_chances}, у соперника {opponent_chances}; реализовано {user_score} и {opponent_score}.")
        if result != MatchResult.win and opponent_keeper_saves >= 3:
            reasons.append(f"Вратарь соперника отразил {opponent_keeper_saves} ударов.")
        if result != MatchResult.loss and user_keeper_saves >= 3:
            reasons.append(f"Ваш вратарь отразил {user_keeper_saves} ударов.")
        if result != MatchResult.win and user_chances >= opponent_chances + 2 and user_score <= opponent_score:
            reasons.append("Вы создали больше моментов, но не реализовали их — в следующий раз чаще выбирайте лучшее действие.")
        if red_card:
            reasons.append("Красная карточка ослабила вашу оборону.")

    return {
        "verdict": verdict,
        "reasons": reasons,
        "chances": chances,
        "user_strength": user_strength,
        "opponent_strength": opponent_strength,
        "user_style": balance["user_style"],
        "opponent_style": balance["opponent_style"],
        "user_formation": user_formation,
        "opponent_formation": opponent_formation,
        "matchup": balance["matchup"],
        "matchup_bonus_pct": balance["matchup_bonus_pct"],
        "lines": [
            {"key": key, "label": label, "user": lines["user"].get(key), "opponent": lines["opponent"].get(key)}
            for key, label in _LINES
        ],
        "user_chances": user_chances,
        "opponent_chances": opponent_chances,
        "user_keeper_saves": user_keeper_saves,
        "opponent_keeper_saves": opponent_keeper_saves,
    }


def _lineup_gk(lineup: LineupOut):
    return next((s.card for s in lineup.slots if s.category == "GK" and s.card), None)


def _card_skill_effect(card, config: GameConfig) -> Optional[dict]:
    effect = effect_for_card(card.skill_code, card.skill_level, card.player.position, config)
    if effect is not None:
        effect["player"] = card.player.display_name
    return effect


def build_skill_snapshot(lineup: LineupOut, opponent_lineup: Optional[LineupOut], config: GameConfig) -> Optional[dict]:
    """Frozen once at match start into Match.server_state["skills"], so later
    card or GameConfig edits never reach this match. In Card Arena only the
    user's own cards act individually (the opponent's shots/defending are
    team aggregates), so the opponent's real goalkeeper is the only opponent
    card that can carry an effect. None when the mechanic is off."""
    if not config.card_skills_enabled:
        return None
    cards: dict[str, dict] = {}
    for slot in lineup.slots:
        if slot.card is not None:
            effect = _card_skill_effect(slot.card, config)
            if effect is not None:
                cards[str(slot.card.id)] = effect
    user_gk = _lineup_gk(lineup)
    opponent_gk = _lineup_gk(opponent_lineup) if opponent_lineup is not None else None
    return {
        "version": SNAPSHOT_VERSION,
        "cards": cards,
        "user_gk": cards.get(str(user_gk.id)) if user_gk is not None else None,
        "opponent_gk": _card_skill_effect(opponent_gk, config) if opponent_gk is not None else None,
    }


def build_equipment_snapshot(lineup: LineupOut) -> Optional[dict]:
    """card id -> {"shot_pp", "dribble_pp"} of the user's own cards, frozen at
    kickoff into Match.server_state["equipment"] (equipment_service keeps the
    capped sums on each card; empty while the mechanic is off). Only the
    user's cards act individually in Card Arena, so the opponent has none."""
    boosts = {
        str(slot.card.id): dict(slot.card.equipment_boosts)
        for slot in lineup.slots if slot.card is not None and slot.card.equipment_boosts
    }
    return boosts or None


def equipment_gk_snapshot(lineup: LineupOut) -> Optional[dict]:
    """Who keeps the user's goal (his «Экипировка» save bonus is in the
    equipment snapshot under his card id)."""
    gk = _lineup_gk(lineup)
    return {"id": gk.id, "name": gk.player.display_name} if gk is not None and gk.equipment_boosts else None


def equipment_coins_pct(lineup: LineupOut, config: GameConfig) -> int:
    """+% coins for a won match: the lineup's coin talismans summed, capped
    by equipment_max_talisman_pct (frozen at kickoff)."""
    total = sum(int((slot.card.equipment_boosts or {}).get("coins_pct") or 0) for slot in lineup.slots if slot.card is not None)
    return min(total, max(0, int(getattr(config, "equipment_max_talisman_pct", 0) or 0)))


_LINES = (("GK", "Вратарь"), ("DEF", "Защита"), ("MID", "Полузащита"), ("FWD", "Атака"))
_BALANCE_TABLE: Optional[list] = None


def _balance_table() -> list:
    global _BALANCE_TABLE
    if _BALANCE_TABLE is None:
        path = Path(__file__).with_name("arena_balance_table.json")
        _BALANCE_TABLE = json.loads(path.read_text(encoding="utf-8"))["table"]
    return _BALANCE_TABLE


def win_chances(strength_ratio: float) -> dict:
    """≈ win/draw/loss % for an average player at this effective strength
    ratio — interpolated (in log ratio) from the table that
    scripts/simulate_arena_balance.py --write measured on the real engine."""
    table = _balance_table()
    x = math.log(max(1e-3, strength_ratio))
    points = [(math.log(row["ratio"]), row) for row in table]
    if x <= points[0][0]:
        row = points[0][1]
    elif x >= points[-1][0]:
        row = points[-1][1]
    else:
        for (x0, r0), (x1, r1) in zip(points, points[1:]):
            if x0 <= x <= x1:
                t = (x - x0) / (x1 - x0) if x1 > x0 else 0
                row = {k: r0[k] + (r1[k] - r0[k]) * t for k in ("win", "draw", "loss")}
                break
    win, loss = round(row["win"]), round(row["loss"])
    return {"win": win, "draw": max(0, 100 - win - loss), "loss": loss}


def _lines_of(lineup: LineupOut) -> dict:
    return {key: _category_avg(lineup, key) for key, _ in _LINES}


@dataclass
class _ArenaOpponent:
    user: Optional[User]
    name: str
    avatar_url: Optional[str]
    points: int
    strength: int
    style: str
    lineup: Optional[LineupOut]
    lines: dict
    formation: str = "4-3-3"


async def _resolve_opponent(db: AsyncSession, pending: dict, user_strength: int, user_lines: dict) -> _ArenaOpponent:
    """The real opponent's current squad when it's still complete, else a
    bot of `bot_ratio` x your strength (under the found player's name)."""
    if pending.get("user_id"):
        opponent = await db.get(User, pending["user_id"])
        if opponent is not None and not opponent.is_banned:
            opponent_lineup = await get_active_lineup(db, opponent)
            if opponent_lineup.is_complete and opponent_lineup.team_strength:
                return _ArenaOpponent(
                    user=opponent, name=pending["name"], avatar_url=pending.get("avatar_url"),
                    points=int(pending.get("points", 0)), strength=opponent_lineup.team_strength,
                    style=arena_tactics.resolve_style(opponent_lineup.tactic), lineup=opponent_lineup,
                    lines=_lines_of(opponent_lineup), formation=opponent_lineup.formation,
                )
    strength = max(1, round(user_strength * float(pending.get("bot_ratio", 1.0))))
    fwd, defense, gk = _synthesize_bot_ratings(user_lines["FWD"], user_lines["DEF"], user_lines["GK"], strength, user_strength)
    mid, _, _ = _synthesize_bot_ratings(user_lines["MID"], user_lines["MID"], user_lines["MID"], strength, user_strength)
    return _ArenaOpponent(
        user=None, name=pending["name"], avatar_url=pending.get("avatar_url"),
        points=int(pending.get("points", 0)), strength=strength,
        style=arena_tactics.resolve_style(pending.get("bot_style")), lineup=None,
        lines={"GK": gk, "DEF": defense, "MID": mid, "FWD": fwd},
        formation=pending.get("bot_formation") or "4-3-3",
    )


async def _pending_opponent(db: AsyncSession, locked_user: User, config: GameConfig) -> dict:
    if not locked_user.arena_pending_opponent:
        from app.services import newbie_service

        locked_user.arena_pending_opponent = (
            await newbie_service.first_arena_opponent(db, locked_user, config)
            or await arena_ladder_service.find_opponent(db, locked_user, config)
        )
        db.add(locked_user)
    return dict(locked_user.arena_pending_opponent)


async def preview_opponent(db: AsyncSession, user: User) -> ArenaPreviewOut:
    """The opponent of the next match (found once, kept until played), with
    both line-ups compared, the style matchup, ≈ chances and the points at
    stake — so the player can pick a style before kickoff and later see
    why the match went the way it did."""
    config = await get_config(db)
    lineup = await get_active_lineup(db, user)
    if not lineup.is_complete:
        raise ConflictError("Complete your starting XI before playing a match")
    locked_user = await lock_user_for_update(db, user.id)
    pending = await _pending_opponent(db, locked_user, config)
    await db.commit()

    user_lines = _lines_of(lineup)
    opponent = await _resolve_opponent(db, pending, lineup.team_strength, user_lines)
    balance = arena_tactics.compute_balance(
        lineup.team_strength, lineup.tactic, opponent.strength, opponent.style, config,
        user_formation=lineup.formation, opponent_formation=opponent.formation,
    )
    division = arena_ladder_service.division_info(locked_user, config)
    return ArenaPreviewOut(
        opponent_name=opponent.name,
        opponent_avatar_url=opponent.avatar_url,
        opponent_is_bot=opponent.user is None,
        opponent_points=opponent.points,
        opponent_division=arena_ladder_service.division_of(opponent.points, config),
        opponent_strength=opponent.strength,
        opponent_style=opponent.style,
        opponent_formation=opponent.formation,
        user_strength=lineup.team_strength,
        user_style=balance["user_style"],
        user_formation=lineup.formation,
        matchup=balance["matchup"],
        matchup_bonus_pct=balance["matchup_bonus_pct"],
        matchup_text=arena_tactics.matchup_text(balance["user_style"], opponent.style),
        lines=[
            ArenaLineCompareOut(key=key, label=label, user=user_lines[key], opponent=opponent.lines[key])
            for key, label in _LINES
        ],
        chances=win_chances(balance["strength_ratio"]),
        points_at_stake=arena_ladder_service.points_preview(locked_user.arena_points, opponent.points, config),
        division=ArenaDivisionOut(**division),
    )


async def start_match(db: AsyncSession, user: User, payload: StartMatchRequest) -> MatchOut:
    config = await get_config(db)

    lineup = await get_active_lineup(db, user)
    if not lineup.is_complete:
        raise ConflictError("Complete your starting XI before playing a match")

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

    # The opponent shown in the preview (or found now for a client that
    # skipped it); used up by this kickoff.
    pending = await _pending_opponent(db, locked_user, config)
    locked_user.arena_pending_opponent = None
    locked_user.arena_last_strength = lineup.team_strength
    db.add(locked_user)

    # No jitter: the strengths are exactly what the preview showed.
    user_strength = lineup.team_strength
    user_lines = _lines_of(lineup)
    opponent = await _resolve_opponent(db, pending, user_strength, user_lines)
    opponent_strength = opponent.strength
    opponent_lineup = opponent.lineup
    user_fwd, user_def, user_gk = user_lines["FWD"], user_lines["DEF"], user_lines["GK"]
    opponent_fwd, opponent_def, opponent_gk = opponent.lines["FWD"], opponent.lines["DEF"], opponent.lines["GK"]

    # «Академия»: talents decided at kickoff (after the opponent is known,
    # so a bot's strength never includes them) and frozen into the state.
    kickoff = await path_match_service.arena_kickoff(
        db, lineup, user_strength=user_strength, opponent_strength=opponent_strength, config=config,
    )
    if kickoff is not None and kickoff.plan is not None and kickoff.plan.active:
        user_strength = max(1, user_strength + kickoff.strength_delta)
        user_fwd = kickoff.ratings.get("FWD", user_fwd)
        user_def = kickoff.ratings.get("DEF", user_def)
        user_gk = kickoff.ratings.get("GK", user_gk)
        user_lines = {**user_lines, "FWD": user_fwd, "DEF": user_def, "GK": user_gk}

    balance = arena_tactics.compute_balance(
        user_strength, lineup.tactic, opponent_strength, opponent.style, config,
        user_formation=lineup.formation, opponent_formation=opponent.formation,
    )
    user_attack, _user_defense = split_strength(user_strength, balance["user_style"])
    opponent_attack, _opponent_defense = split_strength(opponent_strength, balance["opponent_style"])

    state = {
        "moments": _generate_moment_queue(user_attack, opponent_attack, config, lineup, opponent.name, balance=balance),
        "next_index": 0,
        "user_score": 0,
        "opponent_score": 0,
        "ratings": {
            "user_fwd": user_fwd, "user_def": user_def, "user_gk": user_gk,
            "opponent_fwd": opponent_fwd, "opponent_def": opponent_def, "opponent_gk": opponent_gk,
        },
        "cards": {},
        "red_card_applied": False,
        "skills": build_skill_snapshot(lineup, opponent_lineup, config),
        "equipment": build_equipment_snapshot(lineup),
        "equipment_gk": equipment_gk_snapshot(lineup),
        "equipment_coins_pct": equipment_coins_pct(lineup, config),
        # Audit only: the chemistry already sits inside the frozen strengths
        # and ratings above, nothing re-reads it mid-match.
        "chemistry": {
            "user": lineup.chemistry.team if lineup.chemistry.enabled else None,
            "opponent": opponent_lineup.chemistry.team if opponent_lineup is not None and opponent_lineup.chemistry.enabled else None,
            "max": lineup.chemistry.team_max if lineup.chemistry.enabled else None,
        },
        # Divisions + the match report: what the engine was told at kickoff.
        "balance": balance,
        "chances": win_chances(balance["strength_ratio"]),
        "lines": {"user": user_lines, "opponent": opponent.lines},
        "opponent_points": opponent.points,
        **(kickoff.state() if kickoff is not None else {}),
    }

    match = Match(
        user_id=locked_user.id,
        opponent_user_id=opponent.user.id if opponent.user is not None else None,
        opponent_name=opponent.name,
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
    if scored_by == "user":
        event_payload = event.get("payload") or {}
        path_match_service.arena_track_goal(state, event_payload.get("shooter_id"), event_payload.get("assist_id"))
    if scored_by:
        state[f"{scored_by}_score"] += 1
        _fit_goal_to_score(event, scored_by, state)
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


async def forfeit_match(db: AsyncSession, user: User, match_id: int) -> MatchOut:
    """Immediately ends an in-progress match as a loss for the player,
    regardless of the partial score — mirrors tactico_service.forfeit_match
    and penalty_service.forfeit_session. Called from the frontend's
    leave-confirmation dialog (matchGuardStore)."""
    config = await get_config(db)
    match = await _lock_match(db, user.id, match_id)
    state = dict(match.server_state or {})
    await _finalize_match(db, user, match, state, config, forced_result=MatchResult.loss)
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
    config = await get_config(db)
    return ArenaStatsOut(
        matches_won=user.matches_won,
        matches_drawn=user.matches_drawn,
        matches_lost=user.matches_lost,
        arena_rating=user.arena_rating,
        arena_rank=await arena_ladder_service.points_rank(db, user),
        division=ArenaDivisionOut(**arena_ladder_service.division_info(user, config)),
    )


async def arena_leaderboard(db: AsyncSession, limit: int = 20) -> list[ArenaLeaderboardEntry]:
    config = await get_config(db)
    users = await arena_ladder_service.leaderboard(db, limit)
    return [
        ArenaLeaderboardEntry(
            user_id=u.id, display_name=u.full_display_name(), avatar_url=u.avatar_url,
            arena_rating=u.arena_rating, arena_points=u.arena_points,
            division=arena_ladder_service.division_of(u.arena_points, config),
            matches_won=u.matches_won, matches_drawn=u.matches_drawn,
            matches_lost=u.matches_lost, goal_difference=u.goals_for - u.goals_against,
            points=u.matches_won * 3 + u.matches_drawn,
        )
        for u in users
    ]
