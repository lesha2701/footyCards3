"""«Карьера тренера» tactics layer (pure — no DB access): playstyle counters
and the scouting hint, familiarity (сыгранность), the match plan
(conditional instructions + substitutions) and the phase-by-phase match
controller that applies it, adaptive bots by difficulty and the post-match
tactical analysis.

Only seasons created with state["tactics_version"] >= 1 use any of this
(career_service._play_round); older seasons keep the original
tournament_match_engine.simulate_match path unchanged. Every coefficient is
a GameConfig.career_* field.
"""
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.services import club_tactical_matchup_service as matchup
from app.services import club_tactical_profile_service as profile_service
from app.services.lineup_service import CATEGORY_POSITIONS

TACTICS_VERSION = 1

MENTALITY_LABELS = {
    "PARK_THE_BUS": "Автобус у ворот", "DEFENSIVE": "Оборонительный", "BALANCED": "Сбалансированный",
    "ATTACKING": "Атакующий",
}
PLAYSTYLE_LABELS = {
    "WING_PLAY": "Игра флангами", "CENTRAL_PLAY": "Игра через центр", "POSSESSION": "Контроль мяча",
    "HIGH_PRESS": "Высокий прессинг", "COUNTER_ATTACK": "Контратаки",
}

# --- playstyle counters --------------------------------------------------------
# style -> the two styles it counters. A five-way rock-paper-scissors: every
# style counters exactly two others and is countered by the remaining two
# (test_career_tactics.test_counter_table_is_a_balanced_cycle). The engine
# applies it as a bounded per-duel ratio shift (ClubTacticalSide.style_edge,
# GameConfig.career_style_counter_permille); the scouting hint reads the very
# same table, and career_style_matchup.json (scripts/simulate_career_tactics.py)
# holds the simulated win rates that confirm it.
COUNTERS: dict[str, tuple[str, str]] = {
    "HIGH_PRESS": ("POSSESSION", "CENTRAL_PLAY"),      # pressing chokes slow or narrow build-up
    "POSSESSION": ("COUNTER_ATTACK", "WING_PLAY"),     # keeping the ball starves transitions and crosses
    "COUNTER_ATTACK": ("HIGH_PRESS", "WING_PLAY"),     # space behind a high line / advanced full-backs
    "WING_PLAY": ("HIGH_PRESS", "CENTRAL_PLAY"),       # going around the press / a narrow block
    "CENTRAL_PLAY": ("POSSESSION", "COUNTER_ATTACK"),  # overloading the middle of a patient or deep side
}


def counters_of(playstyle: str) -> list[str]:
    """Styles that counter `playstyle`."""
    return [style for style, beaten in COUNTERS.items() if playstyle in beaten]


def counter_shift(config) -> float:
    return max(0, int(getattr(config, "career_style_counter_permille", 0) or 0)) / 1000


def style_edge_for(playstyle: str, config) -> Optional[dict[str, float]]:
    shift = counter_shift(config)
    if shift <= 0:
        return None
    return {beaten: shift for beaten in COUNTERS[playstyle]}


def matchup_hint(mine: str, theirs: str) -> str:
    """"advantage" / "neutral" / "disadvantage" for my playstyle against
    theirs — the same table the engine's style edge is built from."""
    if theirs in COUNTERS.get(mine, ()):
        return "advantage"
    if mine in COUNTERS.get(theirs, ()):
        return "disadvantage"
    return "neutral"


# --- versioned simulation table --------------------------------------------------

MATRIX_PATH = Path(__file__).with_name("career_style_matchup.json")


def engine_fingerprint(counter_permille: int) -> str:
    """Hash of everything the simulated matchup table depends on: the
    counter table, the counter shift it was generated with and the tactical
    engine's constants. test_career_tactics fails when it no longer matches
    the stored table — rerun scripts/simulate_career_tactics.py --write."""
    payload = {
        "counters": COUNTERS, "counter_permille": counter_permille,
        "initiative": matchup.INITIATIVE_MULT, "sample": matchup.SAMPLE_FRACTION,
        "press_pool": matchup.HIGH_PRESS_POOL_MULT, "transition": matchup.TRANSITION_BONUS,
        "amplify": matchup.RATIO_AMPLIFICATION, "stage1": matchup.STAGE1_BANDS, "stage2": matchup.STAGE2_BANDS,
        "zones": matchup.PLAYSTYLE_ZONE_WEIGHTS, "retry": matchup.POSSESSION_RETRY_MAX,
        "press_shift": matchup.HIGH_PRESS_DEFENSE_SHIFT, "mentality_shift": matchup.MENTALITY_DEFENSE_SHIFT,
        "pool": matchup.DEFENSIVE_POOL_STRATEGY,
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


def win_pct(mine: str, theirs: str) -> float:
    """Simulated win % of `mine` against `theirs` at equal strength."""
    return float(load_matrix()["table"][mine][theirs]["win"])


def pp_per_rating_point() -> float:
    return float(load_matrix()["pp_per_rating_point"])


# --- familiarity ---------------------------------------------------------------------

def familiarity_for(stored: int, last_formation: Optional[str], last_playstyle: Optional[str],
                    formation: str, playstyle: str, config) -> int:
    """Familiarity (tenths of a %) the team has with `formation` + `playstyle`
    given what it played last: each changed component keeps only
    career_familiarity_keep_pct of it."""
    value = max(0, int(stored or 0))
    keep = int(config.career_familiarity_keep_pct)
    if last_formation is not None and formation != last_formation:
        value = value * keep // 100
    if last_playstyle is not None and playstyle != last_playstyle:
        value = value * keep // 100
    return value


def familiarity_after_match(used: int, config) -> int:
    return min(int(config.career_familiarity_max_tenths), used + int(config.career_familiarity_step_tenths))


# --- match plan -----------------------------------------------------------------------

SCORE_STATES = ("behind", "level", "ahead")


class PlanError(ValueError):
    pass


def clean_plan(raw: Optional[dict], slot_codes: set[str], squad_ids: set[int], config) -> Optional[dict]:
    """Validates a match plan from the client; raises PlanError. Rules:
    {score: behind|level|ahead, margin: 1-3, from_minute: 1-89, mentality?,
    playstyle?}; subs: {minute: 1-89, slot: code|None (= most tired outfield
    player), card_id: squad card|None (= best fit from the bench),
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
        mentality, playstyle = rule.get("mentality"), rule.get("playstyle")
        if mentality is None and playstyle is None:
            raise PlanError("Указание должно менять настрой или стиль")
        if mentality is not None and mentality not in matchup.MENTALITIES:
            raise PlanError("Неизвестный настрой")
        if playstyle is not None and playstyle not in matchup.PLAYSTYLES:
            raise PlanError("Неизвестный стиль")
        rules.append({
            "score": rule["score"],
            "margin": 0 if rule["score"] == "level" else as_int(rule.get("margin", 1), 1, 3, "Разница в счёте"),
            "from_minute": as_int(rule.get("from_minute"), 1, 89, "Минута"),
            "mentality": mentality, "playstyle": playstyle,
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


# Legend bots' own conditional instructions (same mechanism as a human plan).
LEGEND_BOT_PLAN = {
    "rules": [
        {"score": "behind", "margin": 1, "from_minute": 60, "mentality": "ATTACKING", "playstyle": None},
        {"score": "ahead", "margin": 2, "from_minute": 65, "mentality": "DEFENSIVE", "playstyle": None},
    ],
    "subs": [],
}


# --- live match ---------------------------------------------------------------------------

@dataclass
class LivePlayer:
    card: Any                 # engine card (id, player_id, player.{rating, position, display_name}, skill)
    base_rating: int          # rating before familiarity/fatigue/form
    pre_fatigue: int          # condition fatigue before kick-off (0-100)
    form: int = 0
    slot: Any = None          # FormationSlot while on the pitch
    on_minute: int = 0
    off_minute: Optional[int] = None


@dataclass
class CareerSideRunner:
    """One team's live state: who is on the pitch, its base tactics, plan,
    familiarity and in-match fatigue. `label` is the engine side ("a"/"b")."""

    label: str
    name: str
    formation: str
    mentality: str
    playstyle: str
    on_pitch: list[LivePlayer]
    bench: list[LivePlayer]
    config: Any
    familiarity: int = 0                 # tenths of a % for the base formation+playstyle
    plan: Optional[dict] = None
    coach: Any = None
    events_meta: list[dict] = field(default_factory=list)  # rule/sub log for the analysis
    _rule_state: Optional[int] = None    # index of the rule currently in force (None = base)
    _subs_done: set = field(default_factory=set)
    _effective: tuple = ()
    _cache_key: Any = None
    _cache: Any = None

    def __post_init__(self):
        self._effective = (self.mentality, self.playstyle)

    def live_fatigue(self, p: LivePlayer, minute: int) -> int:
        played = max(0, minute - p.on_minute)
        return min(100, round(p.pre_fatigue + self.config.career_fatigue_per_match * played / 90))

    def _familiarity_pct(self, playstyle: str) -> float:
        value = self.familiarity
        if playstyle != self.playstyle:
            value = value * int(self.config.career_familiarity_keep_pct) // 100
        return value / 10

    def _rating(self, p: LivePlayer, minute: int, fam_pct: float) -> int:
        penalty = self.live_fatigue(p, minute) / 100 * self.config.career_fatigue_penalty_pct / 100
        rating = p.base_rating * (1 + fam_pct / 100) * (1 - penalty) + p.form
        return max(1, min(99, round(rating)))

    def _apply_rules(self, minute: int, diff: int) -> list[dict]:
        rules = (self.plan or {}).get("rules") or []
        mentality, playstyle, active = self.mentality, self.playstyle, None
        for i, rule in enumerate(rules):
            if _rule_active(rule, minute, diff):
                mentality = rule.get("mentality") or mentality
                playstyle = rule.get("playstyle") or playstyle
                active = i
        if (mentality, playstyle) == self._effective:
            self._rule_state = active
            return []
        self._effective = (mentality, playstyle)
        self._rule_state = active
        if active is None:
            text = f"📋 {self.name}: возврат к базовой тактике"
        else:
            changes = []
            if mentality != self.mentality:
                changes.append(f"настрой «{MENTALITY_LABELS[mentality]}»")
            if playstyle != self.playstyle:
                changes.append(f"стиль «{PLAYSTYLE_LABELS[playstyle]}»")
            text = f"📋 {self.name}: указание {active + 1} — " + (", ".join(changes) or "базовая тактика")
        payload = {"rule": active, "mentality": mentality, "playstyle": playstyle}
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
        events = self._apply_subs(minute) + self._apply_rules(minute, own - opp)
        mentality, playstyle = self._effective
        fam_pct = self._familiarity_pct(playstyle)
        ratings = [self._rating(p, minute, fam_pct) for p in self.on_pitch]
        # Ratings move by whole points only every few minutes: rebuild the
        # side (zone profile) only when something actually changed.
        key = (mentality, playstyle, tuple(p.card.id for p in self.on_pitch), tuple(ratings))
        if key == self._cache_key:
            return (*self._cache, events)
        with_slots = []
        for p, rating in zip(self.on_pitch, ratings):
            p.card.player.rating = rating
            with_slots.append((p.card, p.slot))
        side = matchup.build_side(with_slots, mentality, playstyle, coach=self.coach)
        side.style_edge = style_edge_for(playstyle, self.config)
        lineup = [
            {"club_card_id": c.id, "player_id": c.player_id, "name": c.player.display_name, "rating": c.player.rating,
             "position": c.player.position.value, "category": slot.category,
             **({"skill": c.skill} if getattr(c, "skill", None) else {})}
            for c, slot in with_slots
        ]
        self._cache_key, self._cache = key, (side, lineup)
        return side, lineup, events

    def minutes_played(self) -> dict[int, int]:
        """card id -> minutes on the pitch (for post-match fatigue)."""
        out = {}
        for p in self.on_pitch + self.bench:
            if p.slot is None:
                continue
            end = p.off_minute if p.off_minute is not None else 90
            out[p.card.id] = max(0, end - p.on_minute)
        return out


class CareerMatchController:
    """tournament_match_engine.MatchController for a career match."""

    def __init__(self, a: CareerSideRunner, b: CareerSideRunner):
        self.a, self.b = a, b

    def before_phase(self, minute: int, score_a: int, score_b: int):
        side_a, lineup_a, ev_a = self.a.state_at(minute, score_a, score_b)
        side_b, lineup_b, ev_b = self.b.state_at(minute, score_b, score_a)
        return side_a, side_b, lineup_a, lineup_b, ev_a + ev_b


# --- adaptive bots --------------------------------------------------------------------------

def bot_tactics_for_round(
    team: dict, difficulty: str, opponent_history: list[dict], bot_state: dict, config, roll: float,
) -> dict:
    """The bot's playstyle for this round. `opponent_history` = the human
    opponent's tactics in rounds ALREADY PLAYED (never this round's choice).
    amateur: its season style; pro: with career_bot_counter_chance_pct a
    counter to the human's last played style; legend: the same, but only when
    the simulated gain beats the familiarity it would lose, and it also plays
    LEGEND_BOT_PLAN. Returns {playstyle, adapted, familiarity, plan}."""
    base = team["playstyle"]
    current = bot_state.get("playstyle") or base
    familiarity = int(bot_state.get("familiarity", 0)) if difficulty == "legend" else 0
    chances = list(config.career_bot_counter_chance_pct or [0, 0, 0])
    chance = chances[("amateur", "pro", "legend").index(difficulty)] if len(chances) == 3 else 0
    result = {"playstyle": current if difficulty == "legend" else base, "adapted": False,
              "familiarity": familiarity, "plan": LEGEND_BOT_PLAN if difficulty == "legend" else None}
    if difficulty == "amateur" or not opponent_history or roll * 100 >= chance:
        return result
    target = opponent_history[-1]["playstyle"]
    options = counters_of(target)
    best = max(options, key=lambda s: (win_pct(s, target), s))
    if difficulty == "legend":
        if matchup_hint(current, target) == "advantage":
            return result
        avg = sum(p["rating"] for p in team["players"]) / max(1, len(team["players"]))
        after = familiarity_for(familiarity, team["formation"], current, team["formation"], best, config)
        loss_pp = (familiarity - after) / 1000 * avg * pp_per_rating_point()
        gain_pp = win_pct(best, target) - win_pct(current, target)
        if gain_pp <= loss_pp:
            return result
        result["familiarity"] = after
    result.update(playstyle=best, adapted=True)
    return result


# --- post-match analysis -------------------------------------------------------------------

def build_analysis(
    events: list[dict], tracker: dict, side: str, me: CareerSideRunner, opponent_playstyle: str,
) -> dict:
    """Facts from the engine for one side: phase stats from the tracker,
    goals by origin from the tagged events, the style matchup actually
    applied, familiarity used, and every instruction/substitution as it
    happened. No inferred causality — only what the engine recorded."""
    other = "b" if side == "a" else "a"
    mine, theirs = tracker.get(side, {}), tracker.get(other, {})

    def goals(team: str) -> dict:
        out = {"wing": 0, "central": 0, "counter": 0, "penalty": 0}
        for e in events:
            if e.get("event_type") != "goal" or e.get("team") != team:
                continue
            payload = e.get("payload") or {}
            if payload.get("is_penalty"):
                out["penalty"] += 1
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

    return {
        "playstyle": me.playstyle, "mentality": me.mentality, "formation": me.formation,
        "opponent_playstyle": opponent_playstyle,
        "matchup": matchup_hint(me.playstyle, opponent_playstyle) if style_edge_for(me.playstyle, me.config) else "neutral",
        "familiarity_pct": me.familiarity / 10,
        "mine": phases(mine), "theirs": phases(theirs),
        "goals_mine": goals(side), "goals_theirs": goals(other),
        "instructions": [m for m in me.events_meta if m["kind"] == "rule"],
        "substitutions": [m for m in me.events_meta if m["kind"] in ("sub", "sub_skipped")],
        "plan": me.plan,
    }
