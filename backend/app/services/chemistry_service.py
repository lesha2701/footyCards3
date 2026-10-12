"""«Химия карточек» — links between NEIGHBOURING slots of a formation
(FIFA-style), replacing the old whole-squad «most common club/country»
bonus when GameConfig.chemistry_enabled is on.

Pure module: no DB access, deterministic. Every number comes from
ChemistryRules (built from GameConfig by rules_from_config); the frontend's
lib/chemistry.ts mirrors compute_chemistry exactly, and both are checked
against the same fixture (frontend/src/test/chemistryCases.json, see
tests/test_chemistry.py and frontend/src/test/chemistry.test.ts).

Rules:
  * Link between two adjacent FILLED slots: same club AND same country =
    strong (rules.link_strong points), club OR country = medium
    (rules.link_medium), neither = none (0).
  * Player chemistry (0..rules.player_max): on his slot's ideal position —
    the number of thresholds his link sum reaches, raised to at least
    rules.player_floor; off his ideal position — 0, regardless of links
    (his links still count for his neighbours).
  * Rating bonus in matches: points × rules.rating_per_point, minus
    rules.off_position_penalty when off the ideal position. Applied to the
    card's match rating only (the displayed card rating never changes), and
    the result is kept within 1..99.
  * Team chemistry = sum of player chemistry, out of player_max × slots.

Application order (see lineup_service.calculate_base_strength and
player_tournament_simulation_service._build_side): card rating + diamond
bonus → + chemistry bonus (capped at 99) → position fit / rarity / tactic
multipliers or zone profile → coach (rarity team bonus / zone boosts) →
stadium & training multipliers. Card skills are separate per-event rolls
and never read the rating, so nothing is counted twice; the old flat
club/country bonus is NOT added when the new chemistry is on.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable

LINK_NONE = "none"
LINK_MEDIUM = "medium"
LINK_STRONG = "strong"

# Adjacency per formation: slot codes are the ones in
# club_formation_service.CLUB_FORMATIONS (lineup_service.FORMATION_SLOTS is
# the same 4-3-3 code set). Edges follow how the editors lay the pitch out
# (one row per line, slots left-to-right in code order), so a drawn line
# always connects two cards that look adjacent.
FORMATION_LINKS: dict[str, tuple[tuple[str, str], ...]] = {
    "4-3-3": (
        ("GK", "DEF2"), ("GK", "DEF3"),
        ("DEF1", "DEF2"), ("DEF2", "DEF3"), ("DEF3", "DEF4"),
        ("DEF1", "MID1"), ("DEF2", "MID2"), ("DEF3", "MID2"), ("DEF4", "MID3"),
        ("MID1", "MID2"), ("MID2", "MID3"),
        ("MID1", "FWD1"), ("MID2", "FWD2"), ("MID3", "FWD3"),
        ("FWD1", "FWD2"), ("FWD2", "FWD3"),
    ),
    "4-4-2": (
        ("GK", "DEF2"), ("GK", "DEF3"),
        ("DEF1", "DEF2"), ("DEF2", "DEF3"), ("DEF3", "DEF4"),
        ("DEF1", "MID1"), ("DEF2", "MID2"), ("DEF3", "MID3"), ("DEF4", "MID4"),
        ("MID1", "MID2"), ("MID2", "MID3"), ("MID3", "MID4"),
        ("MID1", "FWD1"), ("MID2", "FWD1"), ("MID3", "FWD2"), ("MID4", "FWD2"),
        ("FWD1", "FWD2"),
    ),
    "3-5-2": (
        ("GK", "DEF1"), ("GK", "DEF2"), ("GK", "DEF3"),
        ("DEF1", "DEF2"), ("DEF2", "DEF3"),
        ("DEF1", "MID1"), ("DEF1", "MID2"), ("DEF2", "MID3"), ("DEF3", "MID4"), ("DEF3", "MID5"),
        ("MID1", "MID2"), ("MID2", "MID3"), ("MID3", "MID4"), ("MID4", "MID5"),
        ("MID1", "FWD1"), ("MID2", "FWD1"), ("MID4", "FWD2"), ("MID5", "FWD2"),
        ("FWD1", "FWD2"),
    ),
    "5-3-2": (
        ("GK", "DEF2"), ("GK", "DEF3"), ("GK", "DEF4"),
        ("DEF1", "DEF2"), ("DEF2", "DEF3"), ("DEF3", "DEF4"), ("DEF4", "DEF5"),
        ("DEF1", "MID1"), ("DEF2", "MID1"), ("DEF3", "MID2"), ("DEF4", "MID3"), ("DEF5", "MID3"),
        ("MID1", "MID2"), ("MID2", "MID3"),
        ("MID1", "FWD1"), ("MID2", "FWD1"), ("MID2", "FWD2"), ("MID3", "FWD2"),
        ("FWD1", "FWD2"),
    ),
}

MAX_RATING = 99


@dataclass(frozen=True)
class ChemistryRules:
    link_strong: int = 2
    link_medium: int = 1
    thresholds: tuple[int, int, int] = (1, 2, 4)
    player_max: int = 3
    player_floor: int = 0
    rating_per_point: int = 1
    off_position_penalty: int = 0

    def as_dict(self) -> dict:
        return {
            "link_strong": self.link_strong, "link_medium": self.link_medium,
            "thresholds": list(self.thresholds), "player_max": self.player_max,
            "player_floor": self.player_floor, "rating_per_point": self.rating_per_point,
            "off_position_penalty": self.off_position_penalty,
        }


def rules_from_config(config) -> ChemistryRules:
    return ChemistryRules(
        link_strong=int(config.chemistry_link_strong),
        link_medium=int(config.chemistry_link_medium),
        thresholds=tuple(sorted((
            int(config.chemistry_threshold_1), int(config.chemistry_threshold_2), int(config.chemistry_threshold_3),
        ))),
        player_max=int(config.chemistry_player_max),
        player_floor=int(config.chemistry_player_floor),
        rating_per_point=int(config.chemistry_rating_per_point),
        off_position_penalty=int(config.chemistry_off_position_penalty),
    )


def rules_from_dict(data: dict | None) -> ChemistryRules | None:
    """Inverse of ChemistryRules.as_dict (rules frozen on a tournament row)."""
    if not data:
        return None
    return ChemistryRules(
        link_strong=int(data["link_strong"]), link_medium=int(data["link_medium"]),
        thresholds=tuple(sorted(int(t) for t in data["thresholds"])), player_max=int(data["player_max"]),
        player_floor=int(data["player_floor"]), rating_per_point=int(data["rating_per_point"]),
        off_position_penalty=int(data["off_position_penalty"]),
    )


def active_rules(config) -> ChemistryRules | None:
    """None = the mechanic is off and every caller keeps the old formula."""
    return rules_from_config(config) if config is not None and getattr(config, "chemistry_enabled", False) else None


def _group_key(value) -> str | None:
    # Same whitespace normalisation as lineup_service.clean_group_key; an
    # empty club/country never links.
    if not isinstance(value, str):
        return value
    cleaned = " ".join(value.split())
    return cleaned or None


def link_level(player_a, player_b) -> str:
    club_a, club_b = _group_key(player_a.club), _group_key(player_b.club)
    country_a, country_b = _group_key(player_a.country), _group_key(player_b.country)
    same_club = club_a is not None and club_a == club_b
    same_country = country_a is not None and country_a == country_b
    if same_club and same_country:
        return LINK_STRONG
    if same_club or same_country:
        return LINK_MEDIUM
    return LINK_NONE


def link_points(level: str, rules: ChemistryRules) -> int:
    if level == LINK_STRONG:
        return rules.link_strong
    if level == LINK_MEDIUM:
        return rules.link_medium
    return 0


@dataclass(frozen=True)
class ChemistryLink:
    a: str
    b: str
    level: str
    points: int


@dataclass(frozen=True)
class PlayerChemistry:
    slot_code: str
    points: int
    link_sum: int
    on_position: bool
    rating_bonus: int


@dataclass
class ChemistryResult:
    formation: str
    links: list[ChemistryLink] = field(default_factory=list)
    players: dict[str, PlayerChemistry] = field(default_factory=dict)
    team: int = 0
    team_max: int = 0

    def rating_bonus(self, slot_code: str) -> int:
        p = self.players.get(slot_code)
        return p.rating_bonus if p is not None else 0


def player_points(link_sum: int, on_position: bool, rules: ChemistryRules) -> int:
    if not on_position:
        return 0
    cap = max(0, rules.player_max)
    reached = sum(1 for t in rules.thresholds if link_sum >= t)
    return min(cap, max(min(rules.player_floor, cap), reached))


def compute_chemistry(
    cards_with_slots: Iterable[tuple[Any, Any]], formation: str, rules: ChemistryRules, slot_count: int | None = None,
) -> ChemistryResult:
    """cards_with_slots: (card-like with .player.{club,country,position},
    FormationSlot) pairs — UserCard, the tournament _EngineCard adapter and
    SimpleNamespace stand-ins all work. Empty slots simply have no links.
    slot_count: the formation's total slot count for team_max (defaults to
    the number of filled slots)."""
    pairs = list(cards_with_slots)
    by_code = {slot.code: card for card, slot in pairs}
    result = ChemistryResult(formation=formation)
    link_sums = {code: 0 for code in by_code}
    for a, b in FORMATION_LINKS.get(formation, ()):
        if a in by_code and b in by_code:
            level = link_level(by_code[a].player, by_code[b].player)
            pts = link_points(level, rules)
            result.links.append(ChemistryLink(a=a, b=b, level=level, points=pts))
            link_sums[a] += pts
            link_sums[b] += pts
    for card, slot in pairs:
        on_position = card.player.position == slot.ideal_position
        pts = player_points(link_sums[slot.code], on_position, rules)
        bonus = pts * rules.rating_per_point - (0 if on_position else rules.off_position_penalty)
        result.players[slot.code] = PlayerChemistry(
            slot_code=slot.code, points=pts, link_sum=link_sums[slot.code], on_position=on_position, rating_bonus=bonus,
        )
    result.team = sum(p.points for p in result.players.values())
    result.team_max = max(0, rules.player_max) * (slot_count if slot_count is not None else len(pairs))
    return result


def boosted_rating(rating: int | float, bonus: int) -> int | float:
    """Match rating with the chemistry bonus, kept within 1..99 — never used
    for the rating shown on the card itself."""
    if not bonus:
        return rating
    return max(1, min(MAX_RATING, rating + bonus))


def to_out(result: ChemistryResult | None, rules: ChemistryRules | None, strength_bonus: int | None = None) -> dict:
    """Serialized form shared by every lineup response (schemas.chemistry.ChemistryOut).
    strength_bonus: how much the chemistry adds to the team strength shown
    for this lineup (None where the mode has no single strength number);
    with the mechanic off it is the old flat club/country bonus."""
    if result is None or rules is None:
        return {"enabled": False, "strength_bonus": strength_bonus}
    return {
        "enabled": True,
        "strength_bonus": strength_bonus,
        "formation": result.formation,
        "team": result.team,
        "team_max": result.team_max,
        "links": [{"a": l.a, "b": l.b, "level": l.level, "points": l.points} for l in result.links],
        "players": [
            {"slot_code": p.slot_code, "points": p.points, "link_sum": p.link_sum, "on_position": p.on_position,
             "rating_bonus": p.rating_bonus}
            for p in result.players.values()
        ],
        "adjacency": [list(edge) for edge in FORMATION_LINKS.get(result.formation, ())],
        "rules": rules.as_dict(),
    }
