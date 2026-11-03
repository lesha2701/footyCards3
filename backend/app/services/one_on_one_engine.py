"""«Атака 1 на 1»: the episode — a run with the ball at the keeper, at most
one feint, a shot — as a pure, deterministic function; a bit-exact port of
frontend/src/lib/oneOnOne/engine.ts.

The client steps the episode live from the player's finger and sends only
the input timeline (control changes, the feint, the shot with their ticks);
the server replays it here and alone decides the outcome. The shot reuses the
free kick's swipe → kick, forces and collision helpers (free_kick_3d_engine).
Keep any change in lockstep with engine.ts — the shared fixture
(tests/fixtures/one_on_one_episodes.json) is checked by both test suites.

Kept apart from the mini-game service on purpose: «Карьера игрока» key
moments can play the same episode.
"""

import math
from dataclasses import dataclass, field

from app.services import free_kick_3d_engine as fk
from app.services.free_kick_3d_engine import (
    BALL_RADIUS,
    EDGE_KEEPER,
    GOAL_HALF_WIDTH,
    GOAL_HEIGHT,
    GRAVITY,
    GROUND_FRICTION,
    GROUND_RESTITUTION,
    KEEPER_BODY_RADIUS,
    KEEPER_HAND_RADIUS,
    KEEPER_MAX_HAND_Y,
    POST_RADIUS,
    POST_RESTITUTION,
    ROLL_DECAY_PER_S,
    SIM_DT,
    SPIN_DECAY_PER_S,
    Swipe,
    mulberry32,
    rating_edge,
)

TICK = 1 / 60
MAX_RUN_TICKS = 600
BALL_LEAD = 0.55

RUN_SPEED = 5.4
EDGE_RUN = 0.5
RUN_ACCEL = 7.5
RUN_BRAKE = 8
STEER_SPREAD = 1.3
TURN_K = 0.16

FEINT_TICKS = 18
FEINT_SIDE_SPEED = 4.2
FEINT_SWEET = 4.5
FEINT_SPAN = 3.2
FEINT_BASE = 0.95
EDGE_FEINT = 0.08
LUNGE = 1.2
LUNGE_TICKS = 10

KEEPER_START_Z = 0.6
KEEPER_MAX_OUT = 8
SMOTHER_RADIUS = 0.85
DIVE_REACH = 2.6
KEEPER_HANDS_Y = 1.1
KEEPER_BODY_FOLLOW = 1.4
FALLEN_Y = 0.25
FALLEN_HALF = 0.85
FALLEN_RADIUS = 0.28
GET_UP = 0.15
RUSH_REACTION = 0.04
RUSH_HAND_Y = 2.0
SPREAD_DIST = 7
SPREAD_HALF = 1
SPREAD_Y = 0.3
SPREAD_RADIUS = 0.3

MAX_FLIGHT = 3
SHOT_MIN_SPEED = 11
SHOT_LIFT_SCALE = 1.2
SHOT_CHIP_LOFT = 0.6
AIM_REF = 18
CHIP_HEIGHT = 1.8
CHIP_KEEPER_OUT = 2


def _lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


@dataclass
class Keeper:
    react_ticks: int
    keep_gap: float
    rush_dist: float
    set_speed: float
    rush_speed: float
    composure: float
    fall_ticks: int
    shot_react: float
    dive_speed: float


@dataclass
class EpisodeSetup:
    seed: int
    edge: float
    start_x: float
    start_z: float
    keeper: Keeper


def create_episode(seed: int, rating: int = 75) -> EpisodeSetup:
    """Mirrors `createEpisode` (draws in the same order)."""
    rnd = mulberry32(seed)
    edge = rating_edge(rating)
    z = _lerp(21, 26, rnd())
    x = _lerp(-6, 6, rnd())
    slow = 1 - EDGE_KEEPER * edge
    react_ticks = math.floor(_lerp(14, 26, rnd()))
    keep_gap = _lerp(4.5, 5.5, rnd())
    rush_dist = _lerp(5, 6.5, rnd())
    set_speed = _lerp(3.2, 3.9, rnd()) * slow
    rush_speed = _lerp(4, 4.7, rnd()) * slow
    composure = _lerp(0.2, 1, rnd())
    fall_ticks = math.floor(_lerp(57, 86, rnd()))
    shot_react = _lerp(0.06, 0.12, rnd())
    dive_speed = _lerp(6, 7.5, rnd()) * slow
    keeper = Keeper(react_ticks, keep_gap, rush_dist, set_speed, rush_speed, composure, fall_ticks, shot_react, dive_speed)
    return EpisodeSetup(seed, edge, x, z, keeper)


@dataclass
class Flight:
    outcome: str  # goal | save | miss
    from_x: float
    from_z: float
    keeper_x: float
    keeper_z: float
    lying_for: float
    spread: bool
    over_y: float | None
    end_t: float
    end_position: tuple[float, float, float]
    end_velocity: tuple[float, float, float]
    events: list[str] = field(default_factory=list)


@dataclass
class EpisodeEnd:
    outcome: str  # goal | save | tackle | miss | lost
    tick: int
    feint: str | None  # bit | read
    chip: bool
    flight: Flight | None


@dataclass
class State:
    tick: int
    x: float
    z: float
    hx: float
    hz: float
    speed: float = 0
    feint_ticks: int = 0
    feint_dir: int = 0
    feint_used: bool = False
    feint: str | None = None
    kx: float = 0
    kz: float = KEEPER_START_Z
    k_mode: str = "wait"  # wait | set | rush | lunge | fallen
    k_ticks: int = 0
    lunge_dir: int = 0
    ended: EpisodeEnd | None = None


def init_state(setup: EpisodeSetup) -> State:
    length = math.sqrt(setup.start_x * setup.start_x + setup.start_z * setup.start_z)
    return State(0, setup.start_x, setup.start_z, -setup.start_x / length, -setup.start_z / length)


def _ball(s: State) -> tuple[float, float]:
    return s.x + s.hx * BALL_LEAD, s.z + s.hz * BALL_LEAD


def _keeper_down(s: State) -> bool:
    return s.k_mode in ("lunge", "fallen")


def _start_feint(setup: EpisodeSetup, s: State, direction: int) -> None:
    s.feint_used = True
    s.feint_ticks = FEINT_TICKS
    s.feint_dir = direction
    bx, bz = _ball(s)
    dx = bx - s.kx
    dz = bz - s.kz
    d = math.sqrt(dx * dx + dz * dz)
    chance = _clamp(1 - abs(d - FEINT_SWEET) / FEINT_SPAN, 0, 1) * FEINT_BASE + EDGE_FEINT * setup.edge
    if not _keeper_down(s) and chance > setup.keeper.composure:
        s.feint = "bit"
        s.k_mode = "lunge"
        s.k_ticks = LUNGE_TICKS
        s.lunge_dir = -direction
    else:
        s.feint = "read"


def _keeper_step(setup: EpisodeSetup, s: State) -> None:
    k = setup.keeper
    if s.k_mode == "lunge":
        s.kx += s.lunge_dir * (LUNGE / LUNGE_TICKS)
        s.k_ticks -= 1
        if s.k_ticks <= 0:
            s.k_mode = "fallen"
            s.k_ticks = k.fall_ticks
        return
    if s.k_mode == "fallen":
        s.k_ticks -= 1
        if s.k_ticks <= 0:
            s.k_mode = "set"
        return
    if s.tick < k.react_ticks:
        return
    bx, bz = _ball(s)
    dx = bx - s.kx
    dz = bz - s.kz
    d = math.sqrt(dx * dx + dz * dz)
    if d < k.rush_dist:
        tx, tz, speed = bx, bz, k.rush_speed
        s.k_mode = "rush"
    else:
        gl = max(0.5, math.sqrt(bx * bx + bz * bz))
        out = _clamp(gl - k.keep_gap, KEEPER_START_Z, KEEPER_MAX_OUT)
        tx = (bx / gl) * out
        tz = (bz / gl) * out
        speed = k.set_speed
        s.k_mode = "set"
    ex = tx - s.kx
    ez = tz - s.kz
    e = math.sqrt(ex * ex + ez * ez)
    step = speed * TICK
    if e <= step:
        s.kx, s.kz = tx, tz
    else:
        s.kx += (ex / e) * step
        s.kz += (ez / e) * step


def _end(s: State, outcome: str, flight: Flight | None = None, chip: bool = False) -> None:
    s.ended = EpisodeEnd(outcome, s.tick, s.feint, chip, flight)


def _step_run(setup: EpisodeSetup, s: State, hold: bool, steer_milli: int) -> None:
    steer = _clamp(steer_milli, -1000, 1000) / 1000
    sx = steer * STEER_SPREAD
    dl = math.sqrt(sx * sx + 1)
    want_x = sx / dl
    want_z = -1 / dl
    hx = s.hx + (want_x - s.hx) * TURN_K
    hz = s.hz + (want_z - s.hz) * TURN_K
    hl = math.sqrt(hx * hx + hz * hz) or 1
    s.hx = hx / hl
    s.hz = hz / hl

    top = RUN_SPEED + EDGE_RUN * setup.edge
    s.speed = min(top, s.speed + RUN_ACCEL * TICK) if hold else max(0, s.speed - RUN_BRAKE * TICK)
    vx = s.hx * s.speed
    vz = s.hz * s.speed
    if s.feint_ticks > 0:
        s.feint_ticks -= 1
        vx += -s.hz * s.feint_dir * FEINT_SIDE_SPEED
        vz += s.hx * s.feint_dir * FEINT_SIDE_SPEED
    s.x += vx * TICK
    s.z += vz * TICK
    s.tick += 1

    _keeper_step(setup, s)

    bx, bz = _ball(s)
    if not _keeper_down(s):
        dx = bx - s.kx
        dz = bz - s.kz
        if dx * dx + dz * dz < SMOTHER_RADIUS * SMOTHER_RADIUS:
            return _end(s, "tackle")
    if bz <= 0:
        return _end(s, "goal" if abs(bx) < GOAL_HALF_WIDTH - POST_RADIUS - BALL_RADIUS else "lost")
    if abs(s.x) > 30 or s.z > 40 or s.tick >= MAX_RUN_TICKS:
        return _end(s, "lost")


def advance(setup: EpisodeSetup, s: State, hold: bool, steer: int, feint: int, shot: Swipe | None) -> None:
    """Mirrors `advance`: the feint, then the shot (unless a feint is under
    way), else the run."""
    if s.ended:
        return
    if feint != 0 and not s.feint_used:
        _start_feint(setup, s, 1 if feint > 0 else -1)
    if shot is not None and s.feint_ticks == 0:
        flight = shoot(setup, s, shot)
        chip = (
            flight.outcome == "goal" and flight.over_y is not None and flight.over_y >= CHIP_HEIGHT
            and flight.keeper_z >= CHIP_KEEPER_OUT
        )
        return _end(s, flight.outcome, flight, chip)
    _step_run(setup, s, hold, steer)


@dataclass
class Timeline:
    """The client's input: control changes (tick, hold 0/1, steer in
    thousandths) in ascending ticks, the feint (tick, ±1) and the shot
    (tick and the quantized swipe)."""

    controls: list[tuple[int, int, int]]
    feint: tuple[int, int] | None
    shot: tuple[int, Swipe] | None


def replay_episode(setup: EpisodeSetup, tl: Timeline) -> EpisodeEnd:
    s = init_state(setup)
    ci = 0
    hold = False
    steer = 0
    while s.ended is None:
        i = s.tick
        while ci < len(tl.controls) and tl.controls[ci][0] <= i:
            hold = tl.controls[ci][1] == 1
            steer = tl.controls[ci][2]
            ci += 1
        feint = tl.feint[1] if tl.feint is not None and tl.feint[0] == i else 0
        shot = tl.shot[1] if tl.shot is not None and tl.shot[0] <= i else None
        advance(setup, s, hold, steer, feint, shot)
    return s.ended


def _hit_lying(p, x0, x1, y, z, r):
    cx = _clamp(p[0], x0, x1)
    nx = p[0] - cx
    ny = p[1] - y
    nz = p[2] - z
    d2 = nx * nx + ny * ny + nz * nz
    rr = r + BALL_RADIUS
    if d2 >= rr * rr:
        return None
    d = math.sqrt(d2) or 1
    return (nx / d, ny / d, nz / d)


def shoot(setup: EpisodeSetup, s: State, q: Swipe) -> Flight:
    """Mirrors `shoot` (minus the render samples)."""
    fx, fz = _ball(s)
    dist = math.sqrt(fx * fx + fz * fz)
    kick_setup = fk.Setup(
        setup.seed, setup.edge, (fx, BALL_RADIUS, fz), [], 99, 0, 0, 0,
        min_speed=SHOT_MIN_SPEED, lift_scale=SHOT_LIFT_SCALE, aim_scale=_clamp(AIM_REF / dist, 1, 3),
        chip_loft=SHOT_CHIP_LOFT,
    )
    velocity, kick_spin = fk.swipe_to_kick(kick_setup, q)

    kx, kz = s.kx, s.kz
    if s.k_mode == "lunge":
        lying_for = (s.k_ticks + setup.keeper.fall_ticks) * TICK
    elif s.k_mode == "fallen":
        lying_for = s.k_ticks * TICK
    else:
        lying_for = 0
    if lying_for > 0:
        reaction = lying_for + GET_UP
    else:
        reaction = setup.keeper.shot_react + (RUSH_REACTION if s.k_mode == "rush" else 0)
    max_hand_y = RUSH_HAND_Y if s.k_mode == "rush" else KEEPER_MAX_HAND_Y
    kdx = fx - kx
    kdz = fz - kz
    spread = lying_for == 0 and kdx * kdx + kdz * kdz < SPREAD_DIST * SPREAD_DIST

    px, py, pz = fx, BALL_RADIUS, fz
    vx, vy, vz = velocity
    sx, sy, sz = kick_spin
    hand_x, hand_y = kx, KEEPER_HANDS_Y
    target_x, target_y = kx, KEEPER_HANDS_Y
    decided = False

    events: list[str] = []
    outcome = "miss"
    over_y = None
    decided_at = -1.0
    step = 0
    max_steps = round(MAX_FLIGHT / SIM_DT)
    while step < max_steps:
        step += 1
        t = step * SIM_DT
        prev_z = pz

        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        mx = fk.MAGNUS_K * (sy * vz - sz * vy)
        my = fk.MAGNUS_K * (sz * vx - sx * vz)
        mz = fk.MAGNUS_K * (sx * vy - sy * vx)
        ax = -fk.DRAG_K * speed * vx + mx
        ay = -GRAVITY - fk.DRAG_K * speed * vy + my
        az = -fk.DRAG_K * speed * vz + mz
        vx, vy, vz = vx + ax * SIM_DT, vy + ay * SIM_DT, vz + az * SIM_DT
        px, py, pz = px + vx * SIM_DT, py + vy * SIM_DT, pz + vz * SIM_DT
        decay = 1 - SPIN_DECAY_PER_S * SIM_DT
        sx *= decay
        sy *= decay
        sz *= decay

        if not decided and t >= reaction:
            decided = True
            if vz < -0.1 and pz > kz:
                tt = (kz - pz) / vz
                target_x = _clamp(px + vx * tt, kx - DIVE_REACH, kx + DIVE_REACH)
                target_y = _clamp(py + vy * tt - 0.5 * GRAVITY * tt * tt, 0.25, max_hand_y)
        if decided:
            ex = target_x - hand_x
            ey = target_y - hand_y
            d = math.sqrt(ex * ex + ey * ey)
            hs = setup.keeper.dive_speed * SIM_DT
            if d <= hs:
                hand_x, hand_y = target_x, target_y
            else:
                hand_x += (ex / d) * hs
                hand_y += (ey / d) * hs

        if py < BALL_RADIUS:
            py = BALL_RADIUS
            if vy < -0.5:
                events.append("bounce")
                vx, vy, vz = vx * GROUND_FRICTION, -vy * GROUND_RESTITUTION, vz * GROUND_FRICTION
                # Off the grass it comes up somewhere else: he reads it again.
                decided = False
            else:
                roll = 1 - ROLL_DECAY_PER_S * SIM_DT
                vx, vy, vz = vx * roll, 0, vz * roll

        if over_y is None and prev_z > kz and pz <= kz:
            over_y = py

        p = (px, py, pz)
        if t < lying_for:
            keeper_normal = _hit_lying(p, kx - FALLEN_HALF, kx + FALLEN_HALF, FALLEN_Y, kz, FALLEN_RADIUS)
        else:
            body_x = _clamp(hand_x, kx - KEEPER_BODY_FOLLOW, kx + KEEPER_BODY_FOLLOW)
            keeper_normal = fk._hit_sphere(p, hand_x, hand_y, kz, KEEPER_HAND_RADIUS) or fk._hit_vertical_capsule(
                p, body_x, kz, KEEPER_BODY_RADIUS, max(KEEPER_BODY_RADIUS, min(hand_y, 1.6)), KEEPER_BODY_RADIUS,
            )
            if not keeper_normal and spread:
                keeper_normal = _hit_lying(p, kx - SPREAD_HALF, kx + SPREAD_HALF, SPREAD_Y, kz, SPREAD_RADIUS)
        if keeper_normal:
            vx, vy, vz = fk._reflect((vx, vy, vz), keeper_normal, 0.3)
            outcome = "save"
            events.append("save")
            decided_at = t
            break

        frame = fk._hit_frame(p)
        if frame:
            normal, push = frame
            px, py, pz = px + normal[0] * push, py + normal[1] * push, pz + normal[2] * push
            before = (vx, vy, vz)
            after = fk._reflect(before, normal, POST_RESTITUTION)
            if after is not before:
                events.append("post")
            vx, vy, vz = after

        if prev_z > -BALL_RADIUS and pz <= -BALL_RADIUS:
            inside = abs(px) < GOAL_HALF_WIDTH - POST_RADIUS and py < GOAL_HEIGHT - POST_RADIUS
            outcome = "goal" if inside else "miss"
            events.append(outcome)
            decided_at = t
            break

        speed2 = vx * vx + vy * vy + vz * vz
        if abs(px) > 40 or pz > fz + 5 or (py <= BALL_RADIUS and speed2 < 1):
            outcome = "miss"
            events.append("miss")
            decided_at = t
            break

    if decided_at < 0:
        decided_at = step * SIM_DT
        events.append("miss")

    return Flight(outcome, fx, fz, kx, kz, lying_for, spread, over_y, decided_at, (px, py, pz), (vx, vy, vz), events)
