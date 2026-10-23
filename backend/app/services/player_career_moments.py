"""«Карьера игрока»: key moments of the player's league match.

When a round is played the match is simulated as usual, but the player's
own match is not final yet: config.player_career_moments (+1 with «Карьера
Pro») moments wait for his decisions until the next round (at most
config.player_career_moment_window_hours). In each one he picks an action
and plays a timing mini-game; the server rolls the outcome:

- attack (forwards, midfielders, sometimes defenders): success = a goal for
  his team (his goal, or his assist for a pass);
- defense / save (defenders, keepers, sometimes midfielders): the opponent
  breaks through — success stops it, failure = a goal for the opponent.

Chance = option base + (attribute - 60) x 0.6 + timing hit bonus
(config.player_career_moment_hit_pct), clamped 10..90%. Moments still open
at the deadline are played by the AI (the safest option, no timing bonus).
The match is then finalized (score, rating, rewards) by player_career_service.
"""
import random
from datetime import datetime, timedelta
from typing import Optional

from app.core.timeutil import ensure_aware

# kind -> [(option code, label, base %, attribute, effect)]
OPTIONS = {
    "attack": [
        ("shot", "Удар по воротам", 40, "atk", "goal"),
        ("pass", "Пас под удар", 50, "atk", "assist"),
        ("dribble", "Обводка вратаря", 32, "atk", "goal"),
    ],
    "defense": [
        ("tackle", "Подкат", 58, "def", "stop"),
        ("block", "Перекрыть удар", 64, "def", "stop"),
    ],
    "save": [
        ("dive", "Прыжок в угол", 60, "def", "stop"),
        ("angle", "Сократить угол", 66, "def", "stop"),
    ],
}
KIND_TEXT = {
    "attack": "Ты получаешь мяч у штрафной — момент!",
    "defense": "Соперник прорывается к воротам — останови его!",
    "save": "Удар в упор — спасай ворота!",
}
# A dribble that works is the prettiest goal: a bigger rating boost.
RATING_BONUS = {"goal": 0.3, "assist": 0.2, "stop": 0.3}
DRIBBLE_EXTRA = 0.3


def kinds_for(line: str, count: int, rng: random.Random) -> list[str]:
    if line == "GK":
        return ["save"] * count
    out = []
    for i in range(count):
        if line == "FWD":
            out.append("attack")
        elif line == "MID":
            out.append("attack" if i % 2 == 0 else ("defense" if rng.random() < 0.6 else "attack"))
        else:  # DEF
            out.append("defense" if i % 2 == 0 else ("attack" if rng.random() < 0.35 else "defense"))
    return out


def make_moments(line: str, count: int, rng: random.Random) -> list[dict]:
    minutes = sorted(rng.sample(range(8, 88), count)) if count else []
    return [
        {
            "i": i, "kind": kind, "minute": minutes[i], "text": KIND_TEXT[kind],
            "options": [{"code": code, "label": label} for code, label, *_ in OPTIONS[kind]],
            "status": "open", "choice": None, "hit": None, "success": None, "auto": False,
        }
        for i, kind in enumerate(kinds_for(line, count, rng))
    ]


def chance(kind: str, option: str, stats: dict, hit: Optional[bool], config) -> int:
    spec = next((o for o in OPTIONS[kind] if o[0] == option), None)
    if spec is None:
        raise ValueError(option)
    _, _, base, attr, _ = spec
    value = stats["attack"] if attr == "atk" else stats["defense"]
    pct = base + (value - 60) * 0.6 + (config.player_career_moment_hit_pct if hit else 0)
    return int(max(10, min(90, round(pct))))


def best_option(kind: str, stats: dict, config) -> str:
    return max(OPTIONS[kind], key=lambda o: chance(kind, o[0], stats, False, config) * (1 if o[4] != "assist" else 0.9))[0]


def resolve(moment: dict, option: str, hit: Optional[bool], stats: dict, config, rng: random.Random, auto: bool = False) -> dict:
    """Rolls one moment in place; returns it."""
    pct = chance(moment["kind"], option, stats, hit, config)
    moment.update({
        "status": "done", "choice": option, "hit": hit, "chance": pct, "auto": auto,
        "success": rng.random() * 100 < pct,
    })
    return moment


def effect_of(moment: dict) -> str:
    return next(o[4] for o in OPTIONS[moment["kind"]] if o[0] == moment["choice"])


def totals(moments: list[dict]) -> dict:
    """What the moments add to the match: own goals, conceded, the player's
    goals / assists / stops and the rating bonus."""
    out = {"own": 0, "opp": 0, "goals": 0, "assists": 0, "stops": 0, "rating": 0.0}
    for m in moments:
        if m["status"] != "done":
            continue
        effect = effect_of(m)
        if effect == "stop":
            if m["success"]:
                out["stops"] += 1
                out["rating"] += RATING_BONUS["stop"]
            else:
                out["opp"] += 1
                out["rating"] -= 0.2
            continue
        if m["success"]:
            out["own"] += 1
            out["goals" if effect == "goal" else "assists"] += 1
            out["rating"] += RATING_BONUS[effect] + (DRIBBLE_EXTRA if m["choice"] == "dribble" else 0)
    return out


def deadline_for(round_at: datetime, next_at: Optional[datetime], config) -> datetime:
    cap = ensure_aware(round_at) + timedelta(hours=config.player_career_moment_window_hours)
    return min(cap, ensure_aware(next_at)) if next_at else cap
