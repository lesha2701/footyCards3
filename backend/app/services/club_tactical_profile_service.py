from dataclasses import dataclass
from typing import Any

from app.models.enums import Position
from app.services.lineup_service import FormationSlot, calculate_base_strength

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


def compute_profile(cards_with_slots: list[tuple[Any, FormationSlot]]) -> TeamTacticalProfile:
    zone_values: dict[str, float] = {}
    for zone in ZONES:
        weighted_sum = 0.0
        weight_total = 0.0
        for card, _slot in cards_with_slots:
            weight = zone_weight(card.player.position, zone)
            if weight > 0:
                weighted_sum += card.player.rating * weight
                weight_total += weight
        zone_values[zone] = round(weighted_sum / weight_total, 1) if weight_total > 0 else 0.0

    return TeamTacticalProfile(team_strength=calculate_base_strength(cards_with_slots), **zone_values)
