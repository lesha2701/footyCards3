"""«Карьера тренера»: positional 2D replay of a match (a Football Manager
style highlights view) built on top of the engine's result.

The engine (tournament_match_engine.simulate_match_controlled) decides
everything — score, events, authors, rewards. This module only *draws* it:
from the match seed, both starting XIs with their formation / tactic and the
event log it deterministically builds key frames — positions of the 22
players and the ball every STEP seconds of game time — for a compressed show
of a few minutes: an episode per moment (build-up, shot, save, goal,
celebration, set pieces, fouls, substitutions) and short accelerated
"bridges" between them.

Pure functions, no DB and no global RNG. Each half is built on its own
generator (seed, half) from a kick-off, so the first half drawn during the
live break is exactly the first half of the finished match (the engine
replays it on the same seed, career_service._seeded).

Coordinates are metres on a 68 x 105 pitch: X across (left → right as the
home side attacks), Y along (0 = home goal line, 105 = away goal line). The
home side ("a") attacks towards Y = 105 all match. A frame is FRAME_SIZE
bytes: ball X, ball Y, holder (pitch slot or 255), then X, Y of the 22 pitch
slots (0-10 home in formation order, 11-21 away), each quantised to 0-255.
"""
from __future__ import annotations

import base64
import math
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.club_formation_service import CLUB_FORMATIONS, DEFAULT_FORMATION

WIDTH, LENGTH = 68.0, 105.0
STEP = 0.5                      # game seconds between key frames in an episode
FRAME_SIZE = 3 + 22 * 2
NO_HOLDER = 255
HALF_TIME = 45
EPISODE_MS = 500                # playback at x1: an episode runs in real time
BRIDGE_MS = 300                 # bridges are accelerated
HALF_BUDGET_S = (90, 150)       # real seconds per half at x1 (3-5 minutes a match)
VERSION = 2
DRIBBLE = 0.6                   # a held ball: metres in front of the holder, the way he runs
PASS_SPEED = 16.0               # m/s a pass travels at (more when the receiver is far)

CHANCE_TYPES = ("goal", "shot", "save", "blocked", "pass_failed")
DEFENCE_TYPES = ("tackle_won", "foul_stopped")

# Pitch rows of each formation from the back line to the front (slot codes
# left → right as the side attacks); same layout as the frontend's
# lib/formationLayout ROWS, wing-backs of 3-4-3 in the midfield row.
ROWS: dict[str, list[list[str]]] = {
    "4-3-3": [["DEF1", "DEF2", "DEF3", "DEF4"], ["MID1", "MID2", "MID3"], ["FWD1", "FWD2", "FWD3"]],
    "4-3-3H": [["DEF1", "DEF2", "DEF3", "DEF4"], ["MID2"], ["MID1", "MID3"], ["FWD1", "FWD2", "FWD3"]],
    "4-2-3-1": [["DEF1", "DEF2", "DEF3", "DEF4"], ["MID1", "MID2"], ["MID3", "MID4", "MID5"], ["FWD1"]],
    "4-4-2": [["DEF1", "DEF2", "DEF3", "DEF4"], ["MID1", "MID2", "MID3", "MID4"], ["FWD1", "FWD2"]],
    "3-5-2": [["DEF1", "DEF2", "DEF3"], ["MID1", "MID2", "MID3", "MID4", "MID5"], ["FWD1", "FWD2"]],
    "5-3-2": [["DEF1", "DEF2", "DEF3", "DEF4", "DEF5"], ["MID1", "MID2", "MID3"], ["FWD1", "FWD2"]],
    "3-4-3": [["DEF1", "DEF2", "DEF3"], ["DEF4", "MID1", "MID2", "DEF5"], ["FWD1", "FWD2", "FWD3"]],
}
# Shirt numbers by slot position (first free one; substitutes from 12).
NUMBERS = {
    "GK": (1,), "RB": (2,), "RWB": (2,), "LB": (3,), "LWB": (3,), "CB": (4, 5, 15),
    "CDM": (6, 16), "CM": (8, 14, 6), "RM": (7,), "RW": (7,), "LM": (11,), "LW": (11,),
    "CAM": (10,), "ST": (9, 19, 10),
}

MENTALITY_SHIFT = {"PARK_THE_BUS": -8.0, "DEFENSIVE": -4.0, "BALANCED": 0.0, "ATTACKING": 4.0}
BLOCK_SHIFT = {"high": 6.0, "mid": 0.0, "low": -8.0}
BLOCK_MAX_LINE = {"high": 55.0, "mid": 45.0, "low": 35.0}   # back line height without the ball
DIRECTION_WIDTH = {"wings": 1.2, "mixed": 1.08, "center": 0.92}


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _q(v: float, size: float) -> int:
    return int(round(_clamp(v, 0.0, size) / size * 255))


def dequantise(value: int, size: float) -> float:
    return value / 255 * size


@dataclass
class Slot:
    index: int          # pitch slot 0-21
    side: str           # "a" / "b"
    code: str           # formation slot code
    category: str       # GK / DEF / MID / FWD
    base: tuple         # (u, v) own coordinates: u across from own left, v from own goal
    row: float = 0.0    # 0 = back line ... 1 = front line (formation rows)


@dataclass
class SideInfo:
    formation: str
    mentality: str
    tactic: dict
    slots: list         # 11 Slot


def _rows_of(formation: str) -> dict[str, float]:
    rows = ROWS.get(formation) or ROWS[DEFAULT_FORMATION]
    return {code: i / max(1, len(rows) - 1) for i, row in enumerate(rows) for code in row}


def _base_shape(formation: str) -> dict[str, tuple[float, float]]:
    rows = ROWS.get(formation) or ROWS[DEFAULT_FORMATION]
    depths = [17.0 + (55.0 - 17.0) * i / max(1, len(rows) - 1) for i in range(len(rows))]
    shape = {"GK": (WIDTH / 2, 5.0)}
    for depth, row in zip(depths, rows):
        k = len(row)
        spacing = min(0.8 / (k - 1), 0.27) if k > 1 else 0
        for i, code in enumerate(row):
            shape[code] = (WIDTH * (0.5 + (i - (k - 1) / 2) * spacing), depth)
    return shape


def _side_info(side: str, lineup: Optional[dict]) -> SideInfo:
    lineup = lineup or {}
    formation = lineup.get("formation") if lineup.get("formation") in CLUB_FORMATIONS else DEFAULT_FORMATION
    shape = _base_shape(formation)
    rows = _rows_of(formation)
    offset = 0 if side == "a" else 11
    slots = []
    for i, fs in enumerate(CLUB_FORMATIONS[formation]):
        slots.append(Slot(offset + i, side, fs.code, fs.category, shape.get(fs.code, (WIDTH / 2, 30.0)),
                          rows.get(fs.code, 0.5)))
    return SideInfo(formation, lineup.get("mentality") or "BALANCED", dict(lineup.get("tactic") or {}), slots)


def to_pitch(side: str, u: float, v: float) -> tuple[float, float]:
    return (u, v) if side == "a" else (WIDTH - u, LENGTH - v)


def to_own(side: str, x: float, y: float) -> tuple[float, float]:
    return to_pitch(side, x, y)  # the mapping is its own inverse


def _other(side: str) -> str:
    return "b" if side == "a" else "a"


@dataclass
class Segment:
    kind: str
    f0: int
    n: int = 0
    t0: float = 0.0
    t1: float = 0.0
    ms: int = EPISODE_MS


@dataclass
class Director:
    """Plays scripted actions frame by frame: team shape from formation,
    tactic, phase and the ball; per-player overrides for the actors; speed-
    limited movement so positions stay continuous between frames."""

    rng: random.Random
    sides: dict
    players: list                  # [{"s","n","name","slot","id"}]
    roster: list                   # pitch slot -> player index (current)
    start_frame: int = 0
    pos: list = field(default_factory=list)
    ball: list = field(default_factory=lambda: [WIDTH / 2, LENGTH / 2])
    holder: Optional[int] = None
    phase: Optional[str] = None    # side in possession (None = dead ball / neutral)
    t: float = 0.0                 # game clock, seconds
    dt: float = STEP
    ov: dict = field(default_factory=dict)        # slot -> (x, y, speed)
    limit: Any = None              # global constraint fn(slot, x, y) -> (x, y)
    frames: bytearray = field(default_factory=bytearray)
    count: int = 0
    marks: list = field(default_factory=list)
    passes: list = field(default_factory=list)
    swaps: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    wobble: list = field(default_factory=list)
    start_roster: list = field(default_factory=list)

    def __post_init__(self):
        self.slots = self.sides["a"].slots + self.sides["b"].slots
        self.wobble = [(self.rng.uniform(0, 6.28), self.rng.uniform(0, 6.28), self.rng.uniform(0.4, 0.8))
                       for _ in self.slots]
        if not self.pos:
            self.pos = [list(self.kickoff_target(s, None)) for s in self.slots]

    # --- helpers --------------------------------------------------------------------------

    @property
    def frame(self) -> int:
        return self.start_frame + self.count

    def side_slots(self, side: str, cats: tuple = ("GK", "DEF", "MID", "FWD")) -> list[int]:
        return [s.index for s in self.sides[side].slots if s.category in cats]

    def keeper(self, side: str) -> int:
        return self.side_slots(side, ("GK",))[0]

    def name_of(self, slot: int) -> Optional[str]:
        return self.players[self.roster[slot]].get("name")

    def find(self, side: str, name: Optional[str], card_id: Any, cats: tuple, exclude: tuple = ()) -> int:
        """The pitch slot of an engine actor: by card id, then by name, else a
        player of a fitting line (an unnamed placeholder takes the name)."""
        own = [i for i in self.side_slots(side) if i not in exclude]
        if card_id is not None:
            for i in own:
                if self.players[self.roster[i]].get("id") == card_id:
                    return i
        if name:
            for i in own:
                if self.players[self.roster[i]].get("name") == name:
                    return i
        pool = [i for i in own if self.slots[i].category in cats] or [i for i in own if self.slots[i].category != "GK"]
        free = [i for i in pool if not self.players[self.roster[i]].get("name")]
        pick = self.rng.choice(free or pool)
        if name and free:
            self.players[self.roster[pick]]["name"] = name
        return pick

    def nearest(self, side: str, x: float, y: float, cats: tuple = ("DEF", "MID", "FWD"), exclude: tuple = ()) -> int:
        pool = [i for i in self.side_slots(side, cats) if i not in exclude]
        return min(pool, key=lambda i: (self.pos[i][0] - x) ** 2 + (self.pos[i][1] - y) ** 2)

    def to_u(self, slot: int) -> float:
        """A player's position across the pitch in his own side's coordinates."""
        return to_own(self.slots[slot].side, *self.pos[slot])[0]

    def at(self, side: str, u: float, v: float) -> tuple[float, float]:
        return to_pitch(side, _clamp(u, 0.5, WIDTH - 0.5), _clamp(v, 0.3, LENGTH - 0.3))

    # --- shape ----------------------------------------------------------------------------

    def kickoff_target(self, s: Slot, kicking: Optional[str]) -> tuple[float, float]:
        u, v = s.base
        if s.category != "GK":
            v = min(v * 0.85, 48.0)
        return self.at(s.side, u, v)

    def shape_target(self, s: Slot) -> tuple[float, float]:
        """Where a player stands in the team shape: the back line's height
        follows the ball (and the block / mentality), the other lines keep
        fixed gaps to it — compact without the ball, stretched with it."""
        info = self.sides[s.side]
        bu, bv = to_own(s.side, *self.ball)
        u0, _ = s.base
        attacking = self.phase == s.side
        defending = self.phase is not None and not attacking
        tactic = info.tactic
        mentality = MENTALITY_SHIFT.get(info.mentality, 0.0)
        if attacking:
            line = _clamp(bv * 0.55 + 5 + mentality, 18, 52)
            span = _clamp(bv * 0.45, 26, 38)          # back line → strikers
            width = DIRECTION_WIDTH.get(tactic.get("direction", "mixed"), 1.08)
            pull = 0.18
        elif defending:
            block = tactic.get("block", "mid")
            line = _clamp(bv * 0.6 + 2 + BLOCK_SHIFT.get(block, 0.0) + mentality, 6, BLOCK_MAX_LINE.get(block, 45))
            line = min(line, max(bv - 3.0, 5.0))       # the back line stays goal-side of the ball
            span = 22.0 if block == "low" else 25.0
            width, pull = 0.74, 0.34
        else:
            line = _clamp(bv * 0.5 + 6 + mentality, 16, 42)
            span, width, pull = 30.0, 0.95, 0.2
        if s.category == "GK":
            v = 3.0 + _clamp((line - 12) * 0.35, 0, 14)  # sweeps behind a high line, on the line when deep
            return self.at(s.side, WIDTH / 2 + (bu - WIDTH / 2) * 0.22, v)
        v = line + span * s.row
        if attacking and s.category == "DEF" and abs(u0 - WIDTH / 2) > 20:
            v += 9.0 + (6.0 if tactic.get("direction") == "wings" else 0.0)   # full-backs overlap
        u = WIDTH / 2 + (u0 - WIDTH / 2) * width + (bu - WIDTH / 2) * pull
        ph1, ph2, w = self.wobble[s.index]
        u += 0.7 * math.sin(self.t * w + ph1)
        v += 0.7 * math.sin(self.t * w * 0.8 + ph2)
        return self.at(s.side, u, _clamp(v, 4.0, 96.0))

    # --- frame loop -----------------------------------------------------------------------

    def _emit(self) -> None:
        holder = NO_HOLDER if self.holder is None else self.holder
        out = self.frames
        out += bytes((_q(self.ball[0], WIDTH), _q(self.ball[1], LENGTH), holder))
        for x, y in self.pos:
            out += bytes((_q(x, WIDTH), _q(y, LENGTH)))
        self.count += 1

    def _move(self) -> None:
        presser = None
        if self.holder is not None and self.phase is not None:
            presser = self.nearest(_other(self.phase), *self.ball, exclude=tuple(self.ov))
        for s in self.slots:
            i = s.index
            speed = 6.0
            if i in self.ov:
                tx, ty, speed = self.ov[i]
            elif i == presser:
                bu, bv = to_own(s.side, *self.ball)
                tx, ty = self.at(s.side, bu, bv - 2.0)
                speed = 7.0
            else:
                tx, ty = self.shape_target(s)
            if self.limit is not None:
                tx, ty = self.limit(s, tx, ty)
            dx, dy = tx - self.pos[i][0], ty - self.pos[i][1]
            dist = math.hypot(dx, dy)
            reach = speed * self.dt
            if dist > reach:
                dx, dy = dx / dist * reach, dy / dist * reach
            self.pos[i][0] = _clamp(self.pos[i][0] + dx, 0.0, WIDTH)
            self.pos[i][1] = _clamp(self.pos[i][1] + dy, 0.0, LENGTH)

    def tick(self, ball_at=None) -> None:
        """One frame. `ball_at` (a point, or a function called after the
        players have moved — so a ball aimed at a player reaches where he is
        now, not where he was a frame ago) places a loose ball."""
        self.t += self.dt
        before = tuple(self.pos[self.holder]) if self.holder is not None else None
        self._move()
        if self.holder is not None:
            hx, hy = self.pos[self.holder]
            dx, dy = hx - before[0], hy - before[1]
            dist = math.hypot(dx, dy)
            if dist > 0.15:
                ux, uy = dx / dist, dy / dist
            else:  # standing: the ball on the side of the goal he attacks
                ux, uy = 0.0, (1.0 if self.slots[self.holder].side == "a" else -1.0)
            self.ball = [_clamp(hx + ux * DRIBBLE, 0, WIDTH), _clamp(hy + uy * DRIBBLE, 0, LENGTH)]
        elif ball_at is not None:
            if callable(ball_at):
                ball_at = ball_at()
            self.ball = [_clamp(ball_at[0], 0, WIDTH), _clamp(ball_at[1], 0, LENGTH)]
        self._emit()

    def predict(self, slot: int, n: int) -> tuple[float, float]:
        """Where a player will be in `n` frames, running straight to his
        override target (or staying put): the meeting point of a pass."""
        x, y = self.pos[slot]
        tx, ty, speed = self.ov.get(slot, (x, y, 6.0))
        dx, dy = tx - x, ty - y
        dist = math.hypot(dx, dy)
        reach = speed * self.dt * n
        if dist > reach:
            dx, dy = dx / dist * reach, dy / dist * reach
        return x + dx, y + dy

    # --- actions --------------------------------------------------------------------------

    def hold(self, slot: int, n: int, run_to: Optional[tuple] = None, speed: float = 6.5) -> None:
        self.holder = slot
        self.phase = self.slots[slot].side
        if run_to is not None:
            self.ov[slot] = (*run_to, speed)
        for _ in range(n):
            self.tick()
        self.ov.pop(slot, None)

    def pass_to(self, frm: int, to: int, run_to: Optional[tuple] = None, frames: Optional[int] = None,
                speed: float = 7.5) -> None:
        start = list(self.ball)
        if run_to is not None:
            self.ov[to] = (*run_to, speed)
        if frames is None:
            # Played to where the receiver will be: the fewest frames at
            # which the ball, at pass speed, meets his run.
            frames = 4
            for k in range(1, 5):
                mx, my = self.predict(to, k)
                if math.hypot(mx - start[0], my - start[1]) <= PASS_SPEED * self.dt * k:
                    frames = k
                    break
        self.passes.append([self.frame, self.frame + frames, frm, to])
        self.holder = None
        for k in range(frames):
            f = (k + 1) / frames
            # Aimed at the receiver after he has moved this frame: the last
            # frame of the pass has the ball exactly at him.
            self.tick(lambda f=f: (start[0] + (self.pos[to][0] - start[0]) * f,
                                   start[1] + (self.pos[to][1] - start[1]) * f))
        self.holder = to
        self.phase = self.slots[to].side

    def kick(self, target, frames: int, keep_phase: bool = True) -> None:
        """The ball to a point; `target` may be a player's live position
        (self.pos[i]) — then it is read after he moves and the ball reaches him."""
        start = list(self.ball)
        self.holder = None
        if not keep_phase:
            self.phase = None
        for k in range(frames):
            f = (k + 1) / frames
            self.tick(lambda f=f: (start[0] + (target[0] - start[0]) * f, start[1] + (target[1] - start[1]) * f))

    def dead(self, n: int) -> None:
        self.holder = None
        for _ in range(n):
            self.tick(self.ball)

    def gather(self, slots: list, least: int, most: int = 16) -> None:
        """A dead ball until the given players reach their override targets
        (a set piece waits for its taker), at least `least` frames."""
        self.holder = None
        for k in range(most):
            if k >= least and all(math.hypot(self.pos[i][0] - self.ov[i][0], self.pos[i][1] - self.ov[i][1]) < 1.0
                                  for i in slots if i in self.ov):
                break
            self.tick(self.ball)

    def mark(self, event_index: int) -> None:
        self.marks.append([max(self.start_frame, self.frame - 1), event_index])

    def begin(self, kind: str, t0: float, ms: int = EPISODE_MS) -> Segment:
        self.t = t0
        seg = Segment(kind, self.frame, t0=t0, ms=ms)
        self.segments.append(seg)
        return seg

    def end(self, seg: Segment, t1: Optional[float] = None) -> None:
        seg.n = self.frame - seg.f0
        seg.t1 = self.t if t1 is None else t1


# --- scenes ----------------------------------------------------------------------------------

def _payload(e: dict) -> dict:
    return e.get("payload") or {}


def _goal_mouth(d: Director, side: str, wide: bool = False, keeper: Optional[int] = None) -> tuple[float, float]:
    """Where a shot of `side` ends: inside the posts (± 3.66 m) or wide. A
    goal past a keeper (`keeper` = his slot) goes at least 1.5 m to one side
    of him — a ball struck at the man would be his to catch."""
    if wide:
        u = WIDTH / 2 + d.rng.choice((-1, 1)) * d.rng.uniform(4.6, 8.5)
    elif keeper is None:
        u = WIDTH / 2 + d.rng.uniform(-2.9, 2.9)
    else:
        ku = to_own(side, *d.pos[keeper])[0]
        lo, hi = WIDTH / 2 - 3.2, WIDTH / 2 + 3.2
        sides = [(lo, ku - 1.5), (ku + 1.5, hi)]
        sides = [(a, b) for a, b in sides if b - a > 0.3] or [(lo, hi)]
        a, b = d.rng.choice(sides)
        u = d.rng.uniform(a, b)
    return to_pitch(side, u, LENGTH)


def _shoot_spot(d: Director, side: str, shot_type: str, cross: bool = False) -> tuple[float, float]:
    """Where the finisher strikes from: 23-29 m out for a long-range shot,
    6-11 m in front of goal after a cross, otherwise 7-18 m inside the box."""
    if shot_type == "long_range":
        return d.at(side, d.rng.uniform(22, 46), d.rng.uniform(76, 82))
    if cross:
        return d.at(side, d.rng.uniform(28, 40), d.rng.uniform(94, 99))
    return d.at(side, d.rng.uniform(24, 44), d.rng.uniform(87, 98))


def _own_v(d: Director, slot: int) -> float:
    return to_own(d.slots[slot].side, *d.pos[slot])[1]


def _arrive(d: Director, slot: int, spot: Optional[tuple]) -> None:
    """The holder carries the ball on to `spot` at a run: the shot is struck
    where the scene says, not wherever he got to."""
    if spot is None:
        d.hold(slot, 1)
        return
    for k in range(12):
        if k >= 1 and math.hypot(d.pos[slot][0] - spot[0], d.pos[slot][1] - spot[1]) < 1.5:
            break
        d.hold(slot, 1, run_to=spot, speed=8.0)


def _build_up(d: Director, side: str, e: dict, detail: int) -> tuple[int, Optional[int]]:
    """Moves the ball from midfield to the finisher. Returns (finisher slot,
    final passer slot or None). The finisher starts his run into the box at
    once and strikes only once he gets to his spot; passes go forwards or
    square, never back to a man behind the ball for no reason."""
    p = _payload(e)
    etype = e.get("event_type")
    counter = p.get("origin") == "counter" or p.get("shot_type") == "empty_net"
    wing = p.get("zone") == "wing_attack"
    flank = d.rng.choice((8.0, WIDTH - 8.0))
    if etype == "pass_failed":
        finisher = d.find(side, p.get("passer"), None, ("MID", "FWD"))
        passer = None
    else:
        finisher = d.find(side, p.get("shooter"), p.get("shooter_id"), ("FWD", "MID"))
        passer = None
        if p.get("assist") or p.get("action") == "pass":
            passer = d.find(side, p.get("assist"), p.get("assist_id"), ("MID", "FWD"), exclude=(finisher,))
    used = {finisher} | ({passer} if passer is not None else set())
    cross = wing and passer is not None and p.get("shot_type") == "in_box"
    spot = None if etype == "pass_failed" else _shoot_spot(d, side, p.get("shot_type", "in_box"), cross)
    if spot is not None:
        d.ov[finisher] = (*spot, 7.0)

    # The first carrier wins / receives the ball deep (counter) or in midfield.
    if counter:
        first = d.nearest(side, *d.at(side, WIDTH / 2, 32), ("DEF", "MID"), exclude=tuple(used))
        d.phase = None
        d.kick(d.pos[first], 2)
        d.hold(first, 2, run_to=d.at(side, d.to_u(first), 40))
        target = passer if passer is not None else finisher
        d.pass_to(first, target, run_to=d.at(side, flank if wing else WIDTH / 2 + d.rng.uniform(-8, 8), 72),
                  frames=3, speed=8.5)
        d.hold(target, 3, run_to=d.at(side, d.to_u(target), 84), speed=8.0)
        if target != finisher:
            d.pass_to(target, finisher, run_to=spot, speed=8.0)
        _arrive(d, finisher, spot)
        return finisher, passer

    mids = [i for i in d.side_slots(side, ("MID",)) if i not in used] or d.side_slots(side, ("DEF",))
    first = d.rng.choice(mids)
    d.phase = side
    d.kick(d.pos[first], 2)
    d.hold(first, 3, run_to=d.at(side, d.to_u(first), d.rng.uniform(42, 50)))
    carrier = first
    pool = [i for i in d.side_slots(side, ("MID", "FWD")) if i not in used and i != first]
    for _ in range(max(0, detail - 2)):
        if not pool:
            break
        cur = _own_v(d, carrier)
        ahead = [i for i in pool if _own_v(d, i) >= cur - 2.0]
        nxt = d.rng.choice(ahead or pool)
        pool.remove(nxt)
        u = flank if wing and d.rng.random() < 0.6 else d.rng.uniform(18, 50)
        v = min(74.0, cur + d.rng.uniform(6, 12))
        d.pass_to(carrier, nxt, run_to=d.at(side, u, v))
        d.hold(nxt, 2, run_to=d.at(side, u, min(78.0, v + d.rng.uniform(3, 7))))
        carrier = nxt
    if passer is not None:
        cur = _own_v(d, carrier)
        assist_spot = (d.at(side, flank, d.rng.uniform(84, 92)) if cross
                       else d.at(side, d.rng.uniform(20, 48), max(74.0, min(80.0, cur + 6))))
        d.pass_to(carrier, passer, run_to=assist_spot)
        d.hold(passer, 2, run_to=assist_spot)
        carrier = passer
    if etype == "pass_failed":
        if carrier != finisher:
            d.pass_to(carrier, finisher, run_to=d.at(side, d.rng.uniform(20, 48), 74))
        d.hold(finisher, 2, run_to=d.at(side, d.to_u(finisher), 80))
        return finisher, None
    if carrier != finisher:
        d.pass_to(carrier, finisher, run_to=spot, speed=8.0)
    _arrive(d, finisher, spot)
    return finisher, passer


def _celebrate(d: Director, side: str, scorer: int, reset: bool = True) -> None:
    corner = d.at(side, d.rng.choice((5.0, WIDTH - 5.0)), 100.0)
    d.ov[scorer] = (*corner, 7.5)
    for i in d.side_slots(side, ("DEF", "MID", "FWD")):
        if i != scorer:
            d.ov[i] = (corner[0] + d.rng.uniform(-5, 5), corner[1] + (-1 if side == "a" else 1) * d.rng.uniform(2, 8), 6.5)
    d.phase = None
    d.dead(8)
    d.ov.clear()
    if reset:
        _reset_kickoff(d, _other(side))


def _reset_kickoff(d: Director, kicking: str, n: int = 6) -> None:
    start = list(d.ball)
    centre = (WIDTH / 2, LENGTH / 2)
    for s in d.slots:
        d.ov[s.index] = (*d.kickoff_target(s, kicking), 9.0)
    fwds = d.side_slots(kicking, ("FWD",)) or d.side_slots(kicking, ("MID",))
    d.ov[fwds[0]] = (centre[0] - 1.5, centre[1] + (-0.8 if kicking == "a" else 0.8), 9.0)
    d.phase = None
    d.holder = None
    for k in range(n):
        f = (k + 1) / n
        d.tick((start[0] + (centre[0] - start[0]) * f, start[1] + (centre[1] - start[1]) * f))
    d.ov.clear()


def _finish_shot(d: Director, side: str, shooter: int, e: dict, idx: int) -> None:
    """The shot itself and what follows it: goal (celebration and kick-off),
    save, miss or block."""
    etype = e["event_type"]
    defending = _other(side)
    keeper = d.keeper(defending)
    if etype == "goal":
        d.kick(_goal_mouth(d, side, keeper=keeper), 2)
        d.mark(idx)
        _celebrate(d, side, shooter)
    elif etype == "save":
        target = (d.pos[keeper][0] + d.rng.uniform(-1.2, 1.2), d.pos[keeper][1])
        d.ov[keeper] = (*target, 5.0)
        d.kick(target, 2)
        d.mark(idx)
        d.ov.pop(keeper, None)
        d.hold(keeper, 3)
    elif etype == "blocked":
        gx, gy = _goal_mouth(d, side)
        mx, my = (d.ball[0] + gx) / 2, (d.ball[1] + gy) / 2
        blocker = d.nearest(defending, mx, my, ("DEF", "MID"))
        d.ov[blocker] = (d.ball[0] + (mx - d.ball[0]) * 0.35, d.ball[1] + (my - d.ball[1]) * 0.35, 8.0)
        d.dead(1)
        d.kick(d.pos[blocker], 1)
        d.mark(idx)
        d.ov.pop(blocker, None)
        bu, bv = to_own(side, *d.ball)
        d.kick(d.at(side, bu + d.rng.uniform(-10, 10), bv - d.rng.uniform(6, 12)), 2, keep_phase=False)
    else:  # shot: off target
        d.kick(_goal_mouth(d, side, wide=True), 2)
        d.mark(idx)
        d.phase = None
        d.dead(2)
        d.kick(d.at(defending, WIDTH / 2, 5.5), 2)
        d.hold(keeper, 2)


def _attack(d: Director, side: str, e: dict, idx: int, detail: int) -> None:
    finisher, _ = _build_up(d, side, e, detail)
    if e["event_type"] == "pass_failed":
        defending = _other(side)
        gx, gy = d.at(side, WIDTH / 2, 92)
        cutter = d.nearest(defending, (d.ball[0] + gx) / 2, (d.ball[1] + gy) / 2, ("DEF", "MID"))
        d.pass_to(finisher, cutter, run_to=None, frames=2)
        d.mark(idx)
        d.hold(cutter, 3, run_to=d.at(defending, d.to_u(cutter), to_own(defending, *d.ball)[1] + 8))
        return
    _finish_shot(d, side, finisher, e, idx)


def _defence(d: Director, e: dict, idx: int) -> None:
    """tackle_won / foul_stopped: the defender (e.team) gets to the carrier."""
    defending = e["team"]
    side = _other(defending)
    p = _payload(e)
    defender = d.find(defending, p.get("defender"), None, ("DEF", "MID"))
    if d.holder is None or d.slots[d.holder].side != side:
        carrier = d.nearest(side, *d.ball, ("MID", "FWD"))
        d.kick(d.pos[carrier], 2)
        d.holder = carrier
        d.phase = side
    carrier = d.holder
    # The defender closes the carrier down before he wins the ball (2-10
    # frames): the ball never jumps to a man metres away.
    for k in range(10):
        if k >= 2 and math.hypot(d.pos[defender][0] - d.pos[carrier][0], d.pos[defender][1] - d.pos[carrier][1]) < 1.5:
            break
        d.ov[defender] = (d.pos[carrier][0], d.pos[carrier][1], 8.5)
        d.hold(carrier, 1)
    d.ov.pop(defender, None)
    if e["event_type"] == "tackle_won":
        d.holder, d.phase = defender, defending
        d.mark(idx)
        d.hold(defender, 3, run_to=d.at(defending, d.to_u(defender), to_own(defending, *d.ball)[1] + 9))
    else:
        d.phase = None
        d.dead(1)
        d.mark(idx)
        d.dead(3)


def _corner(d: Director, e: dict, idx: int) -> None:
    side = e["team"]
    defending = _other(side)
    p = _payload(e)
    shooter = d.find(side, p.get("shooter"), p.get("shooter_id"), ("FWD", "DEF"))
    taker = d.find(side, p.get("taker") or p.get("assist"), p.get("assist_id"), ("MID", "FWD"), exclude=(shooter,))
    left = d.rng.random() < 0.5
    flag = d.at(side, 0.6 if left else WIDTH - 0.6, LENGTH - 0.6)
    d.phase = None
    d.kick(flag, 2)
    d.ov[taker] = (*flag, 9.0)
    box_att = d.side_slots(side, ("FWD", "DEF"))[:5] + [shooter]
    for i in set(box_att):
        if i != taker:
            d.ov[i] = (*d.at(side, d.rng.uniform(26, 42), d.rng.uniform(93, 99)), 8.0)
    for i in d.side_slots(defending, ("DEF", "MID", "FWD"))[:8]:
        d.ov[i] = (*d.at(side, d.rng.uniform(25, 43), d.rng.uniform(95, 101)), 8.0)
    d.gather([taker, shooter], 5)
    head = d.at(side, d.rng.uniform(29, 39), d.rng.uniform(96, 99))
    d.holder = taker
    # The cross meets the header where his run takes him.
    d.pass_to(taker, shooter, run_to=head, frames=3, speed=7.0)
    d.ov.clear()
    _finish_set_piece_shot(d, side, shooter, e, idx)


def _free_kick(d: Director, e: dict, idx: int) -> None:
    side = e["team"]
    defending = _other(side)
    p = _payload(e)
    taker = d.find(side, p.get("shooter"), p.get("shooter_id"), ("MID", "FWD"))
    bu, bv = d.rng.uniform(20, 48), d.rng.uniform(76, 82)
    spot = d.at(side, bu, bv)
    d.phase = None
    d.kick(spot, 2)
    d.ov[taker] = (*d.at(side, bu - 1.5, bv - 2.0), 9.0)
    # A wall of three 9.15 m from the ball on the line to the goal centre.
    gu, gv = WIDTH / 2 - bu, LENGTH - bv
    norm = math.hypot(gu, gv)
    wu, wv = bu + gu / norm * 9.15, bv + gv / norm * 9.15
    for k, i in enumerate(d.side_slots(defending, ("DEF", "MID"))[:3]):
        d.ov[i] = (*d.at(side, wu + (k - 1) * 0.9, wv), 9.0)
    d.gather([taker], 5)
    d.ov.clear()
    d.holder = taker
    _finish_set_piece_shot(d, side, taker, e, idx)


def _penalty(d: Director, e: dict, idx: int) -> None:
    side = e["team"]
    defending = _other(side)
    p = _payload(e)
    shooter = d.find(side, p.get("shooter"), p.get("shooter_id"), ("FWD", "MID"))
    keeper = d.keeper(defending)
    spot = d.at(side, WIDTH / 2, LENGTH - 11.0)
    d.phase = None
    d.kick(spot, 2)
    d.ov[shooter] = (*d.at(side, WIDTH / 2 + 0.5, LENGTH - 13.5), 9.0)
    d.ov[keeper] = (*d.at(side, WIDTH / 2, LENGTH - 0.6), 9.0)

    def outside_box(s: Slot, x: float, y: float) -> tuple[float, float]:
        if s.index in d.ov:
            return x, y
        u, v = to_own(side, x, y)
        return d.at(side, u, min(v, LENGTH - 19.5))

    d.limit = outside_box
    d.gather([shooter, keeper], 6)
    d.holder = shooter
    _finish_set_piece_shot(d, side, shooter, e, idx)
    d.limit = None


def _finish_set_piece_shot(d: Director, side: str, shooter: int, e: dict, idx: int) -> None:
    keeper = d.keeper(_other(side))
    # The shooter gets to the ball and strikes it.
    d.holder = None
    d.ov[shooter] = (*d.ball, 9.0)
    d.dead(1)
    d.holder = shooter
    d.tick()
    if e["event_type"] == "goal":
        d.kick(_goal_mouth(d, side, keeper=keeper), 2)
        d.mark(idx)
        d.ov.clear()
        d.limit = None
        _celebrate(d, side, shooter)
    elif e["event_type"] == "save":
        target = (d.pos[keeper][0] + d.rng.uniform(-1.5, 1.5), d.pos[keeper][1])
        d.kick(target, 2)
        d.mark(idx)
        d.ov.clear()
        d.limit = None
        d.hold(keeper, 3)
    else:
        d.kick(_goal_mouth(d, side, wide=True), 2)
        d.mark(idx)
        d.ov.clear()
        d.limit = None
        d.dead(2)
        d.kick(d.at(_other(side), WIDTH / 2, 5.5), 2, keep_phase=False)
        d.hold(keeper, 2)


def _breakaway(d: Director, e: dict, idx: int) -> None:
    """shot_type empty_net: a clean counter — the keeper caught upfield."""
    side = e["team"]
    keeper = d.keeper(_other(side))
    d.ov[keeper] = (*d.at(side, WIDTH / 2 + d.rng.uniform(-6, 6), LENGTH - 24), 7.0)
    finisher, _ = _build_up(d, side, {**e, "payload": {**_payload(e), "origin": "counter"}}, 2)
    d.ov.pop(keeper, None)
    _finish_shot(d, side, finisher, e, idx)


def _substitution(d: Director, e: dict, idx: int, players: list) -> None:
    side = e.get("team")
    p = _payload(e)
    if side not in ("a", "b"):
        return
    out = d.find(side, p.get("out"), p.get("out_id"), ("DEF", "MID", "FWD"))
    taken = {pl["n"] for pl in players if pl["s"] == side}
    num = next(n for n in range(12, 100) if n not in taken)
    players.append({"s": side, "n": num, "name": p.get("in"), "slot": d.slots[out].code, "id": p.get("in_id")})
    d.roster[out] = len(players) - 1
    d.swaps.append([d.frame, out, len(players) - 1])
    d.mark(idx)


def _episode(d: Director, group: list, detail: int) -> None:
    """One moment: the first chance event gets a build-up; the events that
    follow it in the same minute (defence, set pieces) chain from there."""
    first = True
    for idx, e in group:
        etype = e.get("event_type")
        p = _payload(e)
        side = e.get("team")
        if side not in ("a", "b"):
            d.mark(idx)
            continue
        if p.get("is_penalty") and etype in ("goal", "save"):
            if not first:
                d.phase = None
                d.dead(2)
            _penalty(d, e, idx)
        elif p.get("set_piece") == "corner":
            _corner(d, e, idx)
        elif p.get("set_piece") == "free_kick":
            _free_kick(d, e, idx)
        elif etype in DEFENCE_TYPES:
            _defence(d, e, idx)
        elif etype in CHANCE_TYPES:
            if p.get("shot_type") == "empty_net":
                _breakaway(d, e, idx)
            else:
                _attack(d, side, e, idx, detail)
        else:
            d.mark(idx)
        first = False


def _bridge(d: Director, t0: float, t1: float, frames: int, side: Optional[str]) -> None:
    """Accelerated play between two moments: the ball goes around midfield,
    ending with the side that attacks next."""
    frames = max(2, frames)
    seg = d.begin("bridge", t0, BRIDGE_MS)
    d.dt = (t1 - t0) / frames
    owner = side or d.rng.choice(("a", "b"))
    done = 0
    while done < frames:
        pool = d.side_slots(owner, ("DEF", "MID"))
        nxt = d.rng.choice([i for i in pool if i != d.holder] or pool)
        before = d.count
        if d.holder is None or d.slots[d.holder].side != owner:
            d.phase = owner
            d.kick(d.pos[nxt], 1)
            d.holder = nxt
        else:
            d.pass_to(d.holder, nxt, run_to=d.at(owner, d.to_u(nxt), d.rng.uniform(30, 58)), frames=1)
        d.hold(nxt, 1)
        done += d.count - before
    d.dt = STEP
    d.t = t1
    d.end(seg, t1)


# --- assembly --------------------------------------------------------------------------------

def _groups(events: list[dict], half: int) -> list[list[tuple[int, dict]]]:
    """Events of one half grouped by minute, in log order; substitutions and
    tactic changes are their own short notices."""
    groups: list[list[tuple[int, dict]]] = []
    for idx, e in enumerate(events):
        minute = int(e.get("minute") or 0)
        if (minute <= HALF_TIME) != (half == 1):
            continue
        notice = e.get("event_type") in ("substitution", "tactic_change")
        last = groups[-1] if groups else None
        if (last and not notice and int(last[0][1].get("minute") or 0) == minute
                and last[0][1].get("event_type") not in ("substitution", "tactic_change")):
            last.append((idx, e))
        else:
            groups.append([(idx, e)])
    return groups


def _initial_players(lineups: dict) -> tuple[list, list, dict]:
    players: list[dict] = []
    roster: list[int] = []
    sides = {}
    for side in ("a", "b"):
        info = _side_info(side, lineups.get(side))
        sides[side] = info
        xi = {row[2]: row for row in (lineups.get(side) or {}).get("xi") or [] if len(row) >= 3}
        taken: set[int] = set()
        for slot in info.slots:
            row = xi.get(slot.code)
            pos = next((fs.ideal_position.value for fs in CLUB_FORMATIONS[info.formation] if fs.code == slot.code), "CM")
            num = next((n for n in NUMBERS.get(pos, ()) if n not in taken), None)
            if num is None:
                num = next(n for n in range(2, 100) if n not in taken and n not in (1,))
            taken.add(num)
            players.append({"s": side, "n": num, "name": row[1] if row else None, "slot": slot.code,
                            "id": row[0] if row else None})
            roster.append(len(players) - 1)
    return players, roster, sides


def _subs_before(events: list[dict], minute: int) -> list[tuple[int, dict]]:
    return [(i, e) for i, e in enumerate(events)
            if e.get("event_type") == "substitution" and int(e.get("minute") or 0) <= minute]


def _build_half(seed: int, half: int, events: list[dict], lineups: dict, start_frame: int,
                detail: int, bridge_frames: int, moment_ms: int = EPISODE_MS) -> tuple[Director, list, list]:
    players, roster, sides = _initial_players(lineups)
    rng = random.Random(seed * 2 + half)
    d = Director(rng=rng, sides=sides, players=players, roster=roster, start_frame=start_frame)
    if half == 2:
        # The second half starts with whoever was on at the break and the
        # tactic in force then (plan instructions of the first half).
        for idx, e in enumerate(events):
            if int(e.get("minute") or 0) > HALF_TIME:
                continue
            if e.get("event_type") == "substitution":
                _substitution(d, e, idx, players)
            elif e.get("event_type") == "tactic_change":
                _apply_tactic(sides, e)
        d.swaps.clear()
        d.marks.clear()
    d.start_roster = list(d.roster)
    start_clock = 0.0 if half == 1 else HALF_TIME * 60.0
    end_clock = HALF_TIME * 60.0 if half == 1 else 90 * 60.0
    kicking = "a" if half == 1 else "b"
    seg = d.begin("kickoff", start_clock)
    _reset_kickoff(d, kicking, n=2)
    fwd = (d.side_slots(kicking, ("FWD",)) or d.side_slots(kicking, ("MID",)))[0]
    back = d.rng.choice(d.side_slots(kicking, ("MID",)) or d.side_slots(kicking, ("DEF",)))
    d.holder = fwd
    d.pass_to(fwd, back, frames=2)
    d.hold(back, 2)
    d.end(seg)

    for group in _groups(events, half):
        minute = int(group[0][1].get("minute") or 0)
        notice = group[0][1].get("event_type") in ("substitution", "tactic_change")
        lead = 5.0 if notice else 20.0
        t0 = max((minute - 1) * 60.0 + lead, d.t)
        if t0 - d.t >= 3.0:
            nxt = group[0][1].get("team")
            etype = group[0][1].get("event_type")
            attacker = (_other(nxt) if etype in DEFENCE_TYPES else nxt) if nxt in ("a", "b") else None
            gap = t0 - d.t
            _bridge(d, d.t, t0, int(_clamp(gap / 40.0, 2, bridge_frames)), None if notice else attacker)
        if notice:
            seg = d.begin("notice", t0)
            for idx, e in group:
                if e.get("event_type") == "substitution":
                    _substitution(d, e, idx, players)
                else:
                    _apply_tactic(sides, e)
                    d.mark(idx)
            d.dead(3) if d.holder is None else d.hold(d.holder, 3)
            d.end(seg)
            continue
        kind = "goal" if any(e.get("event_type") == "goal" for _, e in group) else "moment"
        seg = d.begin(kind, t0, EPISODE_MS if kind == "goal" else moment_ms)
        _episode(d, group, detail)
        d.end(seg)
    if end_clock - d.t >= 3.0:
        _bridge(d, d.t, end_clock, int(_clamp((end_clock - d.t) / 40.0, 2, bridge_frames)), None)
    seg = d.begin("whistle", max(d.t, end_clock))
    d.phase = None
    d.dead(3)
    d.end(seg, seg.t0)
    return d, players, roster


def _apply_tactic(sides: dict, e: dict) -> None:
    p = _payload(e)
    if e.get("team") in sides and p.get("tactic"):
        sides[e["team"]].tactic = dict(p["tactic"])
        sides[e["team"]].mentality = p.get("mentality") or sides[e["team"]].mentality


def _real_seconds(d: Director) -> float:
    return sum(s.n * s.ms for s in d.segments) / 1000


# Detail / bridge length / ms per frame of a moment without a goal, from the
# fullest show to the shortest; goals always run in real time.
VARIANTS = ((4, 8, 500), (4, 6, 500), (3, 5, 500), (2, 4, 500), (2, 2, 500), (2, 2, 400), (2, 2, 320))
LONG_VARIANTS = ((4, 14, 500), (4, 22, 500))


def _half(seed: int, half: int, events: list[dict], lineups: dict, start_frame: int):
    lo, hi = HALF_BUDGET_S
    best = None
    for detail, bridges, moment_ms in VARIANTS:
        built = _build_half(seed, half, events, lineups, start_frame, detail, bridges, moment_ms)
        secs = _real_seconds(built[0])
        if best is None or abs(secs - (lo + hi) / 2) < abs(best[1] - (lo + hi) / 2):
            best = (built, secs)
        if secs <= hi:
            if secs >= lo:
                return built
            for detail2, bridges2, ms2 in LONG_VARIANTS:  # a quiet half: longer bridges
                longer = _build_half(seed, half, events, lineups, start_frame, detail2, bridges2, ms2)
                if _real_seconds(longer[0]) <= hi:
                    built = longer
            return built
    return best[0]


def build_replay(seed: int, events: list[dict], lineups: Optional[dict], halves: int = 2) -> dict:
    """Key frames for the compressed show of a career match. `halves` = 1
    during the live break (only the first half exists yet)."""
    lineups = lineups or {}
    frames = bytearray()
    segments, marks, passes, swaps = [], [], [], []
    players_out: list[dict] = []
    roster_out: list[int] = []
    current: list[int] = []
    for half in range(1, halves + 1):
        d, players, _ = _half(seed, half, events, lineups, len(frames) // FRAME_SIZE)
        if half == 1:
            players_out, roster_out = players, list(d.start_roster)
        else:
            # The second half's players extend the first half's list (its
            # substitutes come after); keep names a placeholder got earlier.
            for i, pl in enumerate(players[:len(players_out)]):
                if not pl.get("name"):
                    pl["name"] = players_out[i].get("name")
            players_out = players
            start = len(frames) // FRAME_SIZE
            swaps += [[start, slot, pidx] for slot, pidx in enumerate(d.start_roster) if current[slot] != pidx]
        frames += d.frames
        segments += [[s.kind, s.f0, s.n, round(s.t0, 1), round(s.t1, 1), s.ms] for s in d.segments if s.n > 0]
        marks += d.marks
        passes += d.passes
        swaps += d.swaps
        current = list(d.roster)
    return {
        "v": VERSION, "step": STEP, "halves": halves, "frame_size": FRAME_SIZE,
        "pitch": [WIDTH, LENGTH], "count": len(frames) // FRAME_SIZE,
        "formations": {s: _side_info(s, lineups.get(s)).formation for s in ("a", "b")},
        "players": players_out, "roster": roster_out, "swaps": swaps,
        "segments": segments, "marks": marks, "passes": passes,
        "frames": base64.b64encode(bytes(frames)).decode("ascii"),
    }


def decode_frames(replay: dict) -> list[dict]:
    """Frames back to metres (tests, debugging)."""
    raw = base64.b64decode(replay["frames"])
    size = replay["frame_size"]
    out = []
    for f in range(len(raw) // size):
        chunk = raw[f * size:(f + 1) * size]
        out.append({
            "ball": (dequantise(chunk[0], WIDTH), dequantise(chunk[1], LENGTH)),
            "holder": None if chunk[2] == NO_HOLDER else chunk[2],
            "players": [(dequantise(chunk[3 + 2 * i], WIDTH), dequantise(chunk[4 + 2 * i], LENGTH)) for i in range(22)],
        })
    return out


def lineup_record(runner) -> dict:
    """The starting XI of a CareerSideRunner, stored with the match result so
    the replay knows who stood where (names and card ids)."""
    return {
        "formation": runner.formation, "mentality": runner.mentality, "tactic": dict(runner.tactic),
        "xi": [[p.card.id, p.card.player.display_name, p.slot.code] for p in runner.on_pitch],
    }
