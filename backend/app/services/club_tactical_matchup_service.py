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


# --- Counter-attack chain (spec §6.5) ----------------------------------------


@dataclass
class ClubTacticalSide:
    cards: list[Any]
    profile: TeamTacticalProfile
    mentality: str
    playstyle: str


def _first_pass_quality_factor(midfield_control: float) -> float:
    """A weak outlet pass caps how dangerous a counter can be, even with elite
    forwards waiting (spec §6.5). Scaled around 70 (a "solid" personal-engine
    midfielder rating) so an average midfield neither boosts nor caps the
    counter (factor 1.0), while a genuinely weak one (~58, the engine's rating
    floor) meaningfully blunts it and a genuinely elite one (~99) sharpens it."""
    return max(0.7, min(1.15, 0.7 + (midfield_control - 58) / (99 - 58) * 0.45))


def resolve_counter(attacking_side_label: str, y: ClubTacticalSide, x: ClubTacticalSide) -> tuple[str, float] | None:
    """Spec §6.5: Y (the team that just won the Stage-1 duel) gets an
    immediate transition check against X's shrunk defensive pool (Task 7),
    resolved via the SAME picked-duelist mechanism as Stage 1/Stage 2 (Task
    6) — not a team-aggregate. Returns (quality_tier, combined_advantage) on
    a successful transition, or None if it stalls or the ball is win back
    immediately (no further recursive counter chain in Phase 1 — bounded
    scope, matches the "roughly 40-70 phases" budget instead of unbounded
    recursion)."""
    zone = random.choices(["central_attack", "wing_attack"], weights=[0.6, 0.4], k=1)[0]
    defence_zone = "wing_defence" if zone == "wing_attack" else "central_defence"

    y_duelist = weighted_pick(y.cards, zone)
    pool = defensive_pool(x.cards, x.mentality, x.playstyle)
    x_duelist = weighted_pick(pool, defence_zone)

    eff_y = y_duelist.player.rating * position_fit(y_duelist.player.position, zone) * TRANSITION_BONUS[y.playstyle] * _first_pass_quality_factor(y.profile.midfield_control)
    eff_x = x_duelist.player.rating * position_fit(x_duelist.player.position, defence_zone)
    total = eff_y + eff_x
    ratio = eff_y / total if total else 0.5

    outcome = resolve_stage1(ratio)
    if outcome != "advance":
        return None

    quality = resolve_quality(ratio)
    if quality == "VERY_HIGH" and len(pool) == 1:
        # Thinnest possible cover beaten decisively — the keeper-race
        # breakaway case _resolve_breakaway (Task 9) already handles.
        return "CLEAN_BREAKAWAY", ratio
    return quality, ratio


# --- Possession-phase orchestrator (spec §6.1-6.6, §8, §12) -----------------

from app.services.club_tactical_profile_service import compute_profile

# Verbatim shape from design spec §8's "Progression zone target (§6.2)"
# column, turned into concrete weights: "none" is the low-event/recycle
# outcome where this phase ends without reaching Stage 1 at all — folds
# spec's "rest low-event"/"~60% attempt progression at all" wording into one
# number per playstyle. HIGH_PRESS behaves like BALANCED in possession per
# spec §8 ("~BALANCED zone mix when in possession").
PLAYSTYLE_ZONE_WEIGHTS: dict[str, dict[str, float]] = {
    "WING_PLAY": {"wing_attack": 0.65, "central_attack": 0.25, "none": 0.10},
    "CENTRAL_PLAY": {"central_attack": 0.65, "wing_attack": 0.25, "none": 0.10},
    "POSSESSION": {"central_attack": 0.40, "wing_attack": 0.40, "none": 0.20},
    "HIGH_PRESS": {"central_attack": 0.45, "wing_attack": 0.45, "none": 0.10},
    "COUNTER_ATTACK": {"central_attack": 0.30, "wing_attack": 0.30, "none": 0.40},
}


def pick_progression_zone(playstyle: str) -> str | None:
    weights = PLAYSTYLE_ZONE_WEIGHTS[playstyle]
    zones = list(weights.keys())
    picked = random.choices(zones, weights=list(weights.values()), k=1)[0]
    return None if picked == "none" else picked


def possession_buildup_survives(midfield_control: float) -> bool:
    """POSSESSION's buildup gate (spec §8): "weak midfield → higher breakdown
    chance before even reaching §6.3". Scaled so a midfield_control of 70
    (this engine's typical "solid" rating) survives 60% of the time, rising
    to a 95%-capped ceiling for elite midfields and a 30%-floored chance for
    weak ones — never zero, since even a weak midfield occasionally strings
    passes together."""
    chance = min(0.95, max(0.30, (midfield_control - 40) / 50))
    return random.random() < chance


def _pick_shot_type(config) -> str:
    weights = [config.match_shot_type_in_box_weight, config.match_shot_type_long_range_weight]
    return random.choices(["in_box", "long_range"], weights=weights, k=1)[0]


def _card_to_actor(card: Any) -> dict:
    return {
        "club_card_id": card.id, "player_id": card.player_id, "name": card.player.display_name,
        "rating": card.player.rating, "position": card.player.position.value,
    }


@dataclass
class Chance:
    attacking_side: str
    minute: int
    quality: str
    shot_type: str
    is_box: bool
    shooter: dict = field(default_factory=dict)
    pass_target: dict = field(default_factory=dict)
    defender: dict = field(default_factory=dict)


def build_side(cards_with_slots: list[tuple[Any, Any]], mentality: str, playstyle: str) -> ClubTacticalSide:
    profile = compute_profile(cards_with_slots)
    cards = [card for card, _slot in cards_with_slots]
    return ClubTacticalSide(cards=cards, profile=profile, mentality=mentality, playstyle=playstyle)


def _resolve_progression_and_duel(attacker: ClubTacticalSide, defender: ClubTacticalSide, attacking_side: str, minute: int, config) -> Chance | None:
    zone = pick_progression_zone(attacker.playstyle)
    if zone is None:
        return None
    if attacker.playstyle == "POSSESSION" and not possession_buildup_survives(attacker.profile.midfield_control):
        return None

    defence_zone = "wing_defence" if zone == "wing_attack" else "central_defence"
    attacker_duelist = weighted_pick(attacker.cards, zone)
    defender_duelist = weighted_pick(defender.cards, defence_zone)
    ratio_1 = zone_ratio(attacker_duelist, zone, defender_duelist, defence_zone)
    outcome_1 = resolve_stage1(ratio_1)

    if outcome_1 == "stall":
        return None
    if outcome_1 == "breakdown":
        defending_side_label = "b" if attacking_side == "a" else "a"
        result = resolve_counter(defending_side_label, defender, attacker)
        if result is None:
            return None
        quality, ratio = result
        if quality == "CLEAN_BREAKAWAY":
            return Chance(attacking_side=defending_side_label, minute=minute, quality="VERY_HIGH", shot_type="empty_net", is_box=False)
        counter_shot_type = _pick_shot_type(config)
        counter_shooter = weighted_pick(defender.cards, "central_attack")
        return Chance(
            attacking_side=defending_side_label, minute=minute, quality=quality, shot_type=counter_shot_type,
            is_box=(counter_shot_type == "in_box"),
            shooter=_card_to_actor(counter_shooter),
            pass_target=_card_to_actor(weighted_pick(defender.cards, "central_attack", exclude_ids=frozenset({counter_shooter.id}))),
            defender=_card_to_actor(weighted_pick(attacker.cards, "central_defence")),
        )

    # advance -> Stage 2 (spec §6.3)
    attacker_second = weighted_pick(attacker.cards, zone, exclude_ids=frozenset({attacker_duelist.id}))
    defender_second = weighted_pick(defender.cards, defence_zone, exclude_ids=frozenset({defender_duelist.id}))
    ratio_2 = zone_ratio(attacker_second, zone, defender_second, defence_zone)
    combined_advantage = (ratio_1 + ratio_2) / 2
    quality = resolve_quality(combined_advantage)
    shot_type = _pick_shot_type(config)
    return Chance(
        attacking_side=attacking_side, minute=minute, quality=quality, shot_type=shot_type, is_box=(shot_type == "in_box"),
        shooter=_card_to_actor(attacker_duelist), pass_target=_card_to_actor(attacker_second), defender=_card_to_actor(defender_second),
    )


def simulate_phase(minute: int, side_a: ClubTacticalSide, side_b: ClubTacticalSide, config) -> Chance | None:
    p_a_initiative = initiative_probability(side_a.profile, side_a.mentality, side_b.profile, side_b.mentality)
    if random.random() < p_a_initiative:
        return _resolve_progression_and_duel(side_a, side_b, "a", minute, config)
    return _resolve_progression_and_duel(side_b, side_a, "b", minute, config)


def simulate_match_phases(side_a: ClubTacticalSide, side_b: ClubTacticalSide, config) -> list[Chance]:
    num_phases = random.randint(config.club_tactical_phases_per_match_min, config.club_tactical_phases_per_match_max)
    minutes = sorted(random.sample(range(1, 90), min(num_phases, 89)))

    chances: list[Chance] = []
    for minute in minutes:
        chance = simulate_phase(minute, side_a, side_b, config)
        if chance is not None:
            chances.append(chance)

    # Sanity-clip to the configured target ceiling (spec §12) — keeps match
    # length in the range players already see today; no minimum enforcement
    # in Phase 1 (would need re-rolling extra phases, deferred to Phase 3
    # tuning if the realized count ever runs low in practice).
    max_target = config.club_tactical_promoted_chance_target_max
    if len(chances) > max_target:
        chances = chances[:max_target]
    return chances
