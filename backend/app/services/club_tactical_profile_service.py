from dataclasses import dataclass
from typing import Any

from app.models.coach import Coach
from app.models.enums import Position
from app.services.coach_boost_service import apply_zone_boosts, depth_bonus_cap_for, resolve_active_boosts
from app.services.lineup_service import CATEGORY_POSITIONS, FormationSlot, calculate_base_strength

ZONES = ("central_attack", "wing_attack", "midfield_control", "central_defence", "wing_defence", "goalkeeping")

# Verbatim from design spec §5. Every position that appears as an
# `ideal_position` in any CLUB_FORMATIONS slot (Task 1) has an entry here;
# test_zone_weights_cover_every_position_used_in_any_formation enforces this.
ZONE_WEIGHTS: dict[Position, dict[str, float]] = {
    Position.GK: {"central_defence": 0.15, "wing_defence": 0.15, "goalkeeping": 1.00},
    Position.CB: {"midfield_control": 0.10, "central_defence": 1.00, "wing_defence": 0.25},
    Position.LB: {"wing_attack": 0.55, "midfield_control": 0.10, "central_defence": 0.20, "wing_defence": 1.00},
    Position.RB: {"wing_attack": 0.55, "midfield_control": 0.10, "central_defence": 0.20, "wing_defence": 1.00},
    Position.CDM: {"central_attack": 0.05, "midfield_control": 0.85, "central_defence": 0.45, "wing_defence": 0.15},
    Position.CM: {"central_attack": 0.20, "wing_attack": 0.05, "midfield_control": 1.00, "central_defence": 0.10},
    Position.CAM: {"central_attack": 0.60, "wing_attack": 0.10, "midfield_control": 0.55},
    Position.LM: {"central_attack": 0.10, "wing_attack": 0.85, "midfield_control": 0.35, "wing_defence": 0.20},
    Position.RM: {"central_attack": 0.10, "wing_attack": 0.85, "midfield_control": 0.35, "wing_defence": 0.20},
    Position.LW: {"central_attack": 0.65, "wing_attack": 1.00, "wing_defence": 0.05},
    Position.RW: {"central_attack": 0.65, "wing_attack": 1.00, "wing_defence": 0.05},
    Position.ST: {"central_attack": 1.00, "wing_attack": 0.10},
}


def zone_weight(position: Position, zone: str) -> float:
    return ZONE_WEIGHTS.get(position, {}).get(zone, 0.0)


# Discretizes the continuous ZONE_WEIGHTS table into the same 1.0/0.9/0.85-
# shaped fit concept calculate_base_strength already uses per formation slot
# (spec §6.3) — reapplied per zone instead. Thresholds: the zone's own
# primary position(s) (weight == 1.00) get full credit; a strong natural
# contributor (weight >= 0.5) gets 0.9; anything present but weakly relevant
# (0 < weight < 0.5) gets 0.85; zero weight means not eligible for this zone.
def position_fit(position: Position, zone: str) -> float:
    weight = zone_weight(position, zone)
    if weight >= 1.00:
        return 1.0
    if weight >= 0.5:
        return 0.9
    if weight > 0.0:
        return 0.85
    return 0.0


@dataclass
class TeamTacticalProfile:
    central_attack: float
    wing_attack: float
    midfield_control: float
    central_defence: float
    wing_defence: float
    goalkeeping: float
    team_strength: int


# Fix for STATUS problem 3 ("formation choice is inert"): a plain weighted
# average is scale-invariant in contributor count by construction — 3-5-2's
# 5 midfield slots average to the exact same midfield_control as 4-3-3's 3
# at equal per-position ratings, contradicting spec §4's own claim that more
# genuine contributors should raise the zone. `weight_total` (the average's
# own denominator) is already the right depth signal: a zone fed by more/
# stronger-weighted slots has a higher weight_total (e.g. 3-5-2's 5 midfield
# slots sum to weight_total=3.10 for midfield_control vs 4-3-3's 3 slots
# summing to 2.40 — see club_tactical_matchup_service module docstring for
# the worked numbers). `weight_total - 1.0` is formation-agnostic (anchors
# the bonus at "zero once a single full-weight contributor exists", so a
# lone ST alone in central_attack gets none) and one-directional (clamped at
# 0, never penalizes a thin zone beyond what the average already reflects —
# only rewards genuine depth). The cap keeps it a minor structural nudge
# (bounded well inside the 58-99 rating scale §5 requires this to "read like
# a rating"), not a dominant term.
DEPTH_BONUS_SCALE = 2.0
DEPTH_BONUS_CAP = 6.0


def compute_profile(cards_with_slots: list[tuple[Any, FormationSlot]], coach: "Coach | None" = None) -> TeamTacticalProfile:
    boosts = resolve_active_boosts(coach)
    depth_cap = depth_bonus_cap_for(DEPTH_BONUS_CAP, boosts)

    zone_values: dict[str, float] = {}
    for zone in ZONES:
        weighted_sum = 0.0
        weight_total = 0.0
        for card, _slot in cards_with_slots:
            weight = zone_weight(card.player.position, zone)
            if weight > 0:
                weighted_sum += card.player.rating * weight
                weight_total += weight
        if weight_total > 0:
            base_avg = weighted_sum / weight_total
            depth_bonus = max(0.0, min(depth_cap, DEPTH_BONUS_SCALE * (weight_total - 1.0)))
            zone_values[zone] = round(min(99.0, base_avg + depth_bonus), 1)
        else:
            zone_values[zone] = 0.0

    zone_values = apply_zone_boosts(zone_values, boosts)
    zone_values = {zone: round(min(99.0, value), 1) for zone, value in zone_values.items()}

    return TeamTacticalProfile(team_strength=calculate_base_strength(cards_with_slots), **zone_values)


# Which zone(s) each playstyle actually leans on — used by playstyle_alignment
# below to check whether a squad's chosen playstyle plays to its OWN strongest
# zones, independent of how strong the squad is in absolute terms (spec §9).
PLAYSTYLE_ZONES: dict[str, tuple[str, ...]] = {
    "WING_PLAY": ("wing_attack", "wing_defence"),
    "CENTRAL_PLAY": ("central_attack", "midfield_control"),
    "POSSESSION": ("midfield_control",),
    "HIGH_PRESS": ("midfield_control", "wing_defence"),
    "COUNTER_ATTACK": ("central_attack", "wing_attack"),
}


def _formation_fit_score(cards_with_slots: list[tuple[Any, FormationSlot]]) -> float:
    """Average of the same 1.0/0.9/0.75 per-slot fit calculate_base_strength
    uses, normalized from its [0.75, 1.0] range into [0, 1] — a squad using
    every slot's ideal position scores 1.0, a squad using only category-legal
    but off-position players throughout scores 0.0."""
    if not cards_with_slots:
        return 0.0
    fits = []
    for card, slot in cards_with_slots:
        if card.player.position == slot.ideal_position:
            fits.append(1.0)
        elif card.player.position in CATEGORY_POSITIONS[slot.category]:
            fits.append(0.9)
        else:
            fits.append(0.75)
    avg_fit = sum(fits) / len(fits)
    return max(0.0, min(1.0, (avg_fit - 0.75) / (1.0 - 0.75)))


def _playstyle_alignment(profile: TeamTacticalProfile, playstyle: str) -> float:
    """Ranks this squad's 6 zones best-to-worst and scores how highly the
    playstyle's target zone(s) rank — 1.0 if they're this squad's very best
    zone(s), 0.0 if they're the worst, regardless of the squad's absolute
    strength (spec §9: "is the zone(s) this playstyle uses actually this
    squad's STRONGEST zone(s)?")."""
    zone_values = {zone: getattr(profile, zone) for zone in ZONES}
    ranked = sorted(zone_values, key=zone_values.get, reverse=True)
    target_zones = PLAYSTYLE_ZONES[playstyle]
    scores = [1 - (ranked.index(zone) / (len(ranked) - 1)) for zone in target_zones]
    return sum(scores) / len(scores)


# target[mentality]: where PARK_THE_BUS/DEFENSIVE want (defence − attack) to
# lean positive, ATTACKING wants it to lean negative, BALANCED wants it near
# zero. A 20-rating gap between defence and attack zones is treated as
# already a full lean (clamped to +/-1) — ratings run ~58-99, so 20 points is
# a large, clearly-intentional squad shape rather than incidental variance.
_MENTALITY_FIT_TARGET = {"PARK_THE_BUS": 1.0, "DEFENSIVE": 0.5, "BALANCED": 0.0, "ATTACKING": -1.0}


def _mentality_fit(profile: TeamTacticalProfile, mentality: str) -> float:
    defence_avg = (profile.central_defence + profile.wing_defence) / 2
    attack_avg = (profile.central_attack + profile.wing_attack) / 2
    gap = max(-1.0, min(1.0, (defence_avg - attack_avg) / 20))
    target = _MENTALITY_FIT_TARGET[mentality]
    return max(0.0, 1 - abs(gap - target) / 2)


def compute_tactical_fit(
    cards_with_slots: list[tuple[Any, FormationSlot]], profile: TeamTacticalProfile, mentality: str, playstyle: str, config
) -> int:
    formation_component = _formation_fit_score(cards_with_slots) * float(config.club_tactical_fit_formation_weight)
    playstyle_component = _playstyle_alignment(profile, playstyle) * float(config.club_tactical_fit_playstyle_weight)
    mentality_component = _mentality_fit(profile, mentality) * float(config.club_tactical_fit_mentality_weight)
    return round(100 * (formation_component + playstyle_component + mentality_component))
