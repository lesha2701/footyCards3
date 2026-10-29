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
  /** The kicker card's edge in [−1, 1] (rating 55 → −1, 75 → 0, 95 → 1):
   * a little more power and curl, a slightly slower keeper. */
  edge: number;
  ball: Vec3;
  wall: WallPlayer[];
  /** Time after the kick when the wall jumps (s). */
  wallJumpAt: number;
  /** Slowest kick (m/s): a free kick is always struck; a penalty may be a
   * soft chip. */
  minSpeed: number;
  /** Loft per swipe height (1 for a free kick; the short penalty distance
   * needs more to reach the top corners). */
  liftScale: number;
  /** Aim per swipe lean (1 for a free kick; a penalty can be pulled wide). */
  aimScale: number;
  /** Extra loft for a soft strike (0 for a free kick): a penalty chip. */
  chipLoft: number;
  /** `guess`: where the keeper commits at `reaction` instead of reading the
   * ball — a penalty keeper going early, or the player's own dive. */
  keeper: {
    x: number;
    reaction: number;
    speed: number;
    guess: { x: number; y: number } | null;
    /** Reads the ball's drop too (a penalty keeper reacting at the strike);
     * a free-kick keeper reads it straight, so dipping shots beat him. */
    readsDrop: boolean;
    /** How far sideways his hands go when reading the ball (m). */
    reach: number;
  };
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
const GROUND_FRICTION = 0.9;
/** A rolling ball loses this share of its speed per second. */
const ROLL_DECAY_PER_S = 0.08;
const POST_RESTITUTION = 0.65;

export const SIM_DT = 1 / 240;
const MAX_TIME = 4;

const MIN_SPEED = 16;
const MAX_SPEED = 34;
const MAX_SPIN = 75;
/** Side spin per unit of swipe bow (rad/s): a 0.1 bow is a clear curler. */
const CURL_GAIN = 260;
/** Lofted shots get topspin so they dip back under the bar. */
const DIP_GAIN = 180;
const MAX_DIP = 40;
/** What a full edge (rating 95) adds: max speed (m/s), curl share, and
 * the keeper's slowdown share. Small on purpose — skill decides. */
const EDGE_SPEED = 2;
const EDGE_CURL = 0.1;
const EDGE_KEEPER = 0.08;

/** Card rating → edge in [−1, 1]. */
export function ratingEdge(rating: number): number {
  return clamp((rating - 75) / 20, -1, 1);
}

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
export function createSetup(seed: number, rating = 75): ShotSetup {
  const rnd = mulberry32(seed);
  const edge = ratingEdge(rating);
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
    edge,
    ball,
    wall,
    wallJumpAt: lerp(0.12, 0.3, rnd()),
    minSpeed: MIN_SPEED,
    liftScale: 1,
    aimScale: 1,
    chipLoft: 0,
    keeper: {
      x: -nearSide * lerp(0.3, 0.9, rnd()),
      reaction: lerp(0.2, 0.32, rnd()),
      speed: lerp(4.6, 5.6, rnd()) * (1 - EDGE_KEEPER * edge),
      guess: null,
      readsDrop: false,
      reach: KEEPER_MAX_REACH,
    },
  };
}

// ---------------------------------------------------------------------------
// Penalties: 11 m, no wall, a sharper keeper — half the time he reads the
// ball (quicker and faster than a free kick's), half the time he commits
// to a corner as it's struck (then the other side, or a chip down the
// middle, beats him).
// ---------------------------------------------------------------------------

export const PENALTY_DISTANCE = 11;
const PENALTY_MIN_SPEED = 12;
const PENALTY_CHIP_LOFT = 0.35;
/** Below this the strike counts as soft and gets the chip's loft (m/s). */
const CHIP_SPEED = 17;
const PENALTY_LIFT_SCALE = 1.4;
const PENALTY_AIM_SCALE = 1.5;
/** A human can't start a dive sooner than this after the strike (s). */
export const PENALTY_MIN_REACTION = 0.18;
/** The player's own keeper: how fast the hands travel (m/s). */
const PLAYER_KEEPER_SPEED = 7.2;
/** The player's keeper with no swipe stays in the middle and still goes for
 * a ball within his reach — a strike down the middle is saved by standing. */
const PLAYER_KEEPER_STAND_REACTION = 0.25;
const PLAYER_KEEPER_STAND_REACH = 1.0;

export function createPenaltySetup(seed: number, rating = 75): ShotSetup {
  const rnd = mulberry32(seed);
  const edge = ratingEdge(rating);
  // Every draw happens in a fixed order, whichever way the keeper goes.
  const commits = rnd() < 0.6;
  const side = rnd() < 0.5 ? -1 : 1;
  const guessX = side * lerp(1.8, 3.2, rnd());
  const guessY = lerp(0.35, 1.9, rnd());
  const early = lerp(0, 0.06, rnd());
  const read = lerp(0.12, 0.18, rnd());
  const speed = lerp(4.9, 5.6, rnd()) * (1 - EDGE_KEEPER * edge);
  return {
    seed,
    edge,
    ball: { x: 0, y: BALL_RADIUS, z: PENALTY_DISTANCE },
    wall: [],
    wallJumpAt: 99,
    minSpeed: PENALTY_MIN_SPEED,
    liftScale: PENALTY_LIFT_SCALE,
    aimScale: PENALTY_AIM_SCALE,
    chipLoft: PENALTY_CHIP_LOFT,
    keeper: {
      x: 0, reaction: commits ? early : read, speed, guess: commits ? { x: guessX, y: guessY } : null, readsDrop: true,
      reach: KEEPER_MAX_REACH,
    },
  };
}

/** The player keeping goal: the dive goes where they swiped, starting when
 * they swiped — after the strike never sooner than a human can
 * (`PENALTY_MIN_REACTION`); before it, at once (and the kicker sees him go:
 * `penaltyBotShot`). No swipe: he stays in the middle and only goes for
 * a ball within `PLAYER_KEEPER_STAND_REACH`. Integer inputs (mm, and ms from the
 * strike — negative during the run-up), as the server gets them. */
export type QuantizedDive = { x: number; y: number; reactionMs: number };

export function playerKeeperSetup(seed: number, dive: QuantizedDive | null): ShotSetup {
  const setup = createPenaltySetup(seed);
  const reaction = !dive ? PLAYER_KEEPER_STAND_REACTION : dive.reactionMs < 0 ? 0 : Math.max(PENALTY_MIN_REACTION, dive.reactionMs / 1000);
  const guess = dive
    ? { x: clamp(dive.x / 1000, -GOAL_HALF_WIDTH, GOAL_HALF_WIDTH), y: clamp(dive.y / 1000, 0.25, KEEPER_MAX_HAND_Y) }
    : null;
  const reach = dive ? KEEPER_MAX_REACH : PLAYER_KEEPER_STAND_REACH;
  return { ...setup, edge: 0, keeper: { x: 0, reaction, speed: PLAYER_KEEPER_SPEED, guess, readsDrop: true, reach } };
}

export type BotShotKind = "low_corner" | "side" | "top_corner" | "power" | "chip" | "wide" | "over";

/** The bot's penalty for a seed: a kind of strike (weighted) and the swipe
 * that plays it — so the server replays it like any player's swipe. Swipe
 * fields are whole numbers (`floor(x + 0.5)` of a positive magnitude: no
 * engine-specific rounding). Draws in a fixed order, whatever the kind. */
const BOT_KINDS: [BotShotKind, number][] = [
  ["low_corner", 28], ["side", 20], ["top_corner", 20], ["power", 12], ["chip", 7], ["wide", 8], ["over", 5],
];

export function penaltyBotShot(seed: number, dive: QuantizedDive | null = null): { kind: BotShotKind; swipe: QuantizedSwipe } {
  const rnd = mulberry32((seed ^ 0x5bd1e995) >>> 0);
  const pick = rnd() * 100;
  const side = rnd() < 0.5 ? -1 : 1;
  const a = rnd();
  const b = rnd();
  const c = rnd();
  const whole = (v: number) => Math.floor(v + 0.5);
  let acc = 0;
  let kind: BotShotKind = "low_corner";
  for (const [k, w] of BOT_KINDS) {
    acc += w;
    if (pick < acc) {
      kind = k;
      break;
    }
  }
  const [dx, dy, ms] = {
    low_corner: [lerp(42, 55, a), lerp(100, 120, b), lerp(150, 180, c)],
    side: [lerp(50, 70, a), lerp(150, 175, b), lerp(160, 190, c)],
    top_corner: [lerp(85, 105, a), lerp(220, 238, b), lerp(140, 160, c)],
    power: [lerp(0, 12, a), lerp(170, 215, b), lerp(115, 140, c)],
    chip: [lerp(0, 6, a), lerp(250, 270, b), lerp(800, 1000, c)],
    wide: [lerp(120, 160, a), lerp(140, 200, b), lerp(140, 170, c)],
    over: [lerp(0, 60, a), lerp(290, 320, b), lerp(130, 160, c)],
  }[kind];
  // A keeper who goes before the strike gets punished: the kicker sees him
  // move and places it the other way.
  const aimed = kind === "low_corner" || kind === "side" || kind === "top_corner";
  const dir = aimed && dive && dive.reactionMs < 0 && dive.x * side > 0 ? -side : side;
  // `|| 0`: a dead-centre strike is 0, not −0 (integers, as the server has them).
  return { kind, swipe: { dx: dir * whole(dx) || 0, dy: -whole(dy), curve: 0, durationMs: whole(ms) } };
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
 * trig): aim from the swipe's horizontal lean, elevation from how far up
 * it went, power from its speed, and topspin growing with the loft so a
 * shot over the wall dips back under the bar. The ball's path copies the
 * swipe's shape: the chord is the aim, a bow to the right sends the ball
 * out to the right first and spins it back left onto the aim (a banana
 * around the wall), and vice versa. */
export function swipeToKick(setup: ShotSetup, q: QuantizedSwipe): KickParams {
  const dx = q.dx / 1000;
  const up = Math.max(0.02, -q.dy / 1000);
  const curve = clamp(q.curve / 1000, -0.5, 0.5);
  const length = Math.sqrt(dx * dx + up * up);
  // Viewport heights per second, softened for short swipes (a low shot is a
  // short swipe and must not come out weak): sqrt(length · 0.4) equals the
  // length for a full 0.4 swipe and is larger below it.
  const swipeSpeed = Math.sqrt(length * 0.4) / (q.durationMs / 1000);
  const speed = clamp(setup.minSpeed + swipeSpeed * 7, setup.minSpeed, MAX_SPEED + EDGE_SPEED * setup.edge);

  // Aim relative to the line ball → goal centre.
  const len = Math.sqrt(setup.ball.x * setup.ball.x + setup.ball.z * setup.ball.z);
  const fx = -setup.ball.x / len;
  const fz = -setup.ball.z / len;
  // Perpendicular pointing to the screen's right (camera looks along f).
  const rx = -fz;
  const rz = fx;

  const aim = clamp(dx / up, -0.8, 0.8) * 0.35 * setup.aimScale;
  // Below a 0.2 swipe the shot flattens out fast: a short swipe is a drive.
  const chip = clamp((CHIP_SPEED - speed) / 3, 0, 1) * setup.chipLoft;
  const lift = clamp((up < 0.2 ? 0.2 - (0.2 - up) * 1.6 : 0.2 + (up - 0.2) * 0.8) * setup.liftScale + chip, 0.02, 0.7);
  // Spin about the vertical axis: ω_y > 0 bends a ball flying to −z to −x
  // (left), so a bow to the right (curve > 0) gets ω_y > 0.
  const side = clamp(curve * CURL_GAIN * (1 + EDGE_CURL * setup.edge), -MAX_SPIN, MAX_SPIN);
  // Launch off the aim towards the bow by the angle a constant sideways
  // Magnus pull (K·ω·v) takes back over the distance: θ = K·ω·D / (2·v).
  const yaw = aim + (MAGNUS_K * side * len) / (2 * speed);

  const dirX = fx + rx * yaw;
  const dirZ = fz + rz * yaw;
  const n = Math.sqrt(dirX * dirX + lift * lift + dirZ * dirZ);
  const velocity: Vec3 = { x: (dirX / n) * speed, y: (lift / n) * speed, z: (dirZ / n) * speed };
  // Topspin is ω about the ball's "right" axis, pointing down the Magnus way.
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
  const guess = setup.keeper.guess;
  if (guess && (v.z >= -0.1 || !sameSide(guess.x, p.x + v.x * ((KEEPER_LINE_Z - p.z) / v.z)))) {
    // Committed, and the ball isn't going his way: he dives there anyway.
    state.targetX = clamp(guess.x, -GOAL_HALF_WIDTH - 0.3, GOAL_HALF_WIDTH + 0.3);
    state.targetY = clamp(guess.y, 0.25, KEEPER_MAX_HAND_Y);
    return;
  }
  // Reading the ball (or committed to the side it's going): he goes for it.
  if (v.z >= -0.1) {
    state.targetX = setup.keeper.x;
    state.targetY = KEEPER_STAND_HAND_Y;
    return;
  }
  const tt = (KEEPER_LINE_Z - p.z) / v.z;
  const minX = setup.keeper.x - setup.keeper.reach;
  const maxX = setup.keeper.x + setup.keeper.reach;
  state.targetX = clamp(p.x + v.x * tt, Math.max(minX, -GOAL_HALF_WIDTH - 0.3), Math.min(maxX, GOAL_HALF_WIDTH + 0.3));
  const drop = setup.keeper.readsDrop ? 0.5 * GRAVITY * tt * tt : 0;
  state.targetY = clamp(p.y + v.y * tt - drop, 0.25, KEEPER_MAX_HAND_Y);
}

/** The ball is heading to the half of the goal the keeper went to (a
 * central ball, within half a metre, counts for neither side). */
function sameSide(guessX: number, ballX: number): boolean {
  return ballX * guessX > 0 && Math.abs(ballX) > 0.5;
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
      if (v.y < -0.5) {
        // A bounce: loses some pace on impact.
        events.push({ t, type: "bounce" });
        v = { x: v.x * GROUND_FRICTION, y: -v.y * GROUND_RESTITUTION, z: v.z * GROUND_FRICTION };
      } else {
        // Rolling: only a little friction per step.
        const roll = 1 - ROLL_DECAY_PER_S * SIM_DT;
        v = { x: v.x * roll, y: 0, z: v.z * roll };
      }
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
export function playShot(seed: number, swipe: SwipeInput | QuantizedSwipe, quantized = false, rating = 75): ShotTrajectory {
  const setup = createSetup(seed, rating);
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
