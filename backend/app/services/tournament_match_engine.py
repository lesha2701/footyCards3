import random

from app.services.match_situations import (
    ATTACK_SITUATIONS_BY_SHOT_TYPE,
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
    return dict(random.choice(pool))


def _build_shot_moment(minute: int, attacking_lineup: list[dict], defending_lineup: list[dict], attacking_side: str, shot_type: str) -> dict:
    moment = {"minute": minute, "kind": "shot", "attacking_side": attacking_side, "shot_type": shot_type}

    if shot_type == "empty_net":
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
    every shot moment carries real actors from BOTH the attacking club
    (shooter/pass target) and the defending club (defender), unlike the
    personal engine's user-vs-abstract-opponent shape."""
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
