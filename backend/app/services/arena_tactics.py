"""Card Arena styles, the style matchup and the pre-match balance — pure
functions, no DB. match_service freezes `compute_balance()`'s result into
Match.server_state["balance"] at kickoff; the engine then reads it for the
possession share, each side's shot frequency and the per-roll rating edge.

Four styles beat each other in a circle (each beats one, loses to one and
is neutral against the other two):

    Атака > Оборона > Владение > Контратака > Атака

and each one also boosts its own line inside team_strength
(lineup_service.TACTIC_CATEGORY_MULTIPLIERS), so the choice is "the style
that fits my squad" vs "the style that counters his".
"""
import math
from typing import Optional

STYLES = ("attacking", "possession", "defensive", "counter")
# Lineups saved before the four-style rework.
LEGACY_STYLES = {"balanced": "possession"}
DEFAULT_STYLE = "possession"

STYLE_LABELS = {
    "attacking": "Атака",
    "possession": "Владение",
    "defensive": "Оборона",
    "counter": "Контратака",
}

BEATS = {
    "attacking": "defensive",
    "defensive": "possession",
    "possession": "counter",
    "counter": "attacking",
}

# Why the winning style wins — shown in the preview and the match report.
BEATS_REASON = {
    "attacking": "штурм ломает глубокую оборону",
    "defensive": "плотный блок гасит контроль мяча",
    "possession": "без мяча контратаке нечего ловить",
    "counter": "контратаки бьют в пространство за спиной",
}

# (attack, defense) multipliers on the team strength.
STYLE_SPLIT: dict[str, tuple[float, float]] = {
    "attacking": (1.10, 0.90),
    "possession": (1.0, 1.0),
    "defensive": (0.90, 1.10),
    "counter": (0.95, 1.05),
}

# Shot-chance weight of the moment queue at parity (the old fixed weight).
BASE_SHOT_WEIGHT = 26


def resolve_style(style: Optional[str]) -> str:
    style = LEGACY_STYLES.get(style or "", style)
    return style if style in STYLES else DEFAULT_STYLE


def matchup(mine: Optional[str], theirs: Optional[str]) -> str:
    """'win' / 'loss' / 'neutral' for `mine` against `theirs`."""
    mine, theirs = resolve_style(mine), resolve_style(theirs)
    if BEATS[mine] == theirs:
        return "win"
    if BEATS[theirs] == mine:
        return "loss"
    return "neutral"


def split(strength: float, style: Optional[str]) -> tuple[float, float]:
    attack, defense = STYLE_SPLIT[resolve_style(style)]
    return max(1.0, strength * attack), max(1.0, strength * defense)


def compute_balance(
    user_strength: int, user_style: Optional[str], opponent_strength: int, opponent_style: Optional[str], config,
) -> dict:
    """Everything the engine needs to make the stronger side win as often as
    it should, frozen at kickoff:

    - `share`: chance a moment belongs to the user — attack vs the other
      side's defense on both ends, sharpened by `arena_share_exponent`;
    - `user_shot_weight` / `opponent_shot_weight`: how often a side's
      moment is a real chance (vs flavor) — again attack vs defense;
    - `edge`: rating points added to every user roll and taken from every
      opponent roll, from the overall strength ratio after the matchup.
    """
    user_style, opponent_style = resolve_style(user_style), resolve_style(opponent_style)
    result = matchup(user_style, opponent_style)
    bonus = float(config.arena_style_matchup_bonus_pct) / 100
    user_mult = 1 + bonus if result == "win" else 1.0
    opponent_mult = 1 + bonus if result == "loss" else 1.0
    user_eff = max(1, user_strength) * user_mult
    opponent_eff = max(1, opponent_strength) * opponent_mult

    user_attack, user_defense = split(user_eff, user_style)
    opponent_attack, opponent_defense = split(opponent_eff, opponent_style)
    user_ratio = user_attack / opponent_defense
    opponent_ratio = opponent_attack / user_defense

    p = float(config.arena_share_exponent)
    share = user_ratio ** p / (user_ratio ** p + opponent_ratio ** p)
    q = float(config.arena_shot_exponent)

    def shot_weight(ratio: float) -> int:
        return max(8, min(80, round(BASE_SHOT_WEIGHT * ratio ** q)))

    ratio = user_eff / opponent_eff
    per_10pct = float(config.arena_edge_rating_per_10pct)
    cap = int(config.arena_edge_rating_max)
    edge = round(per_10pct * math.log(ratio) / math.log(1.1))
    edge = max(-cap, min(cap, edge))

    return {
        "user_style": user_style,
        "opponent_style": opponent_style,
        "matchup": result,
        "matchup_bonus_pct": int(config.arena_style_matchup_bonus_pct) if result != "neutral" else 0,
        "strength_ratio": round(ratio, 3),
        "share": round(share, 4),
        "user_shot_weight": shot_weight(user_ratio),
        "opponent_shot_weight": shot_weight(opponent_ratio),
        "edge": edge,
    }


def matchup_text(user_style: str, opponent_style: str) -> str:
    """One line for the preview/report: who the style matchup favours."""
    result = matchup(user_style, opponent_style)
    mine, theirs = STYLE_LABELS[resolve_style(user_style)], STYLE_LABELS[resolve_style(opponent_style)]
    if result == "win":
        return f"«{mine}» против «{theirs}»: преимущество у вас — {BEATS_REASON[resolve_style(user_style)]}"
    if result == "loss":
        return f"«{mine}» против «{theirs}»: преимущество у соперника — {BEATS_REASON[resolve_style(opponent_style)]}"
    return f"«{mine}» против «{theirs}»: стили не дают никому преимущества"
