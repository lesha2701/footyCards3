/** What a footballer does with the ball: the kicks (planned at the windup,
 * released at the contact), tackles and feints. The brain and the human call
 * the same functions, so both play by the same physics and the same odds. */
import {
  Act, BALL_R, BOX_D, GOAL_H, GOAL_HALF, HALF_L, HALF_W, Kick, ROLL_DECEL, TICK,
  clamp, dirOf, dist, launch, predict, rnd, rndN,
  type Feint, type KickPlan, type MatchState, type Player,
} from "./core";

/** His top speed (m/s): tired legs lose up to a sixth of it. */
export const sprintOf = (p: Player) => (7.1 + p.pace * 1.5) * (0.84 + 0.16 * Math.min(1, p.stamina / 0.35));

/** Windups: ticks from the decision to the foot meeting the ball. */
const WINDUP: Partial<Record<Kick, number>> = {
  [Kick.Pass]: 9, [Kick.Through]: 10, [Kick.Lob]: 13, [Kick.Cross]: 14, [Kick.Shot]: 13, [Kick.Clear]: 11, [Kick.Throw]: 28, [Kick.Corner]: 24,
};
/** How long the rest of the kick's move takes. */
const FOLLOW = 14;
export const GOAL_X = HALF_L;
/** Opponents closer than this (m) hurry him. */
const PRESSURE = 3.2;

export function nearestOpp(s: MatchState, p: Player): { o: Player | null; d: number } {
  let o: Player | null = null;
  let d = 1e9;
  for (const q of s.players) {
    if (q.team === p.team || q.role === "GK") continue;
    const e = dist(p.x, p.z, q.x, q.z);
    if (e < d) { d = e; o = q; }
  }
  return { o, d };
}

const pressureOn = (s: MatchState, p: Player) => clamp(1 - nearestOpp(s, p).d / PRESSURE, 0, 1);

/** Starts the kick: the windup runs in `stepKick`. */
export function startKick(s: MatchState, p: Player, plan: KickPlan) {
  p.plan = plan;
  p.act = Act.Kick;
  p.actT = 0;
  p.actLen = (WINDUP[plan.kind] ?? 10) + FOLLOW;
  // Strikes with the foot on the side of the ball's way, mostly the right.
  const ux = plan.tx - p.x, uz = plan.tz - p.z;
  const cross = p.hx * uz - p.hz * ux;
  p.side = plan.kind === Kick.Throw ? 1 : cross < -2 ? -1 : cross > 6 && rnd(s) < 0.2 ? -1 : 1;
  const b = s.ball;
  if (plan.to >= 0) b.to = plan.to;
}

export const windupOf = (p: Player) => (p.plan ? (WINDUP[p.plan.kind] ?? 10) : 10);

/** Everyone past the second-last defender when the ball is played. */
export function offsideLine(s: MatchState, team: 0 | 1): number {
  const dir = dirOf(team);
  let a = -1e9, b = -1e9;
  for (const q of s.players) {
    if (q.team === team) continue;
    const v = q.x * dir;
    if (v > a) { b = a; a = v; } else if (v > b) b = v;
  }
  return Math.max(b, 0);
}

function markOffside(s: MatchState, p: Player) {
  const line = offsideLine(s, p.team);
  const dir = dirOf(p.team);
  const bx = s.ball.x * dir;
  for (const m of s.players) {
    if (m.team !== p.team || m.i === p.i) continue;
    const v = m.x * dir;
    m.off = v > line + 0.1 && v > bx + 0.1 && v > 0;
  }
}

function clearOffside(s: MatchState) {
  for (const m of s.players) m.off = false;
}

/** The foot meets the ball. */
export function releaseKick(s: MatchState, p: Player) {
  const plan = p.plan;
  const b = s.ball;
  if (!plan) return;
  p.plan = null;
  if (b.owner !== p.i && !(b.owner < 0 && dist(p.x, p.z, b.x, b.z) < 1.6)) return;
  const d = dist(b.x, b.z, plan.tx, plan.tz);
  const shot = plan.kind === Kick.Shot;
  // The human's passes are helped on their way, and so kept tidier at the foot.
  const spread = ((shot ? plan.err * 2.8 : plan.err) * (!shot && p.i === s.user ? 0.5 : 1) * d) / 10;
  const ex = spread * rndN(s), ez = spread * rndN(s);
  const t = shot
    ? { ...plan, tz: plan.tz + ez, ty: Math.max(0.12, plan.ty + spread * 0.5 * rndN(s)) }
    : { ...plan, tx: plan.tx + ex, tz: plan.tz + ez };
  b.owner = -1; b.last = p.i; b.kick = plan.kind; b.kicker = p.i; b.since = 0;
  b.fromX = b.x; b.fromZ = b.z;
  if (b.y < BALL_R) b.y = BALL_R;
  launch(s, t);
  b.to = plan.to;
  // A cross hit into a man closing it down comes off him, usually behind.
  if (plan.kind === Kick.Cross) {
    const q = nearestOpp(s, p);
    if (q.o && q.d < 2.8 && rnd(s) < 0.42) {
      const dir = dirOf(p.team);
      b.last = q.o.i; b.kicker = q.o.i; b.kick = Kick.Tackle; b.to = -1; b.since = 0;
      b.vx = dir * (7 + rnd(s) * 6); b.vz = Math.sign(p.z || 1) * (rnd(s) * 3 - 1); b.vy = 2 + rnd(s) * 3.5;
      b.sx = 0; b.sy = 0; b.sz = 0;
    }
  }
  const passing = plan.kind === Kick.Pass || plan.kind === Kick.Through || plan.kind === Kick.Lob || plan.kind === Kick.Cross || plan.kind === Kick.GkRoll || plan.kind === Kick.GkPunt;
  clearOffside(s);
  if (passing) {
    markOffside(s, p);
    s.teams[p.team].passes += 1;
  }
  if (shot) {
    const tm = s.teams[p.team];
    tm.shots += 1;
    if (Math.abs(t.tz) < GOAL_HALF && t.ty < GOAL_H) tm.onTarget += 1;
  }
  predict(s);
  s.ev.push({ t: "kick", p: p.i, kind: plan.kind, speed: plan.speed });
  p.cool = 16;
}

// --- plans ----------------------------------------------------------------------------------------

/** The pace that gets a ball rolling `d` metres to arrive at `end` m/s. */
export const rollPace = (d: number, end: number) => Math.sqrt(end * end + 2 * ROLL_DECEL * d);

/** How long a ball takes to roll d from pace v. */
export const rollTime = (v: number, d: number) => {
  const q = v * v - 2 * ROLL_DECEL * d;
  return q <= 0 ? v / ROLL_DECEL : (v - Math.sqrt(q)) / ROLL_DECEL;
};

/** How safely a ball rolls from him to (x, z): above 0 it gets there first. */
export function laneMargin(s: MatchState, p: Player, x: number, z: number, pace: number): number {
  const d = dist(p.x, p.z, x, z) || 1;
  let worst = 9;
  for (const o of s.players) {
    if (o.team === p.team) continue;
    const dx = x - p.x, dz = z - p.z;
    const u = clamp(((o.x - p.x) * dx + (o.z - p.z) * dz) / (d * d), 0.05, 1);
    const along = d * u;
    const time = rollTime(pace, along);
    const off = dist(p.x + dx * u, p.z + dz * u, o.x, o.z);
    // He has to read it first, and he comes from a stand.
    const m = off - 0.9 - Math.max(0, time - 0.25) * sprintOf(o) * 0.74;
    if (m < worst) worst = m;
  }
  return worst;
}

export function planPass(s: MatchState, p: Player, m: Player, power: number): KickPlan {
  const d0 = dist(p.x, p.z, m.x, m.z);
  const pace = clamp(rollPace(d0, 6.5 + power * 8), 9, 26);
  const t = rollTime(pace, d0);
  // Into his feet where he'll be.
  const tx = clamp(m.x + m.vx * t * 0.8, -HALF_L + 1, HALF_L - 1);
  const tz = clamp(m.z + m.vz * t * 0.8, -HALF_W + 1, HALF_W - 1);
  const d = dist(p.x, p.z, tx, tz);
  return {
    kind: Kick.Pass, tx, ty: 0, tz, speed: clamp(rollPace(d, 6.5 + power * 8), 9, 26), curl: 0, to: m.i, ground: true,
    err: 0.08 + (1 - p.pass) * 0.32 + pressureOn(s, p) * 0.14 + (d > 25 ? 0.08 : 0),
  };
}

/** Into the space ahead of the runner. */
export function planThrough(s: MatchState, p: Player, m: Player, power: number): KickPlan {
  const dir = dirOf(p.team);
  const lead = 6 + power * 6;
  const vl = Math.sqrt(m.vx * m.vx + m.vz * m.vz);
  const ux = vl > 1 ? m.vx / vl : dir, uz = vl > 1 ? m.vz / vl : 0;
  const fwdx = Math.max(ux * dir, 0.35) * dir;
  const tx = clamp(m.x + fwdx * lead, -HALF_L + 3, HALF_L - 3);
  const tz = clamp(m.z + uz * lead * 0.7, -HALF_W + 2, HALF_W - 2);
  const d = dist(p.x, p.z, tx, tz);
  return {
    kind: Kick.Through, tx, ty: 0, tz, speed: clamp(rollPace(d, 4), 9, 24), curl: 0, to: m.i, ground: true,
    err: 0.1 + (1 - p.pass) * 0.32 + pressureOn(s, p) * 0.16,
  };
}

/** A high ball: to a man, or a spot. */
export function planLob(s: MatchState, p: Player, tx: number, tz: number, to: number, power: number): KickPlan {
  const d = dist(p.x, p.z, tx, tz);
  return {
    kind: Kick.Lob, tx, ty: 0.9, tz, speed: clamp(d * (0.44 - power * 0.1) + 5, 9, 22), curl: 0, to, ground: false,
    err: 0.12 + (1 - p.pass) * 0.32 + pressureOn(s, p) * 0.16,
  };
}

/** Into the box from wide: swings towards the goal off the far foot. */
export function planCross(s: MatchState, p: Player, tx: number, tz: number, to: number, power: number, kind: Kick = Kick.Cross): KickPlan {
  const d = dist(p.x, p.z, tx, tz);
  const swing = (p.z > 0 ? 1 : -1) * dirOf(p.team) * 16;
  return {
    kind, tx, ty: 1.9, tz, speed: clamp(d * 0.5 + 8 + power * 4, 13, 24), curl: swing, to, ground: false,
    err: 0.14 + (1 - p.pass) * 0.3 + pressureOn(s, p) * 0.2,
  };
}

/** `aim` −1..1 across the goal, `power` 0..1, `curl` −1..1, `chip`. */
export function planShot(s: MatchState, p: Player, aim: number, power: number, curl: number, chip: boolean): KickPlan {
  const dir = dirOf(p.team);
  const gx = dir * GOAL_X;
  const tz = aim * (GOAL_HALF - 0.32);
  const d = dist(p.x, p.z, gx, tz);
  const ux = (gx - p.x) / (d || 1), uz = (tz - p.z) / (d || 1);
  const facing = clamp(p.hx * ux + p.hz * uz, -1, 1);
  const hurry = pressureOn(s, p);
  let err = 0.09 + (1 - p.shot) * 0.34 + hurry * 0.16 + clamp(0.5 - facing, 0, 1.5) * 0.1 + power * power * 0.09;
  if (Math.abs(curl) > 0.2) err *= 0.9;
  // The AI aims at corners a thumb can't: it pays for that in accuracy.
  if (p.i !== s.user) err *= 1.55;
  if (chip) {
    return {
      kind: Kick.Shot, tx: gx, ty: 1.5, tz, speed: clamp(d * 0.6, 7, 14), curl: 0, to: -1, err: err * 1.3, ground: false,
    };
  }
  const speed = 15 + power * (11 + p.shot * 8);
  // Low when placed, rising when struck; a full-power one can go over.
  const ty = clamp(0.25 + power * power * 1.55 + d * 0.012, 0.2, 2.3);
  return {
    kind: Kick.Shot, tx: gx + dir * 0.4, ty, tz, speed, curl: curl * 34, to: -1, err, ground: false,
  };
}

export function planClear(s: MatchState, p: Player): KickPlan {
  const dir = dirOf(p.team);
  const side = p.z === 0 ? (rnd(s) < 0.5 ? 1 : -1) : Math.sign(p.z);
  const tx = clamp(p.x + dir * (26 + rnd(s) * 14), -HALF_L + 4, HALF_L - 4);
  const tz = clamp(p.z + side * (6 + rnd(s) * 12), -HALF_W + 3, HALF_W - 3);
  return { kind: Kick.Clear, tx, ty: 0.5, tz, speed: 21, curl: 0, to: -1, err: 0.2, ground: false };
}

// --- tackles --------------------------------------------------------------------------------------

/** The foot nearer the ball. */
const footFor = (s: MatchState, p: Player) => (p.hx * (s.ball.z - p.z) - p.hz * (s.ball.x - p.x) > 0 ? -1 : 1);

/** The lunge: `stepTackle` carries him at the ball, he doesn't stop to poke at it. */
export function startTackle(s: MatchState, p: Player) {
  p.act = Act.Tackle; p.actT = 0; p.actLen = 30;
  p.side = footFor(s, p);
}

export const SLIDE_LEN = 52;
/** How far ahead (s) a slide meets a ball it can see. */
const SLIDE_LOOK = 0.32;
const SLIDE_PACE = 8.8;

/** Down and along the grass: at where the ball will be if it's near enough to
 * judge, otherwise the way he is running. */
export function startSlide(s: MatchState, p: Player) {
  p.act = Act.Slide; p.actT = 0; p.actLen = SLIDE_LEN; p.sub = 0;
  const b = s.ball;
  const v = Math.sqrt(p.vx * p.vx + p.vz * p.vz);
  const tx = b.x + b.vx * SLIDE_LOOK - p.x, tz = b.z + b.vz * SLIDE_LOOK - p.z;
  const d = Math.sqrt(tx * tx + tz * tz);
  let ux = v > 1 ? p.vx / v : p.hx, uz = v > 1 ? p.vz / v : p.hz;
  if (d > 0.5 && d < 7) { ux = tx / d; uz = tz / d; }
  p.side = footFor(s, p);
  const pace = Math.max(SLIDE_PACE, v);
  p.vx = ux * pace; p.vz = uz * pace;
  p.hx = ux; p.hz = uz;
}

/** Knocks him down: he loses the ball. */
export function fell(s: MatchState, p: Player, hard: boolean) {
  p.act = Act.Down; p.actT = 0; p.actLen = hard ? 60 : 40; p.sub = 0;
  p.plan = null;
  if (s.ball.owner === p.i) s.ball.owner = -1;
}

// --- feints ---------------------------------------------------------------------------------------

/** Ticks a feint takes. Its second half is the burst away. */
const FEINT_LEN = 42;

export function startFeint(s: MatchState, p: Player, kind: Feint, side: number) {
  p.act = Act.Feint; p.actT = 0; p.actLen = FEINT_LEN;
  p.sub = kind; p.side = side;
  p.cool = 0;
  p.runUp = Math.sqrt(p.vx * p.vx + p.vz * p.vz);
}

/** At the feint's middle: who bites. */
export function feintBites(s: MatchState, p: Player) {
  // Sold the wrong way: a step-over goes against `side`, a roll with it.
  const way = p.sub === 2 ? -p.side : p.side;
  const right = { x: -p.hz * way, z: p.hx * way };
  for (const q of s.players) {
    if (q.team === p.team || q.role === "GK" || q.beat > 0) continue;
    const d = dist(p.x, p.z, q.x, q.z);
    if (d > 3.6) continue;
    const chance = 0.42 + p.dribble * 0.5 - q.defend * 0.32 - (d - 1.5) * 0.08 - Math.max(0, p.runUp - 5.6) * 0.14;
    if (rnd(s) < chance) {
      q.beat = 34;
      q.beatX = right.x; q.beatZ = right.z;
      s.ev.push({ t: "feint", p: p.i, beat: q.i });
    }
  }
}

export const inBox = (x: number, z: number, dir: number) => x * dir > HALF_L - BOX_D && Math.abs(z) < 20.16;

export const tickTime = (seconds: number) => Math.round(seconds / TICK);
