"""Flank duels of «Карьера тренера»: who is hard or easy for whom.

A flank attack goes down one side: the attacker who stands on that flank
(by his formation slot) meets the defender on the opposite flank of the
other team — the right winger plays against the left back
(club_tactical_matchup_service._resolve_progression_and_duel). On top of the
ratings, such a personal duel gets an edge (a stage-1 bias, the same unit
as roles and man-marking, career_tactics_service.TacticAxes.player_shift)
made of three parts, capped together:

  * style — one field per footballer (STYLES; NULL = derived, style_of).
    As an attacker it reads speed / technique / power, as a defender
    speed / power / reading; MATRIX is the rock-paper-scissors of the two:
    every type has one easy, one hard and one even matchup.
  * rivalry — known matchups set in the admin (PlayerRivalry): «Мендеш
    гасит Ямаля», levels -3..+3.
  * history — every career match adds its flank duels to one global row per
    pair (DuelHistory). With enough duels a lopsided record turns into fear
    (the loser) or a favourite opponent (the winner), ±1..2 levels.

The pieces for one match live in a DuelBook (loaded once, read by the
engine, collecting the duels it played); save_log adds them to the history.
Numbers: career_tactics_tuning["duels"] over DEFAULT_TUNING. A bias of 0.2
is about ±10 percentage points of the duels the attacker wins between two
equal players (stage-1 band 0.30 / 0.45 / 0.25).
"""
import zlib
from types import SimpleNamespace
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.duel import DuelHistory, PlayerRivalry
from app.models.player import Player
from app.services.player_identity import normalize, person_key

STYLES = ("speed", "technique", "power", "reading")
STYLE_LABELS = {"speed": "Скорость", "technique": "Техника", "power": "Сила", "reading": "Чтение игры"}
# The same field read in the two roles of a duel.
AS_ATTACKER = {"speed": "speed", "technique": "technique", "power": "power", "reading": "technique"}
AS_DEFENDER = {"speed": "speed", "technique": "reading", "power": "power", "reading": "reading"}
ATTACKER_LABELS = {"speed": "скоростной", "technique": "технарь", "power": "силовой"}
DEFENDER_LABELS = {"speed": "быстрый", "power": "силовой", "reading": "читающий игру"}
# (attacker type, defender type) -> +1 the attacker has the edge, -1 the defender, 0 even.
MATRIX: dict[tuple[str, str], int] = {
    ("speed", "speed"): -1, ("speed", "power"): 1, ("speed", "reading"): 0,
    ("technique", "speed"): 1, ("technique", "power"): 0, ("technique", "reading"): -1,
    ("power", "speed"): 0, ("power", "power"): -1, ("power", "reading"): 1,
}
MATRIX_REASONS: dict[tuple[str, str], str] = {
    ("speed", "speed"): "быстрый защитник догоняет — убежать некуда",
    ("speed", "power"): "силовой защитник медленный — не успевает",
    ("speed", "reading"): "на равных",
    ("technique", "speed"): "быстрый защитник рано бросается в отбор — финт, и он позади",
    ("technique", "power"): "на равных",
    ("technique", "reading"): "читающий игру не ведётся на финты",
    ("power", "speed"): "на равных",
    ("power", "power"): "ломается о такого же «танка»",
    ("power", "reading"): "читающий игру не выигрывает борьбу корпусом",
}

LEFT = frozenset({"LB", "LWB", "LM", "LW"})
RIGHT = frozenset({"RB", "RWB", "RM", "RW"})
# Duels in the centre: a striker (or a «десятка») against a centre-back.
CENTRE_ATT = frozenset({"ST", "CAM"})
CENTRE_DEF = frozenset({"CB"})
_DEFENSIVE = frozenset({"GK", "CB", "LB", "RB", "LWB", "RWB", "CDM"})
_ATTACKING = frozenset({"LW", "RW", "LM", "RM", "ST", "CAM"})

DEFAULT_TUNING: dict[str, Any] = {
    "style": 0.08,           # matrix edge (±1)
    "rivalry_level": 0.055,  # per level of a known rivalry (±3)
    "history_level": 0.04,   # per level of fear / favourite opponent (±2)
    "cap": 0.20,             # the three together
    # Share of flank attacks down the LEFT flank for tactic["flank"].
    "flank_share": {"both": 0.5, "left": 0.7, "right": 0.3},
    # History: decided duels needed, the winner's share for level 1 / 2,
    # and how many decided duels a pair remembers (older ones fade).
    "history_min": 20,
    "history_shares": [0.6, 0.7],
    "history_cap": 60,
    # Adaptive bots switch their attacks to the flank whose duels are better
    # by at least this much (sum of edges).
    "bot_switch": 0.08,
    # The same edge in the centre (striker vs centre-back), as a share of
    # the flank one: the centre is crowded, one duel decides less.
    "centre_scale": 0.75,
    # Half-time: a «Профи» / «Легенда» bot that lost at least
    # `halftime_min` flank duels on its flank of attack, winning no more
    # than `halftime_share` of them, switches to the other one.
    "halftime_min": 3,
    "halftime_share": 0.35,
    # Match stories: «выключил» = the defender won at least this many
    # duels of a pair, the attacker none.
    "story_shutout": 4,
}


def tuning_of(career_tuning: Optional[dict]) -> dict:
    custom = (career_tuning or {}).get("duels") or {}
    return {**DEFAULT_TUNING, **custom}


def side_of(position: Any) -> Optional[str]:
    """"left" / "right" / None for a slot's (or player's) position."""
    code = getattr(position, "value", position)
    return "left" if code in LEFT else "right" if code in RIGHT else None


def centre_of(position: Any) -> Optional[str]:
    """"att" (striker, «десятка») / "def" (centre-back) / None for a slot."""
    code = getattr(position, "value", position)
    return "att" if code in CENTRE_ATT else "def" if code in CENTRE_DEF else None


def style_of(player: Any) -> str:
    """The player's duel style: set in the admin, else a stable derived one —
    from his person (so every version of him agrees) and his line."""
    style = getattr(player, "duel_style", None)
    if style in STYLES:
        return style
    position = getattr(getattr(player, "position", None), "value", getattr(player, "position", None))
    pool = (("speed", "power", "reading") if position in _DEFENSIVE
            else ("speed", "technique", "power") if position in _ATTACKING else STYLES)
    return pool[zlib.crc32(person_key(player).encode()) % len(pool)]


def history_level(attacker_wins: float, defender_wins: float, tuning: dict) -> int:
    """-2..+2: fear (the defender wins most) or a favourite opponent."""
    decided = attacker_wins + defender_wins
    if decided < tuning["history_min"] or decided <= 0:
        return 0
    share = attacker_wins / decided
    level = sum(1 for s in tuning["history_shares"] if share >= s)
    if level:
        return level
    return -sum(1 for s in tuning["history_shares"] if 1 - share >= s)


@dataclass
class DuelBook:
    """Everything one match needs about its players' duels; `log` collects
    the duels the engine played (attacker key, defender key, outcome,
    minute, where: "left" / "right" flank or "centre")."""

    tuning: dict
    players: dict[int, tuple[str, str, str]]  # player_id -> (person key, style, name)
    rivalries: dict[tuple[str, str], int] = field(default_factory=dict)
    history: dict[tuple[str, str], tuple[float, float]] = field(default_factory=dict)
    log: list[tuple[str, str, str, int, str]] = field(default_factory=list)
    # Coach skill «Аналитик»: person key -> how much of his fear (history
    # against him) is left, 1 = all, 0 = none.
    fear_left: dict[str, float] = field(default_factory=dict)

    def info(self, card: Any) -> Optional[tuple[str, str, str]]:
        return self.players.get(getattr(card, "player_id", None)) if card is not None else None

    def edge(self, att_card: Any, def_card: Any, where: str = "flank") -> Optional[dict]:
        """The duel's edge for the attacker, with its parts; None when either
        player is unknown (e.g. «Мой игрок»). In the centre the edge is
        scaled by centre_scale."""
        e = self._edge(att_card, def_card)
        if e is not None and where == "centre":
            cap = self.tuning["cap"] * self.tuning["centre_scale"]
            e["bias"] = max(-cap, min(cap, e["bias"] * self.tuning["centre_scale"]))
        return e

    def _edge(self, att_card: Any, def_card: Any) -> Optional[dict]:
        att, dfn = self.info(att_card), self.info(def_card)
        if att is None or dfn is None:
            return None
        t = self.tuning
        a_type, d_type = AS_ATTACKER[att[1]], AS_DEFENDER[dfn[1]]
        style = MATRIX[(a_type, d_type)]
        rivalry = self.rivalries.get((att[0], dfn[0]), 0)
        wins = self.history.get((att[0], dfn[0]), (0.0, 0.0))
        hist = history_level(wins[0], wins[1], t)
        fear = 1.0
        if hist < 0:
            fear = self.fear_left.get(att[0], 1.0)
        elif hist > 0:
            fear = self.fear_left.get(dfn[0], 1.0)
        raw = style * t["style"] + rivalry * t["rivalry_level"] + hist * t["history_level"] * fear
        bias = max(-t["cap"], min(t["cap"], raw))
        return {
            "bias": bias, "style": style, "rivalry": rivalry, "history": hist,
            "attacker_type": a_type, "defender_type": d_type,
            "record": [round(wins[0]), round(wins[1])],
        }

    def record(self, att_card: Any, def_card: Any, outcome: str, minute: int = 0, where: str = "left") -> None:
        att, dfn = self.info(att_card), self.info(def_card)
        if att is not None and dfn is not None and att[0] != dfn[0]:
            self.log.append((att[0], dfn[0], outcome, int(minute), where))

    def played(self, until: Optional[int] = None) -> dict[tuple[str, str], list[int]]:
        """Decided duels of this match per pair: [attacker wins, defender
        wins]; `until` = only those up to that minute (the first half)."""
        out: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        for a, d, outcome, minute, _where in self.log:
            if until is not None and minute > until:
                continue
            if outcome == "advance":
                out[(a, d)][0] += 1
            elif outcome == "breakdown":
                out[(a, d)][1] += 1
        return dict(out)


def pp(bias: float) -> int:
    """A bias as approximate percentage points of the duels won."""
    return round(bias * 50)


def describe(book: DuelBook, att_card: Any, def_card: Any, where: str = "flank") -> Optional[dict]:
    """A duel for the screens: names, the edge in п.п., verdict and reasons."""
    e = book.edge(att_card, def_card, where)
    if e is None:
        return None
    reasons = []
    if e["style"]:
        reasons.append(f"{ATTACKER_LABELS[e['attacker_type']]} против: {DEFENDER_LABELS[e['defender_type']]} — "
                       + MATRIX_REASONS[(e["attacker_type"], e["defender_type"])])
    if e["rivalry"]:
        reasons.append("известное противостояние")
    if e["history"] < 0:
        reasons.append(f"боится: {e['record'][0]}:{e['record'][1]} в дуэлях")
    elif e["history"] > 0:
        reasons.append(f"любимый соперник: {e['record'][0]}:{e['record'][1]} в дуэлях")
    value = pp(e["bias"])
    verdict = "easy" if value >= 3 else "hard" if value <= -3 else "even"
    return {
        "attacker": book.info(att_card)[2], "defender": book.info(def_card)[2],
        "attacker_card_id": getattr(att_card, "id", None), "defender_card_id": getattr(def_card, "id", None),
        "attacker_player_id": getattr(att_card, "player_id", None),
        "attacker_style": e["attacker_type"], "defender_style": e["defender_type"],
        "pp": value, "verdict": verdict, "reasons": reasons, "record": e["record"],
    }


def flank_duels(book: DuelBook, attackers: list[tuple[Any, Any]], defenders: list[tuple[Any, Any]]) -> list[dict]:
    """Expected duels when `attackers` ((card, slot) of the attacking XI) go
    down a flank against `defenders`' opposite flank: each wide attacker vs
    the deepest player on that side (full-back first)."""
    order = {"LB": 0, "RB": 0, "LWB": 1, "RWB": 1, "LM": 2, "RM": 2, "LW": 3, "RW": 3}
    out = []
    for card, slot in attackers:
        side = side_of(slot.ideal_position)
        if side is None or slot.ideal_position.value in ("LB", "RB", "LWB", "RWB"):
            continue
        facing = "right" if side == "left" else "left"
        candidates = [(c, s) for c, s in defenders if side_of(s.ideal_position) == facing]
        if not candidates:
            continue
        def_card = min(candidates, key=lambda cs: order.get(cs[1].ideal_position.value, 9))[0]
        duel = describe(book, card, def_card)
        if duel is not None:
            out.append({**duel, "flank": side})
    return out


def best_flank(book: DuelBook, attackers: list[tuple[Any, Any]], defenders: list[tuple[Any, Any]]) -> str:
    """A bot's flank: the side whose expected duels are better by bot_switch."""
    score = {"left": 0.0, "right": 0.0}
    for duel in flank_duels(book, attackers, defenders):
        score[duel["flank"]] += duel["pp"] / 50
    gap = score["left"] - score["right"]
    if abs(gap) < book.tuning["bot_switch"]:
        return "both"
    return "left" if gap > 0 else "right"


def centre_duels(book: DuelBook, attackers: list[tuple[Any, Any]], defenders: list[tuple[Any, Any]]) -> list[dict]:
    """Expected duels in the centre: each striker / «десятка» against each
    centre-back of the other side (the engine meets any of them)."""
    backs = [c for c, s in defenders if centre_of(s.ideal_position) == "def"]
    out = []
    for card, slot in attackers:
        if centre_of(slot.ideal_position) != "att":
            continue
        for back in backs:
            duel = describe(book, card, back, "centre")
            if duel is not None:
                out.append({**duel, "flank": "centre"})
    return out


def halftime_flank(book: DuelBook, keys: set[str], flank: str) -> Optional[str]:
    """A bot's flank for the second half: when its attackers (`keys`) lost
    the first-half flank duels on the flank it attacked, it tries the other
    one. None = keep the flank."""
    t = book.tuning
    score = {"left": [0, 0], "right": [0, 0]}
    for a, _d, outcome, minute, where in book.log:
        if a in keys and where in score and minute <= 45 and outcome in ("advance", "breakdown"):
            score[where][0 if outcome == "advance" else 1] += 1
    focus = [flank] if flank in score else ["left", "right"]
    for side in focus:
        won, lost = score[side]
        if won + lost >= t["halftime_min"] and won <= t["halftime_share"] * (won + lost):
            other = "right" if side == "left" else "left"
            o_won, o_lost = score[other]
            if flank == "both" or o_won >= o_lost:
                return other
            return "both"
    return None


def first_half(book: DuelBook, my_keys: set[str], limit: int = 5) -> dict:
    """The live match centre at the break: my players' flank duels of the
    first half, and what to do about the ones that go badly."""
    names = {key: name for key, _style, name in book.players.values()}
    side_of_pair: dict[tuple[str, str], str] = {}
    for a, d, _o, minute, where in book.log:
        if minute <= 45:
            side_of_pair[(a, d)] = where
    rows, hints = [], []
    for (a, d), (aw, dw) in sorted(book.played(until=45).items(), key=lambda kv: -sum(kv[1])):
        if a not in my_keys and d not in my_keys:
            continue
        mine = "attack" if a in my_keys else "defence"
        where = side_of_pair.get((a, d), "left")
        rows.append({"attacker": names.get(a, a), "defender": names.get(d, d), "attacker_wins": aw,
                     "defender_wins": dw, "mine": mine, "flank": where})
        if aw + dw < 3:
            continue
        if mine == "attack" and dw >= 2 * max(aw, 1):
            if where == "centre":
                way = "сыграй через фланги"
            else:
                way = f"переведи атаки на {'правый' if where == 'left' else 'левый'} фланг"
            hints.append({"text": f"{names.get(a, a)} проигрывает {names.get(d, d)} {aw}:{dw} — {way} или замени игрока.",
                          "flank": None if where == "centre" else ("right" if where == "left" else "left")})
        elif mine == "defence" and aw >= 2 * max(dw, 1):
            hints.append({"text": f"Их {names.get(a, a)} обыгрывает {names.get(d, d)} {aw}:{dw} — замени защитника "
                                  "или сыграй осторожнее.", "flank": None})
    return {"duels": rows[:limit], "hints": hints}


def stories(book: DuelBook, my_keys: set[str]) -> list[str]:
    """Match stories of my players' duels: a known rival beaten or a
    shutout, fear gone or born (the history before vs after this match)."""
    t = book.tuning
    names = {key: name for key, _style, name in book.players.values()}
    out = []
    for (a, d), (aw, dw) in sorted(book.played().items(), key=lambda kv: -sum(kv[1])):
        if a not in my_keys and d not in my_keys:
            continue
        an, dn = names.get(a, a), names.get(d, d)
        before = book.history.get((a, d), (0.0, 0.0))
        old = history_level(before[0], before[1], t)
        new = history_level(before[0] + aw, before[1] + dw, t)
        rivalry = book.rivalries.get((a, d), 0)
        if new < 0 <= old:
            out.append(f"{dn} стал неудобным соперником для {an}: {round(before[0] + aw)}:{round(before[1] + dw)} в дуэлях.")
        elif new > 0 >= old:
            out.append(f"{an} нашёл ключ к {dn}: {round(before[0] + aw)}:{round(before[1] + dw)} в дуэлях.")
        elif old < 0 <= new:
            out.append(f"{an} больше не боится {dn}.")
        elif rivalry < 0 and aw > dw:
            out.append(f"{an} переиграл своего «палача» {dn}: {aw}:{dw}.")
        elif dw >= t["story_shutout"] and aw == 0:
            out.append(f"{dn} выключил {an}: {aw}:{dw} в дуэлях.")
        elif aw >= t["story_shutout"] and dw == 0:
            out.append(f"{an} разорвал {dn}: {aw}:{dw} в дуэлях.")
    return out[:3]


# --- DB ----------------------------------------------------------------------------------

async def load_book(db: AsyncSession, player_ids: set[int], career_tuning: Optional[dict]) -> DuelBook:
    tuning = tuning_of(career_tuning)
    ids = {int(i) for i in player_ids if i and int(i) > 0}
    rows = (await db.execute(select(Player).where(Player.id.in_(ids)))).unique().scalars().all() if ids else []
    players = {p.id: (person_key(p), style_of(p), p.display_name) for p in rows}
    keys = {v[0] for v in players.values()}
    rivalries: dict[tuple[str, str], int] = {}
    history: dict[tuple[str, str], tuple[float, float]] = {}
    if keys:
        for r in (await db.execute(select(PlayerRivalry).where(
            PlayerRivalry.attacker_key.in_(keys), PlayerRivalry.defender_key.in_(keys),
        ))).scalars():
            rivalries[(r.attacker_key, r.defender_key)] = max(-3, min(3, r.level))
        for h in (await db.execute(select(DuelHistory).where(
            DuelHistory.attacker_key.in_(keys), DuelHistory.defender_key.in_(keys),
        ))).scalars():
            history[(h.attacker_key, h.defender_key)] = (h.attacker_wins, h.defender_wins)
    return DuelBook(tuning=tuning, players=players, rivalries=rivalries, history=history)


async def save_log(db: AsyncSession, book: DuelBook) -> None:
    """Adds the match's decided duels to the global history (one upsert per
    pair — no read-modify-write, so parallel seasons can't lose updates),
    then scales pairs above history_cap back to it, keeping their ratio."""
    played = book.played()
    if not played:
        return
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    # Sorted: two seasons saving overlapping pairs lock them in the same
    # order, so they wait for each other instead of deadlocking.
    for (a, d), (aw, dw) in sorted(played.items()):
        stmt = insert(DuelHistory).values(attacker_key=a, defender_key=d, attacker_wins=float(aw), defender_wins=float(dw))
        await db.execute(stmt.on_conflict_do_update(
            index_elements=["attacker_key", "defender_key"],
            set_={"attacker_wins": DuelHistory.attacker_wins + float(aw),
                  "defender_wins": DuelHistory.defender_wins + float(dw)},
        ))
    cap = float(book.tuning["history_cap"])
    total = DuelHistory.attacker_wins + DuelHistory.defender_wins
    await db.execute(
        update(DuelHistory)
        .where(total > cap, or_(*[(DuelHistory.attacker_key == a) & (DuelHistory.defender_key == d) for a, d in played]))
        .values(attacker_wins=DuelHistory.attacker_wins * cap / total, defender_wins=DuelHistory.defender_wins * cap / total)
        .execution_options(synchronize_session=False)
    )


# --- admin ---------------------------------------------------------------------------

def rivalry_out(r: PlayerRivalry) -> dict:
    return {"id": r.id, "attacker": r.attacker_name, "defender": r.defender_name, "attacker_key": r.attacker_key,
            "defender_key": r.defender_key, "level": r.level, "note": r.note}


async def admin_overview(db: AsyncSession, career_tuning: Optional[dict] = None, limit: int = 30) -> dict:
    """Known rivalries, plus the pairs the global history has made the most
    one-sided (the antagonists the players found themselves)."""
    tuning = tuning_of(career_tuning)
    rivalries = (await db.execute(select(PlayerRivalry).order_by(PlayerRivalry.attacker_name, PlayerRivalry.id))).scalars().all()
    rows = (await db.execute(
        select(DuelHistory).where(DuelHistory.attacker_wins + DuelHistory.defender_wins >= tuning["history_min"])
    )).scalars().all()
    emerged = []
    for h in rows:
        level = history_level(h.attacker_wins, h.defender_wins, tuning)
        if level:
            emerged.append({"attacker_key": h.attacker_key, "defender_key": h.defender_key, "level": level,
                            "record": [round(h.attacker_wins), round(h.defender_wins)]})
    emerged.sort(key=lambda r: (-abs(r["level"]), -(r["record"][0] + r["record"][1])))
    return {
        "styles": [{"code": c, "label": STYLE_LABELS[c]} for c in STYLES],
        "rivalries": [rivalry_out(r) for r in rivalries],
        "history": emerged[:limit],
    }


async def admin_save_rivalry(db: AsyncSession, attacker_id: int, defender_id: int, level: int,
                             note: Optional[str]) -> PlayerRivalry:
    """Creates the pair (or updates it when it exists) by the players' person keys."""
    attacker, defender = await db.get(Player, attacker_id), await db.get(Player, defender_id)
    if attacker is None or defender is None:
        raise NotFoundError("Футболист не найден")
    a_key, d_key = person_key(attacker), person_key(defender)
    if a_key == d_key:
        raise ConflictError("Это один и тот же футболист")
    row = (await db.execute(select(PlayerRivalry).where(
        PlayerRivalry.attacker_key == a_key, PlayerRivalry.defender_key == d_key,
    ))).scalar_one_or_none() or PlayerRivalry(attacker_key=a_key, defender_key=d_key)
    row.attacker_name, row.defender_name = attacker.display_name, defender.display_name
    row.level, row.note = max(-3, min(3, level)), (note or None)
    db.add(row)
    await db.flush()
    return row



async def admin_bulk_rivalries(db: AsyncSession, text: str) -> dict:
    """Many known rivalries at once, one per line:
    «Атакующий; Защитник; уровень -3..3; заметка» (заметка optional).
    Names match the players' display names (any version of the footballer);
    lines that can't be read are returned with the reason, the rest saved."""
    saved, errors = 0, []
    by_name: dict[str, list] = defaultdict(list)
    for r in (await db.execute(select(Player.id, Player.person_key, Player.display_name))).all():
        by_name[normalize(r.display_name)].append(r)
    for number, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 3:
            errors.append({"line": number, "text": line, "error": "нужно: атакующий; защитник; уровень"})
            continue
        try:
            level = int(parts[2])
        except ValueError:
            errors.append({"line": number, "text": line, "error": "уровень — число от -3 до 3"})
            continue
        if not -3 <= level <= 3:
            errors.append({"line": number, "text": line, "error": "уровень — число от -3 до 3"})
            continue
        found = []
        for name in parts[:2]:
            rows = by_name.get(normalize(name), [])
            keys = {person_key(SimpleNamespace(person_key=r.person_key, display_name=r.display_name)) for r in rows}
            if not rows:
                found.append((name, None, "не найден"))
            elif len(keys) > 1:
                found.append((name, None, "несколько разных футболистов с таким именем"))
            else:
                found.append((name, rows[0].id, None))
        bad = [f"{name}: {err}" for name, _id, err in found if err]
        if bad:
            errors.append({"line": number, "text": line, "error": "; ".join(bad)})
            continue
        try:
            await admin_save_rivalry(db, found[0][1], found[1][1], level, parts[3] if len(parts) > 3 else None)
        except (ConflictError, NotFoundError) as exc:
            errors.append({"line": number, "text": line, "error": exc.message})
            continue
        saved += 1
    return {"saved": saved, "errors": errors}


async def admin_stats(db: AsyncSession, career_tuning: Optional[dict] = None) -> dict:
    """How the duels actually play out, for tuning: per style matchup the
    decided duels and the attacker's win share (the global history, every
    pair counted with its remembered duels), plus fear / favourite pairs
    and how many players have a style set by hand."""
    tuning = tuning_of(career_tuning)
    players = (await db.execute(
        select(Player.person_key, Player.display_name, Player.duel_style, Player.position)
    )).all()
    style_by_key: dict[str, str] = {}
    explicit = 0
    for r in players:
        p = SimpleNamespace(person_key=r.person_key, display_name=r.display_name, duel_style=r.duel_style,
                            position=r.position)
        key = person_key(p)
        if r.duel_style in STYLES:
            explicit += 1
            style_by_key[key] = r.duel_style
        else:
            style_by_key.setdefault(key, style_of(p))
    cells: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    levels = {str(lv): 0 for lv in (-2, -1, 1, 2)}
    total_pairs, total = 0, 0.0
    for h in (await db.execute(select(DuelHistory))).scalars():
        total_pairs += 1
        total += h.attacker_wins + h.defender_wins
        level = history_level(h.attacker_wins, h.defender_wins, tuning)
        if level:
            levels[str(level)] += 1
        a, d = style_by_key.get(h.attacker_key), style_by_key.get(h.defender_key)
        if a is None or d is None:
            continue
        cell = cells[(AS_ATTACKER[a], AS_DEFENDER[d])]
        cell[0] += h.attacker_wins
        cell[1] += h.defender_wins
    matrix = []
    for (a_type, d_type), expected in MATRIX.items():
        aw, dw = cells.get((a_type, d_type), [0.0, 0.0])
        decided = aw + dw
        matrix.append({
            "attacker_type": a_type, "defender_type": d_type,
            "attacker_label": ATTACKER_LABELS[a_type], "defender_label": DEFENDER_LABELS[d_type],
            "expected": expected, "duels": round(decided),
            "attacker_win_pct": round(100 * aw / decided, 1) if decided else None,
        })
    return {
        "pairs": total_pairs, "duels": round(total), "levels": levels, "matrix": matrix,
        "players_explicit_style": explicit,
        "rivalries": int((await db.execute(select(func.count(PlayerRivalry.id)))).scalar() or 0),
    }
