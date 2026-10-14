"""«Карьера тренера» tactics layer (pure — no DB access).

A team's tactic is a set of independent axes, grouped by phase of play,
instead of one "playstyle" that mixed them up:

  in possession   direction  (wings / mixed / center) — where attacks go
                  buildup    (short / mixed / direct) — how they are built
  transitions     on_loss    (counterpress / drop)    — right after losing the ball
                  on_win     (fast / keep)            — right after winning it
  out of poss.    block      (high / mid / low)       — where the team defends

plus the existing mentality (risk). Every axis is a real engine lever
(TacticAxes, plugged into club_tactical_matchup_service through
ClubTacticalSide.career) with a cost and a benefit; matchups come from
INTERACTIONS — the one table the engine applies in duels, the scouting
report explains, adaptive bots optimise against, and
career_tactics_matchup.json (scripts/simulate_career_tactics.py) confirms by
simulation. The five old playstyles survive as PRESETS (named axis sets).

Also here: familiarity, the match plan (conditional instructions +
substitutions) and the phase-by-phase match controller, adaptive bots and
the post-match analysis. Only seasons with state["tactics_version"] >= 1 use
any of this; older seasons keep tournament_match_engine.simulate_match.
Every coefficient lives in GameConfig.career_* (career_tactics_tuning for
the axis levers).
"""
import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.services import chemistry_service
from app.services import club_tactical_matchup_service as matchup
from app.services import club_tactical_profile_service as profile_service
from app.services.lineup_service import CATEGORY_POSITIONS

TACTICS_VERSION = 1

MENTALITY_LABELS = {
    "PARK_THE_BUS": "Автобус у ворот", "DEFENSIVE": "Оборонительный", "BALANCED": "Сбалансированный",
    "ATTACKING": "Атакующий",
}

# --- axes and presets --------------------------------------------------------------

AXES: dict[str, tuple[str, ...]] = {
    "direction": ("wings", "mixed", "center"),
    "buildup": ("short", "mixed", "direct"),
    "on_loss": ("counterpress", "drop"),
    "on_win": ("fast", "keep"),
    "block": ("high", "mid", "low"),
    "tackling": ("normal", "hard", "soft"),
}
AXIS_LABELS = {
    "direction": "Направление атаки", "buildup": "Построение атаки", "on_loss": "После потери мяча",
    "on_win": "После отбора", "block": "Линия обороны и прессинга", "tackling": "Отбор мяча",
}
VALUE_LABELS = {
    "direction": {"wings": "Фланги", "mixed": "Смешанно", "center": "Центр"},
    "buildup": {"short": "Короткий пас", "mixed": "Смешанно", "direct": "Прямой пас"},
    "on_loss": {"counterpress": "Контрпрессинг", "drop": "Отход в блок"},
    "on_win": {"fast": "Быстрая атака", "keep": "Сохранить мяч"},
    "block": {"high": "Высокий прессинг", "mid": "Средний блок", "low": "Низкий блок"},
    "tackling": {"normal": "Обычный", "hard": "Жёсткий", "soft": "Аккуратный"},
}
# One line per choice for the tactics screen: what it gives and what it costs.
VALUE_HINTS = {
    "direction": {
        "wings": "Атаки через бровки: навесы, обход прессинга. Крайние уходят вперёд — сзади остаётся место.",
        "mixed": "Атаки и через центр, и по флангам — без явного перекоса.",
        "center": "Атаки через центр. Вязнет против низкого блока.",
    },
    "buildup": {
        "short": "Терпеливый розыгрыш: больше повторных попыток, вскрывает низкий блок. Рискован под высоким прессингом.",
        "mixed": "Обычный розыгрыш без особых рисков.",
        "direct": "Быстро за спину защитникам — опасно против высокой линии, но мяч чаще теряется.",
    },
    "on_loss": {
        "counterpress": "Сразу давить после потери: гасит контратаки соперника. Игроки устают быстрее.",
        "drop": "Отойти и закрыть зоны: больше защитников сзади при контратаке соперника.",
    },
    "on_win": {
        "fast": "Мгновенно атаковать после отбора: опасно против высокой линии и ушедших вперёд крайних.",
        "keep": "Сохранить мяч: дольше владеем инициативой, контратаки слабее.",
    },
    "block": {
        "high": "Прессинг у чужих ворот: чаще отбираем мяч, ловим короткий розыгрыш. Сзади мало людей, быстрее усталость.",
        "mid": "Средний блок: баланс без явных слабостей.",
        "low": "Глубокий блок: закрывает центр и защищает много людей, но отдаёт фланги и инициативу.",
    },
    "tackling": {
        "normal": "Игроки идут в отбор, когда уверены, что заберут мяч чисто, без риска фола.",
        "hard": "Идут в отбор на всё: чаще отбирают мяч, но больше фолов, пенальти, жёлтых и красных. Промах оставляет дыру сзади.",
        "soft": "Не идут в подкат, а сопровождают соперника: меньше фолов и карточек, но мяч отбирают реже.",
    },
}
NEUTRAL_TACTIC = {
    "direction": "mixed", "buildup": "mixed", "on_loss": "drop", "on_win": "keep", "block": "mid", "tackling": "normal",
}

PRESETS: dict[str, dict[str, str]] = {
    "WING_PLAY": {"direction": "wings", "buildup": "mixed", "on_loss": "drop", "on_win": "keep", "block": "mid",
                  "tackling": "normal"},
    "CENTRAL_PLAY": {"direction": "center", "buildup": "short", "on_loss": "counterpress", "on_win": "keep", "block": "mid",
                     "tackling": "normal"},
    "POSSESSION": {"direction": "mixed", "buildup": "short", "on_loss": "counterpress", "on_win": "keep", "block": "mid",
                   "tackling": "soft"},
    "HIGH_PRESS": {"direction": "mixed", "buildup": "direct", "on_loss": "counterpress", "on_win": "fast", "block": "high",
                   "tackling": "hard"},
    "COUNTER_ATTACK": {"direction": "mixed", "buildup": "direct", "on_loss": "drop", "on_win": "fast", "block": "low",
                       "tackling": "normal"},
}
PRESET_LABELS = {
    "WING_PLAY": "Фланговая игра", "CENTRAL_PLAY": "Игра через центр", "POSSESSION": "Контроль мяча",
    "HIGH_PRESS": "Прессинг", "COUNTER_ATTACK": "Контратаки",
}
CUSTOM = "CUSTOM"

# Default axis levers; GameConfig.career_tactics_tuning overrides any key.
DEFAULT_TUNING: dict[str, Any] = {
    # Share of progressions down the flanks (the rest go central).
    "wing_share": {"wings": 0.70, "mixed": 0.50, "center": 0.30},
    # Phases that end in a safe recycle instead of an attack.
    "recycle": {"short": 0.16, "mixed": 0.10, "direct": 0.06},
    # Chance of a second attempt after a stalled duel (x midfield quality).
    "retry": {"short": 0.55, "mixed": 0.25, "direct": 0.0},
    "initiative": {"high": 1.04, "mid": 1.0, "low": 0.86, "keep": 1.08, "fast": 1.0},
    # Share of the back line available in defence (high block pushes up).
    "pool": {"high": 0.80, "mid": 1.0, "low": 1.15},
    # ...and right after losing the ball.
    "counter_pool": {"counterpress": 1.0, "drop": 1.2},
    "transition": {"fast": 1.5, "keep": 1.0},
    # In-match fatigue rate.
    "fatigue": {"high": 1.25, "mid": 1.0, "low": 0.9, "counterpress": 1.15, "drop": 1.0},
    # Interaction strengths: how much a duel's advance/breakdown odds tilt
    # (0.3 = advance x1.3 and breakdown x0.7 for the favoured attacker), see
    # INTERACTIONS and club_tactical_matchup_service._stage1_weights.
    "shift": {
        "press_vs_short": 0.24, "direct_behind_line": 0.26, "direct_inaccuracy": 0.06, "wings_beat_press": 0.24,
        "low_block_center": 0.24, "low_block_crosses": 0.21, "patient_vs_low_block": 0.2,
        "fast_counter_high_line": 0.32, "counterpress": 0.32, "counter_behind_fullbacks": 0.24,
        "hard_tackling_wins": 0.12, "soft_tackling_jockeys": 0.10, "hard_tackle_gaps": 0.16,
    },
    # Tackling: foul / tackle-attempt rates and post-match card odds.
    "foul": {"normal": 1.0, "hard": 1.6, "soft": 0.6},
    "tackle_attempt": {"normal": 1.0, "hard": 1.35, "soft": 0.7},
    # Set pieces: chances a blocked/saved shot gives a corner, goal odds
    # of a corner / direct free kick / penalty (scaled by the players), and
    # how much the right delivery vs the defending scheme matters.
    "corner_chance": 0.35,
    "corner_goal": 0.06,
    "free_kick_goal": 0.07,
    "penalty_goal": 0.76,
    "routine_edge": 1.4,
    "routine_miss": 0.8,
    # Training before a round (career_service.TRAININGS).
    "training": {"recovery_fatigue": -12, "load_fatigue": 5, "tactical_familiarity_tenths": 15,
                 "opponent_boost": 1.25, "set_piece_boost": 1.35},
    # Scouting: how much a counter-attack interaction weighs vs a build-up
    # one, and the score above which a matchup is called an advantage.
    "counter_weight": 0.35,
    "hint_threshold": 0.05,
}

# One table, three readers (engine duels, scouting, bots). sign +1 favours
# the attacking side of that duel, -1 the defending side. "base" entries are
# an axis's own trade-off (not a matchup) and stay out of the scouting hint.
INTERACTIONS: list[dict] = [
    {"id": "press_vs_short", "kind": "build_up", "att": {"buildup": "short"}, "def": {"block": "high"}, "sign": -1,
     "label": "Высокий прессинг перехватывает короткий розыгрыш"},
    {"id": "direct_behind_line", "kind": "build_up", "att": {"buildup": "direct"}, "def": {"block": "high"}, "sign": 1,
     "label": "Прямой пас за спину высокой линии"},
    {"id": "wings_beat_press", "kind": "build_up", "zone": "wing_attack", "att": {}, "def": {"block": "high"},
     "sign": 1, "label": "Атака флангом обходит высокий прессинг"},
    {"id": "low_block_center", "kind": "build_up", "zone": "central_attack", "att": {}, "def": {"block": "low"},
     "sign": -1, "label": "Низкий блок закрывает центр"},
    {"id": "low_block_crosses", "kind": "build_up", "zone": "wing_attack", "att": {}, "def": {"block": "low"},
     "sign": 1, "label": "Низкий блок отдаёт фланги и навесы"},
    {"id": "patient_vs_low_block", "kind": "build_up", "att": {"buildup": "short"}, "def": {"block": "low"},
     "sign": 1, "label": "Терпеливый розыгрыш вскрывает низкий блок"},
    {"id": "fast_counter_high_line", "kind": "counter", "att": {"on_win": "fast"}, "def": {"block": "high"},
     "sign": 1, "label": "Быстрая контратака в пространство за высокой линией"},
    {"id": "counter_behind_fullbacks", "kind": "counter", "att": {"on_win": "fast"}, "def": {"direction": "wings"},
     "sign": 1, "label": "Быстрая атака в зону ушедших вперёд крайних"},
    {"id": "counterpress", "kind": "counter", "att": {}, "def": {"on_loss": "counterpress"}, "sign": -1,
     "label": "Контрпрессинг гасит контратаку сразу после потери"},
    {"id": "direct_inaccuracy", "kind": "build_up", "att": {"buildup": "direct"}, "def": {}, "sign": -1,
     "base": True, "label": "Длинные передачи чаще теряются"},
    {"id": "hard_tackling_wins", "kind": "build_up", "att": {}, "def": {"tackling": "hard"}, "sign": -1,
     "base": True, "label": "Жёсткий отбор чаще забирает мяч"},
    {"id": "soft_tackling_jockeys", "kind": "build_up", "att": {}, "def": {"tackling": "soft"}, "sign": 1,
     "base": True, "label": "Аккуратный отбор реже забирает мяч"},
    {"id": "hard_tackle_gaps", "kind": "counter", "att": {}, "def": {"tackling": "hard"}, "sign": 1,
     "base": True, "label": "Промах в жёстком отборе оставляет дыру"},
]
INTERACTION_LABELS = {ix["id"]: ix["label"] for ix in INTERACTIONS}


def tuning_of(config) -> dict:
    """DEFAULT_TUNING with GameConfig.career_tactics_tuning on top (one level
    of nesting is merged, so the admin can override a single number)."""
    custom = getattr(config, "career_tactics_tuning", None) or {}
    merged = {}
    for key, value in DEFAULT_TUNING.items():
        if isinstance(value, dict) and isinstance(custom.get(key), dict):
            merged[key] = {**value, **custom[key]}
        else:
            merged[key] = custom.get(key, value)
    return merged


class TacticError(ValueError):
    pass


def clean_tactic(raw: Any, partial: bool = False) -> dict:
    """Validated axes; `partial` (plan instructions) allows a subset."""
    if not isinstance(raw, dict):
        raise TacticError("Неверный формат тактики")
    out = {}
    for axis, values in AXES.items():
        if axis not in raw or raw[axis] is None:
            if partial:
                continue
            if axis == "tackling":  # added later: older clients don't send it
                out[axis] = NEUTRAL_TACTIC[axis]
                continue
            raise TacticError(f"Не выбрано: {AXIS_LABELS[axis].lower()}")
        if raw[axis] not in values:
            raise TacticError(f"{AXIS_LABELS[axis]}: неизвестное значение")
        out[axis] = raw[axis]
    unknown = set(raw) - set(AXES)
    if unknown:
        raise TacticError("Неизвестный параметр тактики")
    return out


def preset_of(tactic: dict) -> str:
    """The preset code whose axes match, or CUSTOM."""
    return next((code for code, axes in PRESETS.items() if axes == tactic), CUSTOM)


def tactic_for(raw_tactic: Optional[dict], playstyle: Optional[str]) -> dict:
    """A participant's / team's axes: the stored tactic, else its legacy
    playstyle's preset, else neutral."""
    if raw_tactic:
        return {**NEUTRAL_TACTIC, **raw_tactic}
    return dict(PRESETS.get(playstyle or "", NEUTRAL_TACTIC))


def describe(tactic: dict) -> str:
    return " · ".join(VALUE_LABELS[axis][tactic[axis]] for axis in AXES)


# --- the engine hook ----------------------------------------------------------------

def _matches(conditions: dict, tactic: dict) -> bool:
    return all(tactic.get(axis) == value for axis, value in conditions.items())


def interactions_for(att: dict, defn: dict, kind: str, zone: Optional[str]) -> list[dict]:
    return [
        ix for ix in INTERACTIONS
        if ix["kind"] == kind and (ix.get("zone") is None or zone is None or ix["zone"] == zone)
        and _matches(ix["att"], att) and _matches(ix["def"], defn)
    ]


@dataclass
class TacticAxes:
    """ClubTacticalSide.career: the axis levers for one side."""

    tactic: dict
    tuning: dict
    # «Разбор соперника» training: interactions in this side's favour are stronger.
    boost: float = 1.0

    def zone_weights(self) -> dict[str, float]:
        none = self.tuning["recycle"][self.tactic["buildup"]]
        wing = self.tuning["wing_share"][self.tactic["direction"]] * (1 - none)
        return {"wing_attack": wing, "central_attack": 1 - none - wing, "none": none}

    def initiative_mult(self) -> float:
        t = self.tuning["initiative"]
        return t[self.tactic["block"]] * t[self.tactic["on_win"]]

    def pool_mult(self, after_losing_ball: bool = False) -> float:
        mult = self.tuning["pool"][self.tactic["block"]]
        if after_losing_ball:
            mult *= self.tuning["counter_pool"][self.tactic["on_loss"]]
        return mult

    def transition_bonus(self) -> float:
        return self.tuning["transition"][self.tactic["on_win"]]

    def retry_chance(self, midfield_control: float) -> float:
        quality = max(0.0, min(1.0, (midfield_control - 58) / (99 - 58)))
        return self.tuning["retry"][self.tactic["buildup"]] * quality

    def foul_mult(self) -> float:
        return self.tuning["foul"][self.tactic.get("tackling", "normal")]

    def tackle_attempt_mult(self) -> float:
        return self.tuning["tackle_attempt"][self.tactic.get("tackling", "normal")]

    def fatigue_mult(self) -> float:
        t = self.tuning["fatigue"]
        return t[self.tactic["block"]] * t[self.tactic["on_loss"]]

    def duel_shift(self, defender: "TacticAxes", kind: str, zone: str) -> tuple[float, tuple]:
        """(Stage-1 bias toward the attacker, ids applied)."""
        applied = interactions_for(self.tactic, defender.tactic, kind, zone)
        favour_attacker = 0.0
        for ix in applied:
            value = ix["sign"] * self.tuning["shift"][ix["id"]]
            if not ix.get("base"):
                value *= self.boost if value > 0 else defender.boost
            favour_attacker += value
        return favour_attacker, tuple(ix["id"] for ix in applied)


# --- scouting: the same table, in expectation ------------------------------------------

def _attack_items(att: dict, defn: dict, tuning: dict, side: str) -> list[dict]:
    """Interactions when `att` attacks `defn`, weighted by how often they
    come up (zone share / counter frequency). `side` = who attacks."""
    weights = TacticAxes(att, tuning).zone_weights()
    items = []
    for kind in ("build_up", "counter"):
        for ix in interactions_for(att, defn, kind, None):
            if ix.get("base"):
                continue
            if kind == "counter":
                weight = tuning["counter_weight"]
            elif ix.get("zone"):
                weight = weights[ix["zone"]]
            else:
                weight = weights["wing_attack"] + weights["central_attack"]
            value = ix["sign"] * tuning["shift"][ix["id"]] * weight
            items.append({"id": ix["id"], "label": ix["label"], "attacker": side,
                          "favours": side if ix["sign"] > 0 else ("them" if side == "me" else "me"),
                          "value": round(value if side == "me" else -value, 4)})
    return items


def matchup_report(mine: dict, theirs: dict, config) -> dict:
    """My tactic vs theirs: every interaction that will apply in either
    direction, its expected weight, and the overall hint."""
    tuning = tuning_of(config)
    items = _attack_items(mine, theirs, tuning, "me") + _attack_items(theirs, mine, tuning, "them")
    score = round(sum(i["value"] for i in items), 4)
    threshold = tuning["hint_threshold"]
    hint = "advantage" if score > threshold else "disadvantage" if score < -threshold else "neutral"
    return {"score": score, "hint": hint, "items": items}


# --- versioned simulation table -------------------------------------------------------------

MATRIX_PATH = Path(__file__).with_name("career_tactics_matchup.json")


def engine_fingerprint() -> str:
    """Hash of everything the simulated table depends on (engine constants,
    interaction table, default tuning, presets). test_career_tactics fails
    when it no longer matches — rerun scripts/simulate_career_tactics.py --write."""
    payload = {
        "interactions": INTERACTIONS, "presets": PRESETS,
        # Training and the scouting-hint knobs don't change simulated matches.
        "tuning": {k: v for k, v in DEFAULT_TUNING.items() if k not in ("training", "counter_weight", "hint_threshold")},
        "initiative": matchup.INITIATIVE_MULT, "sample": matchup.SAMPLE_FRACTION,
        "amplify": matchup.RATIO_AMPLIFICATION, "stage1": matchup.STAGE1_BANDS, "stage2": matchup.STAGE2_BANDS,
        "mentality_shift": matchup.MENTALITY_DEFENSE_SHIFT, "pool": matchup.DEFENSIVE_POOL_STRATEGY,
        "zone_weights": {pos.value: w for pos, w in profile_service.ZONE_WEIGHTS.items()},
        "depth": [profile_service.DEPTH_BONUS_SCALE, profile_service.DEPTH_BONUS_CAP],
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


_matrix_cache: Optional[dict] = None


def load_matrix() -> dict:
    global _matrix_cache
    if _matrix_cache is None:
        _matrix_cache = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    return _matrix_cache


def preset_win_pct(mine: str, theirs: str) -> Optional[float]:
    """Simulated win % of preset vs preset at equal strength (None if either
    tactic is custom)."""
    table = load_matrix().get("presets", {})
    try:
        return float(table[mine][theirs]["win"])
    except KeyError:
        return None


# --- familiarity ---------------------------------------------------------------------------

def familiarity_for(stored: int, last_formation: Optional[str], last_tactic: Optional[dict],
                    formation: str, tactic: dict, config) -> int:
    """Familiarity (tenths of a %) with `formation` + `tactic` given what was
    played last: a new formation keeps career_familiarity_keep_pct, each
    changed axis keeps career_familiarity_axis_keep_pct."""
    value = max(0, int(stored or 0))
    if last_formation is not None and formation != last_formation:
        value = value * int(config.career_familiarity_keep_pct) // 100
    if last_tactic:
        for axis in AXES:
            if last_tactic.get(axis) is not None and last_tactic.get(axis) != tactic.get(axis):
                value = value * int(config.career_familiarity_axis_keep_pct) // 100
    return value


def familiarity_after_match(used: int, config) -> int:
    return min(int(config.career_familiarity_max_tenths), used + int(config.career_familiarity_step_tenths))


# --- match plan ------------------------------------------------------------------------------

SCORE_STATES = ("behind", "level", "ahead")


class PlanError(ValueError):
    pass


def clean_plan(raw: Optional[dict], slot_codes: set[str], squad_ids: set[int], config) -> Optional[dict]:
    """Validates a match plan from the client; raises PlanError. Rules:
    {score: behind|level|ahead, margin: 1-3, from_minute: 1-89, mentality?,
    tactic?: some axes}; subs: {minute: 1-89, slot: code|None (= most tired
    outfield player), card_id: squad card|None (= best fit from the bench),
    min_fatigue: 0-100}."""
    if not raw:
        return None
    rules_in = raw.get("rules") or []
    subs_in = raw.get("subs") or []
    if not isinstance(rules_in, list) or not isinstance(subs_in, list):
        raise PlanError("Неверный формат плана")
    if len(rules_in) > int(config.career_max_plan_rules):
        raise PlanError(f"Не больше {config.career_max_plan_rules} указаний на матч")
    if len(subs_in) > int(config.career_max_substitutions):
        raise PlanError(f"Не больше {config.career_max_substitutions} замен на матч")

    def as_int(value, low, high, what):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise PlanError(f"{what}: допустимо {low}–{high}")
        return value

    rules = []
    for rule in rules_in:
        if not isinstance(rule, dict) or rule.get("score") not in SCORE_STATES:
            raise PlanError("Условие указания: проигрываем, ничья или ведём")
        mentality = rule.get("mentality")
        if mentality is not None and mentality not in matchup.MENTALITIES:
            raise PlanError("Неизвестный настрой")
        try:
            tactic = clean_tactic(rule.get("tactic") or {}, partial=True)
        except TacticError as exc:
            raise PlanError(str(exc)) from exc
        if mentality is None and not tactic:
            raise PlanError("Указание должно что-то менять: настрой или тактику")
        rules.append({
            "score": rule["score"],
            "margin": 0 if rule["score"] == "level" else as_int(rule.get("margin", 1), 1, 3, "Разница в счёте"),
            "from_minute": as_int(rule.get("from_minute"), 1, 89, "Минута"),
            "mentality": mentality, "tactic": tactic,
        })

    subs = []
    used_cards: set[int] = set()
    for sub in subs_in:
        if not isinstance(sub, dict):
            raise PlanError("Неверный формат замены")
        slot, card_id = sub.get("slot"), sub.get("card_id")
        if slot is not None and slot not in slot_codes:
            raise PlanError("Неизвестная позиция для замены")
        if card_id is not None:
            if isinstance(card_id, bool) or not isinstance(card_id, int) or card_id not in squad_ids:
                raise PlanError("Выйти на замену может только игрок заявки")
            if card_id in used_cards:
                raise PlanError("Один игрок не может выйти на замену дважды")
            used_cards.add(card_id)
        subs.append({
            "minute": as_int(sub.get("minute"), 1, 89, "Минута замены"),
            "slot": slot, "card_id": card_id,
            "min_fatigue": as_int(sub.get("min_fatigue", 0), 0, 100, "Порог усталости"),
        })
    if not rules and not subs:
        return None
    return {"rules": rules, "subs": subs}


def drop_stale_subs(plan: Optional[dict], slot_codes: set[str]) -> Optional[dict]:
    """After a formation change: substitutions aimed at slots the new
    formation doesn't have are removed."""
    if not plan:
        return plan
    subs = [s for s in plan.get("subs") or [] if s.get("slot") is None or s["slot"] in slot_codes]
    if not plan.get("rules") and not subs:
        return None
    return {**plan, "subs": subs}


def _rule_active(rule: dict, minute: int, diff: int) -> bool:
    if minute < rule["from_minute"]:
        return False
    if rule["score"] == "behind":
        return diff <= -rule["margin"]
    if rule["score"] == "ahead":
        return diff >= rule["margin"]
    return diff == 0


# --- set pieces ------------------------------------------------------------------------------

CORNER_ROUTINES = {"near": "Навес на ближнюю штангу", "far": "Навес на дальнюю штангу"}
SET_PIECE_DEFENCES = {"zonal": "Зонная защита", "man": "Персональная опека"}
# Which delivery beats which defence (the other pairing is a miss).
ROUTINE_BEATS = {"far": "zonal", "near": "man"}
SET_PIECE_TAKERS = ("corner_taker", "free_kick_taker", "penalty_taker")
DEFAULT_SET_PIECES = {"corner_taker": None, "free_kick_taker": None, "penalty_taker": None,
                      "corner_routine": "far", "corner_defence": "zonal"}
# Auto-picked takers when none is chosen (or the chosen one isn't on the pitch).
TAKER_POSITIONS = {
    "corner_taker": ("LW", "RW", "LM", "RM", "CAM", "CM", "LB", "RB"),
    "free_kick_taker": ("CAM", "CM", "LW", "RW", "ST", "LM", "RM", "CDM"),
    "penalty_taker": ("ST", "CAM", "LW", "RW", "CM", "LM", "RM"),
}


def clean_set_pieces(raw: Any, squad_ids: set[int]) -> dict:
    """Validated set-piece settings (takers are squad card ids or None = auto)."""
    if not isinstance(raw, dict):
        raise PlanError("Неверный формат стандартов")
    out = dict(DEFAULT_SET_PIECES)
    for key in SET_PIECE_TAKERS:
        value = raw.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value not in squad_ids):
            raise PlanError("Исполнитель стандартов — только игрок заявки")
        out[key] = value
    if raw.get("corner_routine", "far") not in CORNER_ROUTINES:
        raise PlanError("Неизвестная подача углового")
    if raw.get("corner_defence", "zonal") not in SET_PIECE_DEFENCES:
        raise PlanError("Неизвестная защита на стандартах")
    out["corner_routine"] = raw.get("corner_routine", "far")
    out["corner_defence"] = raw.get("corner_defence", "zonal")
    return out



# Legend bots' own conditional instructions (same mechanism as a human plan).
LEGEND_BOT_PLAN = {
    "rules": [
        {"score": "behind", "margin": 1, "from_minute": 60, "mentality": "ATTACKING",
         "tactic": {"block": "high", "buildup": "direct"}},
        {"score": "ahead", "margin": 2, "from_minute": 65, "mentality": "DEFENSIVE", "tactic": {"block": "low"}},
    ],
    "subs": [],
}


# --- live match ------------------------------------------------------------------------------

@dataclass
class LivePlayer:
    card: Any                 # engine card (id, player_id, player.{rating, position, display_name}, skill)
    base_rating: int          # rating before familiarity/fatigue/form
    pre_fatigue: int          # condition fatigue before kick-off (0-100)
    form: int = 0
    slot: Any = None          # FormationSlot while on the pitch
    on_minute: int = 0
    off_minute: Optional[int] = None
    gained: float = 0.0       # fatigue gained in this match
    chem_bonus: int = 0       # «химия» rating bonus in the current XI


@dataclass
class CareerSideRunner:
    """One team's live state: who is on the pitch, its base tactic, plan,
    familiarity and in-match fatigue. `label` is the engine side ("a"/"b")."""

    label: str
    name: str
    formation: str
    mentality: str
    tactic: dict
    on_pitch: list[LivePlayer]
    bench: list[LivePlayer]
    config: Any
    familiarity: int = 0                 # tenths of a % for the base formation + tactic
    plan: Optional[dict] = None
    coach: Any = None
    # Chemistry rules frozen at the season start (chemistry_service; None =
    # the mechanic was off). Recomputed for the XI after every substitution.
    chem_rules: Any = None
    # Set-piece takers and schemes (DEFAULT_SET_PIECES shape).
    set_pieces: Optional[dict] = None
    # Training effects for this match (career_service.TRAININGS).
    boost: float = 1.0
    set_piece_boost: float = 1.0
    training: Optional[str] = None
    events_meta: list[dict] = field(default_factory=list)  # rule/sub log for the analysis
    _subs_done: set = field(default_factory=set)
    _effective: tuple = ()
    _cache_key: Any = None
    _cache: Any = None
    _minute: int = 0

    def __post_init__(self):
        self.tactic = {**NEUTRAL_TACTIC, **self.tactic}
        self.tuning = tuning_of(self.config)
        self._effective = (self.mentality, tuple(sorted(self.tactic.items())))
        self.chemistry_team, self.chemistry_max = 0, 0
        self.refresh_chemistry()
        self.chemistry_start = (self.chemistry_team, self.chemistry_max)

    def refresh_chemistry(self) -> None:
        """Neighbour-link chemistry of the players on the pitch (the same
        chemistry_service the other modes use); each one's bonus feeds his
        match rating."""
        if self.chem_rules is None:
            return
        result = chemistry_service.compute_chemistry(
            [(p.card, p.slot) for p in self.on_pitch], self.formation, self.chem_rules, slot_count=len(self.on_pitch),
        )
        for p in self.on_pitch:
            p.chem_bonus = result.rating_bonus(p.slot.code)
        for p in self.bench:
            p.chem_bonus = 0
        self.chemistry_team, self.chemistry_max = result.team, result.team_max

    @property
    def effective_tactic(self) -> dict:
        return dict(self._effective[1])

    def live_fatigue(self, p: LivePlayer, minute: int) -> int:
        return min(100, round(p.pre_fatigue + p.gained))

    def _advance_fatigue(self, minute: int) -> None:
        """In-match fatigue: career_fatigue_per_match per 90 minutes on the
        pitch, faster under a high block / counter-press."""
        elapsed = max(0, minute - self._minute)
        if elapsed:
            rate = self.config.career_fatigue_per_match / 90 * TacticAxes(self.effective_tactic, self.tuning).fatigue_mult()
            for p in self.on_pitch:
                p.gained += rate * elapsed
        self._minute = max(self._minute, minute)

    def _familiarity_pct(self, tactic: dict) -> float:
        value = familiarity_for(self.familiarity, None, self.tactic, self.formation, tactic, self.config)
        return value / 10

    def _rating(self, p: LivePlayer, minute: int, fam_pct: float) -> int:
        penalty = self.live_fatigue(p, minute) / 100 * self.config.career_fatigue_penalty_pct / 100
        base = chemistry_service.boosted_rating(p.base_rating, p.chem_bonus)
        rating = base * (1 + fam_pct / 100) * (1 - penalty) + p.form
        return max(1, min(99, round(rating)))

    def _apply_rules(self, minute: int, diff: int) -> list[dict]:
        rules = (self.plan or {}).get("rules") or []
        mentality, tactic, active = self.mentality, dict(self.tactic), None
        for i, rule in enumerate(rules):
            if _rule_active(rule, minute, diff):
                mentality = rule.get("mentality") or mentality
                tactic.update(rule.get("tactic") or {})
                active = i
        effective = (mentality, tuple(sorted(tactic.items())))
        if effective == self._effective:
            return []
        previous = self.effective_tactic
        self._effective = effective
        if active is None:
            text = f"📋 {self.name}: возврат к базовой тактике"
        else:
            changes = []
            if mentality != self.mentality:
                changes.append(f"настрой «{MENTALITY_LABELS[mentality]}»")
            changes += [VALUE_LABELS[axis][tactic[axis]].lower() for axis in AXES if tactic[axis] != previous[axis]]
            text = f"📋 {self.name}: указание {active + 1} — " + (", ".join(changes) or "без изменений")
        payload = {"rule": active, "mentality": mentality, "tactic": tactic}
        self.events_meta.append({"kind": "rule", "minute": minute, **payload})
        return [{"minute": minute, "event_type": "tactic_change", "team": self.label, "description": text,
                 "payload": payload}]

    def _pick_bench(self, slot, wanted: Optional[int], minute: int) -> Optional[LivePlayer]:
        on_players = {p.card.player_id for p in self.on_pitch}
        fits = [p for p in self.bench if p.off_minute is None and p.card.player_id not in on_players
                and p.card.player.position in CATEGORY_POSITIONS[slot.category]]
        if wanted is not None:
            chosen = next((p for p in fits if p.card.id == wanted), None)
            if chosen is not None:
                return chosen
        if not fits:
            return None
        return max(fits, key=lambda p: (self._rating(p, minute, 0), -p.card.id))

    def _apply_subs(self, minute: int) -> list[dict]:
        events = []
        for i, sub in enumerate((self.plan or {}).get("subs") or []):
            if i in self._subs_done or minute < sub["minute"]:
                continue
            if sub.get("slot") is not None:
                out = next((p for p in self.on_pitch if p.slot.code == sub["slot"]), None)
            else:
                outfield = [p for p in self.on_pitch if p.slot.category != "GK"]
                out = max(outfield, key=lambda p: (self.live_fatigue(p, minute), p.card.id)) if outfield else None
            if out is None or self.live_fatigue(out, minute) < sub.get("min_fatigue", 0):
                continue  # condition not met yet — checked again next phase
            incoming = self._pick_bench(out.slot, sub.get("card_id"), minute)
            self._subs_done.add(i)
            if incoming is None:
                self.events_meta.append({"kind": "sub_skipped", "minute": minute, "sub": i})
                continue
            fatigue = self.live_fatigue(out, minute)
            out.off_minute = minute
            incoming.slot, incoming.on_minute = out.slot, minute
            self.on_pitch[self.on_pitch.index(out)] = incoming
            self.bench.remove(incoming)
            self.bench.append(out)
            self.refresh_chemistry()
            name_in, name_out = incoming.card.player.display_name, out.card.player.display_name
            self.events_meta.append({"kind": "sub", "minute": minute, "sub": i, "in": name_in, "out": name_out,
                                     "fatigue": fatigue})
            events.append({
                "minute": minute, "event_type": "substitution", "team": self.label,
                "description": f"🔁 {self.name}: {name_in} вместо {name_out}",
                "payload": {"in": name_in, "out": name_out, "in_id": incoming.card.id, "out_id": out.card.id,
                            "sub": i, "fatigue": fatigue},
            })
        return events

    def state_at(self, minute: int, own: int, opp: int):
        self._advance_fatigue(minute)
        events = self._apply_subs(minute) + self._apply_rules(minute, own - opp)
        mentality = self._effective[0]
        tactic = self.effective_tactic
        fam_pct = self._familiarity_pct(tactic)
        ratings = [self._rating(p, minute, fam_pct) for p in self.on_pitch]
        # Ratings move by whole points only every few minutes: rebuild the
        # side (zone profile) only when something actually changed.
        key = (self._effective, tuple(p.card.id for p in self.on_pitch), tuple(ratings))
        if key == self._cache_key:
            return (*self._cache, events)
        with_slots = []
        for p, rating in zip(self.on_pitch, ratings):
            p.card.player.rating = rating
            with_slots.append((p.card, p.slot))
        side = matchup.build_side(with_slots, mentality, matchup.CAREER_PLAYSTYLE, coach=self.coach)
        side.career = TacticAxes(tactic, self.tuning, boost=self.boost)
        lineup = [
            {"club_card_id": c.id, "player_id": c.player_id, "name": c.player.display_name, "rating": c.player.rating,
             "position": c.player.position.value, "category": slot.category,
             **({"skill": c.skill} if getattr(c, "skill", None) else {})}
            for c, slot in with_slots
        ]
        self._cache_key, self._cache = key, (side, lineup)
        return side, lineup, events

    def finish(self) -> None:
        self._advance_fatigue(90)

    # --- set pieces ---

    def set_piece_settings(self) -> dict:
        return {**DEFAULT_SET_PIECES, **(self.set_pieces or {})}

    def taker(self, kind: str) -> Optional[LivePlayer]:
        """The chosen taker if he is on the pitch, else the best-rated player
        in a fitting position, else the best outfield player."""
        outfield = [p for p in self.on_pitch if p.slot.category != "GK"]
        chosen = self.set_piece_settings().get(kind)
        found = next((p for p in outfield if p.card.id == chosen), None)
        if found is not None:
            return found
        fitting = [p for p in outfield if p.card.player.position.value in TAKER_POSITIONS[kind]]
        pool = fitting or outfield
        return max(pool, key=lambda p: (p.card.player.rating, -p.card.id)) if pool else None

    def aerial(self, exclude: Optional[LivePlayer] = None) -> Optional[LivePlayer]:
        """Best header in the box: strikers and centre-backs first."""
        pool = [p for p in self.on_pitch if p is not exclude and p.card.player.position.value in ("ST", "CB")]
        pool = pool or [p for p in self.on_pitch if p is not exclude and p.slot.category != "GK"]
        return max(pool, key=lambda p: (p.card.player.rating, -p.card.id)) if pool else None

    def keeper(self) -> Optional[LivePlayer]:
        return next((p for p in self.on_pitch if p.slot.category == "GK"), None)

    def minutes_played(self) -> dict[int, int]:
        """card id -> minutes on the pitch."""
        out = {}
        for p in self.on_pitch + self.bench:
            if p.slot is None:
                continue
            end = p.off_minute if p.off_minute is not None else 90
            out[p.card.id] = max(0, end - p.on_minute)
        return out

    def fatigue_gained(self) -> dict[int, int]:
        """card id -> fatigue gained in this match (post-match condition)."""
        return {p.card.id: round(p.gained) for p in self.on_pitch + self.bench if p.slot is not None}


def _rating_of(p: Optional[LivePlayer]) -> int:
    return int(p.card.player.rating) if p is not None else 60


def _actor(p: Optional[LivePlayer]) -> dict:
    if p is None:
        return {}
    return {"name": p.card.player.display_name, "club_card_id": p.card.id}


class CareerMatchController:
    """tournament_match_engine.MatchController for a career match: sides
    per phase, tackling levers, penalties and set pieces."""

    def __init__(self, a: CareerSideRunner, b: CareerSideRunner):
        self.a, self.b = a, b
        self.set_piece_log: list[dict] = []

    def _side(self, label: str) -> CareerSideRunner:
        return self.a if label == "a" else self.b

    def _axes(self, label: str) -> TacticAxes:
        runner = self._side(label)
        return TacticAxes(runner.effective_tactic, runner.tuning)

    # tackling levers for the defending side (engine hooks)
    def tackle_attempt_mult(self, defending: str) -> float:
        return self._axes(defending).tackle_attempt_mult()

    def foul_mult(self, defending: str) -> float:
        return self._axes(defending).foul_mult()

    def penalty(self, attacking: str, minute: int, card_kind: str) -> tuple[dict, bool]:
        """A penalty after a foul in the box: the taker vs the keeper."""
        shooter = self._side(attacking).taker("penalty_taker")
        defending = "b" if attacking == "a" else "a"
        keeper = self._side(defending).keeper()
        tuning = self._side(attacking).tuning
        chance = max(0.55, min(0.92, tuning["penalty_goal"] + (_rating_of(shooter) - _rating_of(keeper)) / 200))
        scored = random.random() < chance
        event = {
            "minute": minute, "event_type": "goal" if scored else "save", "team": attacking,
            "payload": {"action": "penalty", "is_penalty": True, "set_piece": "penalty", "card": card_kind,
                        "shooter": _actor(shooter).get("name"), "shooter_id": _actor(shooter).get("club_card_id"),
                        "keeper": _actor(keeper).get("name")},
            "description": (f"⚽ Пенальти! {_actor(shooter).get('name', 'Игрок')} реализует удар с точки"
                            if scored else f"🧤 {_actor(keeper).get('name', 'Вратарь')} отражает пенальти!"),
        }
        self.set_piece_log.append({"kind": "penalty", "team": attacking, "scored": scored})
        return event, scored

    def _corner(self, attacking: str, minute: int) -> tuple[dict, bool]:
        att, dfn = self._side(attacking), self._side("b" if attacking == "a" else "a")
        tuning = att.tuning
        taker = att.taker("corner_taker")
        target = att.aerial(exclude=taker)
        marker = dfn.aerial()
        routine = att.set_piece_settings()["corner_routine"]
        defence = dfn.set_piece_settings()["corner_defence"]
        edge = tuning["routine_edge"] if ROUTINE_BEATS[routine] == defence else tuning["routine_miss"]
        delivery = 1 + 0.5 * (_rating_of(taker) - 70) / 30
        header = 2 * _rating_of(target) / max(1, _rating_of(target) + _rating_of(marker))
        chance = max(0.01, min(0.25, tuning["corner_goal"] * delivery * header * edge * att.set_piece_boost))
        scored = random.random() < chance
        name = _actor(target).get("name", "Игрок")
        event = {
            "minute": minute, "event_type": "goal" if scored else "shot", "team": attacking,
            "payload": {"action": "header", "set_piece": "corner", "routine": routine, "defence": defence,
                        "taker": _actor(taker).get("name"), "shooter": name, "shooter_id": _actor(target).get("club_card_id"),
                        "assist": _actor(taker).get("name"), "assist_id": _actor(taker).get("club_card_id")},
            "description": (f"⚽ Гол после углового! {name} головой с подачи {_actor(taker).get('name', '')}"
                            if scored else f"🚩 Угловой: {name} бьёт головой — мимо"),
        }
        self.set_piece_log.append({"kind": "corner", "team": attacking, "scored": scored, "edge": edge > 1})
        return event, scored

    def _free_kick(self, attacking: str, minute: int) -> tuple[dict, bool]:
        att, dfn = self._side(attacking), self._side("b" if attacking == "a" else "a")
        taker, keeper = att.taker("free_kick_taker"), dfn.keeper()
        quality = 1 + (_rating_of(taker) - _rating_of(keeper)) / 40
        chance = max(0.02, min(0.22, att.tuning["free_kick_goal"] * quality * att.set_piece_boost))
        scored = random.random() < chance
        name = _actor(taker).get("name", "Игрок")
        event = {
            "minute": minute, "event_type": "goal" if scored else "save", "team": attacking,
            "payload": {"action": "free_kick", "set_piece": "free_kick", "shooter": name,
                        "shooter_id": _actor(taker).get("club_card_id"), "keeper": _actor(keeper).get("name")},
            "description": (f"⚽ {name} забивает со штрафного!" if scored else f"🧤 Штрафной {name} — вратарь на месте"),
        }
        self.set_piece_log.append({"kind": "free_kick", "team": attacking, "scored": scored})
        return event, scored

    def set_pieces(self, new_events: list[dict], minute: int) -> list[tuple[dict, Optional[str]]]:
        """Set pieces that follow the moment just played: a blocked or saved
        shot can give a corner, a foul outside the box a direct free kick."""
        out = []
        for ev in new_events:
            payload = ev.get("payload") or {}
            if payload.get("set_piece") or payload.get("is_penalty"):
                continue
            if ev["event_type"] in ("blocked", "save"):
                attacking = ev["team"]
                if random.random() < self._side(attacking).tuning["corner_chance"]:
                    event, scored = self._corner(attacking, minute)
                    out.append((event, attacking if scored else None))
            elif ev["event_type"] == "foul_stopped":
                attacking = "b" if ev["team"] == "a" else "a"
                event, scored = self._free_kick(attacking, minute)
                out.append((event, attacking if scored else None))
        return out

    def before_phase(self, minute: int, score_a: int, score_b: int):
        side_a, lineup_a, ev_a = self.a.state_at(minute, score_a, score_b)
        side_b, lineup_b, ev_b = self.b.state_at(minute, score_b, score_a)
        return side_a, side_b, lineup_a, lineup_b, ev_a + ev_b

    def finish(self) -> None:
        self.a.finish()
        self.b.finish()


# --- adaptive bots -----------------------------------------------------------------------------

def pp_per_score() -> float:
    """Win p.p. per unit of matchup score, fitted (least squares through 0)
    on the stored preset table: net result (win - loss) / 2 of every preset
    pairing against its matchup_report score with the default tuning."""
    table = load_matrix().get("presets") or {}
    neutral_config = type("DefaultTuning", (), {"career_tactics_tuning": {}})()
    sxy = sxx = 0.0
    for a, row in table.items():
        for b, result in row.items():
            if a == b or a not in PRESETS or b not in PRESETS:
                continue
            x = matchup_report(PRESETS[a], PRESETS[b], neutral_config)["score"]
            y = (float(result["win"]) - float(result["loss"])) / 2
            sxy += x * y
            sxx += x * x
    return sxy / sxx if sxx > 0 else 0.0


def _familiarity_as_shift(tenths: int) -> float:
    """Familiarity in matchup-score units: its rating points (% of a typical
    ~75 rating) in win p.p., divided by p.p. per score unit."""
    per_score = pp_per_score()
    if per_score <= 0:
        return float("inf")
    per_point = float(load_matrix().get("pp_per_rating_point") or 1.6)
    return tenths / 1000 * 75 * per_point / per_score


def bot_tactics_for_round(
    team: dict, difficulty: str, opponent_history: list[dict], bot_state: dict, config, roll: float,
) -> dict:
    """The bot's tactic for this round. `opponent_history` = the human
    opponent's tactics in rounds ALREADY PLAYED (never this round's choice).
    amateur: its season tactic; pro: with career_bot_counter_chance_pct the
    preset that scores best (matchup_report) against the human's last played
    tactic; legend: the same, but only when the gain beats the familiarity it
    would lose, plus LEGEND_BOT_PLAN. Returns {tactic, adapted, familiarity, plan}."""
    base = tactic_for(team.get("tactic"), team.get("playstyle"))
    current = tactic_for(bot_state.get("tactic"), None) if bot_state.get("tactic") else base
    familiarity = int(bot_state.get("familiarity", 0)) if difficulty == "legend" else 0
    chances = list(config.career_bot_counter_chance_pct or [0, 0, 0])
    chance = chances[("amateur", "pro", "legend").index(difficulty)] if len(chances) == 3 else 0
    result = {"tactic": current if difficulty == "legend" else base, "adapted": False,
              "familiarity": familiarity, "plan": LEGEND_BOT_PLAN if difficulty == "legend" else None}
    if difficulty == "amateur" or not opponent_history or roll * 100 >= chance:
        return result
    target = tactic_for(opponent_history[-1].get("tactic"), opponent_history[-1].get("playstyle"))
    scored = sorted(((matchup_report(axes, target, config)["score"], code) for code, axes in PRESETS.items()), reverse=True)
    best = dict(PRESETS[scored[0][1]])
    if difficulty == "legend":
        now = matchup_report(current, target, config)["score"]
        after = familiarity_for(familiarity, team["formation"], current, team["formation"], best, config)
        if scored[0][0] - now <= _familiarity_as_shift(familiarity - after):
            return result
        result["familiarity"] = after
    result.update(tactic=best, adapted=True)
    return result


# --- post-match analysis -------------------------------------------------------------------------

def build_analysis(
    events: list[dict], tracker: dict, side: str, me: CareerSideRunner, opponent: CareerSideRunner,
) -> dict:
    """Facts from the engine for one side: phase stats from the tracker,
    goals by origin from the tagged events, which axis interactions actually
    applied in duels and how they went, familiarity used, and every
    instruction/substitution as it happened. No inferred causality — only
    what the engine recorded."""
    other = "b" if side == "a" else "a"
    mine, theirs = tracker.get(side, {}), tracker.get(other, {})

    def goals(team: str) -> dict:
        out = {"wing": 0, "central": 0, "counter": 0, "penalty": 0, "set_piece": 0}
        for e in events:
            if e.get("event_type") != "goal" or e.get("team") != team:
                continue
            payload = e.get("payload") or {}
            if payload.get("is_penalty"):
                out["penalty"] += 1
            elif payload.get("set_piece"):
                out["set_piece"] += 1
            elif payload.get("origin") == "counter":
                out["counter"] += 1
            elif payload.get("zone") == "wing_attack":
                out["wing"] += 1
            else:
                out["central"] += 1
        return out

    def phases(stats: dict) -> dict:
        return {k: int(stats.get(k, 0)) for k in (
            "attacks", "wing_attack", "central_attack", "recycled", "advance", "stall", "breakdown",
            "counters", "counter_chances",
        )}

    def set_pieces(team: str) -> dict:
        out = {k: 0 for k in ("corner", "corner_goals", "free_kick", "free_kick_goals", "penalty", "penalty_goals")}
        for e in events:
            kind = (e.get("payload") or {}).get("set_piece")
            if kind and e.get("team") == team:
                out[kind] += 1
                if e.get("event_type") == "goal":
                    out[f"{kind}_goals"] += 1
        return out

    duels = []
    for who, stats in (("me", mine), ("them", theirs)):
        for ix_id, (applied, won) in sorted((stats.get("interactions") or {}).items()):
            duels.append({"id": ix_id, "label": INTERACTION_LABELS.get(ix_id, ix_id), "attacker": who,
                          "applied": applied, "attacker_won": won})

    return {
        "formation": me.formation, "mentality": me.mentality, "tactic": me.tactic,
        "preset": preset_of(me.tactic), "opponent_tactic": opponent.tactic,
        "matchup": matchup_report(me.tactic, opponent.tactic, me.config),
        "familiarity_pct": me.familiarity / 10,
        "training": me.training,
        "chemistry": {"team": me.chemistry_start[0], "max": me.chemistry_start[1]} if me.chem_rules else None,
        "mine": phases(mine), "theirs": phases(theirs),
        "goals_mine": goals(side), "goals_theirs": goals(other),
        "set_pieces_mine": set_pieces(side), "set_pieces_theirs": set_pieces(other),
        "duels": duels,
        "instructions": [m for m in me.events_meta if m["kind"] == "rule"],
        "substitutions": [m for m in me.events_meta if m["kind"] in ("sub", "sub_skipped")],
        "plan": me.plan,
    }
