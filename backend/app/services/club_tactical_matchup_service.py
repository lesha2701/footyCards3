import random
from dataclasses import dataclass, field
from typing import Any

from app.services.club_tactical_profile_service import TeamTacticalProfile, position_fit, zone_weight

MENTALITIES = ("PARK_THE_BUS", "DEFENSIVE", "BALANCED", "ATTACKING")
PLAYSTYLES = ("WING_PLAY", "CENTRAL_PLAY", "POSSESSION", "HIGH_PRESS", "COUNTER_ATTACK")

# Verbatim from design spec §7.
INITIATIVE_MULT: dict[str, float] = {"PARK_THE_BUS": 0.55, "DEFENSIVE": 0.80, "BALANCED": 1.00, "ATTACKING": 1.25}
SAMPLE_FRACTION: dict[str, float] = {"PARK_THE_BUS": 1.00, "DEFENSIVE": 0.90, "BALANCED": 0.75, "ATTACKING": 0.55}
HIGH_PRESS_POOL_MULT = 0.85

# Verbatim from design spec §8's "Transition bonus (§6.5)" column.
TRANSITION_BONUS: dict[str, float] = {
    "WING_PLAY": 1.0, "CENTRAL_PLAY": 1.0, "POSSESSION": 0.7, "HIGH_PRESS": 1.3, "COUNTER_ATTACK": 1.5,
}


def initiative_probability(profile_a: TeamTacticalProfile, mentality_a: str, profile_b: TeamTacticalProfile, mentality_b: str) -> float:
    score_a = profile_a.midfield_control * INITIATIVE_MULT[mentality_a]
    score_b = profile_b.midfield_control * INITIATIVE_MULT[mentality_b]
    total = score_a + score_b
    return score_a / total if total else 0.5


# --- Player selection (spec §6.6) ------------------------------------------


def weighted_pick(cards: list[Any], zone: str, exclude_ids: frozenset = frozenset()) -> Any:
    """Among the given cards, picks one at random with probability
    proportional to its position's zone_weight for `zone` — the same
    "weighted-pick, not uniform-random" idea tournament_match_engine._pick_actor
    already uses for shot moments today, zone-scoped instead of category-scoped
    (spec §6.6). Falls back to a uniform pick among all non-excluded cards if
    none has any weight for this zone (mirrors _pick_actor's own fallback
    shape) — should only happen for a near-empty candidate list in tests."""
    candidates = []
    weights = []
    for card in cards:
        if card.id in exclude_ids:
            continue
        weight = zone_weight(card.player.position, zone)
        if weight > 0:
            candidates.append(card)
            weights.append(weight)
    if not candidates:
        candidates = [c for c in cards if c.id not in exclude_ids]
        weights = [1.0] * len(candidates)
    return random.choices(candidates, weights=weights, k=1)[0]


def zone_ratio(attacker: Any, attacker_zone: str, defender: Any, defender_zone: str) -> float:
    eff_attacker = attacker.player.rating * position_fit(attacker.player.position, attacker_zone)
    eff_defender = defender.player.rating * position_fit(defender.player.position, defender_zone)
    total = eff_attacker + eff_defender
    return eff_attacker / total if total else 0.5


# --- Duel bands (spec §6.3) -------------------------------------------------
# Each row is (lower_bound_exclusive, outcome_weights); rows are checked in
# order and the first `ratio > lower_bound` wins, so the final row's -1.0
# sentinel always matches (covers the "< 0.40" bucket without a special case).
STAGE1_BANDS: list[tuple[float, tuple[float, float, float]]] = [
    (0.75, (0.10, 0.25, 0.65)),   # breakdown, stall, advance
    (0.60, (0.18, 0.35, 0.47)),
    (0.40, (0.30, 0.45, 0.25)),
    (-1.0, (0.45, 0.35, 0.20)),
]
STAGE2_BANDS: list[tuple[float, tuple[float, float, float, float]]] = [
    (0.75, (0.05, 0.20, 0.50, 0.25)),   # LOW, NORMAL, HIGH, VERY_HIGH
    (0.60, (0.15, 0.35, 0.38, 0.12)),
    (0.40, (0.25, 0.50, 0.22, 0.03)),
    (-1.0, (0.55, 0.35, 0.09, 0.01)),
]


def _band(value: float, bands: list[tuple[float, tuple]]) -> tuple:
    for lower_bound, outcome in bands:
        if value > lower_bound:
            return outcome
    return bands[-1][1]


def resolve_stage1(ratio: float) -> str:
    breakdown, stall, advance = _band(ratio, STAGE1_BANDS)
    return random.choices(["breakdown", "stall", "advance"], weights=[breakdown, stall, advance], k=1)[0]


def resolve_quality(combined_advantage: float) -> str:
    low, normal, high, very_high = _band(combined_advantage, STAGE2_BANDS)
    return random.choices(["LOW", "NORMAL", "HIGH", "VERY_HIGH"], weights=[low, normal, high, very_high], k=1)[0]


def defensive_pool(cards: list[Any], mentality: str, playstyle: str) -> list[Any]:
    """Spec §6.4: a transition moment's defensive duelist is drawn from a
    mentality-sized random SUBSET of the team's real defensive-zone
    contributors, re-rolled fresh every call — never from a rating-adjusted
    version of the back line. "Defensive-zone contributors" = anyone with
    nonzero central_defence or wing_defence weight (CB/LB/RB/CDM, plus GK's
    small 0.15 sliver — rarely picked in practice since weighted_pick still
    weights by that same small value)."""
    contributors = [c for c in cards if zone_weight(c.player.position, "central_defence") > 0 or zone_weight(c.player.position, "wing_defence") > 0]
    if not contributors:
        return []

    fraction = SAMPLE_FRACTION[mentality]
    if playstyle == "HIGH_PRESS":
        fraction *= HIGH_PRESS_POOL_MULT

    pool_size = max(1, round(fraction * len(contributors)))
    pool_size = min(pool_size, len(contributors))
    return random.sample(contributors, pool_size)
