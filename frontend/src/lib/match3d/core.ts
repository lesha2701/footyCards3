/**
 * «Матч 3D»: the state of a real 11-a-side match and the ball's physics.
 *
 * The whole simulation (this folder, three.js-free) is a pure function of
 * `setup + input per tick`: the scene steps it at a fixed 60 Hz and only ever
 * reads it, so the server can replay a match by running this same code in V8
 * instead of keeping a port. For that the engine uses + − × ÷ and Math.sqrt
 * only (their results are the same everywhere; Math.sin and friends are not)
 * and its own seeded generator; engine.test.ts checks both.
 *
 * World: metres, the centre spot at the origin, x along the pitch, z across
 * it, y up. Team 0 attacks +x, team 1 attacks −x.
 */

export const HZ = 60;
export const TICK = 1 / HZ;
export const HALF_L = 52.5;
export const HALF_W = 34;
export const GOAL_HALF = 3.66;
export const GOAL_H = 2.44;
export const NET_DEPTH = 2;
export const BOX_D = 16.5;
export const BOX_HALF = 20.16;
export const SIX_D = 5.5;
export const SIX_HALF = 9.16;
export const PEN_SPOT = 11;
export const BALL_R = 0.11;
const POST_R = 0.06;

/** The match runs from 80′ to 90′ in this many real seconds of play. */
export const MATCH_SECONDS = 200;
export const START_MIN = 80;
export const END_MIN = 90;
/** Game seconds per tick. */
export const CLOCK_RATE = ((END_MIN - START_MIN) * 60) / MATCH_SECONDS / HZ;

const GRAVITY = 9.81;
const DRAG_K = 0.0135;
const MAGNUS_K = 0.006;
const SPIN_DECAY = 0.08;
const RESTITUTION = 0.46;
/** Grass takes the pace off a landing ball: it sits up, it doesn't skid on. */
const BOUNCE_FRICTION = 0.68;
/** A rolling ball slows by this (m/s²); pass planning relies on it. */
/** Constant, so a pass can be planned exactly: see `rollPace`. */
export const ROLL_DECEL = 4.2;

export type Role = "GK" | "CB" | "FB" | "DM" | "CM" | "W" | "ST";

export const enum Act {
  None, Kick, Trap, Tackle, Slide, Down, Getup, Header, Volley, Feint,
  Throw, Dive, Catch, Hold, GkThrow, GkKick, Celebrate, Dejected, Stumble,
}

export const enum Kick { None, Pass, Through, Lob, Cross, Shot, Clear, Throw, Save, Tackle, Header, Corner, GkRoll, GkPunt }

export const enum Feint { Stepover, Dragback, BallRoll, Roulette }

export const enum Phase { Kickoff, Play, Dead, Goal, FullTime }

export type SetKind = "kickoff" | "throw" | "corner" | "goalkick" | "free" | "penalty";

/** What a kick will be, decided at the windup, released at the contact. */
export type KickPlan = {
  kind: Kick;
  /** Where to (y: at what height it should get there). */
  tx: number; ty: number; tz: number;
  speed: number;
  /** Side spin, rad/s (+ bends it to the left of its flight). */
  curl: number;
  /** Who it's for (-1: nobody, a shot). */
  to: number;
  /** Scatter (m per 10 m), set by who strikes it and how. */
  err: number;
  /** A ground ball (false: it flies). */
  ground: boolean;
};

export type Player = {
  i: number;
  team: 0 | 1;
  slot: number;
  role: Role;
  num: number;
  /** Abilities, 0-1. */
  pace: number; shot: number; pass: number; dribble: number; defend: number; save: number;
  x: number; z: number; vx: number; vz: number;
  /** Facing, unit. */
  hx: number; hz: number;
  /** Where the brain wants him and how fast (m/s). */
  tx: number; tz: number; want: number;
  /** Looks at the ball instead of where he runs (a defender backing off). */
  faceBall: boolean;
  act: Act; actT: number; actLen: number;
  /** The foot (1 right, −1 left), or the side of a dive / feint. */
  side: number;
  /** Feint type; save type. */
  sub: number;
  /** Height of the jump (m; presentation reads it too). */
  air: number;
  plan: KickPlan | null;
  /** Ticks until he may tackle or take the ball again. */
  cool: number;
  /** Beaten by a feint: this many ticks off balance, this way. */
  beat: number; beatX: number; beatZ: number;
  /** Past the second-last defender when the pass was played. */
  off: boolean;
  /** Legs, 0-1: a sprint spends them, walking gives them back. */
  stamina: number;
  /** His pace going into a feint (m/s): it only sells at a walk. */
  runUp: number;
  /** Next ball touch in the dribble (ticks). */
  touch: number;
  /** The length of this count, ticks. */
  touchLen: number;
  /** Where the last touch left the ball from. */
  touchX: number;
  touchZ: number;
  /** Ticks left of a run in behind, offside if the pass comes late. */
  dash: number;
  /** Attacking runs. */
  runT: number; runX: number; runZ: number;
  /** Set by the team's brain: 1 presses the ball, 2 covers; 0 holds shape. */
  duty: number;
  /** Who he marks, -1 nobody. */
  mark: number;
  /** Keeper: reaction left, whether he'll get to the shot. */
  react: number; saves: boolean; hands: number;
};

export type Ball = {
  x: number; y: number; z: number;
  vx: number; vy: number; vz: number;
  /** Spin, rad/s. */
  sx: number; sy: number; sz: number;
  owner: number;
  /** Last touch (player), and which kick is under way. */
  last: number; kick: Kick; kicker: number;
  /** The player the ball is for (-1 nobody). */
  to: number;
  /** Ticks since the last kick. */
  since: number;
  inNet: boolean;
  /** Where it was struck from. */
  fromX: number; fromZ: number;
  /** For the rendering. */
  roll: number;
};

export type SetPiece = {
  kind: SetKind; team: 0 | 1; x: number; z: number; taker: number; t: number;
  /** The taker stands at the ball. */
  ready: boolean;
  /** This kick is played in the swipe scene: its seed (see `SceneKick`). */
  scene: number;
};

/** A penalty or a close free kick with the human in it is played out in the
 * set-piece scene; only its outcome comes back to the match. */
export type SceneKick = {
  /** "keep": their penalty, the human in goal. */
  kind: "penalty" | "free" | "keep";
  seed: number;
  /** How good the man on the ball is, as a card (55..95). */
  rating: number;
  /** Metres from the goal line and along it, the free kick's spot. */
  distance: number;
  offset: number;
};
export type SceneOutcome = "goal" | "save" | "miss" | "wall";

export type Team = { name: string; rating: number; goals: number; shots: number; onTarget: number; passes: number; passesOk: number; corners: number; fouls: number; possTicks: number; tackles: number };

export type MatchEvent =
  | { t: "kick"; p: number; kind: Kick; speed: number }
  | { t: "post" } | { t: "bar" } | { t: "net" } | { t: "bounce" }
  | { t: "goal"; team: 0 | 1; p: number; kind: Kick; long: boolean; assist: number }
  | { t: "save"; p: number; held: boolean } | { t: "miss"; p: number; near: boolean }
  | { t: "whistle"; n: number } | { t: "out"; set: SetKind; team: 0 | 1 }
  | { t: "tackle"; p: number; won: boolean } | { t: "foul"; p: number; on: number }
  | { t: "offside"; p: number } | { t: "feint"; p: number; beat: number }
  | { t: "switch"; p: number } | { t: "halfchance" } | { t: "added"; seconds: number }
  /** Everybody was moved at once: the picture cuts. */
  | { t: "cut" };

export type Setup = { seed: number; home: string; away: string; homeRating: number; awayRating: number; minutes?: number };

export type MatchState = {
  tick: number;
  rng: number;
  phase: Phase;
  phaseT: number;
  /** Seconds of the game clock since kick-off (80′ = 0). */
  clock: number;
  /** Added time in game seconds. */
  added: number;
  players: Player[];
  ball: Ball;
  teams: [Team, Team];
  set: SetPiece | null;
  /** Who plays for the human (-1: nobody, all AI). */
  user: number;
  /** The team in possession (the last one to control the ball). */
  poss: 0 | 1;
  /** Who's on the ball's trail, per team. */
  chaser: [number, number];
  /** Where the ball will be: x, y, z every PRED_STEP ticks from `predFrom`. */
  pred: Float64Array;
  predN: number;
  predFrom: number;
  /** Tick of the last goal, who scored it. */
  lastGoal: { tick: number; team: 0 | 1; p: number; kind: Kick; long: boolean; scene?: boolean } | null;
  /** Assist candidate: the last team-mate who touched it. */
  prevTouch: number;
  /** Ticks the user's press is remembered for an aerial chance. */
  wantShot: number;
  /** «Отбор» pressed too far off: until this tick he goes in once he is close enough. */
  tackleT: number;
  /** The human's press with the ball on its way: played first time when he gets to it. */
  want: { k: "pass" | "through" | "lob" | "shot"; power: number; curl: number; chip: boolean } | null;
  wantX: number;
  wantZ: number;
  wantT: number;
  /** User's stick idle for this many ticks. */
  idle: number;
  /** The human calls a second man to the ball. */
  contain: boolean;
  /** No automatic change of the human's man before this tick. */
  switchT: number;
  /** The thumb that was already down when the game changed his man: it was
   * steering somebody else. It counts again once it moves or lifts. */
  locked: boolean; lockX: number; lockZ: number;
  /** The stick last tick. */
  stickX: number; stickZ: number;
  /** When each team last lost the ball: the counter-press runs from here. */
  lostAt: [number, number];
  ev: MatchEvent[];
};

export const PRED_STEP = 4;
export const PRED_MAX = 60;

// --- generator ---------------------------------------------------------------------------------

export function rnd(s: MatchState): number {
  s.rng = (s.rng + 0x6d2b79f5) | 0;
  let t = s.rng;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

/** About normal: −1..1, peaked at 0. */
export const rndN = (s: MatchState) => rnd(s) + rnd(s) - 1;

// --- small math ----------------------------------------------------------------------------------

export const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);
export const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
export const dist = (ax: number, az: number, bx: number, bz: number) => {
  const dx = ax - bx, dz = az - bz;
  return Math.sqrt(dx * dx + dz * dz);
};
export const dist2 = (ax: number, az: number, bx: number, bz: number) => {
  const dx = ax - bx, dz = az - bz;
  return dx * dx + dz * dz;
};
/** Squared distance from a point to the segment a-b. */
export function segDist2(ax: number, az: number, bx: number, bz: number, px: number, pz: number): number {
  const dx = bx - ax, dz = bz - az;
  const l = dx * dx + dz * dz || 1;
  const u = clamp(((px - ax) * dx + (pz - az) * dz) / l, 0, 1);
  const ex = ax + dx * u - px, ez = az + dz * u - pz;
  return ex * ex + ez * ez;
}

export const dirOf = (team: 0 | 1) => (team === 0 ? 1 : -1);

/** Under this pace (m/s) a man walks the ball; above it he runs with it. */
/** `Player.sub` of a Getup that comes out of a slide. */
export const FROM_SLIDE = 9;
export const WALK_DRIBBLE = 2.4;
/** Which foot he plays it with: 1 right, −1 left. One man in four is left-footed. */
export const touchFoot = (p: Player) => (p.i % 4 === 3 ? -1 : 1);
export const speedOf = (b: Ball) => Math.sqrt(b.vx * b.vx + b.vy * b.vy + b.vz * b.vz);

// --- the ball in flight --------------------------------------------------------------------------

function stepFlight(b: Pick<Ball, "x" | "y" | "z" | "vx" | "vy" | "vz" | "sx" | "sy" | "sz">, dt: number) {
  const speed = Math.sqrt(b.vx * b.vx + b.vy * b.vy + b.vz * b.vz);
  const ax = -DRAG_K * speed * b.vx + MAGNUS_K * (b.sy * b.vz - b.sz * b.vy);
  const ay = -GRAVITY - DRAG_K * speed * b.vy + MAGNUS_K * (b.sz * b.vx - b.sx * b.vz);
  const az = -DRAG_K * speed * b.vz + MAGNUS_K * (b.sx * b.vy - b.sy * b.vx);
  b.vx += ax * dt; b.vy += ay * dt; b.vz += az * dt;
  b.x += b.vx * dt; b.y += b.vy * dt; b.z += b.vz * dt;
  const decay = 1 - SPIN_DECAY * dt;
  b.sx *= decay; b.sy *= decay; b.sz *= decay;
}

function stepRoll(b: Pick<Ball, "x" | "y" | "z" | "vx" | "vy" | "vz">, dt: number) {
  const v = Math.sqrt(b.vx * b.vx + b.vz * b.vz);
  if (v < 0.03) {
    b.vx = 0; b.vz = 0;
    return;
  }
  const lost = ROLL_DECEL * dt;
  const k = lost >= v ? 0 : (v - lost) / v;
  b.vx *= k; b.vz *= k;
  b.x += b.vx * dt; b.z += b.vz * dt;
  b.y = BALL_R; b.vy = 0;
}

function grounded(b: Ball | PredBall): boolean {
  return b.y <= BALL_R + 0.002 && Math.abs(b.vy) < 0.7;
}

type PredBall = { x: number; y: number; z: number; vx: number; vy: number; vz: number; sx: number; sy: number; sz: number };

function bounce(b: PredBall): boolean {
  if (b.y >= BALL_R || b.vy >= 0) return false;
  b.y = BALL_R;
  const hard = -b.vy > 0.7;
  b.vy = hard ? -b.vy * RESTITUTION : 0;
  b.vx *= BOUNCE_FRICTION; b.vz *= BOUNCE_FRICTION;
  b.sx *= 0.6; b.sy *= 0.6; b.sz *= 0.6;
  return hard;
}

const scratch: PredBall = { x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0, sx: 0, sy: 0, sz: 0 };

/** Where the ball will be for the next few seconds (no one touching it). */
export function predict(s: MatchState) {
  const b = s.ball, p = scratch;
  p.x = b.x; p.y = b.y; p.z = b.z; p.vx = b.vx; p.vy = b.vy; p.vz = b.vz; p.sx = b.sx; p.sy = b.sy; p.sz = b.sz;
  s.predFrom = s.tick;
  const dt = TICK / 2;
  let n = 0;
  for (; n < PRED_MAX; n++) {
    for (let k = 0; k < PRED_STEP * 2; k++) {
      if (grounded(p)) stepRoll(p, dt);
      else {
        stepFlight(p, dt);
        bounce(p);
      }
    }
    s.pred[n * 3] = p.x; s.pred[n * 3 + 1] = p.y; s.pred[n * 3 + 2] = p.z;
  }
  s.predN = n;
}

/** The ball in `ticks` from now, along the prediction. */
export function predAt(s: MatchState, ticks: number): { x: number; y: number; z: number } {
  const at = clamp(Math.floor((ticks + s.tick - s.predFrom) / PRED_STEP), 0, s.predN - 1);
  return { x: s.pred[at * 3], y: s.pred[at * 3 + 1], z: s.pred[at * 3 + 2] };
}

// --- the frame -----------------------------------------------------------------------------------

function hitPost(b: Ball, gx: number, pz: number): boolean {
  const rr = POST_R + BALL_R;
  if (b.y > GOAL_H + rr) return false;
  const nx = b.x - gx, nz = b.z - pz;
  const d2 = nx * nx + nz * nz;
  if (d2 >= rr * rr) return false;
  const d = Math.sqrt(d2) || 1;
  const ux = nx / d, uz = nz / d;
  const vn = b.vx * ux + b.vz * uz;
  if (vn >= 0) return false;
  b.vx -= 1.65 * vn * ux; b.vz -= 1.65 * vn * uz;
  b.x = gx + ux * rr; b.z = pz + uz * rr;
  return true;
}

function hitBar(b: Ball, gx: number): boolean {
  if (Math.abs(b.z) > GOAL_HALF) return false;
  const rr = POST_R + BALL_R;
  const nx = b.x - gx, ny = b.y - GOAL_H;
  const d2 = nx * nx + ny * ny;
  if (d2 >= rr * rr) return false;
  const d = Math.sqrt(d2) || 1;
  const ux = nx / d, uy = ny / d;
  const vn = b.vx * ux + b.vy * uy;
  if (vn >= 0) return false;
  b.vx -= 1.65 * vn * ux; b.vy -= 1.65 * vn * uy;
  b.x = gx + ux * rr; b.y = GOAL_H + uy * rr;
  return true;
}

/** Inside the goal the net takes the pace out of it. */
function netStep(b: Ball) {
  const back = Math.abs(b.x) - HALF_L;
  if (back > NET_DEPTH - BALL_R) {
    b.x = (b.x > 0 ? 1 : -1) * (HALF_L + NET_DEPTH - BALL_R);
    b.vx *= -0.12; b.vy *= 0.35; b.vz *= 0.35;
  }
  if (Math.abs(b.z) > GOAL_HALF - BALL_R) {
    b.z = (b.z > 0 ? 1 : -1) * (GOAL_HALF - BALL_R);
    b.vz *= -0.2;
  }
  if (b.y > GOAL_H - BALL_R) {
    b.y = GOAL_H - BALL_R;
    b.vy *= -0.2;
  }
  b.vx *= 0.97; b.vz *= 0.97;
}

/** A tick of the free ball. Returns nothing: events go on `s.ev`. */
export function stepBall(s: MatchState) {
  const b = s.ball;
  b.since += 1;
  // The table runs out after a few seconds; a long roll outlives it.
  if (s.tick - s.predFrom >= PRED_STEP * PRED_MAX * 0.6) predict(s);
  const dt = TICK / 2;
  for (let n = 0; n < 2; n++) {
    if (grounded(b)) stepRoll(b, dt);
    else {
      stepFlight(b, dt);
      if (bounce(b) && -b.vy > 1.4) s.ev.push({ t: "bounce" });
    }
    if (b.inNet) {
      netStep(b);
      continue;
    }
    const near = Math.abs(Math.abs(b.x) - HALF_L) < 0.6;
    if (near && Math.abs(b.z) < GOAL_HALF + 0.4 && b.y < GOAL_H + 0.4) {
      const gx = b.x > 0 ? HALF_L : -HALF_L;
      if (hitPost(b, gx, -GOAL_HALF) || hitPost(b, gx, GOAL_HALF)) {
        s.ev.push({ t: "post" });
        predict(s);
      } else if (hitBar(b, gx)) {
        s.ev.push({ t: "bar" });
        predict(s);
      }
    }
  }
  // The spin of the rolling ball, for the eye.
  b.roll += Math.sqrt(b.vx * b.vx + b.vz * b.vz) * TICK / BALL_R;
}

export function ballAt(b: Ball, x: number, y: number, z: number) {
  b.x = x; b.y = y; b.z = z;
  b.vx = 0; b.vy = 0; b.vz = 0;
  b.sx = 0; b.sy = 0; b.sz = 0;
}

// --- kicks ---------------------------------------------------------------------------------------

/** Sets the ball off: a ground ball at `speed` along the line, or in the air
 * so as to reach (tx, ty, tz) at about that pace. */
export function launch(s: MatchState, plan: KickPlan) {
  const b = s.ball;
  const dx = plan.tx - b.x, dz = plan.tz - b.z;
  const d = Math.sqrt(dx * dx + dz * dz) || 1;
  const ux = dx / d, uz = dz / d;
  if (plan.ground) {
    b.vx = ux * plan.speed; b.vz = uz * plan.speed;
    b.vy = 0; b.y = BALL_R;
    b.sx = 0; b.sy = plan.curl * 0.2; b.sz = 0;
    return;
  }
  // Drag eats the pace: the flight takes a bit longer than speed says.
  const flat = Math.max(4, plan.speed);
  const slow = 1 + DRAG_K * flat * (d / flat) * 0.5;
  const t = (d / flat) * slow;
  b.vx = ux * flat; b.vz = uz * flat;
  b.vy = (plan.ty - b.y) / t + 0.5 * GRAVITY * t;
  // Back spin on what's hit under, side spin as asked. The curl bends the
  // flight by about Magnus·spin·speed·t²/2 sideways: aim off by half of it.
  const bend = 0.5 * MAGNUS_K * plan.curl * flat * t * t;
  const cz = bend * 0.9;
  b.vz += (ux * cz) / t;
  b.vx -= (uz * cz) / t;
  b.sx = 0; b.sy = plan.curl; b.sz = 0;
}

export function freshState(setup: Setup, players: Player[]): MatchState {
  const team = (name: string, rating: number): Team => ({ name, rating, goals: 0, shots: 0, onTarget: 0, passes: 0, passesOk: 0, corners: 0, fouls: 0, possTicks: 0, tackles: 0 });
  return {
    tick: 0, rng: setup.seed | 0, phase: Phase.Kickoff, phaseT: 0, clock: 0, added: 0,
    players,
    ball: { x: 0, y: BALL_R, z: 0, vx: 0, vy: 0, vz: 0, sx: 0, sy: 0, sz: 0, owner: -1, last: -1, kick: Kick.None, kicker: -1, to: -1, since: 0, inNet: false, fromX: 0, fromZ: 0, roll: 0 },
    teams: [team(setup.home, setup.homeRating), team(setup.away, setup.awayRating)],
    set: null, user: -1, poss: 0, chaser: [-1, -1],
    pred: new Float64Array(PRED_MAX * 3), predN: 0, predFrom: 0,
    lastGoal: null, prevTouch: -1, wantShot: 0, tackleT: 0, want: null, wantX: 0, wantZ: 0, wantT: 0, idle: 0, contain: false, switchT: 0, locked: false, lockX: 0, lockZ: 0, stickX: 0, stickZ: 0, lostAt: [-9999, -9999], ev: [],
  };
}
