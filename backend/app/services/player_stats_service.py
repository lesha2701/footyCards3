from app.models.enums import Position

# How far a position's Attack/Defense split leans from the base `rating`,
# in points. Central midfield (CM) is the balanced pivot — both stats equal
# rating there. Everything else leans toward attack or defense depending on
# its real-football role.
_SKEW: dict[Position, int] = {
    Position.GK: 18,
    Position.CB: 14,
    Position.LB: 8,
    Position.RB: 8,
    Position.CDM: 6,
    Position.CM: 0,
    Position.CAM: 8,
    Position.LM: 6,
    Position.RM: 6,
    Position.LW: 12,
    Position.RW: 12,
    Position.ST: 16,
}

_DEFENSIVE_POSITIONS = {Position.GK, Position.CB, Position.LB, Position.RB, Position.CDM}


def compute_default_attack_defense(rating: int, position: Position) -> tuple[int, int]:
    """Default Attack/Defense split for a player who doesn't have one set
    explicitly — leans away from `rating` by a position-specific amount,
    clamped to the same [1, 99] range as `rating` itself."""
    skew = _SKEW[position]
    if position in _DEFENSIVE_POSITIONS:
        attack, defense = rating - skew, rating + skew
    else:
        attack, defense = rating + skew, rating - skew

    def clamp(value: int) -> int:
        return max(1, min(99, value))

    return clamp(attack), clamp(defense)
