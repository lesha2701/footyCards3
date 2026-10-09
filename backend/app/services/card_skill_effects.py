"""Pure match-engine helpers for card skills. No DB access.

Application order (identical in Card Arena and player tournaments):

1. card rating (+ diamond bonus) -> coach / stadium / training act on
   ratings and the team profile, exactly as before skills existed;
2. the engine's existing rating curve turns that into the base probability
   of ONE specific roll (miss, failed pass, save, stage-1 advance);
3. the skill adds its percentage points to that probability only — the
   summed same-direction skill bonus is capped at `cap_pp`;
4. the adjusted probability is kept within [floor, ceiling], never pulling a
   base value that was already outside those bounds back in.

Coaches and stadiums never touch these per-event probabilities directly, so
nothing is applied twice. Every effect dict is a frozen snapshot taken
before the match starts (see `effect_for_card`), so later card or GameConfig
changes never reach an already-started match.

RNG contract: a roll with no applicable effect consumes random() exactly as
the original code did, so seeded behavior of skill-less matches is unchanged.
"""
import random
from bisect import bisect
from itertools import accumulate
from typing import Any, Optional

from app.services.card_skill_catalog import SKILL_DEFINITIONS, roman

SNAPSHOT_VERSION = 1


def level_bonus_pp(config, level: int) -> int:
    return int(getattr(config, f"card_skill_level_{level}_bonus_pp", 0) or 0)


def rules_from_config(config) -> dict:
    return {
        "cap_pp": int(config.card_skill_event_bonus_cap_pp),
        "floor": int(config.card_skill_probability_floor_pct) / 100,
        "ceiling": int(config.card_skill_probability_ceiling_pct) / 100,
    }


def is_position_compatible(code: str, position) -> bool:
    definition = SKILL_DEFINITIONS.get(code)
    return definition is not None and position in definition.positions


def effect_for_card(skill_code: Optional[str], skill_level: Optional[int], position, config) -> Optional[dict]:
    """Snapshot of what one card's skill does in a match about to start, or
    None when it has no effect: mechanic off, no skill, a skill the engine
    does not model, or a card whose (possibly admin-edited) position no
    longer fits the server catalog. Per-skill admin disabling deliberately
    does NOT remove the effect of an already-owned skill (it only closes new
    acquisition) — see card_skill_service docstring."""
    if not skill_code or not skill_level or not config.card_skills_enabled:
        return None
    definition = SKILL_DEFINITIONS.get(skill_code)
    if definition is None or not definition.engine_supported:
        return None
    if position not in definition.positions:
        return None
    rules = rules_from_config(config)
    bonus = max(0, min(level_bonus_pp(config, skill_level), rules["cap_pp"]))
    if bonus <= 0:
        return None
    return {"code": skill_code, "level": skill_level, "bonus_pp": bonus, **rules}


def effect_of(effect: Optional[dict], code: str) -> Optional[dict]:
    return effect if effect and effect.get("code") == code else None


def _note(effect: dict, player: Optional[str], decisive: bool) -> dict:
    definition = SKILL_DEFINITIONS.get(effect["code"])
    return {
        "code": effect["code"],
        "name": definition.name if definition else effect["code"],
        "level": effect["level"],
        "level_label": roman(effect["level"]),
        "bonus_pp": effect["bonus_pp"],
        "player": player,
        "decisive": decisive,
    }


def _adjusted(base: float, adjustments: list[tuple[dict, int, Any]]) -> float:
    """adjustments: (effect, sign, player) — sign +1 raises the probability of
    the roll's 'hit' outcome, -1 lowers it. Same-direction bonuses are summed
    and capped together; opposite directions net out."""
    rules = adjustments[0][0]
    cap = rules["cap_pp"]
    up = min(cap, sum(e["bonus_pp"] for e, sign, _ in adjustments if sign > 0))
    down = min(cap, sum(e["bonus_pp"] for e, sign, _ in adjustments if sign < 0))
    value = base + (up - down) / 100
    low = min(rules["floor"], base)
    high = max(rules["ceiling"], base)
    return max(low, min(high, value))


def skill_roll(base: float, adjustments: list[tuple[Optional[dict], int, Any]]) -> tuple[bool, list[dict]]:
    """One Bernoulli roll `random() < p`, optionally skill-adjusted. Returns
    (hit, notes). A note is produced for every effect that took part in the
    calculation; `decisive` is True only when the SAME random draw would have
    produced the other outcome without the skills AND the flipped outcome is
    the one that effect favors — so the log can claim causality exactly when
    the engine itself establishes it."""
    active = [(e, s, p) for e, s, p in adjustments if e]
    if not active:
        return random.random() < base, []
    r = random.random()
    base_hit = r < base
    hit = r < _adjusted(base, active)
    notes = [_note(e, p, hit != base_hit and hit == (s > 0)) for e, s, p in active]
    return hit, notes


def skill_choice(
    outcomes: list[str], weights: list[float], boosted: str, effect: Optional[dict], player: Any = None,
) -> tuple[str, list[dict]]:
    """Weighted pick that matches `random.choices(outcomes, weights, k=1)[0]`
    draw-for-draw when `effect` is None. With an effect, the boosted outcome's
    share gains bonus_pp (capped/bounded like skill_roll) and the remaining
    outcomes are scaled down proportionally."""
    if not effect:
        return random.choices(outcomes, weights=weights, k=1)[0], []
    total = float(sum(weights))
    idx = outcomes.index(boosted)
    base_share = weights[idx] / total
    new_share = _adjusted(base_share, [(effect, 1, player)])
    rest = 1.0 - base_share
    scale = (1.0 - new_share) / rest if rest > 0 else 0.0
    new_weights = [new_share if i == idx else (w / total) * scale for i, w in enumerate(weights)]

    r = random.random()
    base_pick = outcomes[bisect(list(accumulate(weights)), r * total, 0, len(outcomes) - 1)]
    pick = outcomes[bisect(list(accumulate(new_weights)), r * sum(new_weights), 0, len(outcomes) - 1)]
    decisive = pick != base_pick and pick == boosted
    return pick, [_note(effect, player, decisive)]
