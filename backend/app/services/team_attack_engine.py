"""The team episodes built on «Атака 1 на 1»: 2 на 1, 3 на 2, пас в разрез,
навес / прострел — a bit-exact port of frontend/src/lib/oneOnOne/team.ts, on
top of one_on_one_engine (the same run, keeper and shot). The client sends
only the input timeline, the server replays it here and alone decides the
outcome. Keep any change in lockstep with team.ts — the shared fixture
(tests/fixtures/team_episodes.json) is checked by both test suites.
"""

import math
from dataclasses import dataclass, field

from app.services import one_on_one_engine as base
from app.services.free_kick_3d_engine import BALL_RADIUS, Swipe, mulberry32

TICK = base.TICK

PASS_WINDUP = 10
MAX_PASSES = 3
PASS_SPEED = 15
PASS_EDGE = 1.5
CUTBACK_SPEED = 20
INTERCEPT_RADIUS = 0.75
MEET_ROUNDS = 3
FIRST_TIME_TICKS = 10
FIRST_TIME_SCATTER = 0.08
VOLLEY_SCATTER = 0.2
VOLLEY_FROM = 0.5
HEADER_SCATTER = 0.26
SCATTER_EDGE = 0.6
KEEPER_DEEP = 4.5
KEEPER_SHUFFLE = 2.4

PASS_GROUND = 0
PASS_THROUGH = 1
PASS_CROSS = 2
PASS_CUTBACK = 3

CROSS_SOFT = 13
CROSS_HARD = 23
CROSS_ARC_LOW = 0.5
CROSS_ARC_HIGH = 3.4
CONTACT_LOW = 0.65
CONTACT_HIGH = 2.2
CROSS_SWEET = 0.55
CROSS_SPREAD = 6
CROSS_AFTER = 0.3
CONTROL_TICKS = 9
CROSS_LATE = 14
LOW_BALL = 1.2
CONTEST_RADIUS = 1.3
KEEPER_ZONE_Z = 6
KEEPER_ZONE_X = 9
CLAIM_RADIUS = 1.9
CLAIM_PRESSED = 1.3
CLAIM_SPEED = 6.5
THROUGH_LEAD = 6
RECEIVER_TOP = 7.4
MEET_MIN_Z = 3.5
RUN_AFTER_CONTROL = 3

MATE_SPEED = 6.1
MATE_BEHIND = 0.8
LANE_MIN = 0.55
LANE_FROM = 25
MATE_MIN_Z = 7

DEF_EDGE = 0.1
STAND_OFF = 3
STAND_NEAR = 1
STAND_FROM = 22
STAND_TO = 14
DEF_LUNGE_DIST = 1.7
LUNGE_SPEED = 8.5
DEF_LUNGE_TICKS = 16
LUNGE_LEAD = 0.18
TACKLE_REACH = 0.85
DOWN_TICKS = 70
FEINT_REACH = 4.5
FEINT_BITE = 0.5
FEINT_EDGE = 0.1
FEINT_DOWN_TICKS = 50
MARK_INSIDE = 0.4
MARK_BLIND = 2.5
CHASE_AFTER = 18

TEAM_KINDS = ("two_v_one", "three_v_two", "through_ball", "cross")


def _lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


@dataclass
class Leg:
    x: float
    z: float
    speed: float


@dataclass
class ManPlan:
    x: float
    z: float
    delay: int
    legs: list[Leg]
    lane: float


@dataclass
class DefPlan:
    x: float
    z: float
    role: str  # press | mark | line
    mark: int
    gap: float
    speed: float
    composure: float
    cover: float
    react_ticks: int


@dataclass
class TeamPlan:
    kind: str
    men: list[ManPlan]
    defs: list[DefPlan]


@dataclass
class TeamSetup(base.EpisodeSetup):
    team: TeamPlan = None


@dataclass
class Man:
    x: float
    z: float
    vx: float = 0
    vz: float = 0
    leg: int = 0
    delay: int = 0
    lane: float = 0
    legs: list[Leg] = field(default_factory=list)


@dataclass
class Def:
    x: float
    z: float
    vx: float = 0
    vz: float = 0
    mode: str = "guard"  # guard | lunge | down
    ticks: int = 0
    dir_x: float = 0
    dir_z: float = 0


@dataclass
class Pass:
    from_x: float
    from_z: float
    to_x: float
    to_z: float
    at: int
    total: int
    high: bool
    arc: float
    contact_y: float
    reach: bool
    claim: bool


@dataclass
class TeamRun:
    men: list[Man]
    defs: list[Def]
    windup: int = 0
    target: int = 0
    mode: int = 0
    power: int = 0
    pass_: Pass | None = None
    passes: int = 0
    touch: int = -1000


def create_team_episode(kind: str, seed: int, rating: int = 75) -> TeamSetup:
    """Mirrors `createTeamEpisode` (draws in the same order)."""
    ep = base.create_episode(seed, rating)
    rnd = mulberry32(seed + 7919)
    side = -1 if rnd() < 0.5 else 1
    slow = 1 - DEF_EDGE * ep.edge

    def make_def(x: float, z: float, role: str, mark: int, gap: float) -> DefPlan:
        speed = _lerp(5.3, 5.9, rnd()) * slow
        composure = _lerp(0.15, 0.9, rnd())
        cover = _lerp(0.15, 0.6, rnd())
        react_ticks = math.floor(_lerp(6, 18, rnd()))
        return DefPlan(x, z, role, mark, gap, speed, composure, cover, react_ticks)

    if kind == "two_v_one":
        start_x = side * _lerp(3, 6, rnd())
        start_z = _lerp(27, 31, rnd())
    elif kind == "three_v_two":
        start_x = _lerp(-2, 2, rnd())
        start_z = _lerp(29, 33, rnd())
    elif kind == "through_ball":
        start_x = _lerp(-6, 6, rnd())
        start_z = _lerp(35, 38, rnd())
    else:
        start_x = side * _lerp(19, 23, rnd())
        start_z = _lerp(23, 27, rnd())

    men: list[ManPlan] = []
    defs: list[DefPlan] = []
    if kind == "two_v_one":
        lane = -side * _lerp(5, 7, rnd())
        men.append(ManPlan(lane, start_z + _lerp(-1, 1, rnd()), 0, [], lane))
        x = _lerp(-1.5, 1.5, rnd())
        z = _lerp(15, 18, rnd())
        defs.append(make_def(x, z, "press", 0, 0))
    elif kind == "three_v_two":
        left = -_lerp(6, 8, rnd())
        right = _lerp(6, 8, rnd())
        men.append(ManPlan(left, start_z + _lerp(-1, 1, rnd()), 0, [], left))
        men.append(ManPlan(right, start_z + _lerp(-1, 1, rnd()), 0, [], right))
        px = side * _lerp(1, 3, rnd())
        pz = _lerp(16, 19, rnd())
        defs.append(make_def(px, pz, "press", 0, 0))
        mx = -side * _lerp(4, 6, rnd())
        mz = _lerp(14, 17, rnd())
        gap = _lerp(1.6, 3, rnd())
        defs.append(make_def(mx, mz, "mark", 0 if side > 0 else 1, gap))
    elif kind == "through_ball":
        line = _lerp(19, 22, rnd())
        start = side * _lerp(11, 14, rnd())
        z = line + _lerp(1.6, 2.2, rnd())
        delay = math.floor(_lerp(40, 100, rnd()))
        cross_x = side * _lerp(3, 5, rnd())
        in_x = -side * _lerp(1, 4, rnd())
        men.append(ManPlan(start, z, delay, [Leg(cross_x, line, 6.6), Leg(in_x, 7, 7.1)], start))
        ax = side * _lerp(7, 9, rnd())
        defs.append(make_def(ax, line, "line", 0, 0))
        bx = -side * _lerp(1, 3, rnd())
        bz = line - _lerp(0, 0.6, rnd())
        defs.append(make_def(bx, bz, "line", 0, 0))
    else:
        near_x = side * _lerp(5, 8, rnd())
        near_z = _lerp(15, 18, rnd())
        far_x = -side * _lerp(1, 4, rnd())
        far_z = _lerp(17, 20, rnd())
        delay = math.floor(_lerp(30, 70, rnd()))
        nx = side * _lerp(1.6, 3, rnd())
        nz = _lerp(6.2, 7.5, rnd())
        fx = -side * _lerp(1.5, 3.4, rnd())
        fz = _lerp(7, 9, rnd())
        men.append(ManPlan(near_x, near_z, delay, [Leg(nx, nz, 6.4)], near_x))
        men.append(ManPlan(far_x, far_z, delay + 10, [Leg(fx, fz, 6.2)], far_x))
        bx = side * _lerp(15, 17, rnd())
        bz = _lerp(13, 16, rnd())
        defs.append(make_def(bx, bz, "press", 0, 0))
        g1 = _lerp(0.4, 1.8, rnd())
        defs.append(make_def(near_x - side * 0.8, near_z - 1, "mark", 0, g1))
        g2 = _lerp(0.4, 1.8, rnd())
        defs.append(make_def(far_x + side * 0.8, far_z - 1, "mark", 1, g2))
    ep.keeper.max_out = KEEPER_DEEP
    return TeamSetup(ep.seed, ep.edge, start_x, start_z, ep.keeper, TeamPlan(kind, men, defs))


def init_team_state(setup: TeamSetup) -> base.State:
    s = base.init_state(setup)
    s.team = TeamRun(
        [Man(m.x, m.z, delay=m.delay, lane=m.lane, legs=m.legs) for m in setup.team.men],
        [Def(d.x, d.z) for d in setup.team.defs],
    )
    return s


def offside_line(r: TeamRun) -> float:
    line = r.defs[0].z
    for d in r.defs:
        line = min(line, d.z)
    return line


def is_offside(s: base.State, target: int) -> bool:
    r = s.team
    m = r.men[target]
    return m.z < offside_line(r) and m.z < base._ball(s)[1]


def _move_to(o, tx: float, tz: float, speed: float) -> None:
    ex = tx - o.x
    ez = tz - o.z
    e = math.sqrt(ex * ex + ez * ez)
    step = speed * TICK
    if e <= step:
        o.vx = 0
        o.vz = 0
        o.x = tx
        o.z = tz
    else:
        o.vx = (ex / e) * speed
        o.vz = (ez / e) * speed
        o.x += o.vx * TICK
        o.z += o.vz * TICK


def _step_men(s: base.State) -> None:
    _, bz = base._ball(s)
    for m in s.team.men:
        if m.delay > 0:
            m.delay -= 1
        elif not m.legs:
            z = max(MATE_MIN_Z, bz + MATE_BEHIND)
            _move_to(m, m.lane * _lerp(LANE_MIN, 1, _clamp(z / LANE_FROM, 0, 1)), z, MATE_SPEED)
        elif m.leg < len(m.legs):
            leg = m.legs[m.leg]
            _move_to(m, leg.x, leg.z, leg.speed)
            if m.x == leg.x and m.z == leg.z:
                m.leg += 1


def _step_defs(setup: TeamSetup, s: base.State) -> None:
    r = s.team
    bx, bz = base._ball(s)
    glen = math.sqrt(bx * bx + bz * bz) or 1
    gx = -bx / glen
    gz = -bz / glen
    for i, d in enumerate(r.defs):
        plan = setup.team.defs[i]
        if d.mode == "down":
            d.vx = 0
            d.vz = 0
            d.ticks -= 1
            if d.ticks <= 0:
                d.mode = "guard"
            continue
        if d.mode == "lunge":
            d.vx = d.dir_x * LUNGE_SPEED
            d.vz = d.dir_z * LUNGE_SPEED
            d.x += d.vx * TICK
            d.z += d.vz * TICK
            d.ticks -= 1
            if r.pass_ is None:
                ex = bx - d.x
                ez = bz - d.z
                if ex * ex + ez * ez < TACKLE_REACH * TACKLE_REACH:
                    return base._end(s, "dispossessed")
            if d.ticks <= 0:
                d.mode = "down"
                d.ticks = DOWN_TICKS
            continue
        if s.tick < plan.react_ticks:
            continue
        beaten = bz < d.z - 1
        if r.pass_ is not None and (r.pass_.high or r.pass_.at < CHASE_AFTER):
            if not r.pass_.high or plan.role != "mark":
                d.vx = 0
                d.vz = 0
                continue
            m = r.men[plan.mark]
            _move_to(d, m.x + (-MARK_INSIDE if m.x > 0 else MARK_INSIDE), m.z - plan.gap, plan.speed)
            continue
        if r.pass_ is not None:
            tx = r.pass_.to_x
            tz = r.pass_.to_z
        elif plan.role == "press" or beaten:
            stand = _lerp(STAND_NEAR, STAND_OFF, _clamp((glen - STAND_TO) / (STAND_FROM - STAND_TO), 0, 1))
            line = setup.team.kind == "cross" and not beaten
            tx = bx if line else bx + gx * stand
            tz = bz - stand if line else bz + gz * stand
            if not beaten and not line:
                near = 0
                best = math.inf
                for j, m in enumerate(r.men):
                    e = (m.x - d.x) * (m.x - d.x) + (m.z - d.z) * (m.z - d.z)
                    if e < best:
                        best = e
                        near = j
                tx += (r.men[near].x - tx) * plan.cover * 0.5
                tz += (r.men[near].z - tz) * plan.cover * 0.5
        elif plan.role == "mark":
            m = r.men[plan.mark]
            tx = m.x + (-MARK_INSIDE if m.x > 0 else MARK_INSIDE)
            tz = m.z - plan.gap
        else:
            tx = plan.x + (bx - plan.x) * 0.25
            tz = plan.z
        _move_to(d, tx, tz, plan.speed)
        if r.pass_ is None and s.feint_ticks == 0:
            ex = bx - d.x
            ez = bz - d.z
            if ex * ex + ez * ez < DEF_LUNGE_DIST * DEF_LUNGE_DIST:
                lx = ex + s.hx * s.speed * LUNGE_LEAD
                lz = ez + s.hz * s.speed * LUNGE_LEAD
                ll = math.sqrt(lx * lx + lz * lz) or 1
                d.mode = "lunge"
                d.ticks = DEF_LUNGE_TICKS
                d.dir_x = lx / ll
                d.dir_z = lz / ll


def _meet_of(m: Man, t: float) -> tuple[float, float]:
    if m.leg < len(m.legs):
        last = m.legs[-1]
        ex = last.x - m.x
        ez = last.z - m.z
        speed = math.sqrt(m.vx * m.vx + m.vz * m.vz)
        if speed * t >= math.sqrt(ex * ex + ez * ez):
            return last.x, last.z
    return m.x + m.vx * t, m.z + m.vz * t


def _release(setup: TeamSetup, s: base.State) -> None:
    r = s.team
    if setup.team.kind != "cross" and is_offside(s, r.target):
        return base._end(s, "offside")
    m = r.men[r.target]
    fx, fz = base._ball(s)
    high = r.mode == PASS_CROSS
    bar = r.power / 100
    pace = (
        _lerp(CROSS_SOFT, CROSS_HARD, bar) if high
        else (CUTBACK_SPEED if r.mode == PASS_CUTBACK else PASS_SPEED) + PASS_EDGE * setup.edge
    )
    t = 0
    to_x = m.x
    to_z = m.z
    for _ in range(MEET_ROUNDS):
        dx = to_x - fx
        dz = to_z - fz
        t = math.sqrt(dx * dx + dz * dz) / pace
        to_x, to_z = _meet_of(m, t)
    if r.mode == PASS_THROUGH:
        gl = math.sqrt(to_x * to_x + to_z * to_z) or 1
        to_x -= (to_x / gl) * THROUGH_LEAD
        to_z -= (to_z / gl) * THROUGH_LEAD
    elif high:
        dx = to_x - fx
        dz = to_z - fz
        d = math.sqrt(dx * dx + dz * dz) or 1
        over = (bar - CROSS_SWEET) * CROSS_SPREAD
        to_x += (dx / d) * over
        to_z += (dz / d) * over
    to_z = max(MEET_MIN_Z, to_z)
    dx = to_x - fx
    dz = to_z - fz
    t = math.sqrt(dx * dx + dz * dz) / pace
    total = max(1, math.floor(t / TICK))
    ex = to_x - m.x
    ez = to_z - m.z
    e = math.sqrt(ex * ex + ez * ez)
    run = max(0, e - base.BALL_LEAD)
    if not high:
        total = max(total, math.floor(run / (RECEIVER_TOP * TICK)) + 1)
    need = run / (total * TICK)
    hx = ex / e if e > 0.1 else s.hx
    hz = ez / e if e > 0.1 else s.hz
    r.men[r.target] = Man(s.x, s.z, s.hx * s.speed, s.hz * s.speed, 0, 0, s.x, [])
    s.x = m.x
    s.z = m.z
    s.hx = hx
    s.hz = hz
    s.speed = min(need, RECEIVER_TOP)
    s.lead = base.BALL_LEAD
    r.pass_ = Pass(
        fx, fz, to_x, to_z, 0, total, high,
        _lerp(CROSS_ARC_LOW, CROSS_ARC_HIGH, bar), _lerp(CONTACT_LOW, CONTACT_HIGH, bar),
        need <= RECEIVER_TOP, high and to_z < KEEPER_ZONE_Z and abs(to_x) < KEEPER_ZONE_X,
    )
    r.passes += 1
    s.free = [fx, fz]
    s.from_y = BALL_RADIUS


def _step_pass(setup: TeamSetup, s: base.State) -> None:
    r = s.team
    p = r.pass_
    free = s.free
    p.at += 1
    dir_x = p.to_x - p.from_x
    dir_z = p.to_z - p.from_z
    if p.at <= p.total:
        k = p.at / p.total
        free[0] = p.from_x + dir_x * k
        free[1] = p.from_z + dir_z * k
        s.from_y = _lerp(BALL_RADIUS, p.contact_y, k) + 4 * p.arc * k * (1 - k) if p.high else BALL_RADIUS
        s.x += s.hx * s.speed * TICK
        s.z += s.hz * s.speed * TICK
    else:
        after = p.at - p.total
        k = 1 + (after * CROSS_AFTER) / p.total
        free[0] = p.from_x + dir_x * k
        free[1] = p.from_z + dir_z * k
        s.from_y = max(BALL_RADIUS, p.contact_y - ((p.contact_y - BALL_RADIUS) * after) / CONTROL_TICKS)
        if p.reach:
            s.x = free[0] - s.hx * base.BALL_LEAD
            s.z = free[1] - s.hz * base.BALL_LEAD
        else:
            s.x += s.hx * s.speed * TICK
            s.z += s.hz * s.speed * TICK
    s.tick += 1
    if p.claim and not base._keeper_down(s):
        ex = p.to_x - s.kx
        ez = p.to_z - s.kz
        e = math.sqrt(ex * ex + ez * ez)
        step = CLAIM_SPEED * TICK
        s.k_mode = "rush"
        if e > step:
            s.kx += (ex / e) * step
            s.kz += (ez / e) * step
    else:
        base._keeper_step(setup, s)
    if not p.high and not base._keeper_down(s):
        tx = (p.to_x * s.kz) / max(1, p.to_z)
        step = KEEPER_SHUFFLE * TICK
        s.kx += _clamp(tx - s.kx, -step, step)
    _step_men(s)
    _step_defs(setup, s)
    if s.ended:
        return

    if not p.high or s.from_y < LOW_BALL:
        left = (p.total - p.at) * TICK * math.sqrt(dir_x * dir_x + dir_z * dir_z) / (p.total * TICK)
        for i, d in enumerate(r.defs):
            if d.mode == "down" or (setup.team.defs[i].role == "mark" and left < MARK_BLIND):
                continue
            ex = free[0] - d.x
            ez = free[1] - d.z
            if ex * ex + ez * ez < INTERCEPT_RADIUS * INTERCEPT_RADIUS:
                return base._end(s, "intercepted")
    if not p.high:
        if not base._keeper_down(s):
            ex = free[0] - s.kx
            ez = free[1] - s.kz
            if ex * ex + ez * ez < base.SMOTHER_RADIUS * base.SMOTHER_RADIUS:
                return base._end(s, "tackle")
        if p.at >= p.total:
            r.pass_ = None
            r.touch = s.tick
            s.free = None
            s.from_y = BALL_RADIUS
            return
    elif p.at == p.total:
        r.touch = s.tick
        if not base._keeper_down(s):
            ex = free[0] - s.kx
            ez = free[1] - s.kz
            if ex * ex + ez * ez < CLAIM_RADIUS * CLAIM_RADIUS:
                ax = free[0] - s.x
                az = free[1] - s.z
                return base._end(s, "cleared" if ax * ax + az * az < CLAIM_PRESSED * CLAIM_PRESSED else "tackle")
        for d in r.defs:
            if d.mode == "down":
                continue
            ex = free[0] - d.x
            ez = free[1] - d.z
            if ex * ex + ez * ez < CONTEST_RADIUS * CONTEST_RADIUS:
                return base._end(s, "cleared")
    elif p.reach and p.at >= p.total + CONTROL_TICKS:
        r.pass_ = None
        r.touch = s.tick
        s.free = None
        s.from_y = BALL_RADIUS
        s.speed = min(s.speed, RUN_AFTER_CONTROL)
        return
    elif p.at >= p.total + CROSS_LATE:
        return base._end(s, "cleared")
    if s.tick >= base.MAX_RUN_TICKS:
        return base._end(s, "lost")


def _strike_ready(s: base.State) -> bool:
    r = s.team
    if s.feint_ticks > 0 or r.windup > 0:
        return False
    return r.pass_ is None or (r.pass_.high and r.pass_.reach and r.pass_.at >= r.pass_.total)


def _strike(setup: TeamSetup, s: base.State, shot: Swipe) -> None:
    r = s.team
    s.blockers = [(d.x, d.z) for d in r.defs if d.mode == "guard"]
    if s.tick - r.touch <= FIRST_TIME_TICKS:
        y = s.from_y if s.from_y is not None else 0
        off = HEADER_SCATTER if y > base.VOLLEY_Y else VOLLEY_SCATTER if y > VOLLEY_FROM else FIRST_TIME_SCATTER
        s.scatter = (mulberry32(setup.seed + s.tick)() - 0.5) * 2 * off * (1 - SCATTER_EDGE * setup.edge)
    flight = base.shoot(setup, s, shot)
    chip = (
        flight.outcome == "goal" and flight.over_y is not None and flight.over_y >= base.CHIP_HEIGHT
        and flight.keeper_z >= base.CHIP_KEEPER_OUT
    )
    base._end(s, flight.outcome, flight, chip)


def team_advance(
    setup: TeamSetup, s: base.State, hold: int, steer: int, feint: int, shot: Swipe | None,
    order: tuple[int, int, int] | None,
) -> None:
    """Mirrors `teamAdvance`: the feint, the pass asked for, the shot if it
    can be struck, else the ball's flight or the run."""
    if s.ended:
        return
    r = s.team
    if feint != 0 and not s.feint_used and r.pass_ is None and r.windup == 0:
        base._start_feint(setup, s, 1 if feint > 0 else -1)
        bx, bz = base._ball(s)
        for i, d in enumerate(r.defs):
            ex = bx - d.x
            ez = bz - d.z
            if (
                d.mode == "guard" and ex * ex + ez * ez < FEINT_REACH * FEINT_REACH
                and setup.team.defs[i].composure < FEINT_BITE + FEINT_EDGE * setup.edge
            ):
                d.mode = "down"
                d.ticks = FEINT_DOWN_TICKS
    if (
        order is not None and 0 <= order[0] < len(r.men) and r.pass_ is None and r.windup == 0
        and r.passes < MAX_PASSES and s.feint_ticks == 0
    ):
        r.windup = PASS_WINDUP
        r.target, r.mode, r.power = order
    if shot is not None and _strike_ready(s):
        return _strike(setup, s, shot)
    if r.pass_ is not None:
        return _step_pass(setup, s)
    base._step_run(setup, s, hold, steer)
    if s.ended:
        return
    _step_men(s)
    _step_defs(setup, s)
    if s.ended:
        return
    if r.windup > 0:
        r.windup -= 1
        if r.windup == 0:
            _release(setup, s)


@dataclass
class TeamTimeline(base.Timeline):
    """The base timeline and the passes: (tick, (teammate, mode, power))."""

    passes: list[tuple[int, tuple[int, int, int]]] = field(default_factory=list)


def replay_team(setup: TeamSetup, tl: TeamTimeline) -> base.EpisodeEnd:
    s = init_team_state(setup)
    passes = dict(tl.passes)
    ci = 0
    hold = 0
    steer = 0
    while s.ended is None:
        i = s.tick
        while ci < len(tl.controls) and tl.controls[ci][0] <= i:
            hold = tl.controls[ci][1]
            steer = tl.controls[ci][2]
            ci += 1
        feint = tl.feint[1] if tl.feint is not None and tl.feint[0] == i else 0
        shot = tl.shot[1] if tl.shot is not None and tl.shot[0] <= i else None
        team_advance(setup, s, hold, steer, feint, shot, passes.get(i))
    return s.ended
