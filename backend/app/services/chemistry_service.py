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
  * Extras for an on-position player, added after the thresholds and
    capped at player_max: + rules.coach_country_points when his country
    equals the equipped coach's (Coach.country, «тренер-земляк»), and
    + rules.stadium_club_points when his club equals the equipped
    stadium's (Stadium.club, «домашний стадион») — the stadium extra only
    where the stadium itself applies (tournaments: the home side only;
    callers pass stadium_club=None for the away side).

Application order (see lineup_service.calculate_base_strength and
player_tournament_simulation_service._build_side): card rating + diamond
bonus → + chemistry bonus (capped at 99) → position fit / rarity / tactic
multipliers or zone profile → coach (rarity team bonus / zone boosts) →
stadium & training multipliers. Card skills are separate per-event rolls
and never read the rating, so nothing is counted twice; the old flat
club/country bonus is NOT added when the new chemistry is on.
"""

from dataclasses import dataclass, field
from types import SimpleNamespace
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
    "4-3-3H": (
        ("GK", "DEF2"), ("GK", "DEF3"),
        ("DEF1", "DEF2"), ("DEF2", "DEF3"), ("DEF3", "DEF4"),
        ("DEF1", "MID1"), ("DEF2", "MID2"), ("DEF3", "MID2"), ("DEF4", "MID3"),
        ("MID1", "MID2"), ("MID2", "MID3"),
        ("MID1", "FWD1"), ("MID1", "FWD2"), ("MID3", "FWD2"), ("MID3", "FWD3"),
        ("FWD1", "FWD2"), ("FWD2", "FWD3"),
    ),
    "4-2-3-1": (
        ("GK", "DEF2"), ("GK", "DEF3"),
        ("DEF1", "DEF2"), ("DEF2", "DEF3"), ("DEF3", "DEF4"),
        ("DEF1", "MID3"), ("DEF2", "MID1"), ("DEF3", "MID2"), ("DEF4", "MID5"),
        ("MID1", "MID2"), ("MID1", "MID4"), ("MID2", "MID4"),
        ("MID3", "MID4"), ("MID4", "MID5"),
        ("MID3", "FWD1"), ("MID4", "FWD1"), ("MID5", "FWD1"),
    ),
    "5-3-2": (
        ("GK", "DEF2"), ("GK", "DEF3"), ("GK", "DEF4"),
        ("DEF1", "DEF2"), ("DEF2", "DEF3"), ("DEF3", "DEF4"), ("DEF4", "DEF5"),
        ("DEF1", "MID1"), ("DEF2", "MID1"), ("DEF3", "MID2"), ("DEF4", "MID3"), ("DEF5", "MID3"),
        ("MID1", "MID2"), ("MID2", "MID3"),
        ("MID1", "FWD1"), ("MID2", "FWD1"), ("MID2", "FWD2"), ("MID3", "FWD2"),
        ("FWD1", "FWD2"),
    ),
    "3-4-3": (
        ("GK", "DEF1"), ("GK", "DEF2"), ("GK", "DEF3"),
        ("DEF1", "DEF2"), ("DEF2", "DEF3"), ("DEF1", "DEF4"), ("DEF3", "DEF5"),
        ("DEF2", "MID1"), ("DEF2", "MID2"),
        ("DEF4", "MID1"), ("MID1", "MID2"), ("MID2", "DEF5"),
        ("DEF4", "FWD1"), ("MID1", "FWD2"), ("MID2", "FWD2"), ("DEF5", "FWD3"),
        ("FWD1", "FWD2"), ("FWD2", "FWD3"),
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
    coach_country_points: int = 1
    stadium_club_points: int = 1

    def as_dict(self) -> dict:
        return {
            "link_strong": self.link_strong, "link_medium": self.link_medium,
            "thresholds": list(self.thresholds), "player_max": self.player_max,
            "player_floor": self.player_floor, "rating_per_point": self.rating_per_point,
            "off_position_penalty": self.off_position_penalty,
            "coach_country_points": self.coach_country_points, "stadium_club_points": self.stadium_club_points,
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
        coach_country_points=int(config.chemistry_coach_country_points),
        stadium_club_points=int(config.chemistry_stadium_club_points),
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
        # Rules frozen before the coach/stadium extras existed had none.
        coach_country_points=int(data.get("coach_country_points", 0)),
        stadium_club_points=int(data.get("stadium_club_points", 0)),
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


_LEVEL_ORDER = {LINK_NONE: 0, LINK_MEDIUM: 1, LINK_STRONG: 2}


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
    coach_bonus: int = 0
    stadium_bonus: int = 0


@dataclass
class ChemistryResult:
    formation: str
    coach_country: str | None = None
    stadium_club: str | None = None
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


def coach_country_of(coach) -> str | None:
    return _group_key(getattr(coach, "country", None)) if coach is not None else None


def stadium_club_of(stadium) -> str | None:
    return _group_key(getattr(stadium, "club", None)) if stadium is not None else None


def compute_chemistry(
    cards_with_slots: Iterable[tuple[Any, Any]], formation: str, rules: ChemistryRules, slot_count: int | None = None,
    coach_country: str | None = None, stadium_club: str | None = None,
    link_floor: dict[str, int] | None = None, on_position_slots: set | None = None,
    extra_points: dict[str, int] | None = None,
) -> ChemistryResult:
    """cards_with_slots: (card-like with .player.{club,country,position},
    FormationSlot) pairs — UserCard, the tournament _EngineCard adapter and
    SimpleNamespace stand-ins all work. Empty slots simply have no links.
    slot_count: the formation's total slot count for team_max (defaults to
    the number of filled slots). coach_country / stadium_club: the equipped
    coach's country and stadium's club (coach_country_of / stadium_club_of;
    None = no such extra).

    Match-time «Академия» talent hooks (path_talent_effects; all None in
    editors and for every card without such a talent): link_floor — slot ->
    minimum link level with that slot (1 medium, 2 strong; «Свой парень»),
    on_position_slots — slots counted as on-position («Универсал» II),
    extra_points — slot -> extra chemistry points when on position."""
    pairs = list(cards_with_slots)
    by_code = {slot.code: card for card, slot in pairs}
    coach_country, stadium_club = _group_key(coach_country), _group_key(stadium_club)
    result = ChemistryResult(formation=formation, coach_country=coach_country, stadium_club=stadium_club)
    link_sums = {code: 0 for code in by_code}
    for a, b in FORMATION_LINKS.get(formation, ()):
        if a in by_code and b in by_code:
            level = link_level(by_code[a].player, by_code[b].player)
            if link_floor:
                floor = max(link_floor.get(a, 0), link_floor.get(b, 0))
                if floor and _LEVEL_ORDER[level] < floor:
                    level = (LINK_NONE, LINK_MEDIUM, LINK_STRONG)[min(floor, 2)]
            pts = link_points(level, rules)
            result.links.append(ChemistryLink(a=a, b=b, level=level, points=pts))
            link_sums[a] += pts
            link_sums[b] += pts
    for card, slot in pairs:
        from app.services.lineup_service import on_ideal_position  # lineup_service imports this module

        on_position = on_ideal_position(card.player.position, slot.ideal_position) or (
            bool(on_position_slots) and slot.code in on_position_slots
        )
        base = player_points(link_sums[slot.code], on_position, rules)
        coach_extra = stadium_extra = 0
        if on_position:
            if coach_country is not None and _group_key(card.player.country) == coach_country:
                coach_extra = max(0, rules.coach_country_points)
            if stadium_club is not None and _group_key(card.player.club) == stadium_club:
                stadium_extra = max(0, rules.stadium_club_points)
        talent_extra = (extra_points or {}).get(slot.code, 0) if on_position else 0
        pts = (
            min(max(0, rules.player_max), base + coach_extra + stadium_extra + talent_extra)
            if (coach_extra or stadium_extra or talent_extra) else base
        )
        bonus = pts * rules.rating_per_point - (0 if on_position else rules.off_position_penalty)
        result.players[slot.code] = PlayerChemistry(
            slot_code=slot.code, points=pts, link_sum=link_sums[slot.code], on_position=on_position, rating_bonus=bonus,
            coach_bonus=coach_extra, stadium_bonus=stadium_extra,
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


def with_match_ratings(cards_with_slots: Iterable[tuple[Any, Any]], chemistry: ChemistryResult | None) -> list[tuple[Any, Any]]:
    """The same (card, slot) pairs with each card's chemistry bonus folded
    into player.rating, for engines that read the rating straight off the
    card (club_tactical_profile_service / club_tactical_matchup_service).
    A card whose bonus is 0 — every card while the mechanic is off — is
    passed through untouched; otherwise a light stand-in keeps id/player_id
    (the engine reports red cards and injuries by card id) and the player
    fields the engine reads. ClubCards have no diamond bonus, so the
    stand-in carries none either."""
    pairs = list(cards_with_slots)
    if chemistry is None:
        return pairs
    out = []
    for card, slot in pairs:
        bonus = chemistry.rating_bonus(slot.code)
        if not bonus:
            out.append((card, slot))
            continue
        p = card.player
        out.append((SimpleNamespace(
            id=card.id, player_id=card.player_id,
            player=SimpleNamespace(
                display_name=p.display_name, position=p.position, rating=boosted_rating(p.rating, bonus),
                rarity=p.rarity, club=p.club, country=p.country,
                attack_rating=getattr(p, "attack_rating", None), defense_rating=getattr(p, "defense_rating", None),
            ),
        ), slot))
    return out


def to_out(
    result: ChemistryResult | None, rules: ChemistryRules | None, strength_bonus: int | None = None,
    frozen: bool = False, live_enabled: bool | None = None,
) -> dict:
    """Serialized form shared by every lineup response (schemas.chemistry.ChemistryOut).
    strength_bonus: how much the chemistry adds to the team strength shown
    for this lineup (None where the mode has no single strength number);
    with the mechanic off it is the old flat club/country bonus.
    frozen: the rules are the ones a RUNNING tournament froze at its start
    (not the live GameConfig); live_enabled: whether GameConfig has the
    mechanic on right now (defaults to `rules is not None`)."""
    meta = {"frozen": frozen, "live_enabled": (rules is not None) if live_enabled is None else live_enabled}
    if result is None or rules is None:
        return {"enabled": False, "strength_bonus": strength_bonus, **meta}
    return {
        "enabled": True,
        "strength_bonus": strength_bonus,
        **meta,
        "formation": result.formation,
        "coach_country": result.coach_country,
        "stadium_club": result.stadium_club,
        "team": result.team,
        "team_max": result.team_max,
        "links": [{"a": l.a, "b": l.b, "level": l.level, "points": l.points} for l in result.links],
        "players": [
            {"slot_code": p.slot_code, "points": p.points, "link_sum": p.link_sum, "on_position": p.on_position,
             "rating_bonus": p.rating_bonus, "coach_bonus": p.coach_bonus, "stadium_bonus": p.stadium_bonus}
            for p in result.players.values()
        ],
        "adjacency": [list(edge) for edge in FORMATION_LINKS.get(result.formation, ())],
        "rules": rules.as_dict(),
    }
