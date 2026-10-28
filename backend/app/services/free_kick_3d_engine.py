"""«Штрафной 3D»: the shot as a pure, deterministic function — a bit-exact
port of frontend/src/lib/freeKick3d/trajectory.ts.

The client shows the flight; the server replays it from the same inputs
(seed, card rating, the swipe in integer thousandths) and alone decides the
outcome. Both sides only use + − × ÷, sqrt, min/max/abs and 32-bit integer
mixing in the same order, so IEEE-754 doubles give identical results.
Keep any change here in lockstep with trajectory.ts — the shared fixture
(tests/fixtures/free_kick_3d_shots.json) is checked by both test suites.

World: metres, y up, the goal line is z = 0, the goal is centred on x = 0
and the ball is kicked towards −z.
"""

import math
from dataclasses import dataclass, field

BALL_RADIUS = 0.11
GOAL_HALF_WIDTH = 3.66
GOAL_HEIGHT = 2.44
POST_RADIUS = 0.06
WALL_DISTANCE = 9.15
WALL_PLAYER_RADIUS = 0.24
WALL_PLAYER_HEIGHT = 1.85
WALL_JUMP_HEIGHT = 0.22
WALL_JUMP_DURATION = 0.5
KEEPER_LINE_Z = -0.4
KEEPER_HAND_RADIUS = 0.32
KEEPER_BODY_RADIUS = 0.3
KEEPER_STAND_HAND_Y = 1.25
KEEPER_MAX_HAND_Y = 2.45
KEEPER_MAX_REACH = 3.4

GRAVITY = 9.81
DRAG_K = 0.0135
MAGNUS_K = 0.006
SPIN_DECAY_PER_S = 0.08
GROUND_RESTITUTION = 0.5
GROUND_FRICTION = 0.9
ROLL_DECAY_PER_S = 0.08
POST_RESTITUTION = 0.65

SIM_DT = 1 / 240
MAX_TIME = 4

MIN_SPEED = 16
MAX_SPEED = 34
MAX_SPIN = 75
CURL_GAIN = 260
DIP_GAIN = 180
MAX_DIP = 40
EDGE_SPEED = 2
EDGE_CURL = 0.1
EDGE_KEEPER = 0.08

PENALTY_DISTANCE = 11
PENALTY_MIN_SPEED = 12
PENALTY_CHIP_LOFT = 0.35
CHIP_SPEED = 17
PENALTY_LIFT_SCALE = 1.4
PENALTY_AIM_SCALE = 1.5
PENALTY_MIN_REACTION = 0.18
PLAYER_KEEPER_SPEED = 7.2

_U32 = 0xFFFFFFFF


def _u32(x: int) -> int:
    return x & _U32


def _i32(x: int) -> int:
    x &= _U32
    return x - 0x100000000 if x & 0x80000000 else x


def _imul(a: int, b: int) -> int:
    return _i32(_u32(a) * _u32(b))


def mulberry32(seed: int):
    """JS `mulberry32` (with the same seed scramble), int ops emulated."""
    s = _u32(seed)
    a = _u32(_imul(_u32(s ^ (s >> 16)), 0x45D9F3B))
    a = _u32(_imul(_i32(a ^ (a >> 16)), 0x45D9F3B))
    a = _u32(a ^ (a >> 16))
    state = [a]

    def rnd() -> float:
        state[0] = _u32(state[0] + 0x6D2B79F5)
        t = state[0]
        t = _imul(_i32(t ^ (_u32(t) >> 15)), _i32(t | 1))
        t = _i32(t ^ (t + _imul(_i32(t ^ (_u32(t) >> 7)), _i32(t | 61))))
        return _u32(t ^ (_u32(t) >> 14)) / 4294967296

    return rnd


def _lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def rating_edge(rating: int) -> float:
    return _clamp((rating - 75) / 20, -1, 1)


@dataclass
class Setup:
    seed: int
    edge: float
    ball: tuple[float, float, float]
    wall: list[tuple[float, float]]
    wall_jump_at: float
    keeper_x: float
    keeper_reaction: float
    keeper_speed: float
    # Penalty knobs (a free kick keeps these defaults — see trajectory.ts).
    min_speed: float = MIN_SPEED
    lift_scale: float = 1
    aim_scale: float = 1
    chip_loft: float = 0
    keeper_guess: tuple[float, float] | None = None
    keeper_reads_drop: bool = False


def create_setup(seed: int, rating: int = 75) -> Setup:
    rnd = mulberry32(seed)
    edge = rating_edge(rating)
    distance = _lerp(18, 26, rnd())
    side = -1 if rnd() < 0.5 else 1
    offset = side * _lerp(0, 8, rnd())
    bx, by, bz = offset, BALL_RADIUS, distance

    length = math.sqrt(bx * bx + bz * bz)
    fx = -bx / length
    fz = -bz / length
    px = -fz
    pz = fx

    count = 3 if rnd() < 0.5 else 4
    near_side = 0 if abs(offset) < 1.5 else (1 if offset > 0 else -1)
    shift = near_side * _lerp(0.6, 1.2, rnd())
    spacing = WALL_PLAYER_RADIUS * 2 + 0.04
    wall = []
    for i in range(count):
        s = (i - (count - 1) / 2) * spacing + shift
        wall.append((bx + fx * WALL_DISTANCE + px * s, bz + fz * WALL_DISTANCE + pz * s))

    wall_jump_at = _lerp(0.12, 0.3, rnd())
    keeper_x = -near_side * _lerp(0.3, 0.9, rnd())
    keeper_reaction = _lerp(0.2, 0.32, rnd())
    keeper_speed = _lerp(4.6, 5.6, rnd()) * (1 - EDGE_KEEPER * edge)
    return Setup(seed, edge, (bx, by, bz), wall, wall_jump_at, keeper_x, keeper_reaction, keeper_speed)


def _same_side(guess_x: float, ball_x: float) -> bool:
    return ball_x * guess_x > 0 and abs(ball_x) > 0.5


# ---------------------------------------------------------------------------
# Penalties (mirrors createPenaltySetup / playerKeeperSetup / penaltyBotShot)
# ---------------------------------------------------------------------------

def create_penalty_setup(seed: int, rating: int = 75) -> Setup:
    rnd = mulberry32(seed)
    edge = rating_edge(rating)
    commits = rnd() < 0.6
    side = -1 if rnd() < 0.5 else 1
    guess_x = side * _lerp(1.8, 3.2, rnd())
    guess_y = _lerp(0.35, 1.9, rnd())
    early = _lerp(0, 0.06, rnd())
    read = _lerp(0.12, 0.18, rnd())
    speed = _lerp(4.9, 5.6, rnd()) * (1 - EDGE_KEEPER * edge)
    return Setup(
        seed, edge, (0, BALL_RADIUS, PENALTY_DISTANCE), [], 99, 0, early if commits else read, speed,
        min_speed=PENALTY_MIN_SPEED, lift_scale=PENALTY_LIFT_SCALE, aim_scale=PENALTY_AIM_SCALE,
        chip_loft=PENALTY_CHIP_LOFT, keeper_guess=(guess_x, guess_y) if commits else None, keeper_reads_drop=True,
    )


@dataclass
class Dive:
    """The player's dive as the client quantized it: where (mm) and when
    (ms from the strike, negative during the run-up)."""

    x: int
    y: int
    reaction_ms: int


def player_keeper_setup(seed: int, dive: "Dive | None") -> Setup:
    base = create_penalty_setup(seed)
    if dive is None:
        reaction, guess = 99, None
    else:
        reaction = 0 if dive.reaction_ms < 0 else max(PENALTY_MIN_REACTION, dive.reaction_ms / 1000)
        guess = (_clamp(dive.x / 1000, -GOAL_HALF_WIDTH, GOAL_HALF_WIDTH), _clamp(dive.y / 1000, 0.25, KEEPER_MAX_HAND_Y))
    return Setup(
        base.seed, 0, base.ball, [], base.wall_jump_at, 0, reaction, PLAYER_KEEPER_SPEED,
        min_speed=base.min_speed, lift_scale=base.lift_scale, aim_scale=base.aim_scale, chip_loft=base.chip_loft,
        keeper_guess=guess, keeper_reads_drop=True,
    )


BOT_KINDS = [
    ("low_corner", 28), ("side", 20), ("top_corner", 20), ("power", 12), ("chip", 7), ("wide", 8), ("over", 5),
]
_BOT_RANGES = {
    "low_corner": ((42, 55), (100, 120), (150, 180)),
    "side": ((50, 70), (150, 175), (160, 190)),
    "top_corner": ((85, 105), (220, 238), (140, 160)),
    "power": ((0, 12), (170, 215), (115, 140)),
    "chip": ((0, 6), (250, 270), (800, 1000)),
    "wide": ((120, 160), (140, 200), (140, 170)),
    "over": ((0, 60), (290, 320), (130, 160)),
}


def penalty_bot_shot(seed: int, dive: "Dive | None" = None) -> tuple[str, "Swipe"]:
    rnd = mulberry32(_u32(seed ^ 0x5BD1E995))
    pick = rnd() * 100
    side = -1 if rnd() < 0.5 else 1
    a, b, c = rnd(), rnd(), rnd()
    acc = 0
    kind = "low_corner"
    for k, w in BOT_KINDS:
        acc += w
        if pick < acc:
            kind = k
            break
    (dx0, dx1), (dy0, dy1), (ms0, ms1) = _BOT_RANGES[kind]
    whole = lambda v: math.floor(v + 0.5)  # noqa: E731
    dx, dy, ms = _lerp(dx0, dx1, a), _lerp(dy0, dy1, b), _lerp(ms0, ms1, c)
    aimed = kind in ("low_corner", "side", "top_corner")
    direction = -side if aimed and dive is not None and dive.reaction_ms < 0 and dive.x * side > 0 else side
    return kind, Swipe(direction * whole(dx), -whole(dy), 0, whole(ms))


@dataclass
class Swipe:
    """The swipe as the client quantized it: integer thousandths of the
    viewport height (dy < 0 is upwards) and whole milliseconds."""

    dx: int
    dy: int
    curve: int
    duration_ms: int


def quantize_duration(ms: int) -> int:
    return round(_clamp(ms, 40, 2000))


def swipe_to_kick(setup: Setup, q: Swipe) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """(velocity, spin) — mirrors `swipeToKick`."""
    dx = q.dx / 1000
    up = max(0.02, -q.dy / 1000)
    curve = _clamp(q.curve / 1000, -0.5, 0.5)
    length = math.sqrt(dx * dx + up * up)
    swipe_speed = math.sqrt(length * 0.4) / (q.duration_ms / 1000)
    speed = _clamp(setup.min_speed + swipe_speed * 7, setup.min_speed, MAX_SPEED + EDGE_SPEED * setup.edge)

    bx, _, bz = setup.ball
    ln = math.sqrt(bx * bx + bz * bz)
    fx = -bx / ln
    fz = -bz / ln
    rx = -fz
    rz = fx

    aim = _clamp(dx / up, -0.8, 0.8) * 0.35 * setup.aim_scale
    chip = _clamp((CHIP_SPEED - speed) / 3, 0, 1) * setup.chip_loft
    lift = _clamp((0.2 - (0.2 - up) * 1.6 if up < 0.2 else 0.2 + (up - 0.2) * 0.8) * setup.lift_scale + chip, 0.02, 0.7)
    side = _clamp(curve * CURL_GAIN * (1 + EDGE_CURL * setup.edge), -MAX_SPIN, MAX_SPIN)
    yaw = aim + (MAGNUS_K * side * ln) / (2 * speed)

    dir_x = fx + rx * yaw
    dir_z = fz + rz * yaw
    n = math.sqrt(dir_x * dir_x + lift * lift + dir_z * dir_z)
    velocity = ((dir_x / n) * speed, (lift / n) * speed, (dir_z / n) * speed)
    dip = _clamp((lift - 0.22) * DIP_GAIN, 0, MAX_DIP)
    spin = (-rx * dip, side, -rz * dip)
    return velocity, spin


def _wall_lift_at(setup: Setup, t: float) -> float:
    k = (t - setup.wall_jump_at) / WALL_JUMP_DURATION
    if k <= 0 or k >= 1:
        return 0
    return WALL_JUMP_HEIGHT * 4 * k * (1 - k)


def _hit_vertical_capsule(p, cx, cz, y0, y1, r):
    cy = _clamp(p[1], y0, y1)
    nx = p[0] - cx
    ny = p[1] - cy
    nz = p[2] - cz
    d2 = nx * nx + ny * ny + nz * nz
    rr = r + BALL_RADIUS
    if d2 >= rr * rr:
        return None
    d = math.sqrt(d2) or 1
    return (nx / d, ny / d, nz / d)


def _hit_sphere(p, cx, cy, cz, r):
    nx = p[0] - cx
    ny = p[1] - cy
    nz = p[2] - cz
    d2 = nx * nx + ny * ny + nz * nz
    rr = r + BALL_RADIUS
    if d2 >= rr * rr:
        return None
    d = math.sqrt(d2) or 1
    return (nx / d, ny / d, nz / d)


def _hit_frame(p):
    rr = POST_RADIUS + BALL_RADIUS
    for sx in (-GOAL_HALF_WIDTH, GOAL_HALF_WIDTH):
        if p[1] > GOAL_HEIGHT + rr:
            continue
        nx = p[0] - sx
        nz = p[2]
        d2 = nx * nx + nz * nz
        if d2 < rr * rr:
            d = math.sqrt(d2) or 1
            return (nx / d, 0, nz / d), rr - d
    if abs(p[0]) <= GOAL_HALF_WIDTH:
        ny = p[1] - GOAL_HEIGHT
        nz = p[2]
        d2 = ny * ny + nz * nz
        if d2 < rr * rr:
            d = math.sqrt(d2) or 1
            return (0, ny / d, nz / d), rr - d
    return None


def _reflect(v, n, restitution):
    vn = v[0] * n[0] + v[1] * n[1] + v[2] * n[2]
    if vn >= 0:
        return v
    k = (1 + restitution) * vn
    return (v[0] - k * n[0], v[1] - k * n[1], v[2] - k * n[2])


@dataclass
class ShotResult:
    outcome: str  # goal | save | miss | wall
    end_t: float
    end_position: tuple[float, float, float]
    end_velocity: tuple[float, float, float]
    spin: tuple[float, float, float]
    events: list[str] = field(default_factory=list)


def simulate_shot(setup: Setup, q: Swipe) -> ShotResult:
    """Mirrors `simulateShot` (minus the render samples)."""
    velocity, kick_spin = swipe_to_kick(setup, q)
    px, py, pz = setup.ball
    vx, vy, vz = velocity
    sx, sy, sz = kick_spin
    hand_x, hand_y = setup.keeper_x, KEEPER_STAND_HAND_Y
    target_x, target_y = setup.keeper_x, KEEPER_STAND_HAND_Y
    decided = False

    def keeper_body_x():
        return _clamp(hand_x, setup.keeper_x - 1.6, setup.keeper_x + 1.6)

    events: list[str] = []
    outcome = "miss"
    decided_at = -1.0
    step = 0
    max_steps = round(MAX_TIME / SIM_DT)
    while step < max_steps:
        step += 1
        t = step * SIM_DT
        prev_z = pz

        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        mx = MAGNUS_K * (sy * vz - sz * vy)
        my = MAGNUS_K * (sz * vx - sx * vz)
        mz = MAGNUS_K * (sx * vy - sy * vx)
        ax = -DRAG_K * speed * vx + mx
        ay = -GRAVITY - DRAG_K * speed * vy + my
        az = -DRAG_K * speed * vz + mz
        vx, vy, vz = vx + ax * SIM_DT, vy + ay * SIM_DT, vz + az * SIM_DT
        px, py, pz = px + vx * SIM_DT, py + vy * SIM_DT, pz + vz * SIM_DT
        decay = 1 - SPIN_DECAY_PER_S * SIM_DT
        sx *= decay
        sy *= decay
        sz *= decay

        if not decided and t >= setup.keeper_reaction:
            decided = True
            guess = setup.keeper_guess
            if guess and (vz >= -0.1 or not _same_side(guess[0], px + vx * ((KEEPER_LINE_Z - pz) / vz))):
                # Committed, and the ball isn't going his way.
                target_x = _clamp(guess[0], -GOAL_HALF_WIDTH - 0.3, GOAL_HALF_WIDTH + 0.3)
                target_y = _clamp(guess[1], 0.25, KEEPER_MAX_HAND_Y)
            elif vz >= -0.1:
                target_x, target_y = setup.keeper_x, KEEPER_STAND_HAND_Y
            else:
                tt = (KEEPER_LINE_Z - pz) / vz
                min_x = setup.keeper_x - KEEPER_MAX_REACH
                max_x = setup.keeper_x + KEEPER_MAX_REACH
                target_x = _clamp(px + vx * tt, max(min_x, -GOAL_HALF_WIDTH - 0.3), min(max_x, GOAL_HALF_WIDTH + 0.3))
                drop = 0.5 * GRAVITY * tt * tt if setup.keeper_reads_drop else 0
                target_y = _clamp(py + vy * tt - drop, 0.25, KEEPER_MAX_HAND_Y)
        if decided:
            ex = target_x - hand_x
            ey = target_y - hand_y
            d = math.sqrt(ex * ex + ey * ey)
            kstep = setup.keeper_speed * SIM_DT
            if d <= kstep:
                hand_x, hand_y = target_x, target_y
            else:
                hand_x += (ex / d) * kstep
                hand_y += (ey / d) * kstep

        if py < BALL_RADIUS:
            py = BALL_RADIUS
            if vy < -0.5:
                events.append("bounce")
                vx, vy, vz = vx * GROUND_FRICTION, -vy * GROUND_RESTITUTION, vz * GROUND_FRICTION
            else:
                roll = 1 - ROLL_DECAY_PER_S * SIM_DT
                vx, vy, vz = vx * roll, 0, vz * roll

        p = (px, py, pz)
        lift = _wall_lift_at(setup, t)
        wall_normal = None
        for wx, wz in setup.wall:
            wall_normal = _hit_vertical_capsule(
                p, wx, wz, lift + WALL_PLAYER_RADIUS, lift + WALL_PLAYER_HEIGHT - WALL_PLAYER_RADIUS, WALL_PLAYER_RADIUS,
            )
            if wall_normal:
                break
        if wall_normal:
            vx, vy, vz = _reflect((vx, vy, vz), wall_normal, 0.35)
            outcome = "wall"
            events.append("wall")
            decided_at = t
            break

        body_x = keeper_body_x()
        keeper_normal = _hit_sphere(p, hand_x, hand_y, KEEPER_LINE_Z, KEEPER_HAND_RADIUS) or _hit_vertical_capsule(
            p, body_x, KEEPER_LINE_Z, KEEPER_BODY_RADIUS, max(KEEPER_BODY_RADIUS, min(hand_y, 1.6)), KEEPER_BODY_RADIUS,
        )
        if keeper_normal:
            vx, vy, vz = _reflect((vx, vy, vz), keeper_normal, 0.3)
            outcome = "save"
            events.append("save")
            decided_at = t
            break

        frame = _hit_frame(p)
        if frame:
            normal, push = frame
            px, py, pz = px + normal[0] * push, py + normal[1] * push, pz + normal[2] * push
            before = (vx, vy, vz)
            after = _reflect(before, normal, POST_RESTITUTION)
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
        if abs(px) > 40 or pz > setup.ball[2] + 5 or (py <= BALL_RADIUS and speed2 < 1):
            outcome = "miss"
            events.append("miss")
            decided_at = t
            break

    if decided_at < 0:
        decided_at = step * SIM_DT
        events.append("miss")

    return ShotResult(outcome, decided_at, (px, py, pz), (vx, vy, vz), kick_spin, events)
