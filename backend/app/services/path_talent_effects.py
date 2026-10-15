"""Match effects of «Начало пути» talents. Pure: no DB access.

Order of a card's match rating (Card Arena and player tournaments):
base rating → diamond / stars / path levels (card_rating_bonus) → chemistry
(with «Свой парень» / «Универсал» II applied to the chemistry itself) →
position fit («Универсал») / rarity / tactic or zone profile → coach →
stadium → STATIC talents (kickoff) → DYNAMIC talents (per moment) → card
skill (a separate per-event probability bonus, card_skill_effects).

All talents together add at most GameConfig.path_talent_cap to one card in
one match (`room` = what the static part left for dynamic ones) and the
match rating never exceeds 99. Everything is frozen at kickoff into the
match state, so later card / admin changes never reach a started match.
Talents never draw random numbers: matches without talents consume the RNG
exactly as before.
"""
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Optional

from app.services.chemistry_service import FORMATION_LINKS, _group_key
from app.services.path_talent_catalog import DYNAMIC, TALENTS, is_adjacent, roman, values_for

SNAPSHOT_VERSION = 1
MAX_RATING = 99


def talent_snapshot(card, catalog, config, mode: str) -> Optional[dict]:
    """What one card's talent can do in a match of `mode` about to start, or
    None: mechanic off, not a path card, talent not unlocked yet, disabled
    by the admin, or not modelled in this mode («не действует»)."""
    player = getattr(card, "player", None)
    code = getattr(player, "path_talent_code", None)
    if not code or not config.path_enabled or code not in TALENTS:
        return None
    definition = TALENTS[code]
    if mode not in definition.modes:
        return None
    row = catalog.talents.get(code)
    if row is not None and not row.is_enabled:
        return None
    level = catalog.talent_level(getattr(card, "path_stage", 0) or 0)
    if level <= 0:
        return None
    return {
        "code": code, "name": definition.name, "emoji": definition.emoji, "kind": definition.kind,
        "level": level, "level_label": roman(level),
        "values": values_for(code, level, row.level_values if row else None),
        "player": player.display_name, "card_id": card.id,
    }


@dataclass
class TalentPlan:
    """Kickoff decisions for one side."""

    talents: dict[int, dict] = field(default_factory=dict)       # card id -> snapshot (+ static, room)
    static: dict[int, int] = field(default_factory=dict)         # card id -> static bonus (aura included)
    position_override: dict[int, Any] = field(default_factory=dict)  # «Универсал»: card id -> slot position
    on_position_slots: set = field(default_factory=set)           # «Универсал» II: chemistry on-position
    link_floor: dict[str, int] = field(default_factory=dict)      # «Свой парень»: slot code -> 1 medium / 2 strong
    extra_points: dict[str, int] = field(default_factory=dict)    # «Свой парень» II: slot code -> + chemistry points
    notes: list[dict] = field(default_factory=list)               # static talents that applied (for the log)

    @property
    def active(self) -> bool:
        return bool(self.talents or self.static)

    def chemistry_hooks(self) -> dict:
        return {
            "link_floor": self.link_floor or None, "on_position_slots": self.on_position_slots or None,
            "extra_points": self.extra_points or None,
        }

    def snapshot(self) -> dict:
        return {
            "version": SNAPSHOT_VERSION,
            "cards": {str(cid): snap for cid, snap in self.talents.items()},
            "static": {str(cid): v for cid, v in self.static.items() if v},
            "notes": self.notes,
        }


def plan_static(
    pairs: list, talents: dict[int, dict], config, *, formation: str, opponent_ratio: Optional[float],
    coach_country: Optional[str], stadium_club: Optional[str], hunger: dict[int, int] | None = None,
    chemistry_on: bool = False,
) -> TalentPlan:
    """pairs: (card, slot) of one side; talents: card id -> talent_snapshot.
    opponent_ratio: opponent strength / own strength at kickoff (None = not
    known, «Большие матчи» then does nothing)."""
    plan = TalentPlan()
    cap = max(0, int(config.path_talent_cap))
    by_slot = {slot.code: card for card, slot in pairs}
    raw: dict[int, int] = {}
    for card, slot in pairs:
        snap = talents.get(card.id)
        if snap is None:
            continue
        code, v = snap["code"], snap["values"]
        player = card.player
        bonus = 0
        if code == "big_matches":
            if opponent_ratio is not None and opponent_ratio >= 1 + v["threshold_pct"] / 100:
                bonus = v["bonus"]
        elif code == "universal":
            if is_adjacent(player.position, slot.ideal_position):
                plan.position_override[card.id] = slot.ideal_position
                if snap["level"] >= 2:
                    if chemistry_on:
                        plan.on_position_slots.add(slot.code)
                    bonus = v["bonus"]
                if not bonus:
                    plan.notes.append(_note(snap, 0))
        elif code == "own_guy":
            # Only where chemistry is in play — otherwise there is nothing to lift.
            if chemistry_on:
                plan.link_floor[slot.code] = v["link_floor"]
                if v.get("extra_points"):
                    plan.extra_points[slot.code] = v["extra_points"]
                plan.notes.append(_note(snap, 0))
        elif code == "academy":
            if coach_country is not None and _group_key(player.country) == _group_key(coach_country):
                bonus += v["coach_bonus"]
            if stadium_club is not None and _group_key(player.club) == _group_key(stadium_club):
                bonus += v["stadium_bonus"]
        elif code == "hunger":
            bonus = min(v["max"], (hunger or {}).get(card.id, 0) * v["per_match"])
        elif code == "captain":
            left = v["aura_cap"]
            for a, b in FORMATION_LINKS.get(formation, ()):
                other = b if a == slot.code else a if b == slot.code else None
                if other is None or other not in by_slot or left <= 0:
                    continue
                give = min(v["aura"], left)
                raw[by_slot[other].id] = raw.get(by_slot[other].id, 0) + give
                left -= give
            if left < v["aura_cap"]:
                plan.notes.append(_note(snap, v["aura_cap"] - left, aura=True))
        if bonus:
            raw[card.id] = raw.get(card.id, 0) + bonus
            plan.notes.append(_note(snap, bonus))
        plan.talents[card.id] = dict(snap)
    for cid, value in raw.items():
        plan.static[cid] = min(cap, value)
    for cid, snap in plan.talents.items():
        snap["static"] = plan.static.get(cid, 0)
        snap["room"] = max(0, cap - snap["static"]) if snap["kind"] == DYNAMIC else 0
    return plan


def _note(snap: dict, bonus: int, aura: bool = False) -> dict:
    return {
        "code": snap["code"], "name": snap["name"], "emoji": snap["emoji"], "level": snap["level"],
        "level_label": snap["level_label"], "player": snap["player"], "bonus": bonus, **({"aura": True} if aura else {}),
    }


def dynamic_bonus(
    snap: Optional[dict], *, minute: int, own: int, opp: int, role: str,
    one_on_one: bool = False, penalty: bool = False,
) -> int:
    """Bonus of a DYNAMIC talent for one moment. role: shooter | passer |
    defender | keeper (the card's part in this roll)."""
    if not snap or snap.get("kind") != DYNAMIC or not snap.get("room"):
        return 0
    code, v = snap["code"], snap["values"]
    bonus = 0
    if code == "second_wind":
        bonus = v["bonus"] if minute >= v["from_minute"] else 0
    elif code == "fighter":
        bonus = v["bonus"] if own < opp else 0
    elif code == "composure":
        if (one_on_one and role in ("shooter", "keeper")) or (penalty and role == "keeper"):
            bonus = v["bonus"]
    elif code == "hold_lead":
        bonus = v["bonus"] if own > opp and minute >= v["from_minute"] and role in ("defender", "keeper") else 0
    return min(bonus, snap["room"])


def with_bonus(rating: int | float, bonus: int) -> int | float:
    return min(MAX_RATING, rating + bonus) if bonus else rating


def dynamic_note(snap: dict, bonus: int) -> dict:
    return _note(snap, bonus)


def override_positions(pairs: list, plan: TalentPlan) -> list:
    """«Универсал»: the same pairs with an adjacent-slot card standing in as
    a natural for the position fit (the card itself is untouched)."""
    if not plan.position_override:
        return pairs
    out = []
    for card, slot in pairs:
        position = plan.position_override.get(card.id)
        if position is None:
            out.append((card, slot))
            continue
        out.append((_with_player(card, position=position), slot))
    return out


class _CardProxy:
    """Delegates every attribute to the wrapped card except `player`."""

    def __init__(self, card, player):
        object.__setattr__(self, "_card", card)
        object.__setattr__(self, "player", player)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_card"), name)


def _with_player(card, **changes):
    p = card.player
    player = SimpleNamespace(
        id=getattr(p, "id", None), display_name=p.display_name, position=p.position, rating=p.rating,
        rarity=p.rarity, club=p.club, country=p.country,
        attack_rating=getattr(p, "attack_rating", None), defense_rating=getattr(p, "defense_rating", None),
        path_talent_code=getattr(p, "path_talent_code", None),
    )
    for key, value in changes.items():
        setattr(player, key, value)
    return _CardProxy(card, player)
