import random
from dataclasses import dataclass, field

from app.services.match_situations import (
    ATTACK_SITUATIONS_BY_ID,
    ATTACK_SITUATIONS_BY_SHOT_TYPE,
    DEFENSE_SITUATIONS_BY_ID,
    DEFENSE_SITUATIONS_BY_SHOT_TYPE,
)

SHOT_TYPES = ("in_box", "long_range", "empty_net")

# Copied verbatim from match_service.py — same weighting, same intent
# (a "team gets a scoring chance" moment happens at this overall frequency;
# only what happens within it differs from the personal engine).
_FLAVOR_WEIGHTS: list[tuple[str, int]] = [
    ("corner", 9), ("yellow_card", 5), ("red_card", 1), ("offside", 6), ("possession", 20),
]
_SHOT_CHANCE_WEIGHT = 26


def _pick_actor(lineup: list[dict], category: str, preferred_positions: tuple, exclude_ids: tuple[int, ...] = ()) -> dict:
    """Same fallback shape as match_service._pick_actor, generalized to a
    plain list-of-dicts lineup instead of a LineupOut (both sides are real
    here, so there's no single privileged "user" lineup to special-case)."""
    cards = [c for c in lineup if c["category"] == category and c["club_card_id"] not in exclude_ids]
    pool = [c for c in cards if c["position"] in preferred_positions] or cards
    if not pool:
        pool = [c for c in lineup if c["category"] != "GK" and c["club_card_id"] not in exclude_ids]
    card = random.choice(pool)
    return {
        "club_card_id": card["club_card_id"],
        "player_id": card["player_id"],
        "name": card["name"],
        "rating": card["rating"],
        "position": card["position"],
    }


def _build_shot_moment(minute: int, attacking_lineup: list[dict], defending_lineup: list[dict], attacking_side: str, shot_type: str) -> dict:
    moment = {"minute": minute, "kind": "shot", "attacking_side": attacking_side, "shot_type": shot_type}

    if shot_type == "empty_net":
        # Special case, deliberately unlike every other shot moment: no real
        # situation to draw actors from (it's an open-goal breakaway, not a
        # crafted chance), so this moment carries no actors at all and — unlike
        # situation_id elsewhere, which is set to None — omits the
        # defense_situation_id key entirely rather than setting it to None.
        # Callers (Task 11) must not assume `actors`/`defense_situation_id`
        # are populated for every kind == "shot" moment.
        moment.update(situation_kind="breakaway", situation_id=None, actors={}, actions=["shoot"])
        return moment

    situation = random.choice(ATTACK_SITUATIONS_BY_SHOT_TYPE[shot_type])
    shooter = _pick_actor(attacking_lineup, situation.shooter_category, situation.shooter_positions)
    pass_target = _pick_actor(
        attacking_lineup, situation.pass_target_category, situation.pass_target_positions, exclude_ids=(shooter["club_card_id"],)
    )
    defense_situation = random.choice(DEFENSE_SITUATIONS_BY_SHOT_TYPE[shot_type])
    defender = _pick_actor(defending_lineup, defense_situation.defender_category, defense_situation.defender_positions)

    moment.update(
        situation_kind="attack", situation_id=situation.id, defense_situation_id=defense_situation.id,
        actors={"shooter": shooter, "pass_target": pass_target, "defender": defender},
        actions=["shoot", "pass"],
    )
    return moment


def generate_moment_queue(strength_a: int, strength_b: int, config, lineup_a: list[dict], lineup_b: list[dict]) -> list[dict]:
    """Two-sided generalization of match_service._generate_moment_queue:
    every non-empty-net shot moment carries real actors from BOTH the
    attacking club (shooter/pass target) and the defending club (defender),
    unlike the personal engine's user-vs-abstract-opponent shape. The
    exception is `shot_type == "empty_net"`, whose moments carry no actors
    and omit `defense_situation_id` entirely — see the comment in
    `_build_shot_moment`."""
    total = strength_a + strength_b
    a_attack_prob = strength_a / total if total else 0.5

    num_chances = random.randint(14, 22)
    minutes = sorted(random.sample(range(1, 90), num_chances))

    kinds = [t for t, _ in _FLAVOR_WEIGHTS] + ["shot_chance"]
    weights = [w for _, w in _FLAVOR_WEIGHTS] + [_SHOT_CHANCE_WEIGHT]
    shot_weights = [
        config.match_shot_type_in_box_weight, config.match_shot_type_long_range_weight, config.match_shot_type_empty_net_weight,
    ]

    moments: list[dict] = []
    for minute in minutes:
        attacking_side = "a" if random.random() < a_attack_prob else "b"
        kind = random.choices(kinds, weights=weights, k=1)[0]
        if kind == "shot_chance":
            shot_type = random.choices(list(SHOT_TYPES), weights=shot_weights, k=1)[0]
            attacking_lineup, defending_lineup = (lineup_a, lineup_b) if attacking_side == "a" else (lineup_b, lineup_a)
            moments.append(_build_shot_moment(minute, attacking_lineup, defending_lineup, attacking_side, shot_type))
        else:
            moments.append({"minute": minute, "kind": "flavor", "event_type": kind, "attacking_side": attacking_side})
    return moments


# --- Resolution -------------------------------------------------------------
# The functions below decide the OUTCOME of each moment generated above,
# reusing the exact same probability curves as the personal Card Arena engine
# (backend/app/services/match_service.py) — _lerp_chance, _lerp_chance_positive,
# _clamp_rating and _resolve_shot_continuation are copied verbatim from there
# (same math, same config field names) rather than re-derived, so admin-tuned
# match_* config values behave identically in both engines.


def _lerp_chance(rating: int, low: float, high: float) -> float:
    r = max(58, min(99, rating))
    return high - (r - 58) / (99 - 58) * (high - low)


def _lerp_chance_positive(rating: int, low: float, high: float) -> float:
    r = max(58, min(99, rating))
    return low + (r - 58) / (99 - 58) * (high - low)


def _clamp_rating(rating: float) -> int:
    return max(58, min(99, round(rating)))


def _resolve_shot_continuation(missed: bool, shot_type: str, config, blocker_rating, keeper_rating) -> tuple[str, dict]:
    blocked = False
    saved = False
    if not missed and shot_type == "long_range" and blocker_rating is not None:
        blocked = random.random() < _lerp_chance(blocker_rating, float(config.match_defender_block_chance_min), float(config.match_defender_block_chance_max))
    if not missed and not blocked:
        saved = random.random() < _lerp_chance_positive(keeper_rating, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max))
    outcome = "shot" if missed else "blocked" if blocked else "save" if saved else "goal"
    return outcome, {"missed": missed, "blocked": blocked}


@dataclass
class MatchResult:
    score_a: int
    score_b: int
    event_log: list[dict] = field(default_factory=list)
    injuries: list[tuple[int, int]] = field(default_factory=list)      # (club_card_id, rounds_remaining)
    red_cards: list[tuple[int, int]] = field(default_factory=list)     # (club_card_id, rounds_remaining=1)


def _resolve_shot_action(attacking_side: str, moment: dict, config) -> tuple[dict, str]:
    """Default action policy for auto-resolution (nobody is watching live):
    shoot when the situation's bias is non-negative (a "clear" chance), pass
    otherwise; the shooter/pass-target choice, and every subsequent
    miss/block/save roll, is otherwise identical to a human picking the same
    action in the personal engine."""
    situation = ATTACK_SITUATIONS_BY_ID[moment["situation_id"]]
    shooter = moment["actors"]["shooter"]
    pass_target = moment["actors"]["pass_target"]
    defender = moment["actors"]["defender"]
    shot_type = moment["shot_type"]

    action = "shoot" if situation.bias >= 0 else "pass"
    if action == "shoot":
        eff_rating = _clamp_rating(shooter["rating"] + situation.bias)
        missed = random.random() < _lerp_chance(eff_rating, float(config.match_attack_shoot_miss_chance_min), float(config.match_attack_shoot_miss_chance_max))
        scorer = shooter
    else:
        eff_passer_rating = _clamp_rating(shooter["rating"] - situation.bias)
        pass_failed = random.random() < _lerp_chance(eff_passer_rating, float(config.match_pass_fail_chance_min), float(config.match_pass_fail_chance_max))
        if pass_failed:
            event = {
                "minute": moment["minute"], "event_type": "pass_failed", "team": attacking_side,
                "payload": {"shot_type": shot_type, "action": "pass", "passer": shooter["name"]},
            }
            return event, "none"
        missed = random.random() < _lerp_chance(pass_target["rating"], float(config.match_receiver_shot_miss_chance_min), float(config.match_receiver_shot_miss_chance_max))
        scorer = pass_target

    outcome, extra = _resolve_shot_continuation(missed, shot_type, config, blocker_rating=defender["rating"], keeper_rating=defender["rating"])
    event = {
        "minute": moment["minute"], "event_type": outcome, "team": attacking_side,
        "payload": {"shot_type": shot_type, "action": action, "shooter": scorer["name"], **extra},
    }
    return event, (attacking_side if outcome == "goal" else "none")


def _resolve_defense_tackle(defending_side: str, moment: dict, config) -> tuple[dict, str, tuple[int, str] | None]:
    """Default policy: defending side always attempts a tackle (same
    rating-driven foul/card rolls as a human picking 'tackle' today).
    Returns (event, scoring_side_or_none, (club_card_id, 'red'|'yellow')_or_none)."""
    defender = moment["actors"]["defender"]
    defense_situation = DEFENSE_SITUATIONS_BY_ID[moment["defense_situation_id"]]
    shot_type = moment["shot_type"]

    foul = random.random() < _lerp_chance(defender["rating"], float(config.match_tackle_foul_chance_min), float(config.match_tackle_foul_chance_max))
    if not foul:
        event = {
            "minute": moment["minute"], "event_type": "tackle_won", "team": defending_side,
            "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"]},
        }
        return event, "none", None

    is_red = random.random() < _lerp_chance(defender["rating"], float(config.match_tackle_red_chance_min), float(config.match_tackle_red_chance_max))
    card_kind = "red" if is_red else "yellow"

    if "box" in defense_situation.tags:
        eff_gk = _clamp_rating(defender["rating"] - config.match_penalty_gk_rating_penalty)
        saved = random.random() < _lerp_chance_positive(eff_gk, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max))
        outcome = "save" if saved else "goal"
        attacking_side = "a" if defending_side == "b" else "b"
        event = {
            "minute": moment["minute"], "event_type": outcome, "team": attacking_side,
            "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"], "card": card_kind, "is_penalty": True},
        }
        return event, (attacking_side if outcome == "goal" else "none"), (defender["club_card_id"], card_kind)

    event = {
        "minute": moment["minute"], "event_type": "foul_stopped", "team": defending_side,
        "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"], "card": card_kind, "is_penalty": False},
    }
    return event, "none", (defender["club_card_id"], card_kind)


def _resolve_breakaway(attacking_side: str, moment: dict, lineup: list[dict], config) -> tuple[dict, str]:
    fwd_candidates = [c for c in lineup if c["category"] == "FWD"]
    fwd_rating = fwd_candidates[0]["rating"] if fwd_candidates else 70
    missed = random.random() < _lerp_chance(fwd_rating, float(config.match_shot_miss_chance_min), float(config.match_shot_miss_chance_max))
    outcome = "shot" if missed else "goal"
    event = {"minute": moment["minute"], "event_type": outcome, "team": attacking_side, "payload": {"shot_type": "empty_net", "missed": missed}}
    return event, (attacking_side if outcome == "goal" else "none")


def simulate_match(strength_a: int, strength_b: int, lineup_a: list[dict], lineup_b: list[dict], config) -> "MatchResult":
    """strength_a/strength_b are the caller's already-adjusted strengths
    (substitution penalty + form multiplier already applied — see
    tournament_simulation_service.match_strength) and drive the
    attacking-probability split; they are NOT recomputed here from the raw
    lineup, so those adjustments actually influence which side attacks more."""
    moments = generate_moment_queue(strength_a, strength_b, config, lineup_a, lineup_b)

    result = MatchResult(score_a=0, score_b=0)
    for moment in moments:
        if moment["kind"] == "flavor":
            continue  # not persisted to event_log — purely narrative in the personal engine, same here
        attacking_side = moment["attacking_side"]
        defending_side = "b" if attacking_side == "a" else "a"

        if moment["situation_kind"] == "breakaway":
            lineup = lineup_a if attacking_side == "a" else lineup_b
            event, scorer = _resolve_breakaway(attacking_side, moment, lineup, config)
            result.event_log.append(event)
            if scorer != "none":
                setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)
            continue

        # Defense is attempted only when a blocked/saved shot has a further
        # (15%) chance the defender committed a foul in the process — mirrors
        # match_service's "tackle can stop an attack before it becomes a shot"
        # flow for the "box"/foul path; everywhere else, shoot/pass resolves
        # directly against the defender's rating via _resolve_shot_continuation's
        # blocker/keeper roll, same as the personal engine.
        event, scorer = _resolve_shot_action(attacking_side, moment, config)
        result.event_log.append(event)
        if scorer != "none":
            setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)

        if event["event_type"] in ("blocked", "save") and random.random() < 0.15:
            defense_event, defense_scorer, card = _resolve_defense_tackle(defending_side, moment, config)
            result.event_log.append(defense_event)
            if defense_scorer != "none":
                setattr(result, f"score_{defense_scorer}", getattr(result, f"score_{defense_scorer}") + 1)
            if card is not None:
                club_card_id, card_kind = card
                if card_kind == "red":
                    result.red_cards.append((club_card_id, 1))
                    if random.random() < 0.3:
                        result.injuries.append((club_card_id, random.randint(1, 3)))

    return result
