/**
 * «Атака 1 на 1»: the whole episode — a run with the ball at the keeper, at
 * most one feint, a shot — as a pure, deterministic function of
 * `seed + rating + input timeline`. The scene steps it live from the
 * player's finger and replays the result; the server replays the same
 * timeline with its bit-exact Python port
 * (backend/app/services/one_on_one_engine.py) and alone decides the outcome.
 * A shared fixture (engine.fixture.test.ts) keeps the two in lockstep.
 *
 * Determinism contract — the same as freeKick3d/trajectory.ts, whose kick
 * (`swipeToKick`), forces and collision helpers the shot reuses:
 * - inputs are integers (ticks, a steer in thousandths, the quantized swipe);
 * - only + − × ÷, Math.sqrt, Math.min/max/abs/floor and mulberry32;
 * - a fixed 60 Hz tick for the run, the free kick's 240 Hz for the flight,
 *   fixed iteration order.
 *
 * Kept apart from the mini-game on purpose: «Карьера игрока» key moments can
 * play the same episode later.
 *
 * World: as the free kick — metres, y up, goal line z = 0, the goal centred
 * on x = 0, the attacker runs towards −z.
 */
import {
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
  accel,
  hitFrame,
  hitSphere,
  hitVerticalCapsule,
  mulberry32,
  ratingEdge,
  reflect,
  swipeToKick,
  type KickParams,
  type QuantizedSwipe,
  type ShotSetup,
  type Vec3,
} from "@/lib/freeKick3d/trajectory";

import type { PassOrder, TeamRun } from "./team";

// ---------------------------------------------------------------------------
// Constants (engine tuning — the economy lives in GameConfig).
// ---------------------------------------------------------------------------

/** One step of the run (s). */
export const TICK = 1 / 60;
/** The run can't last longer than this (ticks): then the chance is gone. */
export const MAX_RUN_TICKS = 600;
/** The ball runs this far ahead of the attacker's feet (m). */
export const BALL_LEAD = 0.55;

const RUN_SPEED = 5.4;
/** A full edge (rating 95) runs this much faster (m/s). */
const EDGE_RUN = 0.5;
const RUN_ACCEL = 7.5;
const RUN_BRAKE = 8;
/** Full steer points the run this far sideways per metre forwards. */
const STEER_SPREAD = 1.3;
/** Share of the way to the wanted heading turned each tick. */
const TURN_K = 0.16;
/** Heading further than this the wrong way along z, he turns via the side. */
const TURN_ROUND = 0.3;
/** The sprint (stick pushed to the rim): this much faster, turning this
 * much wider, the ball pushed this far ahead (easier for the keeper to
 * smother); the ball's distance from the foot follows by LEAD_K a tick. */
const SPRINT_PACE = 1.2;
const SPRINT_TURN_K = 0.08;
const SPRINT_LEAD = 0.95;
const LEAD_K = 0.08;

/** The feint: a sidestep this long (ticks) at this lateral speed (m/s). */
export const FEINT_TICKS = 18;
export const FEINT_SIDE_SPEED = 4.2;
/** The keeper bites best at this distance from the ball (m), not at all
 * FEINT_SPAN either side of it. */
const FEINT_SWEET = 4.5;
const FEINT_SPAN = 3.2;
const FEINT_BASE = 0.95;
const EDGE_FEINT = 0.08;
/** Biting: he lunges this far the wrong way over LUNGE_TICKS, then lies
 * on the grass for his seeded `fallTicks`. */
export const LUNGE = 1.2;
export const LUNGE_TICKS = 10;

export const KEEPER_START_Z = 0.6;
/** He never comes further out than this (m from the line). */
const KEEPER_MAX_OUT = 8;
/** Within this of the ball (keeper on his feet) he smothers it (m). */
export const SMOTHER_RADIUS = 0.85;
/** Sideways reach of his hands from where he stands, in a shot (m). */
export const DIVE_REACH = 2.6;
export const KEEPER_HANDS_Y = 1.1;
/** How far his hands can move from his body sideways before he moves too. */
const KEEPER_BODY_FOLLOW = 1.4;
/** A keeper on the grass is a low capsule along x. */
export const FALLEN_Y = 0.25;
export const FALLEN_HALF = 0.85;
const FALLEN_RADIUS = 0.28;
/** Back on his feet: this long before he can go for a shot (s). */
const GET_UP = 0.15;
/** A keeper sprinting out reacts later to a shot (s) and can't leap: his
 * hands go no higher than RUSH_HAND_Y — a chip goes over him. */
const RUSH_REACTION = 0.04;
const RUSH_HAND_Y = 2.0;
/** Close to the ball (m) he spreads himself — «звёздочка»: a low capsule
 * SPREAD_HALF either side of him blocks shots near his feet. */
const SPREAD_DIST = 7;
export const SPREAD_HALF = 1;
export const SPREAD_Y = 0.3;
const SPREAD_RADIUS = 0.3;

const MAX_FLIGHT = 3;
const SHOT_MIN_SPEED = 11;
const SHOT_LIFT_SCALE = 1.2;
const SHOT_CHIP_LOFT = 0.6;
/** Aim scale = AIM_REF / distance (1..3): a full lean is ~5 m off the
 * centre of the goal from any distance. */
export const AIM_REF = 18;
/** A goal over a keeper who came out at least CHIP_KEEPER_OUT m: «парашют». */
const CHIP_HEIGHT = 1.8;
const CHIP_KEEPER_OUT = 2;
/** Struck from above this (m) it is a header, and no faster than this
 * (m/s); under HEADER_Y he throws himself at it, and it goes harder. */
export const VOLLEY_Y = 0.95;
export const HEADER_Y = 1.4;
const HEADER_SPEED = 11;
const DIVING_HEADER_SPEED = 14;
/** A man in the way of a shot: a capsule this wide and this tall (m). */
const BLOCK_RADIUS = 0.34;
const BLOCK_HEIGHT = 1.85;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type EpisodeKeeper = {
  /** Ticks before he leaves his line. */
  reactTicks: number;
  /** Distance he keeps from the ball while closing the angle (m). */
  keepGap: number;
  /** Closer than this he rushes at the ball (m). */
  rushDist: number;
  setSpeed: number;
  rushSpeed: number;
  /** A feint beats him when its chance is above this. */
  composure: number;
  /** Ticks he lies on the grass after biting. */
  fallTicks: number;
  /** His reaction to a shot (s). */
  shotReact: number;
  /** How fast his hands travel in a dive (m/s). */
  diveSpeed: number;
  /** He comes no further out than this (m; default KEEPER_MAX_OUT). */
  maxOut?: number;
};

export type EpisodeSetup = {
  seed: number;
  /** The attacker card's edge in [−1, 1] (see `ratingEdge`). */
  edge: number;
  start: { x: number; z: number };
  keeper: EpisodeKeeper;
};

export type KeeperMode = "wait" | "set" | "rush" | "lunge" | "fallen";
export type FeintResult = "bit" | "read";
/** dispossessed, intercepted, offside, cleared and blocked: the team
 * episodes' (team.ts). */
export type EpisodeOutcome =
  | "goal" | "save" | "tackle" | "miss" | "lost"
  | "dispossessed" | "intercepted" | "offside" | "cleared" | "blocked";

export type EpisodeState = {
  /** Ticks stepped so far. */
  tick: number;
  x: number;
  z: number;
  /** Heading (unit, xz). */
  hx: number;
  hz: number;
  speed: number;
  /** How far ahead of his feet the ball is (m). */
  lead: number;
  feintTicks: number;
  feintDir: number;
  feintUsed: boolean;
  feint: FeintResult | null;
  kx: number;
  kz: number;
  kMode: KeeperMode;
  /** Lunge or lying ticks left. */
  kTicks: number;
  lungeDir: number;
  ended: EpisodeEnd | null;
  /** The ball off his feet: a pass on its way (team.ts) — at this height. */
  free?: { x: number; z: number } | null;
  fromY?: number;
  /** Men in the way of a shot (m; team.ts). */
  blockers?: { x: number; z: number }[];
  /** A shot struck first time goes this far off line (team.ts; a share of
   * its pace across). */
  scatter?: number;
  /** The team episodes' own state (team.ts). */
  team?: TeamRun;
};

/** One tick's input: the finger held (run) and its steer in thousandths
 * (−1000 left … 1000 right); a feint (−1 / 1) on the tick it's made; the
 * shot once released (it waits for a feint in progress to finish). */
/** hold: 0 — stop, 1 — run with the ball, 2 — sprint, 3 — back, away from the goal. */
/** `pass` (team.ts): the pass on the tick it's played. */
export type TickInput = { hold: number; steer: number; feint: number; shot: QuantizedSwipe | null; pass?: PassOrder | null };

export type FlightSample = {
  t: number;
  ball: Vec3;
  handX: number;
  handY: number;
  bodyX: number;
  lying: boolean;
};

export type FlightEvent = { t: number; type: "post" | "bounce" | "save" | "goal" | "miss" | "wall" };

export type ShotFlight = {
  outcome: "goal" | "save" | "miss" | "blocked";
  kick: KickParams;
  from: { x: number; z: number };
  keeper: { x: number; z: number; lyingFor: number; reaction: number; spread: boolean };
  /** Height of the ball as it passed the keeper (null if it never did). */
  overY: number | null;
  samples: FlightSample[];
  events: FlightEvent[];
  end: { t: number; position: Vec3; velocity: Vec3 };
};

export type EpisodeEnd = {
  outcome: EpisodeOutcome;
  /** The tick the episode ended on (the shot's, for a shot). */
  tick: number;
  feint: FeintResult | null;
  /** A goal over a keeper who came out. */
  chip: boolean;
  flight: ShotFlight | null;
};

/** What the server receives: control changes `[tick, hold 0/1/2, steer]`
 * (ascending ticks), the feint and the shot with the tick they were made. */
export type EpisodeTimeline = {
  controls: [number, number, number][];
  feint: { tick: number; dir: number } | null;
  shot: ({ tick: number } & QuantizedSwipe) | null;
  /** The team episodes' passes (team.ts). */
  passes?: ({ tick: number } & PassOrder)[];
};

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

/** The attacker's start and the keeper's temperament for a seed. Draws in
 * a fixed order. */
export function createEpisode(seed: number, rating = 75): EpisodeSetup {
  const rnd = mulberry32(seed);
  const edge = ratingEdge(rating);
  const z = lerp(21, 26, rnd());
  const x = lerp(-6, 6, rnd());
  const slow = 1 - EDGE_KEEPER * edge;
  const keeper: EpisodeKeeper = {
    reactTicks: Math.floor(lerp(14, 26, rnd())),
    keepGap: lerp(4.5, 5.5, rnd()),
    rushDist: lerp(5, 6.5, rnd()),
    setSpeed: lerp(3.2, 3.9, rnd()) * slow,
    rushSpeed: lerp(4, 4.7, rnd()) * slow,
    composure: lerp(0.2, 1, rnd()),
    fallTicks: Math.floor(lerp(57, 86, rnd())),
    shotReact: lerp(0.06, 0.12, rnd()),
    diveSpeed: lerp(6, 7.5, rnd()) * slow,
  };
  return { seed, edge, start: { x, z }, keeper };
}

export function initState(setup: EpisodeSetup): EpisodeState {
  // Facing the goal centre.
  const len = Math.sqrt(setup.start.x * setup.start.x + setup.start.z * setup.start.z);
  return {
    tick: 0,
    x: setup.start.x,
    z: setup.start.z,
    hx: -setup.start.x / len,
    hz: -setup.start.z / len,
    speed: 0,
    lead: BALL_LEAD,
    feintTicks: 0,
    feintDir: 0,
    feintUsed: false,
    feint: null,
    kx: 0,
    kz: KEEPER_START_Z,
    kMode: "wait",
    kTicks: 0,
    lungeDir: 0,
    ended: null,
  };
}

export function ballOf(s: EpisodeState): { x: number; z: number } {
  if (s.free) return s.free;
  return { x: s.x + s.hx * s.lead, z: s.z + s.hz * s.lead };
}

export function keeperDown(s: EpisodeState): boolean {
  return s.kMode === "lunge" || s.kMode === "fallen";
}

// ---------------------------------------------------------------------------
// The run
// ---------------------------------------------------------------------------

/** The sidestep starts; the keeper bites (lunges the wrong way and goes
 * down) when its chance — best at FEINT_SWEET metres from him — beats his
 * composure. */
export function startFeint(setup: EpisodeSetup, s: EpisodeState, dir: number) {
  s.feintUsed = true;
  s.feintTicks = FEINT_TICKS;
  s.feintDir = dir;
  const b = ballOf(s);
  const dx = b.x - s.kx;
  const dz = b.z - s.kz;
  const d = Math.sqrt(dx * dx + dz * dz);
  const chance = clamp(1 - Math.abs(d - FEINT_SWEET) / FEINT_SPAN, 0, 1) * FEINT_BASE + EDGE_FEINT * setup.edge;
  if (!keeperDown(s) && chance > setup.keeper.composure) {
    s.feint = "bit";
    s.kMode = "lunge";
    s.kTicks = LUNGE_TICKS;
    s.lungeDir = -dir;
  } else {
    s.feint = "read";
  }
}

/** The keeper over one tick: waits, closes the angle, rushes the ball — or
 * lunges and lies there after biting on a feint. */
export function keeperStep(setup: EpisodeSetup, s: EpisodeState) {
  const k = setup.keeper;
  if (s.kMode === "lunge") {
    s.kx += s.lungeDir * (LUNGE / LUNGE_TICKS);
    s.kTicks -= 1;
    if (s.kTicks <= 0) {
      s.kMode = "fallen";
      s.kTicks = k.fallTicks;
    }
    return;
  }
  if (s.kMode === "fallen") {
    s.kTicks -= 1;
    if (s.kTicks <= 0) s.kMode = "set";
    return;
  }
  if (s.tick < k.reactTicks) return;
  const b = ballOf(s);
  const dx = b.x - s.kx;
  const dz = b.z - s.kz;
  const d = Math.sqrt(dx * dx + dz * dz);
  let tx: number;
  let tz: number;
  let speed: number;
  if (d < k.rushDist) {
    tx = b.x;
    tz = b.z;
    speed = k.rushSpeed;
    s.kMode = "rush";
  } else {
    // On the line goal centre → ball, keepGap short of it.
    const gl = Math.max(0.5, Math.sqrt(b.x * b.x + b.z * b.z));
    const out = clamp(gl - k.keepGap, KEEPER_START_Z, k.maxOut ?? KEEPER_MAX_OUT);
    tx = (b.x / gl) * out;
    tz = (b.z / gl) * out;
    speed = k.setSpeed;
    s.kMode = "set";
  }
  const ex = tx - s.kx;
  const ez = tz - s.kz;
  const e = Math.sqrt(ex * ex + ez * ez);
  const step = speed * TICK;
  if (e <= step) {
    s.kx = tx;
    s.kz = tz;
  } else {
    s.kx += (ex / e) * step;
    s.kz += (ez / e) * step;
  }
}

export function end(s: EpisodeState, outcome: EpisodeOutcome, flight: ShotFlight | null = null, chip = false) {
  s.ended = { outcome, tick: s.tick, feint: s.feint, chip, flight };
}

export function stepRun(setup: EpisodeSetup, s: EpisodeState, input: TickInput) {
  const steer = clamp(input.steer, -1000, 1000) / 1000;
  const sx = steer * STEER_SPREAD;
  const dl = Math.sqrt(sx * sx + 1);
  const back = input.hold === 3;
  let wantX = sx / dl;
  let wantZ = (back ? 1 : -1) / dl;
  // Turning right round he goes through the side, not on the spot.
  if (back ? s.hz < -TURN_ROUND : s.hz > TURN_ROUND) {
    wantX = sx > 0 || (sx === 0 && s.hx >= 0) ? 1 : -1;
    wantZ = 0;
  }
  const sprint = input.hold === 2;
  const turnK = sprint ? SPRINT_TURN_K : TURN_K;
  const hx = s.hx + (wantX - s.hx) * turnK;
  const hz = s.hz + (wantZ - s.hz) * turnK;
  const hl = Math.sqrt(hx * hx + hz * hz) || 1;
  s.hx = hx / hl;
  s.hz = hz / hl;

  const top = sprint ? (RUN_SPEED + EDGE_RUN * setup.edge) * SPRINT_PACE : RUN_SPEED + EDGE_RUN * setup.edge;
  if (!input.hold) s.speed = Math.max(0, s.speed - RUN_BRAKE * TICK);
  else if (s.speed > top) s.speed = Math.max(top, s.speed - RUN_BRAKE * TICK);
  else s.speed = Math.min(top, s.speed + RUN_ACCEL * TICK);
  s.lead += ((sprint ? SPRINT_LEAD : BALL_LEAD) - s.lead) * LEAD_K;
  let vx = s.hx * s.speed;
  let vz = s.hz * s.speed;
  if (s.feintTicks > 0) {
    // The sidestep, to the heading's right (dir 1) or left (−1).
    s.feintTicks -= 1;
    vx += -s.hz * s.feintDir * FEINT_SIDE_SPEED;
    vz += s.hx * s.feintDir * FEINT_SIDE_SPEED;
  }
  s.x += vx * TICK;
  s.z += vz * TICK;
  s.tick += 1;

  keeperStep(setup, s);

  const b = ballOf(s);
  if (!keeperDown(s)) {
    const dx = b.x - s.kx;
    const dz = b.z - s.kz;
    if (dx * dx + dz * dz < SMOTHER_RADIUS * SMOTHER_RADIUS) return end(s, "tackle");
  }
  if (b.z <= 0) return end(s, Math.abs(b.x) < GOAL_HALF_WIDTH - POST_RADIUS - BALL_RADIUS ? "goal" : "lost");
  if (Math.abs(s.x) > 30 || s.z > 40 || s.tick >= MAX_RUN_TICKS) return end(s, "lost");
}

/** One tick of the episode (nothing once it has ended). The order is the
 * contract: the feint, then the shot (unless a feint is under way), else
 * the run. */
export function advance(setup: EpisodeSetup, s: EpisodeState, input: TickInput): void {
  if (s.ended) return;
  if (input.feint !== 0 && !s.feintUsed) startFeint(setup, s, input.feint > 0 ? 1 : -1);
  if (input.shot && s.feintTicks === 0) {
    const flight = shoot(setup, s, input.shot);
    return end(s, flight.outcome, flight, isChip(flight));
  }
  stepRun(setup, s, input);
}

export function isChip(f: ShotFlight): boolean {
  return f.outcome === "goal" && f.overY !== null && f.overY >= CHIP_HEIGHT && f.keeper.z >= CHIP_KEEPER_OUT;
}

/** The server's replay: the timeline's inputs tick by tick until it ends. */
export function replayEpisode(setup: EpisodeSetup, tl: EpisodeTimeline): EpisodeEnd {
  const s = initState(setup);
  let ci = 0;
  let hold = 0;
  let steer = 0;
  while (!s.ended) {
    const i = s.tick;
    while (ci < tl.controls.length && tl.controls[ci][0] <= i) {
      hold = tl.controls[ci][1];
      steer = tl.controls[ci][2];
      ci += 1;
    }
    advance(setup, s, {
      hold,
      steer,
      feint: tl.feint && tl.feint.tick === i ? tl.feint.dir : 0,
      shot: tl.shot && tl.shot.tick <= i ? tl.shot : null,
    });
  }
  return s.ended;
}

// ---------------------------------------------------------------------------
// The shot: the free kick's swipe → kick and ball physics, against a keeper
// standing wherever the run left him (or lying there).
// ---------------------------------------------------------------------------

/** A ball lying on the grass against a capsule along x. */
function hitLying(p: Vec3, x0: number, x1: number, y: number, z: number, r: number): Vec3 | null {
  const cx = clamp(p.x, x0, x1);
  const nx = p.x - cx;
  const ny = p.y - y;
  const nz = p.z - z;
  const d2 = nx * nx + ny * ny + nz * nz;
  const rr = r + BALL_RADIUS;
  if (d2 >= rr * rr) return null;
  const d = Math.sqrt(d2) || 1;
  return { x: nx / d, y: ny / d, z: nz / d };
}

export function shoot(setup: EpisodeSetup, s: EpisodeState, q: QuantizedSwipe, sampleEvery = 2): ShotFlight {
  const from = ballOf(s);
  const fromY = s.fromY ?? BALL_RADIUS;
  const blockers = s.blockers ?? [];
  const dist = Math.sqrt(from.x * from.x + from.z * from.z);
  const kickSetup: ShotSetup = {
    seed: setup.seed,
    edge: setup.edge,
    ball: { x: from.x, y: fromY, z: from.z },
    wall: [],
    wallJumpAt: 99,
    minSpeed: SHOT_MIN_SPEED,
    liftScale: SHOT_LIFT_SCALE,
    aimScale: clamp(AIM_REF / dist, 1, 3),
    chipLoft: SHOT_CHIP_LOFT,
    keeper: { x: 0, reaction: 0, speed: 0, guess: null, readsDrop: true, reach: 0 },
  };
  const kick = swipeToKick(kickSetup, q);
  if (fromY > VOLLEY_Y) {
    // Off the head: placed, not hit.
    const u = kick.velocity;
    const pace = Math.sqrt(u.x * u.x + u.y * u.y + u.z * u.z);
    const top = (s.fromY as number) > HEADER_Y ? HEADER_SPEED : DIVING_HEADER_SPEED;
    if (pace > top) kick.velocity = { x: (u.x / pace) * top, y: (u.y / pace) * top, z: (u.z / pace) * top };
  }
  if (s.scatter) kick.velocity = { ...kick.velocity, x: kick.velocity.x + kick.velocity.z * s.scatter };

  const kx = s.kx;
  const kz = s.kz;
  const lyingFor = s.kMode === "lunge" ? (s.kTicks + setup.keeper.fallTicks) * TICK : s.kMode === "fallen" ? s.kTicks * TICK : 0;
  const reaction = lyingFor > 0 ? lyingFor + GET_UP : setup.keeper.shotReact + (s.kMode === "rush" ? RUSH_REACTION : 0);
  const maxHandY = s.kMode === "rush" ? RUSH_HAND_Y : KEEPER_MAX_HAND_Y;
  const kdx = from.x - kx;
  const kdz = from.z - kz;
  const spread = lyingFor === 0 && kdx * kdx + kdz * kdz < SPREAD_DIST * SPREAD_DIST;

  let p: Vec3 = { x: from.x, y: fromY, z: from.z };
  let v: Vec3 = { ...kick.velocity };
  const spin: Vec3 = { ...kick.spin };
  let handX = kx;
  let handY = KEEPER_HANDS_Y;
  let targetX = kx;
  let targetY = KEEPER_HANDS_Y;
  let decided = false;
  const bodyX = () => clamp(handX, kx - KEEPER_BODY_FOLLOW, kx + KEEPER_BODY_FOLLOW);

  const samples: FlightSample[] = [];
  const events: FlightEvent[] = [];
  const record = (t: number) =>
    samples.push({ t, ball: { ...p }, handX, handY, bodyX: bodyX(), lying: t < lyingFor });

  let outcome: ShotFlight["outcome"] = "miss";
  let overY: number | null = null;
  let decidedAt = -1;
  let step = 0;
  record(0);
  const maxSteps = Math.round(MAX_FLIGHT / SIM_DT);
  while (step < maxSteps) {
    step += 1;
    const t = step * SIM_DT;
    const prevZ = p.z;

    const a = accel(v, spin);
    v = { x: v.x + a.x * SIM_DT, y: v.y + a.y * SIM_DT, z: v.z + a.z * SIM_DT };
    p = { x: p.x + v.x * SIM_DT, y: p.y + v.y * SIM_DT, z: p.z + v.z * SIM_DT };
    const decay = 1 - SPIN_DECAY_PER_S * SIM_DT;
    spin.x *= decay;
    spin.y *= decay;
    spin.z *= decay;

    if (!decided && t >= reaction) {
      // He reads the ball where it crosses his line (with the drop).
      decided = true;
      if (v.z < -0.1 && p.z > kz) {
        const tt = (kz - p.z) / v.z;
        targetX = clamp(p.x + v.x * tt, kx - DIVE_REACH, kx + DIVE_REACH);
        targetY = clamp(p.y + v.y * tt - 0.5 * GRAVITY * tt * tt, 0.25, maxHandY);
      }
    }
    if (decided) {
      const ex = targetX - handX;
      const ey = targetY - handY;
      const d = Math.sqrt(ex * ex + ey * ey);
      const hs = setup.keeper.diveSpeed * SIM_DT;
      if (d <= hs) {
        handX = targetX;
        handY = targetY;
      } else {
        handX += (ex / d) * hs;
        handY += (ey / d) * hs;
      }
    }

    if (p.y < BALL_RADIUS) {
      p.y = BALL_RADIUS;
      if (v.y < -0.5) {
        events.push({ t, type: "bounce" });
        v = { x: v.x * GROUND_FRICTION, y: -v.y * GROUND_RESTITUTION, z: v.z * GROUND_FRICTION };
        // Off the grass it comes up somewhere else: he reads it again.
        decided = false;
      } else {
        const roll = 1 - ROLL_DECAY_PER_S * SIM_DT;
        v = { x: v.x * roll, y: 0, z: v.z * roll };
      }
    }

    if (overY === null && prevZ > kz && p.z <= kz) overY = p.y;

    let blockNormal: Vec3 | null = null;
    for (const b of blockers) {
      blockNormal = hitVerticalCapsule(p, b.x, b.z, BLOCK_RADIUS, BLOCK_HEIGHT - BLOCK_RADIUS, BLOCK_RADIUS);
      if (blockNormal) break;
    }
    if (blockNormal) {
      v = reflect(v, blockNormal, 0.35);
      outcome = "blocked";
      events.push({ t, type: "wall" });
      decidedAt = t;
      break;
    }

    const keeperNormal =
      t < lyingFor
        ? hitLying(p, kx - FALLEN_HALF, kx + FALLEN_HALF, FALLEN_Y, kz, FALLEN_RADIUS)
        : (hitSphere(p, handX, handY, kz, KEEPER_HAND_RADIUS) ??
          hitVerticalCapsule(
            p, bodyX(), kz, KEEPER_BODY_RADIUS, Math.max(KEEPER_BODY_RADIUS, Math.min(handY, 1.6)), KEEPER_BODY_RADIUS,
          ) ??
          (spread ? hitLying(p, kx - SPREAD_HALF, kx + SPREAD_HALF, SPREAD_Y, kz, SPREAD_RADIUS) : null));
    if (keeperNormal) {
      v = reflect(v, keeperNormal, 0.3);
      outcome = "save";
      events.push({ t, type: "save" });
      decidedAt = t;
      break;
    }

    const frame = hitFrame(p);
    if (frame) {
      p = { x: p.x + frame.normal.x * frame.push, y: p.y + frame.normal.y * frame.push, z: p.z + frame.normal.z * frame.push };
      const before = v;
      v = reflect(v, frame.normal, POST_RESTITUTION);
      if (before !== v) events.push({ t, type: "post" });
    }

    if (prevZ > -BALL_RADIUS && p.z <= -BALL_RADIUS) {
      const inside = Math.abs(p.x) < GOAL_HALF_WIDTH - POST_RADIUS && p.y < GOAL_HEIGHT - POST_RADIUS;
      outcome = inside ? "goal" : "miss";
      events.push({ t, type: inside ? "goal" : "miss" });
      decidedAt = t;
      break;
    }

    const speed2 = v.x * v.x + v.y * v.y + v.z * v.z;
    if (Math.abs(p.x) > 40 || p.z > from.z + 5 || (p.y <= BALL_RADIUS && speed2 < 1)) {
      outcome = "miss";
      events.push({ t, type: "miss" });
      decidedAt = t;
      break;
    }

    if (step % sampleEvery === 0) record(t);
  }
  if (decidedAt < 0) {
    decidedAt = step * SIM_DT;
    events.push({ t: decidedAt, type: "miss" });
  }
  if (samples[samples.length - 1].t !== decidedAt) record(decidedAt);

  return {
    outcome,
    kick,
    from,
    keeper: { x: kx, z: kz, lyingFor, reaction, spread },
    overY,
    samples,
    events,
    end: { t: decidedAt, position: { ...p }, velocity: { ...v } },
  };
}

/** Interpolated flight sample at time t (for rendering). */
export function flightAt(f: ShotFlight, t: number): FlightSample {
  const s = f.samples;
  if (t <= s[0].t) return s[0];
  const last = s[s.length - 1];
  if (t >= last.t) return last;
  let lo = 0;
  let hi = s.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (s[mid].t <= t) lo = mid;
    else hi = mid;
  }
  const a = s[lo];
  const b = s[hi];
  const k = (t - a.t) / (b.t - a.t);
  return {
    t,
    ball: { x: lerp(a.ball.x, b.ball.x, k), y: lerp(a.ball.y, b.ball.y, k), z: lerp(a.ball.z, b.ball.z, k) },
    handX: lerp(a.handX, b.handX, k),
    handY: lerp(a.handY, b.handY, k),
    bodyX: lerp(a.bodyX, b.bodyX, k),
    lying: a.lying,
  };
}
