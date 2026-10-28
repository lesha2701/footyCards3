/**
 * «Живой штрафной» (3D prototype): the whole shot as a pure, deterministic
 * function — `seed + swipe → trajectory + outcome`. The scene only replays
 * the samples; nothing in here touches three.js, Rapier, Date or Math.random.
 *
 * Determinism contract (so the backend can replay a shot for anti-cheat):
 * - the swipe is quantized to integers first (`quantizeSwipe`), the server
 *   receives exactly those integers;
 * - the simulation only uses + − × ÷, Math.sqrt, Math.min/max/abs/round and
 *   a 32-bit PRNG (mulberry32 via Math.imul) — all IEEE-754 exact, so a
 *   Python port with the same operation order (floats are doubles there
 *   too, `imul` is `(a * b) & 0xFFFFFFFF`) reproduces the result bit for
 *   bit. No sin/cos/atan/exp: those may differ by an ulp between engines;
 * - fixed time step, fixed iteration order, no early exits that depend on
 *   anything but the state.
 *
 * World: metres, y up, the goal line is z = 0, the goal is centred on x = 0
 * and the ball is kicked towards −z.
 */

export type Vec3 = { x: number; y: number; z: number };

export type ShotOutcome = "goal" | "save" | "miss" | "wall";

/** Raw swipe as the UI measures it, normalized by the viewport height:
 * dx > 0 is to the right, dy < 0 is upwards (screen coordinates). `curve`
 * is the path's largest signed deviation from its chord divided by the
 * chord length (> 0 = the path bows to the right). */
export type SwipeInput = { dx: number; dy: number; curve: number; durationMs: number };

/** What the server would receive: the swipe in integer thousandths. */
export type QuantizedSwipe = { dx: number; dy: number; curve: number; durationMs: number };

export type WallPlayer = { x: number; z: number };

export type ShotSetup = {
  seed: number;
  ball: Vec3;
  wall: WallPlayer[];
  /** Time after the kick when the wall jumps (s). */
  wallJumpAt: number;
  keeper: { x: number; reaction: number; speed: number };
};

export type KickParams = { velocity: Vec3; spin: Vec3 };

export type ShotSample = {
  t: number;
  ball: Vec3;
  /** Keeper's hands (centre of the reach sphere). */
  keeperHand: Vec3;
  /** Keeper's body base (feet), x only moves. */
  keeperX: number;
  wallLift: number;
};

export type ShotEvent = { t: number; type: "post" | "bounce" | "wall" | "save" | "goal" | "miss" };

export type ShotTrajectory = {
  outcome: ShotOutcome;
  samples: ShotSample[];
  events: ShotEvent[];
  /** State at the moment the outcome was decided — the physics handoff. */
  end: { t: number; position: Vec3; velocity: Vec3 };
};

// ---------------------------------------------------------------------------
// Constants (prototype tuning; once this becomes a real mode they move to
// GameConfig like every other economy-relevant number).
// ---------------------------------------------------------------------------

export const BALL_RADIUS = 0.11;
export const GOAL_HALF_WIDTH = 3.66;
export const GOAL_HEIGHT = 2.44;
export const POST_RADIUS = 0.06;
export const WALL_DISTANCE = 9.15;
export const WALL_PLAYER_RADIUS = 0.24;
export const WALL_PLAYER_HEIGHT = 1.85;
export const WALL_JUMP_HEIGHT = 0.22;
export const WALL_JUMP_DURATION = 0.5;
export const KEEPER_LINE_Z = -0.4;
export const KEEPER_HAND_RADIUS = 0.32;
export const KEEPER_BODY_RADIUS = 0.3;
export const KEEPER_STAND_HAND_Y = 1.25;
export const KEEPER_MAX_HAND_Y = 2.45;
export const KEEPER_MAX_REACH = 3.4;

const GRAVITY = 9.81;
/** 0.5 · ρ · Cd · A / m for a size-5 ball. */
const DRAG_K = 0.0135;
/** Magnus coefficient: a = K · (ω × v). */
const MAGNUS_K = 0.006;
const SPIN_DECAY_PER_S = 0.08;
const GROUND_RESTITUTION = 0.5;
const GROUND_FRICTION = 0.82;
const POST_RESTITUTION = 0.65;

export const SIM_DT = 1 / 240;
const MAX_TIME = 4;

const MIN_SPEED = 14;
const MAX_SPEED = 34;
const MAX_SPIN = 75;
/** Side spin per unit of swipe bow (rad/s): a 0.1 bow is a clear curler. */
const CURL_GAIN = 260;
/** Lofted shots get topspin so they dip back under the bar. */
const DIP_GAIN = 180;
const MAX_DIP = 40;

// ---------------------------------------------------------------------------
// Seeded randomness (setup only — the flight itself has no randomness).
// ---------------------------------------------------------------------------

export function mulberry32(seed: number): () => number {
  // Scramble first: raw neighbouring seeds (1, 2, 3…) start out correlated.
  let a = Math.imul((seed ^ (seed >>> 16)) >>> 0, 0x45d9f3b) >>> 0;
  a = Math.imul(a ^ (a >>> 16), 0x45d9f3b) >>> 0;
  a = (a ^ (a >>> 16)) >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Ball spot, wall and keeper for a seed. The wall stands 9.15 m from the
 * ball on the line to the goal centre and covers the near-post side; the
 * keeper leans to the far post. */
export function createSetup(seed: number): ShotSetup {
  const rnd = mulberry32(seed);
  const distance = lerp(18, 26, rnd());
  const side = rnd() < 0.5 ? -1 : 1;
  const offset = side * lerp(0, 8, rnd());
  const ball: Vec3 = { x: offset, y: BALL_RADIUS, z: distance };

  // Unit vector ball → goal centre (in xz) and its perpendicular.
  const len = Math.sqrt(ball.x * ball.x + ball.z * ball.z);
  const fx = -ball.x / len;
  const fz = -ball.z / len;
  const px = -fz;
  const pz = fx;

  const count = rnd() < 0.5 ? 3 : 4;
  // Near post = the side the ball is on (a central ball gets a centred wall).
  const nearSide = Math.abs(offset) < 1.5 ? 0 : offset > 0 ? 1 : -1;
  const shift = nearSide * lerp(0.6, 1.2, rnd());
  const spacing = WALL_PLAYER_RADIUS * 2 + 0.04;
  const wall: WallPlayer[] = [];
  for (let i = 0; i < count; i++) {
    const s = (i - (count - 1) / 2) * spacing + shift;
    wall.push({ x: ball.x + fx * WALL_DISTANCE + px * s, z: ball.z + fz * WALL_DISTANCE + pz * s });
  }

  return {
    seed,
    ball,
    wall,
    wallJumpAt: lerp(0.12, 0.3, rnd()),
    keeper: {
      x: -nearSide * lerp(0.3, 0.9, rnd()),
      reaction: lerp(0.2, 0.32, rnd()),
      speed: lerp(4.6, 5.6, rnd()),
    },
  };
}

// ---------------------------------------------------------------------------
// Swipe → kick
// ---------------------------------------------------------------------------

export function quantizeSwipe(s: SwipeInput): QuantizedSwipe {
  return {
    dx: Math.round(s.dx * 1000),
    dy: Math.round(s.dy * 1000),
    curve: Math.round(s.curve * 1000),
    durationMs: Math.round(clamp(s.durationMs, 40, 2000)),
  };
}

/** Swipe → initial velocity and spin. Direction is built from slopes (no
 * trig): yaw from the swipe's horizontal lean, elevation from how far up
 * it went, power from its speed, side spin from how much it bowed (a path
 * bowing right curls the ball right), and topspin growing with the loft so
 * a shot over the wall dips back under the bar. */
export function swipeToKick(setup: ShotSetup, q: QuantizedSwipe): KickParams {
  const dx = q.dx / 1000;
  const up = Math.max(0.02, -q.dy / 1000);
  const curve = clamp(q.curve / 1000, -0.5, 0.5);
  const length = Math.sqrt(dx * dx + up * up);
  const swipeSpeed = length / (q.durationMs / 1000); // viewport heights per second
  const speed = clamp(MIN_SPEED + swipeSpeed * 7, MIN_SPEED, MAX_SPEED);

  // Aim relative to the line ball → goal centre.
  const len = Math.sqrt(setup.ball.x * setup.ball.x + setup.ball.z * setup.ball.z);
  const fx = -setup.ball.x / len;
  const fz = -setup.ball.z / len;
  // Perpendicular pointing to the screen's right (camera looks along f).
  const rx = -fz;
  const rz = fx;

  const yaw = clamp(dx / up, -0.8, 0.8) * 0.35;
  const lift = clamp(0.2 + (up - 0.2) * 0.8, 0.02, 0.7);

  const dirX = fx + rx * yaw;
  const dirZ = fz + rz * yaw;
  const n = Math.sqrt(dirX * dirX + lift * lift + dirZ * dirZ);
  const velocity: Vec3 = { x: (dirX / n) * speed, y: (lift / n) * speed, z: (dirZ / n) * speed };
  // Spin about the vertical axis: ω_y < 0 bends a ball flying to −z to +x.
  // Topspin is ω about the ball's "right" axis, pointing down the Magnus way.
  const side = clamp(-curve * CURL_GAIN, -MAX_SPIN, MAX_SPIN);
  const dip = clamp((lift - 0.22) * DIP_GAIN, 0, MAX_DIP);
  const spin: Vec3 = { x: -rx * dip, y: side, z: -rz * dip };
  return { velocity, spin };
}

// ---------------------------------------------------------------------------
// Forces
// ---------------------------------------------------------------------------

/** Magnus acceleration K · (ω × v): perpendicular to both the velocity and
 * the spin axis. Exported for the tests. */
export function magnusAccel(spin: Vec3, v: Vec3): Vec3 {
  return {
    x: MAGNUS_K * (spin.y * v.z - spin.z * v.y),
    y: MAGNUS_K * (spin.z * v.x - spin.x * v.z),
    z: MAGNUS_K * (spin.x * v.y - spin.y * v.x),
  };
}

function accel(v: Vec3, spin: Vec3): Vec3 {
  const speed = Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
  const m = magnusAccel(spin, v);
  return {
    x: -DRAG_K * speed * v.x + m.x,
    y: -GRAVITY - DRAG_K * speed * v.y + m.y,
    z: -DRAG_K * speed * v.z + m.z,
  };
}

// ---------------------------------------------------------------------------
// Actors over time
// ---------------------------------------------------------------------------

export function wallLiftAt(setup: ShotSetup, t: number): number {
  const k = (t - setup.wallJumpAt) / WALL_JUMP_DURATION;
  if (k <= 0 || k >= 1) return 0;
  return WALL_JUMP_HEIGHT * 4 * k * (1 - k);
}

type KeeperState = { handX: number; handY: number; targetX: number; targetY: number; decided: boolean };

/** At reaction time the keeper reads the ball linearly (no curve, no
 * gravity — that's why bent and dipping shots beat him) and goes there. */
function keeperDecide(state: KeeperState, setup: ShotSetup, p: Vec3, v: Vec3) {
  state.decided = true;
  if (v.z >= -0.1) {
    state.targetX = setup.keeper.x;
    state.targetY = KEEPER_STAND_HAND_Y;
    return;
  }
  const tt = (KEEPER_LINE_Z - p.z) / v.z;
  const minX = setup.keeper.x - KEEPER_MAX_REACH;
  const maxX = setup.keeper.x + KEEPER_MAX_REACH;
  state.targetX = clamp(p.x + v.x * tt, Math.max(minX, -GOAL_HALF_WIDTH - 0.3), Math.min(maxX, GOAL_HALF_WIDTH + 0.3));
  state.targetY = clamp(p.y + v.y * tt, 0.25, KEEPER_MAX_HAND_Y);
}

function keeperStep(state: KeeperState, speed: number, dt: number) {
  const ex = state.targetX - state.handX;
  const ey = state.targetY - state.handY;
  const d = Math.sqrt(ex * ex + ey * ey);
  const step = speed * dt;
  if (d <= step) {
    state.handX = state.targetX;
    state.handY = state.targetY;
  } else {
    state.handX += (ex / d) * step;
    state.handY += (ey / d) * step;
  }
}

// ---------------------------------------------------------------------------
// Collisions
// ---------------------------------------------------------------------------

/** Ball vs a vertical capsule (axis along y from y0 to y1). Returns the
 * outward normal on contact, else null. */
function hitVerticalCapsule(p: Vec3, cx: number, cz: number, y0: number, y1: number, r: number): Vec3 | null {
  const cy = clamp(p.y, y0, y1);
  const nx = p.x - cx;
  const ny = p.y - cy;
  const nz = p.z - cz;
  const d2 = nx * nx + ny * ny + nz * nz;
  const rr = r + BALL_RADIUS;
  if (d2 >= rr * rr) return null;
  const d = Math.sqrt(d2) || 1;
  return { x: nx / d, y: ny / d, z: nz / d };
}

function hitSphere(p: Vec3, cx: number, cy: number, cz: number, r: number): Vec3 | null {
  const nx = p.x - cx;
  const ny = p.y - cy;
  const nz = p.z - cz;
  const d2 = nx * nx + ny * ny + nz * nz;
  const rr = r + BALL_RADIUS;
  if (d2 >= rr * rr) return null;
  const d = Math.sqrt(d2) || 1;
  return { x: nx / d, y: ny / d, z: nz / d };
}

/** Posts (vertical, at x = ±half width) and the crossbar (along x). */
function hitFrame(p: Vec3): { normal: Vec3; push: number } | null {
  const rr = POST_RADIUS + BALL_RADIUS;
  for (const sx of [-GOAL_HALF_WIDTH, GOAL_HALF_WIDTH]) {
    if (p.y > GOAL_HEIGHT + rr) continue;
    const nx = p.x - sx;
    const nz = p.z;
    const d2 = nx * nx + nz * nz;
    if (d2 < rr * rr) {
      const d = Math.sqrt(d2) || 1;
      return { normal: { x: nx / d, y: 0, z: nz / d }, push: rr - d };
    }
  }
  if (Math.abs(p.x) <= GOAL_HALF_WIDTH) {
    const ny = p.y - GOAL_HEIGHT;
    const nz = p.z;
    const d2 = ny * ny + nz * nz;
    if (d2 < rr * rr) {
      const d = Math.sqrt(d2) || 1;
      return { normal: { x: 0, y: ny / d, z: nz / d }, push: rr - d };
    }
  }
  return null;
}

function reflect(v: Vec3, n: Vec3, restitution: number): Vec3 {
  const vn = v.x * n.x + v.y * n.y + v.z * n.z;
  if (vn >= 0) return v;
  const k = (1 + restitution) * vn;
  return { x: v.x - k * n.x, y: v.y - k * n.y, z: v.z - k * n.z };
}

// ---------------------------------------------------------------------------
// The simulation
// ---------------------------------------------------------------------------

/** Flies the ball until the outcome is decided. Samples are recorded every
 * `sampleEvery` steps (default 2 → 120 Hz, plenty for interpolation). */
export function simulateShot(setup: ShotSetup, kick: KickParams, sampleEvery = 2): ShotTrajectory {
  let p: Vec3 = { ...setup.ball };
  let v: Vec3 = { ...kick.velocity };
  const spin: Vec3 = { ...kick.spin };
  const keeper: KeeperState = {
    handX: setup.keeper.x,
    handY: KEEPER_STAND_HAND_Y,
    targetX: setup.keeper.x,
    targetY: KEEPER_STAND_HAND_Y,
    decided: false,
  };
  // The body follows the hands sideways, but only so far.
  const keeperBodyX = () => clamp(keeper.handX, setup.keeper.x - 1.6, setup.keeper.x + 1.6);

  const samples: ShotSample[] = [];
  const events: ShotEvent[] = [];
  const record = (t: number) =>
    samples.push({
      t,
      ball: { ...p },
      keeperHand: { x: keeper.handX, y: keeper.handY, z: KEEPER_LINE_Z },
      keeperX: keeperBodyX(),
      wallLift: wallLiftAt(setup, t),
    });

  let outcome: ShotOutcome = "miss";
  let decidedAt = -1;
  let step = 0;
  record(0);

  const maxSteps = Math.round(MAX_TIME / SIM_DT);
  while (step < maxSteps) {
    step += 1;
    const t = step * SIM_DT;
    const prevZ = p.z;

    // Semi-implicit Euler.
    const a = accel(v, spin);
    v = { x: v.x + a.x * SIM_DT, y: v.y + a.y * SIM_DT, z: v.z + a.z * SIM_DT };
    p = { x: p.x + v.x * SIM_DT, y: p.y + v.y * SIM_DT, z: p.z + v.z * SIM_DT };
    const decay = 1 - SPIN_DECAY_PER_S * SIM_DT;
    spin.x *= decay;
    spin.y *= decay;
    spin.z *= decay;

    if (!keeper.decided && t >= setup.keeper.reaction) keeperDecide(keeper, setup, p, v);
    if (keeper.decided) keeperStep(keeper, setup.keeper.speed, SIM_DT);

    // Ground.
    if (p.y < BALL_RADIUS) {
      p.y = BALL_RADIUS;
      if (v.y < -0.5) events.push({ t, type: "bounce" });
      v = { x: v.x * GROUND_FRICTION, y: v.y < 0 ? -v.y * GROUND_RESTITUTION : v.y, z: v.z * GROUND_FRICTION };
    }

    // Wall.
    const lift = wallLiftAt(setup, t);
    let wallNormal: Vec3 | null = null;
    for (const w of setup.wall) {
      wallNormal = hitVerticalCapsule(
        p, w.x, w.z, lift + WALL_PLAYER_RADIUS, lift + WALL_PLAYER_HEIGHT - WALL_PLAYER_RADIUS, WALL_PLAYER_RADIUS,
      );
      if (wallNormal) break;
    }
    if (wallNormal) {
      v = reflect(v, wallNormal, 0.35);
      outcome = "wall";
      events.push({ t, type: "wall" });
      decidedAt = t;
      break;
    }

    // Keeper: hands sphere, then the body (a capsule from the feet to the
    // hands' height, standing at the clamped x).
    const bodyX = keeperBodyX();
    const keeperNormal =
      hitSphere(p, keeper.handX, keeper.handY, KEEPER_LINE_Z, KEEPER_HAND_RADIUS) ??
      hitVerticalCapsule(
        p, bodyX, KEEPER_LINE_Z, KEEPER_BODY_RADIUS, Math.max(KEEPER_BODY_RADIUS, Math.min(keeper.handY, 1.6)), KEEPER_BODY_RADIUS,
      );
    if (keeperNormal) {
      v = reflect(v, keeperNormal, 0.3);
      outcome = "save";
      events.push({ t, type: "save" });
      decidedAt = t;
      break;
    }

    // Frame.
    const frame = hitFrame(p);
    if (frame) {
      p = { x: p.x + frame.normal.x * frame.push, y: p.y + frame.normal.y * frame.push, z: p.z + frame.normal.z * frame.push };
      const before = v;
      v = reflect(v, frame.normal, POST_RESTITUTION);
      if (before !== v) events.push({ t, type: "post" });
    }

    // Goal line.
    if (prevZ > -BALL_RADIUS && p.z <= -BALL_RADIUS) {
      const inside = Math.abs(p.x) < GOAL_HALF_WIDTH - POST_RADIUS && p.y < GOAL_HEIGHT - POST_RADIUS;
      outcome = inside ? "goal" : "miss";
      events.push({ t, type: inside ? "goal" : "miss" });
      decidedAt = t;
      break;
    }

    // Wide, slow or back towards the kicker: it's over.
    const speed2 = v.x * v.x + v.y * v.y + v.z * v.z;
    if (Math.abs(p.x) > 40 || p.z > setup.ball.z + 5 || (p.y <= BALL_RADIUS && speed2 < 1)) {
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

  return { outcome, samples, events, end: { t: decidedAt, position: { ...p }, velocity: { ...v } } };
}

/** The whole thing in one call — what a server replay would run. */
export function playShot(seed: number, swipe: SwipeInput | QuantizedSwipe, quantized = false): ShotTrajectory {
  const setup = createSetup(seed);
  const q = quantized ? (swipe as QuantizedSwipe) : quantizeSwipe(swipe);
  return simulateShot(setup, swipeToKick(setup, q));
}

/** Interpolated sample at time t (for rendering). */
export function sampleAt(traj: ShotTrajectory, t: number): ShotSample {
  const s = traj.samples;
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
  const mix = (u: Vec3, w: Vec3): Vec3 => ({ x: lerp(u.x, w.x, k), y: lerp(u.y, w.y, k), z: lerp(u.z, w.z, k) });
  return {
    t,
    ball: mix(a.ball, b.ball),
    keeperHand: mix(a.keeperHand, b.keeperHand),
    keeperX: lerp(a.keeperX, b.keeperX, k),
    wallLift: lerp(a.wallLift, b.wallLift, k),
  };
}
