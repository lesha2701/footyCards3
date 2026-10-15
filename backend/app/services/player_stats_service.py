from app.models.enums import Position

# How far a position's Attack/Defense split leans from the base `rating`,
# in points. Central midfield (CM) is the balanced pivot — both stats equal
# rating there. Everything else leans toward attack or defense depending on
# its real-football role.
_SKEW: dict[Position, int] = {
    Position.GK: 18,
    Position.CB: 14,
    Position.LB: 8,
    Position.LWB: 4,
    Position.RWB: 4,
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

_DEFENSIVE_POSITIONS = {Position.GK, Position.CB, Position.LB, Position.RB, Position.LWB, Position.RWB, Position.CDM}


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


def card_rating_bonus(card) -> int:
    """Everything a specific owned copy adds to its player's rating: the
    diamond upgrade (diamond cards only), earned stars (non-diamond only,
    services/card_star_service.py) and «Начало пути» levels (path cards
    only, services/path_service.py). All are fixed on the card row when
    earned. getattr: also called with ClubCard rows and lightweight
    stand-ins that carry none of these columns."""
    return (
        (getattr(card, "diamond_rating_bonus", 0) or 0) + (getattr(card, "star_rating_bonus", 0) or 0)
        + (getattr(card, "path_rating_bonus", 0) or 0)
    )


def effective_card_stats(player, diamond_rating_bonus: int) -> tuple[int, int, int]:
    """A card's real (rating, attack, defense) for display and gameplay.

    `diamond_rating_bonus` is the copy's whole rating bonus — pass
    card_rating_bonus(card) (diamond upgrade + stars). With no bonus this is
    just the template's own values (falling back attack/defense to rating,
    same as PlayerOut does for rows predating those columns). A boosted
    card's rating grows by its bonus (capped at 99, the same ceiling every
    other card is clamped to), and attack/defense scale by the same ratio
    the rating grew by — preserving that specific card's own designed
    attack/defense split rather than sliding it onto the generic position
    curve above."""
    # getattr, not direct access: this is also called via calculate_base_strength
    # with club_tactical_profile_service.py's lighter-weight player stand-ins,
    # which carry rating/position/rarity/club/country but not attack/defense.
    base_attack = getattr(player, "attack_rating", None) or player.rating
    base_defense = getattr(player, "defense_rating", None) or player.rating

    if diamond_rating_bonus <= 0:
        return player.rating, base_attack, base_defense

    new_rating = min(99, player.rating + diamond_rating_bonus)
    ratio = new_rating / player.rating

    def clamp(value: float) -> int:
        return max(1, min(99, round(value)))

    return new_rating, clamp(base_attack * ratio), clamp(base_defense * ratio)
