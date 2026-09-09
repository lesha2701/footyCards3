from dataclasses import dataclass, field

from app.models.coach import Coach
from app.models.enums import CoachBoostType, Rarity

# This module is deliberately a one-way leaf: it imports nothing from
# club_tactical_profile_service.py / club_tactical_matchup_service.py /
# match_service.py. A later phase makes those three modules call INTO
# this one (passing their own base values as plain parameters) — if this
# module imported back from any of them, that would be a circular import
# the moment that wiring lands.


@dataclass(frozen=True)
class ActiveCoachBoosts:
    by_type: dict[CoachBoostType, float] = field(default_factory=dict)


def resolve_active_boosts(coach: Coach | None) -> ActiveCoachBoosts:
    """coach=None (nothing equipped) returns an empty ActiveCoachBoosts, so
    every function below needs zero special-casing for "no coach".

    `float(b.magnitude)` matters here, not stylistically: CoachBoost.magnitude
    is a `Numeric` column, which SQLAlchemy returns as `decimal.Decimal`, not
    `float`, once a Coach is loaded from a real database (this module's own
    unit tests never round-trip through a DB, so they cannot catch this —
    every `Coach`/`CoachBoost` in test_coach_boost_service.py is a bare
    in-memory object, never flushed). Mixing `Decimal` into this module's
    plain-float arithmetic (`base_shift + offset`, etc.) would raise
    `TypeError` the moment a later phase calls this against a real DB-backed
    Coach. Casting once, right here, is this codebase's own established
    pattern for the identical gotcha — see `float(p.probability)` in
    `pack_service.roll_rarities`."""
    if coach is None:
        return ActiveCoachBoosts(by_type={})
    return ActiveCoachBoosts(by_type={b.boost_type: float(b.magnitude) for b in coach.boosts})


_ZONE_TO_BOOST_TYPE: dict[str, CoachBoostType] = {
    "central_attack": CoachBoostType.ATTACK_CENTRAL,
    "wing_attack": CoachBoostType.ATTACK_WING,
    "midfield_control": CoachBoostType.MIDFIELD_CONTROL,
    "central_defence": CoachBoostType.DEFENCE_CENTRAL,
    "wing_defence": CoachBoostType.DEFENCE_WING,
    "goalkeeping": CoachBoostType.GOALKEEPING,
}


def apply_zone_boosts(zone_values: dict[str, float], boosts: ActiveCoachBoosts) -> dict[str, float]:
    """Tournament hook — compute_profile's 6 zones, spec §5 items 1-6."""
    return {
        zone: value + boosts.by_type.get(_ZONE_TO_BOOST_TYPE[zone], 0.0)
        for zone, value in zone_values.items()
    }


def depth_bonus_cap_for(base_cap: float, boosts: ActiveCoachBoosts) -> float:
    """Tournament hook — spec §5 item 11 (SQUAD_STABILITY)."""
    return base_cap + boosts.by_type.get(CoachBoostType.SQUAD_STABILITY, 0.0)


def initiative_mult_for(base_mult: float, boosts: ActiveCoachBoosts) -> float:
    """Tournament hook — spec §5 item 8 (BALL_CONTROL)."""
    return base_mult + boosts.by_type.get(CoachBoostType.BALL_CONTROL, 0.0)


def defensive_shift_for(mentality: str, base_shift: float, boosts: ActiveCoachBoosts) -> float:
    """Tournament hook — spec §5 item 9 (DEFENSIVE_DISCIPLINE), only for
    ATTACKING mentality, clamped so the result never exceeds 0.0 (an
    ATTACKING-mentality team can never be pushed to defend as well as
    BALANCED purely by a coach — see this session's Phase 1 STATUS doc's
    "safety bug" writeup for why an uncapped bonus here would be unsafe)."""
    if mentality != "ATTACKING":
        return base_shift
    offset = boosts.by_type.get(CoachBoostType.DEFENSIVE_DISCIPLINE, 0.0)
    return min(0.0, base_shift + offset)


def transition_bonus_for(playstyle: str, base_bonus: float, boosts: ActiveCoachBoosts) -> float:
    """Tournament hook — spec §5 item 10 (COUNTER_MASTERY), only for
    COUNTER_ATTACK playstyle."""
    if playstyle != "COUNTER_ATTACK":
        return base_bonus
    return base_bonus + boosts.by_type.get(CoachBoostType.COUNTER_MASTERY, 0.0)


def first_pass_input_bonus(boosts: ActiveCoachBoosts) -> float:
    """Tournament hook — spec §5 item 7 (PASSING_ACCURACY), tournament
    half: added to midfield_control before _first_pass_quality_factor
    runs, per the spec — this function only resolves the bonus value, the
    call site itself is a later phase's job."""
    return boosts.by_type.get(CoachBoostType.PASSING_ACCURACY, 0.0)


_ARENA_CATEGORY_TO_BOOST_TYPE: dict[str, CoachBoostType] = {
    "FWD": CoachBoostType.ATTACK_CENTRAL,
    "DEF": CoachBoostType.DEFENCE_CENTRAL,
    "GK": CoachBoostType.GOALKEEPING,
}


def arena_category_bonus(category: str, boosts: ActiveCoachBoosts) -> int:
    """Arena hook — spec §5 items 1/4/6's Arena half (FWD/DEF/GK category
    averages). Any other category (e.g. "MID", which Arena doesn't even
    have) resolves to 0, never raises."""
    boost_type = _ARENA_CATEGORY_TO_BOOST_TYPE.get(category)
    if boost_type is None:
        return 0
    return round(boosts.by_type.get(boost_type, 0.0))


def arena_pass_fail_chance_reduction(boosts: ActiveCoachBoosts) -> float:
    """Arena hook — spec §5 item 7's Arena half (percentage points to
    subtract from match_pass_fail_chance_min/max)."""
    return boosts.by_type.get(CoachBoostType.PASSING_ACCURACY, 0.0)


def arena_team_strength_bonus(boosts: ActiveCoachBoosts) -> int:
    """Arena hook — spec §5 item 3's Arena stand-in (MIDFIELD_CONTROL has
    no Arena category of its own, so it bumps team_strength directly)."""
    return round(boosts.by_type.get(CoachBoostType.MIDFIELD_CONTROL, 0.0))


# Starting-point numbers on the same scale this codebase already uses for
# zone-boost base_units (spec §4: common=1 tier -> 2 rating points, up to
# legendary=4 tier -> 8) — not validated by simulation yet, same "starting
# point, not final" caveat every other magnitude in this match engine
# carries until it's been through a real balance pass.
_ARENA_RARITY_TEAM_STRENGTH_BONUS: dict[Rarity, int] = {
    Rarity.common: 2,
    Rarity.rare: 4,
    Rarity.epic: 6,
    Rarity.legendary: 8,
}


def arena_rarity_team_strength_bonus(coach: "Coach | None") -> int:
    """A simple, universal Card Arena squad-power bonus scaled only by the
    equipped coach's own rarity — independent of which specific boosts it
    has. This is a deliberately simpler, first-cut mechanic than
    arena_category_bonus/arena_pass_fail_chance_reduction/
    arena_team_strength_bonus above (which read individual boost types via
    ActiveCoachBoosts) — those remain in place for a future full-fidelity
    Arena pass; this function only ever reads .rarity, never .boosts."""
    if coach is None:
        return 0
    return _ARENA_RARITY_TEAM_STRENGTH_BONUS.get(coach.rarity, 0)
