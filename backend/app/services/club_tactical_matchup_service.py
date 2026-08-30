import random
from dataclasses import dataclass, field
from typing import Any

from app.services.club_tactical_profile_service import TeamTacticalProfile

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
