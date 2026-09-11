import random
from dataclasses import dataclass, field
from typing import Any

from app.models.coach import Coach
from app.services.club_tactical_profile_service import TeamTacticalProfile, position_fit, zone_weight
from app.services.coach_boost_service import (
    defensive_shift_for,
    first_pass_input_bonus,
    initiative_mult_for,
    resolve_active_boosts,
    transition_bonus_for,
)

MENTALITIES = ("PARK_THE_BUS", "DEFENSIVE", "BALANCED", "ATTACKING")
PLAYSTYLES = ("WING_PLAY", "CENTRAL_PLAY", "POSSESSION", "HIGH_PRESS", "COUNTER_ATTACK")

# Verbatim from design spec §7.
INITIATIVE_MULT: dict[str, float] = {"PARK_THE_BUS": 0.55, "DEFENSIVE": 0.80, "BALANCED": 1.00, "ATTACKING": 1.25}
SAMPLE_FRACTION: dict[str, float] = {"PARK_THE_BUS": 1.00, "DEFENSIVE": 0.90, "BALANCED": 0.75, "ATTACKING": 0.55}
HIGH_PRESS_POOL_MULT = 0.85

# Verbatim from design spec §8's "Transition bonus (§6.5)" column, except
# COUNTER_ATTACK — raised 1.5 -> 2.0 on 2026-09-07 as part of the playstyle
# rock-paper-scissors rebalance (see scripts/simulate_tactical_matrix.py):
# COUNTER_ATTACK needed a real edge over at least one other style to satisfy
# "every style can counter something" without also making it a dominator —
# a stronger transition punch (this multiplier only applies to COUNTER's own
# breakdown-triggered chances) was the isolated lever, versus touching
# HIGH_PRESS_POOL_MULT/HIGH_PRESS_DEFENSE_SHIFT which affect HIGH_PRESS
# against every opponent, not just COUNTER_ATTACK specifically.
TRANSITION_BONUS: dict[str, float] = {
    "WING_PLAY": 1.0, "CENTRAL_PLAY": 1.0, "POSSESSION": 0.7, "HIGH_PRESS": 1.3, "COUNTER_ATTACK": 2.0,
}

# --- Fix for STATUS problem 4 ("most duels resolve on one identical band
# regardless of rating gap") -------------------------------------------------
# Raw zone_ratio's achievable range is only ~[0.37, 0.63] for a normal duel
# (99-vs-58 with perfect fit on both sides tops out at 0.631), so
# STAGE1_BANDS/STAGE2_BANDS' top row (">0.75") was essentially unreachable —
# a 95-vs-60 duel landed mostly in the "0.40-0.60"/"0.60-0.75" buckets no
# matter how lopsided the rating gap. Rescaling around the neutral 0.5 point
# by a fixed factor stretches the reachable range so real gaps actually cross
# band boundaries, without changing what "even" (0.5) means or requiring any
# band-table edit.
#
# Lowered 2.5 -> 1.0 on 2026-09-07 (see scripts/simulate_tactical_matrix.py):
# 2.5 made squad-level rating gaps swing match outcomes far more sharply than
# wanted — a 20-point average rating gap between two full squads (comparable
# to a 200+ point team_strength gap) was deciding ~97% of matches. At 1.0
# (i.e. no rescale — zone_ratio's raw value is used as-is) the same gap lands
# close to the target ~80/20 split. Deliberate trade-off: the extreme
# single-duel case problem 4 originally targeted (a 95-vs-60 individual duel
# reaching the ">0.75" band) is no longer guaranteed at this lower value —
# card class still meaningfully separates outcomes, just far more gradually,
# per explicit user calibration ("real difference should only start well
# above the biggest realistic gaps seen so far").
RATIO_AMPLIFICATION = 1.0


def _amplify(ratio: float, k: float | None = None) -> float:
    # `k`'s default is read from the module global at CALL time, not baked
    # in as a default-argument value at def time — the latter would freeze
    # whatever RATIO_AMPLIFICATION was when this module first imported,
    # silently ignoring any later reassignment (e.g. the balance-simulation
    # script's variant A/B switching).
    if k is None:
        k = RATIO_AMPLIFICATION
    return max(0.0, min(1.0, 0.5 + (ratio - 0.5) * k))


def initiative_probability(side_a: "ClubTacticalSide", side_b: "ClubTacticalSide") -> float:
    mult_a = initiative_mult_for(INITIATIVE_MULT[side_a.mentality], resolve_active_boosts(side_a.coach))
    mult_b = initiative_mult_for(INITIATIVE_MULT[side_b.mentality], resolve_active_boosts(side_b.coach))
    score_a = side_a.profile.midfield_control * mult_a
    score_b = side_b.profile.midfield_control * mult_b
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


def zone_ratio(attacker: Any, attacker_zone: str, defender: Any, defender_zone: str, ratio_shift: float = 0.0) -> float:
    """`ratio_shift` is the mechanism behind the mentality/HIGH_PRESS defense
    bonuses (see MENTALITY_DEFENSE_SHIFT/HIGH_PRESS_DEFENSE_SHIFT below): a
    fixed, BOUNDED nudge to the ratio itself (positive favors the defender),
    applied AFTER the raw rating-based ratio is computed — never a multiplier
    on the defender's rating. An earlier version multiplied
    defender.rating by up to 2.3x for PARK_THE_BUS; at that magnitude a
    58-rated worst-possible defender (58*2.3=133.4 effective) beat even a
    99-rated best-possible attacker (ratio 0.43, under 50%) purely from
    mentality — exactly the "turns a weak defender into a functional
    stopper" outcome spec §6.5 explicitly rules out. A fixed ratio-point
    shift can't do that: it's clamped to [0.05, 0.95] and applied to the
    raw ratio, so an extreme rating gap always survives a bounded shift in
    the gap's favor, while a close, ordinary duel is where the shift
    actually swings the outcome."""
    eff_attacker = attacker.player.rating * position_fit(attacker.player.position, attacker_zone)
    eff_defender = defender.player.rating * position_fit(defender.player.position, defender_zone)
    total = eff_attacker + eff_defender
    raw = eff_attacker / total if total else 0.5
    shifted = max(0.05, min(0.95, raw - ratio_shift))
    return _amplify(shifted)


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


# --- Fix for STATUS problem 1 ("mentality is backwards" — the pool shrinks
# but who gets picked inside it barely shifts) -------------------------------
# Uniformly sampling a subset and then weighted-picking by POSITION inside it
# doesn't move the picked defender's EXPECTED rating at all — a random subset
# of any size has the same expected rating as the whole group. The fix has to
# bias WHICH members survive the shrink, not just how many: as mentality
# commits more players forward, the team's genuinely BEST defensive cover
# should be the first to be unavailable (pulled out of position), leaving
# thinner, weaker cover behind — never a rating-adjusted defender, only a
# different, real, unmodified one becoming likelier to be the one who's there.
#
# Three strategies, kept selectable via DEFENSIVE_POOL_STRATEGY so
# scripts/simulate_tactical_balance.py can A/B them against real match
# outcomes (see that script's report) — "uniform" is the original no-op
# behavior, kept only as the empirical baseline to compare against.
def _pool_uniform(contributors: list[Any], pool_size: int) -> list[Any]:
    return random.sample(contributors, pool_size)


def _pool_soft_bias(contributors: list[Any], pool_size: int) -> list[Any]:
    """Weighted sampling WITHOUT replacement of who gets EXCLUDED, weight
    proportional to rating rank (highest-rated = likeliest to be excluded
    first) — probabilistic, not deterministic, so the same defender isn't
    guaranteed to be benched by a given mentality every single time, but the
    picked defender's expected rating still measurably drops as pool_size
    shrinks."""
    ranked = sorted(contributors, key=lambda c: c.player.rating, reverse=True)
    n_exclude = len(ranked) - pool_size
    weights = [len(ranked) - i for i in range(len(ranked))]
    pool = list(ranked)
    for _ in range(n_exclude):
        idx = random.choices(range(len(pool)), weights=weights, k=1)[0]
        pool.pop(idx)
        weights.pop(idx)
    return pool


def _pool_hard_bias(contributors: list[Any], pool_size: int) -> list[Any]:
    """Deterministic: always keep the pool_size WEAKEST contributors, always
    excluding the strongest first. Maximum possible bias — an upper bound to
    compare the softer strategy against."""
    ranked = sorted(contributors, key=lambda c: c.player.rating, reverse=True)
    return ranked[len(ranked) - pool_size:]


_POOL_STRATEGIES: dict[str, Any] = {"uniform": _pool_uniform, "soft_bias": _pool_soft_bias, "hard_bias": _pool_hard_bias}
DEFENSIVE_POOL_STRATEGY = "soft_bias"


def defensive_pool(cards: list[Any], mentality: str, playstyle: str) -> list[Any]:
    """Spec §6.4: a transition moment's defensive duelist is drawn from a
    mentality-sized SUBSET of the team's real defensive-zone contributors,
    re-rolled fresh every call — never from a rating-adjusted version of the
    back line. "Defensive-zone contributors" = anyone with nonzero
    central_defence or wing_defence weight (CB/LB/RB/CDM, plus GK's small
    0.15 sliver — rarely picked in practice since weighted_pick still weights
    by that same small value). WHICH members make up the subset is decided by
    DEFENSIVE_POOL_STRATEGY (problem-1 fix, see above) — PARK_THE_BUS
    (fraction=1.00) always returns everyone regardless of strategy, matching
    its "keeps the full back line eligible" spec intent exactly."""
    contributors = [c for c in cards if zone_weight(c.player.position, "central_defence") > 0 or zone_weight(c.player.position, "wing_defence") > 0]
    if not contributors:
        return []

    fraction = SAMPLE_FRACTION[mentality]
    if playstyle == "HIGH_PRESS":
        fraction *= HIGH_PRESS_POOL_MULT

    pool_size = max(1, min(len(contributors), round(fraction * len(contributors))))
    if pool_size >= len(contributors):
        return list(contributors)
    return _POOL_STRATEGIES[DEFENSIVE_POOL_STRATEGY](contributors, pool_size)


# --- Counter-attack chain (spec §6.5) ----------------------------------------


@dataclass
class ClubTacticalSide:
    cards: list[Any]
    profile: TeamTacticalProfile
    mentality: str
    playstyle: str
    coach: "Coach | None" = None


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

    y_boosts = resolve_active_boosts(y.coach)
    transition_bonus = transition_bonus_for(y.playstyle, TRANSITION_BONUS[y.playstyle], y_boosts)
    midfield_for_pass = y.profile.midfield_control + first_pass_input_bonus(y_boosts)
    eff_y = y_duelist.player.rating * position_fit(y_duelist.player.position, zone) * transition_bonus * _first_pass_quality_factor(midfield_for_pass)
    eff_x = x_duelist.player.rating * position_fit(x_duelist.player.position, defence_zone)
    total = eff_y + eff_x
    raw_ratio = eff_y / total if total else 0.5
    shifted = max(0.05, min(0.95, raw_ratio - defender_ratio_shift_for(x)))
    ratio = _amplify(shifted)

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


# --- Fix for STATUS problem 2 (POSSESSION/HIGH_PRESS had no compensating
# formula, only spec prose) ---------------------------------------------------
# POSSESSION's "rewards a strong midfield by extending phases (more Stage-2
# attempts per won initiative)": possession_buildup_survives already punishes
# a weak midfield (the other half of spec §8's sentence); this is the reward
# half — a strong-midfield POSSESSION team that STALLS at Stage 1 (not a
# breakdown — they didn't lose the ball, just didn't break through yet) gets
# one immediate re-attempt with freshly picked duelists, scaled the same way
# possession_buildup_survives is (0 at a 58-rated midfield, up to a capped
# ceiling at 99) so this never triggers for a middling-strength midfield.
# Raised 0.5 -> 0.65 on 2026-09-07 as part of the playstyle RPS rebalance —
# POSSESSION had become the weakest style once RATIO_AMPLIFICATION's own
# reduction (see below) diluted its retry mechanic's leverage too.
POSSESSION_RETRY_MAX = 0.65


def possession_retry_chance(midfield_control: float) -> float:
    return max(0.0, min(POSSESSION_RETRY_MAX, (midfield_control - 58) / (99 - 58) * POSSESSION_RETRY_MAX))


# HIGH_PRESS "forces more opponent breakdowns": passed as zone_ratio's
# ratio_shift when the DEFENDING side is HIGH_PRESS, in the normal
# (non-transition) Stage-1 duel — previously HIGH_PRESS had zero effect on an
# opponent's own progression attempt; its only real lever was its own pool
# shrinking (defensive_pool's ×0.85 stack), which is about exposure when
# HIGH_PRESS is caught out, not about forcing turnovers as the spec claims.
#
# Set to 0.0 on 2026-09-07 as part of the playstyle rock-paper-scissors
# rebalance (see TRANSITION_BONUS's COUNTER_ATTACK note): any positive value
# here immediately reversed COUNTER_ATTACK's edge over HIGH_PRESS (even 0.02
# was enough to flip a clean 41/38 COUNTER win into a 43/35 HIGH_PRESS win),
# because it applies to EVERY duel HIGH_PRESS defends, not just the specific
# transition moments COUNTER_ATTACK exploits — there's no way to boost
# HIGH_PRESS broadly without also blunting its one real counter. Per explicit
# user priority ("no single style should beat every other one"), this stays
# at 0.0; HIGH_PRESS still has real defensive identity via its own transition
# bonus and defensive_pool shrink, just not this extra lever. Known trade-off:
# spec item 6's "HIGH_PRESS forces more breakdowns than BALANCED against a
# weak-midfield POSSESSION opponent" no longer holds in isolation (the two
# were measured statistically indistinguishable — see
# test_high_press_forces_more_breakdowns_than_balanced_against_weak_midfield_possession's
# updated assertion).
HIGH_PRESS_DEFENSE_SHIFT = 0.0

# Third component of the problem-1 fix, added after simulation showed the
# other two (ratio amplification + pool-bias, everywhere) still weren't
# enough: PARK_THE_BUS's low initiative_mult means it concedes roughly 40%
# MORE total opponent phases than ATTACKING does against the same fixed
# opponent (measured via scripts/simulate_tactical_balance.py) — a
# structural volume effect that a few rating-points' worth of pool-bias on
# the picked defender cannot offset. Spec §7 states mentality's entire
# structural effect should be JUST initiative_mult + sample_fraction ("no
# separate exposure multiplier layered on top") — but that design, exactly
# as specified, empirically cannot make PARK_THE_BUS concede fewer goals
# than ATTACKING against identical defenders, which is the spec's own
# explicit goal (§6.5's worked example). This direct per-phase defensive
# ratio shift is a deliberate departure from §7 to actually achieve what §7
# was trying to achieve — "packing men behind the ball" reads as harder to
# break down structurally, not a rating change to any individual card.
#
# A fixed ratio-point shift (not a rating multiplier — see zone_ratio's own
# docstring for why a multiplier was abandoned: at the magnitude needed, it
# let a 58-rated worst-possible defender beat a 99-rated best-possible
# attacker purely from mentality). Calibrated on 2026-09-07 against three
# explicit targets: (1) PARK_THE_BUS still concedes clearly less than
# ATTACKING for identical weak defenders vs an elite attacker (the original
# problem-1 goal), (2) a ~20-point squad rating gap narrows from the
# neutral-tactics ~80/20 split down toward ~66/33 when the stronger side
# plays a mismatched mentality and the weaker side plays its best one (per
# explicit user calibration), (3) an extreme single duel (e.g. 99 vs 58)
# still clearly favors the better-rated player regardless of mentality —
# zone_ratio's [0.05, 0.95] clamp guarantees this last one structurally.
MENTALITY_DEFENSE_SHIFT: dict[str, float] = {"PARK_THE_BUS": 0.16, "DEFENSIVE": 0.09, "BALANCED": 0.0, "ATTACKING": -0.07}


def defender_ratio_shift_for(defender: "ClubTacticalSide") -> float:
    shift = MENTALITY_DEFENSE_SHIFT[defender.mentality]
    if defender.playstyle == "HIGH_PRESS":
        shift += HIGH_PRESS_DEFENSE_SHIFT
    return defensive_shift_for(defender.mentality, shift, resolve_active_boosts(defender.coach))


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


def build_side(
    cards_with_slots: list[tuple[Any, Any]], mentality: str, playstyle: str,
    coach: "Coach | None" = None, training_multiplier: float = 1.0,
) -> ClubTacticalSide:
    profile = compute_profile(cards_with_slots, coach=coach, training_multiplier=training_multiplier)
    cards = [card for card, _slot in cards_with_slots]
    return ClubTacticalSide(cards=cards, profile=profile, mentality=mentality, playstyle=playstyle, coach=coach)


# Second half of the problem-1 fix. The counter-attack chain (§6.5) already
# drew its defensive duelist from defensive_pool — but that sub-case only
# fires when the BUS side's OWN attack just broke down, which is rare
# precisely because a low initiative_mult means the bus side barely attacks
# in the first place. Simulation confirmed this: with the pool-bias applied
# ONLY there, PARK_THE_BUS still conceded MORE than ATTACKING against the
# same weak-defender squad (6.96 vs 5.88 GA/match) — ceding more total
# opponent phases (§6.1) completely swamped a benefit that almost never
# triggered. Applying the SAME mentality-shaped pool to the NORMAL Stage-1/
# Stage-2 defensive pick too (not just transitions) is a deliberate
# departure from spec §6.4's literal scoping ("before the counter-attack
# chain can pick a defensive duelist") — but §6.4's own stated intent
# ("mentality changes structure, not ratings") only actually holds together
# if it applies everywhere a mentality's own back line defends, not just its
# rarest sub-case. See scripts/simulate_tactical_balance.py's report for the
# comparison against the spec-literal, counter-chain-only scoping.
POOL_APPLIES_TO_NORMAL_DEFENSE = True


def _pick_defender(defender: ClubTacticalSide, defence_zone: str, exclude_ids: frozenset = frozenset()) -> Any:
    if not POOL_APPLIES_TO_NORMAL_DEFENSE:
        return weighted_pick(defender.cards, defence_zone, exclude_ids=exclude_ids)
    pool = defensive_pool(defender.cards, defender.mentality, defender.playstyle)
    return weighted_pick(pool, defence_zone, exclude_ids=exclude_ids)


def _resolve_progression_and_duel(attacker: ClubTacticalSide, defender: ClubTacticalSide, attacking_side: str, minute: int, config) -> Chance | None:
    zone = pick_progression_zone(attacker.playstyle)
    if zone is None:
        return None
    if attacker.playstyle == "POSSESSION" and not possession_buildup_survives(attacker.profile.midfield_control):
        return None

    defence_zone = "wing_defence" if zone == "wing_attack" else "central_defence"
    ratio_shift = defender_ratio_shift_for(defender)

    # Up to 2 attempts: the second is POSSESSION's problem-2 fix (see
    # possession_retry_chance) — a strong-midfield POSSESSION team that
    # merely stalled (didn't lose the ball) gets one fresh re-attempt with
    # newly picked duelists, extending how many real Stage-2 attempts a won
    # initiative produces. Every other playstyle always gets exactly 1.
    attacker_duelist = weighted_pick(attacker.cards, zone)
    defender_duelist = _pick_defender(defender, defence_zone)
    ratio_1 = zone_ratio(attacker_duelist, zone, defender_duelist, defence_zone, ratio_shift)
    outcome_1 = resolve_stage1(ratio_1)

    if (
        outcome_1 == "stall"
        and attacker.playstyle == "POSSESSION"
        and random.random() < possession_retry_chance(attacker.profile.midfield_control)
    ):
        attacker_duelist = weighted_pick(attacker.cards, zone)
        defender_duelist = _pick_defender(defender, defence_zone)
        ratio_1 = zone_ratio(attacker_duelist, zone, defender_duelist, defence_zone, ratio_shift)
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
    defender_second = _pick_defender(defender, defence_zone, exclude_ids=frozenset({defender_duelist.id}))
    ratio_2 = zone_ratio(attacker_second, zone, defender_second, defence_zone, ratio_shift)
    combined_advantage = (ratio_1 + ratio_2) / 2
    quality = resolve_quality(combined_advantage)
    shot_type = _pick_shot_type(config)
    return Chance(
        attacking_side=attacking_side, minute=minute, quality=quality, shot_type=shot_type, is_box=(shot_type == "in_box"),
        shooter=_card_to_actor(attacker_duelist), pass_target=_card_to_actor(attacker_second), defender=_card_to_actor(defender_second),
    )


def simulate_phase(minute: int, side_a: ClubTacticalSide, side_b: ClubTacticalSide, config) -> Chance | None:
    p_a_initiative = initiative_probability(side_a, side_b)
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
