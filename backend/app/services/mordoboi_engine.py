"""«Мордобой» — pure rules engine (no DB), like stratego_engine.

A bout is `rounds` rounds of `exchanges` exchanges. In every exchange both
boxers secretly pick one action; when both picks are in, `resolve_exchange`
applies them at once:

- strikes: jab (fast, cheap), hook (strong), uppercut (strongest, costly).
  Strike vs strike is a small rock-paper-scissors: the hook beats the jab
  (rides through it), the uppercut beats the hook (comes up inside it), the
  jab beats the uppercut (lands before the wind-up). Same strikes trade.
- block: takes only part of a strike (the uppercut slips under the guard
  the most) and recovers extra stamina.
- dodge: slips the hook completely and counters; slips a jab with a chance
  that depends on speed; walks straight into the uppercut (extra damage).

Stamina pays for every action except the block; an action the boxer can't
afford is refused (the block always stays available). Below a quarter of
stamina the boxer is tired and hits softer. HP 0 is a knockout; after the
last round the judges score each round 10-9 by damage dealt.

The state is a plain JSON-able dict (it lives in MordoboiMatch.server_state).
Sides are "user" (the match creator) and "opponent", same as Stratego.
"""
import random
from typing import Optional

SIDES = ("user", "opponent")
ACTIONS = ("jab", "hook", "uppercut", "block", "dodge")
STRIKES = ("jab", "hook", "uppercut")

# Strike vs strike: key beats value.
BEATS = {"hook": "jab", "uppercut": "hook", "jab": "uppercut"}

BASE_DAMAGE = {"jab": 6, "hook": 11, "uppercut": 16}
STAMINA_COST = {"jab": 4, "hook": 10, "uppercut": 16, "block": 0, "dodge": 7}
# Share of a strike that gets through a block.
BLOCK_THROUGH = {"jab": 0.15, "hook": 0.35, "uppercut": 0.6}
UPPERCUT_VS_DODGE = 1.3
COUNTER_DAMAGE = 5  # base damage of the counter after slipping a hook / jab
STAMINA_REGEN = 4  # every exchange
BLOCK_REGEN = 8  # extra for blocking
ROUND_RECOVERY_PCT = 50  # share of missing stamina recovered between rounds
TIRED_PCT = 25
TIRED_DAMAGE = 0.75

# Which positions make a quick boxer / a heavy hitter.
FAST_POSITIONS = {"LW": 14, "RW": 14, "LM": 10, "RM": 10, "LWB": 10, "RWB": 10, "CAM": 6, "ST": 4, "CF": 6}
POWER_POSITIONS = {"ST": 8, "CF": 6, "CB": 8, "CDM": 6, "GK": 4}


class EngineError(Exception):
    pass


def other_side(side: str) -> str:
    return "opponent" if side == "user" else "user"


def _clamp(value: float, low: int = 30, high: int = 99) -> int:
    return max(low, min(high, round(value)))


def boxer_stats(rating: int, attack: int, defense: int, position: str, base_hp: int) -> dict:
    """A card as a boxer. Cards carry no separate pace/physical stats, so:
    power (hook/uppercut damage) = attack + a bonus for physical positions;
    speed (jab damage, slipping jabs) = rating + a bonus for wide/attacking
    positions; guard (less damage taken) = defense; stamina pool grows with
    the overall rating."""
    return {
        "power": _clamp(attack + POWER_POSITIONS.get(position, 0) - 4),
        "speed": _clamp(rating + FAST_POSITIONS.get(position, 0) - 6),
        "guard": _clamp(defense),
        "max_hp": base_hp,
        "max_stamina": 50 + round(rating * 0.5),
    }


def new_fighter(stats: dict, card: Optional[dict]) -> dict:
    return {
        **stats, "hp": stats["max_hp"], "stamina": stats["max_stamina"], "card": card,
        "landed": 0, "damage_dealt": 0,
    }


def new_state(user: dict, opponent: dict, rounds: int, exchanges: int) -> dict:
    return {
        "fighters": {"user": user, "opponent": opponent},
        "rounds": rounds, "exchanges_per_round": exchanges,
        "round": 1, "exchange": 1,  # 1-based, the exchange being picked now
        "picks": {"user": None, "opponent": None},
        "log": [], "round_damage": {"user": 0, "opponent": 0},
        "scorecards": [],  # per finished round: {"user": 10, "opponent": 9}
        "finished": False, "winner": None, "reason": None,
    }


def affordable(fighter: dict, action: str) -> bool:
    return fighter["stamina"] >= STAMINA_COST[action]


def available_actions(fighter: dict) -> list[str]:
    return [a for a in ACTIONS if affordable(fighter, a)]


def exchange_index(state: dict) -> int:
    """Global 1-based number of the exchange being picked now."""
    return (state["round"] - 1) * state["exchanges_per_round"] + state["exchange"]


def total_exchanges(state: dict) -> int:
    return state["rounds"] * state["exchanges_per_round"]


def validate_pick(state: dict, side: str, action: str) -> None:
    if state["finished"]:
        raise EngineError("Бой уже закончен")
    if action not in ACTIONS:
        raise EngineError("Неизвестное действие")
    if not affordable(state["fighters"][side], action):
        raise EngineError("Не хватает выносливости — заблокируйся, чтобы отдышаться")


def _damage(attacker: dict, defender: dict, action: str, rng: random.Random) -> int:
    stat = attacker["speed"] if action == "jab" else attacker["power"]
    dmg = BASE_DAMAGE[action] * (0.55 + stat / 110)
    if attacker["stamina"] * 100 < attacker["max_stamina"] * TIRED_PCT:
        dmg *= TIRED_DAMAGE
    dmg *= 1 - defender["guard"] / 400
    dmg *= rng.uniform(0.9, 1.1)
    return max(1, round(dmg))


def _jab_slip_chance(dodger: dict, jabber: dict) -> float:
    return max(0.2, min(0.8, 0.5 + (dodger["speed"] - jabber["speed"]) / 100))


def _hit(action: str, me: dict, them: dict, other_action: str, rng: random.Random) -> tuple[int, str]:
    """Damage `side` deals with `action` against `other_action`, plus a
    short outcome tag for the log."""
    if action not in STRIKES:
        return 0, "none"
    if other_action in STRIKES:
        if BEATS[other_action] == action:
            return 0, "beaten"  # the other strike rode through this one
        return _damage(me, them, action, rng), "landed"
    if other_action == "block":
        return max(1, round(_damage(me, them, action, rng) * BLOCK_THROUGH[action])), "blocked"
    # other_action == "dodge"
    if action == "uppercut":
        return round(_damage(me, them, action, rng) * UPPERCUT_VS_DODGE), "caught"
    if action == "hook":
        return 0, "slipped"
    if rng.random() < _jab_slip_chance(them, me):
        return 0, "slipped"
    return _damage(me, them, action, rng), "landed"


def _counter(dodger: dict, striker: dict, rng: random.Random) -> int:
    dmg = COUNTER_DAMAGE * (0.55 + dodger["speed"] / 110) * (1 - striker["guard"] / 400) * rng.uniform(0.9, 1.1)
    return max(1, round(dmg))


def resolve_exchange(state: dict, rng: random.Random) -> dict:
    """Applies both picks. Returns the log entry (also appended to the log)."""
    picks = state["picks"]
    if any(picks[s] is None for s in SIDES):
        raise EngineError("Ждём выбор обоих боксёров")
    f = state["fighters"]
    actions = {s: picks[s]["action"] for s in SIDES}
    damage = {"user": 0, "opponent": 0}  # damage dealt BY the side
    outcome: dict[str, str] = {}
    for side in SIDES:
        opp = other_side(side)
        damage[side], outcome[side] = _hit(actions[side], f[side], f[opp], actions[opp], rng)
    for side in SIDES:
        opp = other_side(side)
        if outcome[side] == "slipped":  # the dodger countered
            damage[opp] += _counter(f[opp], f[side], rng)
            outcome[opp] = "counter"
    for side in SIDES:
        fighter = f[side]
        cost = STAMINA_COST[actions[side]]
        regen = STAMINA_REGEN + (BLOCK_REGEN if actions[side] == "block" else 0)
        fighter["stamina"] = max(0, min(fighter["max_stamina"], fighter["stamina"] - cost + regen))
    for side in SIDES:
        opp = other_side(side)
        if damage[side] > 0:
            f[side]["landed"] += 1
            f[side]["damage_dealt"] += damage[side]
            state["round_damage"][side] += damage[side]
        f[opp]["hp"] = max(0, f[opp]["hp"] - damage[side])

    entry = {
        "n": exchange_index(state), "round": state["round"], "exchange": state["exchange"],
        "actions": actions, "outcome": outcome, "damage": damage,
        "hp": {s: f[s]["hp"] for s in SIDES}, "stamina": {s: f[s]["stamina"] for s in SIDES},
        "auto": {s: bool(picks[s].get("auto")) for s in SIDES},
    }
    state["log"].append(entry)
    state["picks"] = {"user": None, "opponent": None}

    down = [s for s in SIDES if f[s]["hp"] <= 0]
    if down:
        _score_round(state)
        if len(down) == 2:
            _finish_on_points(state, reason="double_ko")
        else:
            _finish(state, other_side(down[0]), "ko")
        entry["end"] = state["reason"]
        return entry

    if state["exchange"] < state["exchanges_per_round"]:
        state["exchange"] += 1
        return entry
    _score_round(state)
    if state["round"] >= state["rounds"]:
        _finish_on_points(state, reason="points")
        entry["end"] = state["reason"]
        return entry
    state["round"] += 1
    state["exchange"] = 1
    for side in SIDES:  # the corner between rounds
        fighter = f[side]
        missing = fighter["max_stamina"] - fighter["stamina"]
        fighter["stamina"] += missing * ROUND_RECOVERY_PCT // 100
    entry["round_end"] = True
    return entry


def _score_round(state: dict) -> None:
    dmg = state["round_damage"]
    if dmg["user"] == dmg["opponent"]:
        card = {"user": 10, "opponent": 10}
    elif dmg["user"] > dmg["opponent"]:
        card = {"user": 10, "opponent": 9}
    else:
        card = {"user": 9, "opponent": 10}
    state["scorecards"].append({**card, "damage": dict(dmg)})
    state["round_damage"] = {"user": 0, "opponent": 0}


def score_totals(state: dict) -> dict:
    return {s: sum(c[s] for c in state["scorecards"]) for s in SIDES}


def _finish_on_points(state: dict, reason: str) -> None:
    totals = score_totals(state)
    if totals["user"] != totals["opponent"]:
        winner = "user" if totals["user"] > totals["opponent"] else "opponent"
    else:
        dealt = {s: state["fighters"][s]["damage_dealt"] for s in SIDES}
        winner = "draw" if dealt["user"] == dealt["opponent"] else max(SIDES, key=lambda s: dealt[s])
    _finish(state, winner, reason)


def _finish(state: dict, winner: str, reason: str) -> None:
    state["finished"] = True
    state["winner"] = winner
    state["reason"] = reason
    state["picks"] = {"user": None, "opponent": None}


def finish_by(state: dict, winner: str, reason: str) -> None:
    """Forfeit / timeout from outside the ring."""
    _finish(state, winner, reason)


# ---------------------------------------------------------------------------
# Bot (also the autopilot for a side that missed its deadline)
# ---------------------------------------------------------------------------

def _counter_to(action: str) -> list[str]:
    """Actions that do well against `action`."""
    return {
        "jab": ["hook", "block"],
        "hook": ["dodge", "uppercut"],
        "uppercut": ["jab", "block"],
        "block": ["uppercut", "jab"],
        "dodge": ["uppercut", "block"],
    }[action]


def bot_choose(state: dict, side: str, rng: random.Random, difficulty: str = "hard") -> str:
    """Picks from what the opponent did before — never from its current
    (secret) pick, which the bot is not given."""
    me = state["fighters"][side]
    opp = other_side(side)
    them = state["fighters"][opp]
    options = available_actions(me)
    weights = {a: 1.0 for a in options}
    if difficulty != "easy":
        recent = [e["actions"][opp] for e in state["log"][-4:]]
        if recent:
            favourite = max(set(recent), key=recent.count)
            for a in _counter_to(favourite):
                if a in weights:
                    weights[a] += 1.5 * recent.count(favourite) / len(recent)
        if me["stamina"] * 100 < me["max_stamina"] * 35 and "block" in weights:
            weights["block"] += 2.0
        if them["hp"] <= 20 and "uppercut" in weights:
            weights["uppercut"] += 1.5
        if them["stamina"] * 100 < them["max_stamina"] * 30 and "hook" in weights:
            weights["hook"] += 1.0
    else:
        weights["block"] = weights.get("block", 1.0) + 0.5
    total = sum(weights.values())
    roll = rng.random() * total
    for action, w in weights.items():
        roll -= w
        if roll <= 0:
            return action
    return options[-1]
