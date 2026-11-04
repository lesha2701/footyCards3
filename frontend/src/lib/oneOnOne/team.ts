/**
 * The team episodes built on «Атака 1 на 1»: 2 на 1, 3 на 2, пас в разрез,
 * навес / прострел. The same deterministic contract as engine.ts (and the
 * same run, keeper and shot — this file adds only who else is on the pitch):
 * a pure function of `kind + seed + rating + input timeline`, stepped live
 * by the scene and replayed by the server with its bit-exact Python port
 * (backend/app/services/team_attack_engine.py); a shared fixture
 * (team.fixture.test.ts) keeps the two in lockstep.
 *
 * Who is who: `s.x / s.z` is always the man the player runs. A pass takes
 * PASS_WINDUP ticks to play and hands him the receiver on release: the ball
 * flies, the receiver runs on to meet it (the stick does nothing then), the
 * passer drops into the receiver's slot among the teammates.
 *
 * World: as in engine.ts — goal line z = 0, the attack runs towards −z.
 */
import { BALL_RADIUS, mulberry32 } from "@/lib/freeKick3d/trajectory";

import {
  BALL_LEAD,
  MAX_RUN_TICKS,
  SMOTHER_RADIUS,
  TICK,
  VOLLEY_Y,
  ballOf,
  createEpisode,
  end,
  initState,
  isChip,
  keeperDown,
  keeperStep,
  shoot,
  startFeint,
  stepRun,
  type EpisodeEnd,
  type EpisodeSetup,
  type EpisodeState,
  type EpisodeTimeline,
  type TickInput,
} from "./engine";

// ---------------------------------------------------------------------------
// Constants (engine tuning — the economy lives in GameConfig).
// ---------------------------------------------------------------------------

/** The pass: this many ticks from the button until the ball leaves. */
export const PASS_WINDUP = 10;
/** At most this many passes in one episode. */
export const MAX_PASSES = 3;
/** Ground pass, m/s (a full edge adds PASS_EDGE). */
const PASS_SPEED = 15;
const PASS_EDGE = 1.5;
/** The cut-back: along the ground too, this fast (m/s). */
const CUTBACK_SPEED = 20;
/** A ground pass this close (m) to a defender on his feet: his. */
const INTERCEPT_RADIUS = 0.75;
/** Fixed rounds of working out where the receiver meets the ball. */
const MEET_ROUNDS = 3;
/** Struck within this many ticks of a pass reaching him the shot is first
 * time: it scatters off line by up to this much (a touch first steadies
 * it, and gives the keeper time), a header more, a full edge less. */
const FIRST_TIME_TICKS = 10;
const FIRST_TIME_SCATTER = 0.08;
const VOLLEY_SCATTER = 0.2;
const VOLLEY_FROM = 0.5;
const HEADER_SCATTER = 0.26;
const SCATTER_EDGE = 0.6;
/** With more than one to mind the keeper stays this near his line (m). */
const KEEPER_DEEP = 4.5;
/** The keeper shuffles across with a ground pass, this fast on top (m/s). */
const KEEPER_SHUFFLE = 2.4;

/** The cross, by the power bar: from a low, soft, short ball to a high,
 * hard, long one. Pace (m/s), how far it arcs over the straight line (m),
 * the height it reaches the runner at (m). At CROSS_SWEET it lands on him;
 * CROSS_SPREAD m per unit of bar short of him or past him. */
const CROSS_SOFT = 13;
const CROSS_HARD = 23;
const CROSS_ARC_LOW = 0.5;
const CROSS_ARC_HIGH = 3.4;
const CONTACT_LOW = 0.65;
const CONTACT_HIGH = 2.2;
const CROSS_SWEET = 0.55;
const CROSS_SPREAD = 6;
/** Past the meeting point it slows to this share and drops to the grass:
 * he can still strike it for CONTROL_TICKS, then he brings it down. Out of
 * his reach it is gone CROSS_LATE ticks later. */
const CROSS_AFTER = 0.3;
const CONTROL_TICKS = 9;
const CROSS_LATE = 14;
/** Under this (m) a cross can be cut out like a ground pass. */
const LOW_BALL = 1.2;
/** A marker this close to the meeting point (m) gets there first. */
const CONTEST_RADIUS = 1.3;
/** A ball dropping here is the keeper's: he comes for it, and this close
 * (m) as it arrives takes it — catches it, or punches it with a man on him
 * (within CLAIM_PRESSED). */
const KEEPER_ZONE_Z = 6;
const KEEPER_ZONE_X = 9;
export const CLAIM_RADIUS = 1.9;
const CLAIM_PRESSED = 1.3;
const CLAIM_SPEED = 6.5;
/** The through ball: played into the space this far ahead of the man (m). */
const THROUGH_LEAD = 6;
/** The receiver runs to meet the ball no faster than this (m/s), and never
 * further in than this (m from the line). */
const RECEIVER_TOP = 7.4;
const MEET_MIN_Z = 3.5;
/** He brings a cross down and is at this pace (m/s). */
const RUN_AFTER_CONTROL = 3;

const MATE_SPEED = 6.1;
/** A pacing teammate keeps this far behind the ball (m): level, onside. */
const MATE_BEHIND = 0.8;
/** Nearing the goal the lanes narrow to this share, from z = LANE_FROM. */
const LANE_MIN = 0.55;
const LANE_FROM = 25;
/** A pacing teammate stops this far from the goal line (m). */
const MATE_MIN_Z = 7;

/** A full edge slows the defenders by this share. */
const DEF_EDGE = 0.1;
/** The presser stands off the ball towards the goal: this far (m) out at
 * STAND_FROM from the goal, closing to STAND_NEAR by STAND_TO — running
 * straight at him ends in his tackle. */
const STAND_OFF = 3;
const STAND_NEAR = 1;
const STAND_FROM = 22;
const STAND_TO = 14;
/** Closer to the ball than this (m) he goes in: slides at LUNGE_SPEED for
 * DEF_LUNGE_TICKS, leading the ball by LUNGE_LEAD (s), and takes it within
 * TACKLE_REACH. */
const DEF_LUNGE_DIST = 1.7;
const LUNGE_SPEED = 8.5;
export const DEF_LUNGE_TICKS = 16;
const LUNGE_LEAD = 0.18;
const TACKLE_REACH = 0.85;
/** Having missed he is on the grass this long; a feint within FEINT_REACH
 * m he bites on (composure under FEINT_BITE) puts him there for less. */
const DOWN_TICKS = 70;
const FEINT_REACH = 4.5;
const FEINT_BITE = 0.5;
const FEINT_EDGE = 0.1;
const FEINT_DOWN_TICKS = 50;
/** A marker stands this far inside the man he marks (m); with his eyes on
 * the man he doesn't cut out a ball this close to him (the cut-back). */
const MARK_INSIDE = 0.4;
const MARK_BLIND = 2.5;
/** A pass this many ticks old before the defenders turn after it. */
const CHASE_AFTER = 18;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** How a pass is played: along the ground to him, into the space ahead of
 * him, in the air, driven low across the goal. `power` (0…100) is the
 * cross's bar. */
export const PASS_GROUND = 0;
export const PASS_THROUGH = 1;
export const PASS_CROSS = 2;
export const PASS_CUTBACK = 3;
export type PassOrder = { target: number; mode: number; power: number };

export const TEAM_KINDS = ["two_v_one", "three_v_two", "through_ball", "cross"] as const;
export type TeamKind = (typeof TEAM_KINDS)[number];

/** A leg of a teammate's scripted run: to here at this pace. */
type Leg = { x: number; z: number; speed: number };
type ManPlan = { x: number; z: number; delay: number; legs: Leg[]; lane: number };
type DefRole = "press" | "mark" | "line";
type DefPlan = {
  x: number;
  z: number;
  role: DefRole;
  /** The teammate he marks, and how far goal side of him (m). */
  mark: number;
  gap: number;
  speed: number;
  /** He bites on a feint when this is low. */
  composure: number;
  /** How far towards the spare man he leans (0…1). */
  cover: number;
  reactTicks: number;
};
export type TeamPlan = { kind: TeamKind; men: ManPlan[]; defs: DefPlan[] };
export type TeamSetup = EpisodeSetup & { team: TeamPlan };

export type TeamMan = { x: number; z: number; vx: number; vz: number; leg: number; delay: number; lane: number; legs: Leg[] };
export type DefMode = "guard" | "lunge" | "down";
export type TeamDef = { x: number; z: number; vx: number; vz: number; mode: DefMode; ticks: number; dirX: number; dirZ: number };
export type TeamPass = {
  fromX: number;
  fromZ: number;
  toX: number;
  toZ: number;
  /** Ticks flown, and how many to the meeting point. */
  at: number;
  total: number;
  high: boolean;
  /** The cross: how far it arcs, how high it reaches him. */
  arc: number;
  contactY: number;
  /** He can get to it; the keeper's coming for it. */
  reach: boolean;
  claim: boolean;
};
export type TeamRun = {
  men: TeamMan[];
  defs: TeamDef[];
  /** Ticks left until the pass being played leaves, and to whom. */
  windup: number;
  target: number;
  mode: number;
  power: number;
  pass: TeamPass | null;
  passes: number;
  /** The tick the last pass reached him. */
  touch: number;
};

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

/** Who stands where for a seed: the base episode (its keeper) and a second
 * seeded stream, drawn in a fixed order. */
export function createTeamEpisode(kind: TeamKind, seed: number, rating = 75): TeamSetup {
  const base = createEpisode(seed, rating);
  const rnd = mulberry32(seed + 7919);
  const side = rnd() < 0.5 ? -1 : 1;
  const slow = 1 - DEF_EDGE * base.edge;
  const def = (x: number, z: number, role: DefRole, mark: number, gap: number): DefPlan => {
    const speed = lerp(5.3, 5.9, rnd()) * slow;
    const composure = lerp(0.15, 0.9, rnd());
    const cover = lerp(0.15, 0.6, rnd());
    const reactTicks = Math.floor(lerp(6, 18, rnd()));
    return { x, z, role, mark, gap, speed, composure, cover, reactTicks };
  };
  const startX = kind === "two_v_one" ? side * lerp(3, 6, rnd()) : kind === "three_v_two" ? lerp(-2, 2, rnd()) : kind === "through_ball" ? lerp(-6, 6, rnd()) : side * lerp(19, 23, rnd());
  const startZ = kind === "two_v_one" ? lerp(27, 31, rnd()) : kind === "three_v_two" ? lerp(29, 33, rnd()) : kind === "through_ball" ? lerp(35, 38, rnd()) : lerp(23, 27, rnd());
  const men: ManPlan[] = [];
  const defs: DefPlan[] = [];
  if (kind === "two_v_one") {
    const lane = -side * lerp(5, 7, rnd());
    men.push({ x: lane, z: startZ + lerp(-1, 1, rnd()), delay: 0, legs: [], lane });
    const x = lerp(-1.5, 1.5, rnd());
    defs.push(def(x, lerp(15, 18, rnd()), "press", 0, 0));
  } else if (kind === "three_v_two") {
    const l = -lerp(6, 8, rnd());
    const r = lerp(6, 8, rnd());
    men.push({ x: l, z: startZ + lerp(-1, 1, rnd()), delay: 0, legs: [], lane: l });
    men.push({ x: r, z: startZ + lerp(-1, 1, rnd()), delay: 0, legs: [], lane: r });
    const px = side * lerp(1, 3, rnd());
    defs.push(def(px, lerp(16, 19, rnd()), "press", 0, 0));
    const mx = -side * lerp(4, 6, rnd());
    const mz = lerp(14, 17, rnd());
    defs.push(def(mx, mz, "mark", side > 0 ? 0 : 1, lerp(1.6, 3, rnd())));
  } else if (kind === "through_ball") {
    const line = lerp(19, 22, rnd());
    const from = side * lerp(11, 14, rnd());
    const z = line + lerp(1.6, 2.2, rnd());
    const delay = Math.floor(lerp(40, 100, rnd()));
    // Across the line first — onside while he does; then in behind it.
    const crossX = side * lerp(3, 5, rnd());
    const inX = -side * lerp(1, 4, rnd());
    men.push({ x: from, z, delay, legs: [{ x: crossX, z: line, speed: 6.6 }, { x: inX, z: 7, speed: 7.1 }], lane: from });
    const ax = side * lerp(7, 9, rnd());
    defs.push(def(ax, line, "line", 0, 0));
    const bx = -side * lerp(1, 3, rnd());
    defs.push(def(bx, line - lerp(0, 0.6, rnd()), "line", 0, 0));
  } else {
    const nearX = side * lerp(5, 8, rnd());
    const nearZ = lerp(15, 18, rnd());
    const farX = -side * lerp(1, 4, rnd());
    const farZ = lerp(17, 20, rnd());
    const delay = Math.floor(lerp(30, 70, rnd()));
    const nx = side * lerp(1.6, 3, rnd());
    const nz = lerp(6.2, 7.5, rnd());
    const fx = -side * lerp(1.5, 3.4, rnd());
    const fz = lerp(7, 9, rnd());
    men.push({ x: nearX, z: nearZ, delay, legs: [{ x: nx, z: nz, speed: 6.4 }], lane: nearX });
    men.push({ x: farX, z: farZ, delay: delay + 10, legs: [{ x: fx, z: fz, speed: 6.2 }], lane: farX });
    const bx = side * lerp(15, 17, rnd());
    defs.push(def(bx, lerp(13, 16, rnd()), "press", 0, 0));
    const g1 = lerp(0.4, 1.8, rnd());
    defs.push(def(nearX - side * 0.8, nearZ - 1, "mark", 0, g1));
    const g2 = lerp(0.4, 1.8, rnd());
    defs.push(def(farX + side * 0.8, farZ - 1, "mark", 1, g2));
  }
  return { ...base, keeper: { ...base.keeper, maxOut: KEEPER_DEEP }, start: { x: startX, z: startZ }, team: { kind, men, defs } };
}

export function initTeamState(setup: TeamSetup): EpisodeState {
  const s = initState(setup);
  s.free = null;
  s.blockers = [];
  s.team = {
    men: setup.team.men.map((m) => ({ x: m.x, z: m.z, vx: 0, vz: 0, leg: 0, delay: m.delay, lane: m.lane, legs: m.legs })),
    defs: setup.team.defs.map((d) => ({ x: d.x, z: d.z, vx: 0, vz: 0, mode: "guard", ticks: 0, dirX: 0, dirZ: 0 })),
    windup: 0,
    target: 0,
    mode: PASS_GROUND,
    power: 0,
    pass: null,
    passes: 0,
    touch: -1000,
  };
  return s;
}

const run = (s: EpisodeState) => s.team as TeamRun;

/** The last defender's line (down on the grass he still counts). */
export function offsideLine(r: TeamRun): number {
  let line = r.defs[0].z;
  for (const d of r.defs) line = Math.min(line, d.z);
  return line;
}

/** Past the last defender and past the ball right now. */
export function isOffside(s: EpisodeState, target: number): boolean {
  const r = run(s);
  const m = r.men[target];
  return m.z < offsideLine(r) && m.z < ballOf(s).z;
}

/** Whom the stick's lean (thousandths) picks: the nearest teammate on that
 * side of him (behind him with the stick pulled back), the nearest of all
 * with the stick upright. Client side: the server just replays the index. */
export function pickMate(s: EpisodeState, lean: number, back = false): number {
  let best = 0;
  let score = Infinity;
  run(s).men.forEach((m, i) => {
    const dx = m.x - s.x;
    const d = Math.hypot(dx, m.z - s.z) + (Math.abs(lean) > 200 && dx * lean < 0 ? 100 : 0) + (back && m.z < s.z ? 50 : 0);
    if (d < score) {
      score = d;
      best = i;
    }
  });
  return best;
}

/** In front of the goal the lofted button chips, wide or far out it
 * crosses. Client side: the timeline carries only what it became. */
const CHIP_ZONE_X = 12;
const CHIP_ZONE_Z = 22;
export const inChipZone = (s: EpisodeState) => Math.abs(s.x) < CHIP_ZONE_X && s.z < CHIP_ZONE_Z;

// ---------------------------------------------------------------------------
// The tick
// ---------------------------------------------------------------------------

function moveTo(o: { x: number; z: number; vx: number; vz: number }, tx: number, tz: number, speed: number) {
  const ex = tx - o.x;
  const ez = tz - o.z;
  const e = Math.sqrt(ex * ex + ez * ez);
  const step = speed * TICK;
  if (e <= step) {
    o.vx = 0;
    o.vz = 0;
    o.x = tx;
    o.z = tz;
  } else {
    o.vx = (ex / e) * speed;
    o.vz = (ez / e) * speed;
    o.x += o.vx * TICK;
    o.z += o.vz * TICK;
  }
}

function stepMen(s: EpisodeState) {
  const b = ballOf(s);
  for (const m of run(s).men) {
    if (m.delay > 0) {
      m.delay -= 1;
    } else if (m.legs.length === 0) {
      // Level with the ball, down his lane.
      const z = Math.max(MATE_MIN_Z, b.z + MATE_BEHIND);
      moveTo(m, m.lane * lerp(LANE_MIN, 1, clamp(z / LANE_FROM, 0, 1)), z, MATE_SPEED);
    } else if (m.leg < m.legs.length) {
      const l = m.legs[m.leg];
      moveTo(m, l.x, l.z, l.speed);
      if (m.x === l.x && m.z === l.z) m.leg += 1;
    }
  }
}

function stepDefs(setup: TeamSetup, s: EpisodeState) {
  const r = run(s);
  const b = ballOf(s);
  const glen = Math.sqrt(b.x * b.x + b.z * b.z) || 1;
  const gx = -b.x / glen;
  const gz = -b.z / glen;
  for (let i = 0; i < r.defs.length; i++) {
    const d = r.defs[i];
    const plan = setup.team.defs[i];
    if (d.mode === "down") {
      d.vx = 0;
      d.vz = 0;
      d.ticks -= 1;
      if (d.ticks <= 0) d.mode = "guard";
      continue;
    }
    if (d.mode === "lunge") {
      d.vx = d.dirX * LUNGE_SPEED;
      d.vz = d.dirZ * LUNGE_SPEED;
      d.x += d.vx * TICK;
      d.z += d.vz * TICK;
      d.ticks -= 1;
      if (!r.pass) {
        const ex = b.x - d.x;
        const ez = b.z - d.z;
        if (ex * ex + ez * ez < TACKLE_REACH * TACKLE_REACH) return end(s, "dispossessed");
      }
      if (d.ticks <= 0) {
        d.mode = "down";
        d.ticks = DOWN_TICKS;
      }
      continue;
    }
    if (s.tick < plan.reactTicks) continue;
    let tx: number;
    let tz: number;
    // The ball past him: everyone goes for it.
    const beaten = b.z < d.z - 1;
    if (r.pass && (r.pass.high || r.pass.at < CHASE_AFTER)) {
      // Caught flat by the pass: he stands; a cross — he stays with his man.
      if (!r.pass.high || plan.role !== "mark") {
        d.vx = 0;
        d.vz = 0;
        continue;
      }
      const m = r.men[plan.mark];
      moveTo(d, m.x + (m.x > 0 ? -MARK_INSIDE : MARK_INSIDE), m.z - plan.gap, plan.speed);
      continue;
    }
    if (r.pass) {
      tx = r.pass.toX;
      tz = r.pass.toZ;
    } else if (plan.role === "press" || beaten) {
      const stand = lerp(STAND_NEAR, STAND_OFF, clamp((glen - STAND_TO) / (STAND_FROM - STAND_TO), 0, 1));
      // A wide man is shown inside: he guards the line, not the middle.
      const line = setup.team.kind === "cross" && !beaten;
      tx = line ? b.x : b.x + gx * stand;
      tz = line ? b.z - stand : b.z + gz * stand;
      if (!beaten && !line) {
        // Leaning to the spare man, cutting the pass.
        let near = 0;
        let best = Infinity;
        for (let j = 0; j < r.men.length; j++) {
          const m = r.men[j];
          const e = (m.x - d.x) * (m.x - d.x) + (m.z - d.z) * (m.z - d.z);
          if (e < best) {
            best = e;
            near = j;
          }
        }
        tx += (r.men[near].x - tx) * plan.cover * 0.5;
        tz += (r.men[near].z - tz) * plan.cover * 0.5;
      }
    } else if (plan.role === "mark") {
      const m = r.men[plan.mark];
      tx = m.x + (m.x > 0 ? -MARK_INSIDE : MARK_INSIDE);
      tz = m.z - plan.gap;
    } else {
      // Holding the line, shifting across with the ball a little.
      tx = plan.x + (b.x - plan.x) * 0.25;
      tz = plan.z;
    }
    moveTo(d, tx, tz, plan.speed);
    if (!r.pass && s.feintTicks === 0) {
      const ex = b.x - d.x;
      const ez = b.z - d.z;
      if (ex * ex + ez * ez < DEF_LUNGE_DIST * DEF_LUNGE_DIST) {
        const lx = ex + s.hx * s.speed * LUNGE_LEAD;
        const lz = ez + s.hz * s.speed * LUNGE_LEAD;
        const l = Math.sqrt(lx * lx + lz * lz) || 1;
        d.mode = "lunge";
        d.ticks = DEF_LUNGE_TICKS;
        d.dirX = lx / l;
        d.dirZ = lz / l;
      }
    }
  }
}

/** Where the man will be `t` s on: as he is going, or at the end of his run. */
function meetOf(m: TeamMan, t: number): { x: number; z: number } {
  if (m.leg < m.legs.length) {
    const last = m.legs[m.legs.length - 1];
    const ex = last.x - m.x;
    const ez = last.z - m.z;
    const speed = Math.sqrt(m.vx * m.vx + m.vz * m.vz);
    if (speed * t >= Math.sqrt(ex * ex + ez * ez)) return { x: last.x, z: last.z };
  }
  return { x: m.x + m.vx * t, z: m.z + m.vz * t };
}

/** The ball leaves: the receiver is the player's from here on. */
function release(setup: TeamSetup, s: EpisodeState) {
  const r = run(s);
  if (setup.team.kind !== "cross" && isOffside(s, r.target)) return end(s, "offside");
  const m = r.men[r.target];
  const from = ballOf(s);
  const high = r.mode === PASS_CROSS;
  const bar = r.power / 100;
  const pace = high ? lerp(CROSS_SOFT, CROSS_HARD, bar) : (r.mode === PASS_CUTBACK ? CUTBACK_SPEED : PASS_SPEED) + PASS_EDGE * setup.edge;
  // Where it meets him.
  let t = 0;
  let toX = m.x;
  let toZ = m.z;
  for (let i = 0; i < MEET_ROUNDS; i++) {
    const dx = toX - from.x;
    const dz = toZ - from.z;
    t = Math.sqrt(dx * dx + dz * dz) / pace;
    const at = meetOf(m, t);
    toX = at.x;
    toZ = at.z;
  }
  if (r.mode === PASS_THROUGH) {
    // Into the space ahead of him, towards the goal.
    const gl = Math.sqrt(toX * toX + toZ * toZ) || 1;
    toX -= (toX / gl) * THROUGH_LEAD;
    toZ -= (toZ / gl) * THROUGH_LEAD;
  } else if (high) {
    // Over- or underhit, it drops past him or short of him.
    const dx = toX - from.x;
    const dz = toZ - from.z;
    const d = Math.sqrt(dx * dx + dz * dz) || 1;
    const over = (bar - CROSS_SWEET) * CROSS_SPREAD;
    toX += (dx / d) * over;
    toZ += (dz / d) * over;
  }
  toZ = Math.max(MEET_MIN_Z, toZ);
  {
    const dx = toX - from.x;
    const dz = toZ - from.z;
    t = Math.sqrt(dx * dx + dz * dz) / pace;
  }
  let total = Math.max(1, Math.floor(t / TICK));
  // He runs to meet it, the ball BALL_LEAD ahead of him, as fast as it
  // takes; along the ground it's played weighted for him, a cross isn't.
  const ex = toX - m.x;
  const ez = toZ - m.z;
  const e = Math.sqrt(ex * ex + ez * ez);
  const dist = Math.max(0, e - BALL_LEAD);
  if (!high) total = Math.max(total, Math.floor(dist / (RECEIVER_TOP * TICK)) + 1);
  const need = dist / (total * TICK);
  const hx = e > 0.1 ? ex / e : s.hx;
  const hz = e > 0.1 ? ez / e : s.hz;
  // He takes the receiver's place; the passer the receiver's slot.
  r.men[r.target] = { x: s.x, z: s.z, vx: s.hx * s.speed, vz: s.hz * s.speed, leg: 0, delay: 0, lane: s.x, legs: [] };
  s.x = m.x;
  s.z = m.z;
  s.hx = hx;
  s.hz = hz;
  s.speed = Math.min(need, RECEIVER_TOP);
  s.lead = BALL_LEAD;
  r.pass = {
    fromX: from.x,
    fromZ: from.z,
    toX,
    toZ,
    at: 0,
    total,
    high,
    arc: lerp(CROSS_ARC_LOW, CROSS_ARC_HIGH, bar),
    contactY: lerp(CONTACT_LOW, CONTACT_HIGH, bar),
    reach: need <= RECEIVER_TOP,
    claim: high && toZ < KEEPER_ZONE_Z && Math.abs(toX) < KEEPER_ZONE_X,
  };
  r.passes += 1;
  s.free = { x: from.x, z: from.z };
  s.fromY = BALL_RADIUS;
}

/** One tick of the ball on its way to the receiver. */
function stepPass(setup: TeamSetup, s: EpisodeState) {
  const r = run(s);
  const p = r.pass as TeamPass;
  const free = s.free as { x: number; z: number };
  p.at += 1;
  const dirX = p.toX - p.fromX;
  const dirZ = p.toZ - p.fromZ;
  if (p.at <= p.total) {
    const k = p.at / p.total;
    free.x = p.fromX + dirX * k;
    free.z = p.fromZ + dirZ * k;
    s.fromY = p.high ? lerp(BALL_RADIUS, p.contactY, k) + 4 * p.arc * k * (1 - k) : BALL_RADIUS;
    s.x += s.hx * s.speed * TICK;
    s.z += s.hz * s.speed * TICK;
  } else {
    // A cross past the meeting point: slowing, dropping, he goes with it.
    const after = p.at - p.total;
    const k = 1 + (after * CROSS_AFTER) / p.total;
    free.x = p.fromX + dirX * k;
    free.z = p.fromZ + dirZ * k;
    s.fromY = Math.max(BALL_RADIUS, p.contactY - ((p.contactY - BALL_RADIUS) * after) / CONTROL_TICKS);
    if (p.reach) {
      s.x = free.x - s.hx * BALL_LEAD;
      s.z = free.z - s.hz * BALL_LEAD;
    } else {
      s.x += s.hx * s.speed * TICK;
      s.z += s.hz * s.speed * TICK;
    }
  }
  s.tick += 1;
  if (p.claim && !keeperDown(s)) {
    // Coming off his line for it.
    const ex = p.toX - s.kx;
    const ez = p.toZ - s.kz;
    const e = Math.sqrt(ex * ex + ez * ez);
    const step = CLAIM_SPEED * TICK;
    s.kMode = "rush";
    if (e > step) {
      s.kx += (ex / e) * step;
      s.kz += (ez / e) * step;
    }
  } else keeperStep(setup, s);
  if (!p.high && !keeperDown(s)) {
    const tx = (p.toX * s.kz) / Math.max(1, p.toZ);
    const step = KEEPER_SHUFFLE * TICK;
    s.kx += clamp(tx - s.kx, -step, step);
  }
  stepMen(s);
  stepDefs(setup, s);
  if (s.ended) return;

  if (!p.high || s.fromY! < LOW_BALL) {
    // Along the ground anyone on his feet can cut it out on the way.
    const left = (p.total - p.at) * TICK * Math.sqrt(dirX * dirX + dirZ * dirZ) / (p.total * TICK);
    for (let i = 0; i < r.defs.length; i++) {
      const d = r.defs[i];
      if (d.mode === "down" || (setup.team.defs[i].role === "mark" && left < MARK_BLIND)) continue;
      const ex = free.x - d.x;
      const ez = free.z - d.z;
      if (ex * ex + ez * ez < INTERCEPT_RADIUS * INTERCEPT_RADIUS) return end(s, "intercepted");
    }
  }
  if (!p.high) {
    if (!keeperDown(s)) {
      const ex = free.x - s.kx;
      const ez = free.z - s.kz;
      if (ex * ex + ez * ez < SMOTHER_RADIUS * SMOTHER_RADIUS) return end(s, "tackle");
    }
    if (p.at >= p.total) {
      r.pass = null;
      r.touch = s.tick;
      s.free = null;
      s.fromY = BALL_RADIUS;
      return;
    }
  } else if (p.at === p.total) {
    // The cross comes down: whoever gets there first.
    r.touch = s.tick;
    if (!keeperDown(s)) {
      const ex = free.x - s.kx;
      const ez = free.z - s.kz;
      if (ex * ex + ez * ez < CLAIM_RADIUS * CLAIM_RADIUS) {
        const ax = free.x - s.x;
        const az = free.z - s.z;
        return end(s, ax * ax + az * az < CLAIM_PRESSED * CLAIM_PRESSED ? "cleared" : "tackle");
      }
    }
    for (const d of r.defs) {
      if (d.mode === "down") continue;
      const ex = free.x - d.x;
      const ez = free.z - d.z;
      if (ex * ex + ez * ez < CONTEST_RADIUS * CONTEST_RADIUS) return end(s, "cleared");
    }
  } else if (p.reach && p.at >= p.total + CONTROL_TICKS) {
    // Not struck: he brings it down and plays on.
    r.pass = null;
    r.touch = s.tick;
    s.free = null;
    s.fromY = BALL_RADIUS;
    s.speed = Math.min(s.speed, RUN_AFTER_CONTROL);
    return;
  } else if (p.at >= p.total + CROSS_LATE) {
    return end(s, "cleared");
  }
  if (s.tick >= MAX_RUN_TICKS) return end(s, "lost");
}

/** Can a shot be struck on this tick? Not while a ground pass is on its
 * way; a cross — from the moment it reaches him until it has dropped past. */
export function strikeReady(s: EpisodeState): boolean {
  const r = run(s);
  if (s.feintTicks > 0 || r.windup > 0) return false;
  return !r.pass || (r.pass.high && r.pass.reach && r.pass.at >= r.pass.total);
}

function strike(setup: TeamSetup, s: EpisodeState, shot: NonNullable<TickInput["shot"]>) {
  const r = run(s);
  s.blockers = r.defs.filter((d) => d.mode === "guard").map((d) => ({ x: d.x, z: d.z }));
  if (s.tick - r.touch <= FIRST_TIME_TICKS) {
    const y = s.fromY ?? 0;
    const off = y > VOLLEY_Y ? HEADER_SCATTER : y > VOLLEY_FROM ? VOLLEY_SCATTER : FIRST_TIME_SCATTER;
    s.scatter = (mulberry32(setup.seed + s.tick)() - 0.5) * 2 * off * (1 - SCATTER_EDGE * setup.edge);
  }
  const flight = shoot(setup, s, shot);
  end(s, flight.outcome, flight, isChip(flight));
}

/** One tick. The order is the contract: the feint, the pass asked for, the
 * shot if it can be struck, else the ball's flight or the run. */
export function teamAdvance(setup: TeamSetup, s: EpisodeState, input: TickInput): void {
  if (s.ended) return;
  const r = run(s);
  if (input.feint !== 0 && !s.feintUsed && !r.pass && r.windup === 0) {
    startFeint(setup, s, input.feint > 0 ? 1 : -1);
    const b = ballOf(s);
    for (let i = 0; i < r.defs.length; i++) {
      const d = r.defs[i];
      const ex = b.x - d.x;
      const ez = b.z - d.z;
      if (d.mode === "guard" && ex * ex + ez * ez < FEINT_REACH * FEINT_REACH && setup.team.defs[i].composure < FEINT_BITE + FEINT_EDGE * setup.edge) {
        d.mode = "down";
        d.ticks = FEINT_DOWN_TICKS;
      }
    }
  }
  const pass = input.pass;
  if (pass && pass.target >= 0 && pass.target < r.men.length && !r.pass && r.windup === 0 && r.passes < MAX_PASSES && s.feintTicks === 0) {
    r.windup = PASS_WINDUP;
    r.target = pass.target;
    r.mode = pass.mode;
    r.power = pass.power;
  }
  if (input.shot && strikeReady(s)) return strike(setup, s, input.shot);
  if (r.pass) return stepPass(setup, s);
  stepRun(setup, s, input);
  if (s.ended) return;
  stepMen(s);
  stepDefs(setup, s);
  if (s.ended) return;
  if (r.windup > 0) {
    r.windup -= 1;
    if (r.windup === 0) release(setup, s);
  }
}

/** The server's replay. */
export function replayTeam(setup: TeamSetup, tl: EpisodeTimeline): EpisodeEnd {
  const s = initTeamState(setup);
  const passes = tl.passes ?? [];
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
    const pass = passes.find((p) => p.tick === i) ?? null;
    teamAdvance(setup, s, {
      hold,
      steer,
      feint: tl.feint && tl.feint.tick === i ? tl.feint.dir : 0,
      shot: tl.shot && tl.shot.tick <= i ? tl.shot : null,
      pass,
    });
  }
  return s.ended;
}
