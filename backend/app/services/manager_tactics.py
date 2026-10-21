"""«Менеджер» tactics — pure functions, no DB.

The club engine's own mentality / playstyle knobs move results only a
little and noisily (scripts/simulate_tactical_matrix.py), which players
can't read. «Менеджер» plays every side with the neutral engine settings
and puts a transparent layer on top, the same idea as Card Arena:

- the formation (one of the seven club formations) decides the slots and
  tilts attack vs defense a little (arena_tactics.FORMATION_SHIFT, scaled
  by GameConfig.manager_formation_effect_pct);
- the style (one of four, in a circle — Атака > Оборона > Владение >
  Контратака > Атака) lifts its own lines (LINE_BOOST) and, against the
  style it beats, every player by GameConfig.manager_style_edge_pct.

All of it becomes a % on each player's rating for that one match
(`modifiers`), so «why did we win» is always explainable.
"""
from typing import Optional

from app.services.arena_tactics import BEATS, BEATS_REASON, FORMATION_SHIFT, STYLE_LABELS, STYLES, formation_label
from app.services.club_formation_service import CLUB_FORMATIONS

__all__ = [
    "BEATS", "BEATS_REASON", "DEFAULT_FORMATION", "DEFAULT_STYLE", "FORMATIONS", "STYLES", "STYLE_LABELS",
    "edge", "formation_label", "modifiers", "rules_out",
]

DEFAULT_FORMATION = "4-3-3"
DEFAULT_STYLE = "possession"
FORMATIONS = tuple(f for f in ("4-3-3", "4-3-3H", "4-2-3-1", "4-4-2", "3-5-2", "5-3-2", "3-4-3") if f in CLUB_FORMATIONS)
ENGINE_MENTALITY = "BALANCED"
ENGINE_PLAYSTYLE = "CENTRAL_PLAY"

# % on the rating of each line, by style.
LINE_BOOST: dict[str, dict[str, int]] = {
    "attacking": {"FWD": 6, "MID": 2, "DEF": -4, "GK": -4},
    "possession": {"FWD": 0, "MID": 6, "DEF": 0, "GK": 0},
    "defensive": {"FWD": -4, "MID": 0, "DEF": 6, "GK": 4},
    "counter": {"FWD": 3, "MID": -2, "DEF": 3, "GK": 0},
}
STYLE_ABOUT = {
    "attacking": "Нападение +6%, полузащита +2%, защита и вратарь −4%",
    "possession": "Полузащита +6%",
    "defensive": "Защита +6%, вратарь +4%, нападение −4%",
    "counter": "Нападение и защита +3%, полузащита −2%",
}
ATTACK_LINES = ("FWD", "MID")


def clean_style(style: Optional[str]) -> str:
    return style if style in STYLES else DEFAULT_STYLE


def clean_formation(formation: Optional[str]) -> str:
    return formation if formation in FORMATIONS else DEFAULT_FORMATION


def edge(style: str, opponent_style: str) -> str:
    """"win" when `style` beats the opponent's, "lose" when beaten, else "even"."""
    if BEATS.get(style) == opponent_style:
        return "win"
    if BEATS.get(opponent_style) == style:
        return "lose"
    return "even"


def modifiers(style: str, formation: str, opponent_style: str, config) -> dict[str, float]:
    """% on the rating of each line for one match."""
    style, formation = clean_style(style), clean_formation(formation)
    scale = getattr(config, "manager_formation_effect_pct", 100) / 100
    attack, defense = FORMATION_SHIFT.get(formation, (0, 0))
    bonus = getattr(config, "manager_style_edge_pct", 4) if edge(style, opponent_style) == "win" else 0
    return {
        line: LINE_BOOST[style][line] + (attack if line in ATTACK_LINES else defense) * scale + bonus
        for line in ("GK", "DEF", "MID", "FWD")
    }


def apply(rating: int, line: str, mods: dict[str, float]) -> int:
    return max(1, round(rating * (100 + mods.get(line, 0)) / 100))


def rules_out(config) -> dict:
    scale = getattr(config, "manager_formation_effect_pct", 100) / 100
    return {
        "styles": [
            {"value": s, "label": STYLE_LABELS[s], "about": STYLE_ABOUT[s], "beats": BEATS[s],
             "beats_label": STYLE_LABELS[BEATS[s]], "reason": BEATS_REASON[s]}
            for s in STYLES
        ],
        "formations": [
            {"value": f, "label": formation_label(f), "attack": round(FORMATION_SHIFT.get(f, (0, 0))[0] * scale, 1),
             "defense": round(FORMATION_SHIFT.get(f, (0, 0))[1] * scale, 1)}
            for f in FORMATIONS
        ],
        "edge_pct": getattr(config, "manager_style_edge_pct", 4),
    }
