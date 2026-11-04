/** The goalkeepers: narrowing the angle, reading shots (a reaction, then a
 * step, a catch or a dive decided once, by how hard the shot is), coming for
 * crosses and through balls, and getting the ball back into play. */
import {
  Act, BOX_D, BOX_HALF, GOAL_H, GOAL_HALF, HALF_L, Kick, PRED_STEP, Phase, TICK,
  clamp, dirOf, dist, predAt, predict, rnd, speedOf,
  type KickPlan, type MatchState, type Player,
} from "./core";
import { laneMargin, rollPace } from "./actions";

/** The human gets this long with the ball in his hands (ticks). */
const USER_HOLD = 360;

/** How far he reaches in a dive (m) with this much time (s), from a stand. */
const DIVE_REACH = 3.3;
const DIVE_TIME = 0.5;
const HOLD_MIN = 80;
const HOLD_MAX = 150;
/** He comes off his line this far at most, by the ball's distance. */
const DEPTH_MAX = 6.5;

export const goalX = (p: Player) => -dirOf(p.team) * HALF_L;

/** Where and when the ball crosses his line, if it's going to. */
function crossing(s: MatchState, p: Player): { z: number; y: number; ticks: number } | null {
  const gx = p.x;
  const dir = dirOf(p.team);
  for (let n = 0; n < s.predN; n++) {
    const x = s.pred[n * 3];
    if ((x - gx) * dir <= 0) {
      return { z: s.pred[n * 3 + 2], y: s.pred[n * 3 + 1], ticks: (n + 1) * PRED_STEP - (s.tick - s.predFrom) };
    }
  }
  return null;
}

export function holdBall(s: MatchState, p: Player) {
  const b = s.ball;
  b.owner = p.i; b.last = p.i; b.kick = Kick.None; b.to = -1;
  b.vx = 0; b.vy = 0; b.vz = 0; b.sx = 0; b.sy = 0; b.sz = 0;
  s.poss = p.team;
  p.act = Act.Hold; p.actT = 0; p.actLen = HOLD_MIN + Math.floor(rnd(s) * (HOLD_MAX - HOLD_MIN));
  p.vx = 0; p.vz = 0;
}

/** The hit of a shot he got to. */
function saveNow(s: MatchState, p: Player) {
  const b = s.ball;
  const v = speedOf(b);
  const dir = dirOf(p.team);
  const hard = v > 22 || b.y > 1.8 || Math.abs(b.z - p.z) > 1.4;
  const hold = !hard ? rnd(s) < 0.9 : rnd(s) < 0.28 + p.save * 0.2;
  if (hold) {
    s.ev.push({ t: "save", p: p.i, held: true });
    holdBall(s, p);
    p.act = Act.Catch; p.actLen = 40;
    return;
  }
  s.ev.push({ t: "save", p: p.i, held: false });
  // Parried: out and away from the goal, or over the bar when it was high.
  const out = 0.32 + rnd(s) * 0.3;
  const side = Math.abs(b.z) < 1 ? (rnd(s) < 0.5 ? -1 : 1) : Math.sign(b.z) || 1;
  // Round the post more often than back into play.
  const round = rnd(s) < 0.5;
  b.vx = dir * v * out * (round ? 0.16 : 0.7);
  b.vz = side * v * (round ? 0.42 + rnd(s) * 0.25 : 0.2 + rnd(s) * 0.35);
  if (b.y > 2 && rnd(s) < 0.65) {
    b.vy = 5 + rnd(s) * 2;
    b.vx = -dir * 3.5;
  } else b.vy = 1.5 + rnd(s) * 3;
  b.owner = -1; b.last = p.i; b.kick = Kick.Save; b.kicker = p.i; b.to = -1; b.since = 0;
  s.prevTouch = p.i;
  predict(s);
}

/** Decided at the reaction's end: can he reach it, and does he? */
function readShot(s: MatchState, p: Player, c: { z: number; y: number; ticks: number }) {
  const dz = c.z - p.z;
  const t = c.ticks * TICK;
  const reach = DIVE_REACH * clamp(t / DIVE_TIME, 0.35, 1.05);
  const wide = Math.abs(dz) / reach;
  const b = s.ball;
  const v = speedOf(b);
  let chance = 1.1 - wide * wide * 0.5 - clamp((v - 20) * 0.022, 0, 0.3);
  // The corners are the hardest, high ones most of all.
  const corner = Math.abs(c.z) / GOAL_HALF;
  if (c.y > 1.7) chance -= corner * 0.34;
  if (c.y < 0.5) chance -= corner * 0.14;
  // From far out he sees it all the way.
  chance += clamp(t - 0.55, 0, 1) * 0.42;
  chance += (p.save - 0.75) * 0.8;
  // From distance he sees it all the way.
  chance += clamp((dist(b.fromX, b.fromZ, goalX(p), 0) - 17) * 0.035, 0, 0.5);
  p.saves = wide <= 1 && rnd(s) < chance;
  if (Math.abs(dz) < 0.85 && c.y < 2) {
    p.act = Act.Catch; p.actT = 0; p.actLen = 34;
    p.sub = c.y > 1.3 ? 2 : c.y < 0.55 ? 0 : 1;
  } else {
    p.act = Act.Dive; p.actT = 0; p.actLen = 90;
    p.side = dz > 0 ? 1 : -1;
    p.sub = c.y > 1.5 ? 2 : c.y < 0.6 ? 0 : 1;
    const speed = Math.min(Math.abs(dz) + 0.5, reach) / Math.max(0.2, t);
    p.vx = 0;
    p.vz = (dz > 0 ? 1 : -1) * clamp(speed, 2, 8);
  }
  p.hands = c.ticks;
}

/** Beyond this he throws it. */
const GROUND_MAX = 26;

/** Somebody stands in the way of the first metres of the ball. */
function inHisWay(s: MatchState, p: Player, m: Player) {
  const d = dist(p.x, p.z, m.x, m.z) || 1;
  const ux = (m.x - p.x) / d, uz = (m.z - p.z) / d;
  for (const o of s.players) {
    if (o.team === p.team) continue;
    const along = (o.x - p.x) * ux + (o.z - p.z) * uz;
    if (along < -1 || along > 13) continue;
    if (Math.abs((o.x - p.x) * uz - (o.z - p.z) * ux) < 2.8) return true;
  }
  return false;
}

function distribute(s: MatchState, p: Player) {
  const us = s.players.filter((m) => m.team === p.team && m.i !== p.i);
  const opps = s.players.filter((m) => m.team !== p.team);
  const dir = dirOf(p.team);
  let best: Player | null = null;
  let score = -1e9;
  for (const m of us) {
    const d = dist(p.x, p.z, m.x, m.z);
    if (d < 12 || d > 42 || inHisWay(s, p, m)) continue;
    let near = 1e9;
    for (const o of opps) near = Math.min(near, dist(m.x, m.z, o.x, o.z));
    // Rolled, the lane has to be clear; thrown, it only has to land free.
    if (d < GROUND_MAX && laneMargin(s, p, m.x, m.z, rollPace(d, 6)) < 0.5) continue;
    const v = Math.min(near, 12) * 2 + (m.x - p.x) * dir * 0.1 + (rnd(s) * 4 - 2);
    if (near > 6 && v > score) {
      score = v;
      best = m;
    }
  }
  if (best && dist(p.x, p.z, best.x, best.z) < 34) {
    const d = dist(p.x, p.z, best.x, best.z);
    releaseHands(s, p, best, d, false);
  } else {
    // Up the pitch: a punt onto a forward.
    let m = us[0], room = -1;
    for (const f of us) {
      if (f.role !== "ST" && f.role !== "W") continue;
      let near = 1e9;
      for (const o of opps) near = Math.min(near, dist(f.x, f.z, o.x, o.z));
      const v = near + rnd(s) * 2;
      if (v > room) { room = v; m = f; }
    }
    releaseHands(s, p, m, dist(p.x, p.z, m.x, m.z), true);
  }
}

/** Starts a keeper's distribution towards `m`. */
export function releaseHands(s: MatchState, p: Player, m: Player, d: number, punt: boolean) {
  const ground = !punt && d < GROUND_MAX;
  const plan: KickPlan = punt
    ? { kind: Kick.GkPunt, tx: m.x + dirOf(p.team) * 4, ty: 0.4, tz: m.z, speed: clamp(d * 0.42, 16, 25), curl: 0, to: m.i, err: 0.3, ground: false }
    : ground
      ? { kind: Kick.GkRoll, tx: m.x, ty: 0, tz: m.z, speed: clamp(rollPace(d, 6), 9, 21), curl: 0, to: m.i, err: 0.05, ground: true }
      : { kind: Kick.Lob, tx: m.x, ty: 0.6, tz: m.z, speed: clamp(d * 0.55, 12, 19), curl: 0, to: m.i, err: 0.1, ground: false };
  p.plan = plan;
  p.act = punt ? Act.GkKick : Act.GkThrow;
  p.actT = 0;
  p.actLen = punt ? 34 : 26;
  p.sub = ground ? 0 : 1;
}

/** One tick of a keeper's brain. */
export function thinkKeeper(s: MatchState, p: Player) {
  const b = s.ball;
  const dir = dirOf(p.team);
  const gx = goalX(p);
  if (p.act === Act.Hold) {
    // On his hands, a few steps to the edge of the area.
    p.want = 0;
    p.tx = p.x; p.tz = p.z;
    // His own side's ball is the human's: it's for him to say where it goes.
    if (s.user >= 0 && s.user !== p.i && s.players[s.user].team === p.team) {
      s.user = p.i;
      s.ev.push({ t: "switch", p: p.i });
    }
    if (s.user === p.i ? p.actT > USER_HOLD : p.actT >= p.actLen) distribute(s, p);
    return;
  }
  if (p.act === Act.GkThrow || p.act === Act.GkKick || p.act === Act.Kick) return;
  if (p.act === Act.Dive || p.act === Act.Down || p.act === Act.Getup) return;

  if (b.owner < 0 && s.phase === Phase.Play && p.act !== Act.Catch) {
    const c = crossing(s, p);
    const coming = c && Math.abs(c.z) < GOAL_HALF + 1.2 && c.y < GOAL_H + 0.8 && c.ticks < 120 && speedOf(b) > 6;
    if (coming && b.last >= 0 && (s.players[b.last].team !== p.team || b.since > 8)) {
      if (p.react < 0) p.react = Math.floor(7 + (1 - p.save) * 14 + rnd(s) * 5);
      if (p.react > 0) p.react -= 1;
      if (p.react === 0) {
        p.react = -1;
        readShot(s, p, c);
        return;
      }
      // Into line while he reads it.
      p.tx = gx + dir * 0.6; p.tz = clamp(c.z, -GOAL_HALF, GOAL_HALF); p.want = 5;
      p.faceBall = true;
      return;
    }
    p.react = -1;
    // A ball he can get to first, in his area.
    for (let t = 0; t < 100; t += 12) {
      const q = predAt(s, t);
      const inBox = (q.x - gx) * dir < BOX_D && Math.abs(q.z) < BOX_HALF;
      if (!inBox) continue;
      const mine = dist(p.x, p.z, q.x, q.z) / 6.5;
      let them = 1e9;
      for (const o of s.players) {
        if (o.team !== p.team) them = Math.min(them, dist(o.x, o.z, q.x, q.z) / 7.5);
      }
      const when = t * TICK;
      if (q.y < 3 && mine < when + 0.15 && mine < them - 0.25 && (q.x - gx) * dir < 11) {
        p.tx = q.x; p.tz = q.z; p.want = 7;
        p.faceBall = true;
        return;
      }
    }
  }

  // Narrowing the angle: on the line from the ball to the middle of the goal.
  const bx = b.x, bz = b.z;
  const toBall = dist(bx, bz, gx, 0);
  const depth = clamp(1 + (45 - toBall) * 0.09, 1, DEPTH_MAX) * (toBall < 26 ? 1 : 0.8);
  let px = gx + ((bx - gx) / (toBall || 1)) * depth;
  let pz = (bz / (toBall || 1)) * depth;
  pz = clamp(pz + bz * 0.04, -GOAL_HALF + 0.4, GOAL_HALF - 0.4);
  // A sweeper when his line is high and there's nobody behind it.
  if (toBall > 40) px = gx + dir * 9;
  // Alone against the runner: straight at him, and down at his feet.
  const carrier = b.owner >= 0 ? s.players[b.owner] : null;
  if (carrier && carrier.team !== p.team && toBall < 18) {
    let cover = 0;
    for (const o of s.players) {
      if (o.team === p.team && o.i !== p.i && (o.x - gx) * dir < (bx - gx) * dir + 0.5) cover += 1;
    }
    if (cover === 0) {
      const d = dist(p.x, p.z, bx, bz);
      px = bx - dir * 1.2; pz = bz;
      p.want = 7;
      if (d < 2.4 && p.cool === 0) {
        p.act = Act.Dive; p.actT = 0; p.actLen = 70;
        p.side = bz > p.z ? 1 : -1; p.sub = 0;
        p.saves = rnd(s) < 0.55 + p.save * 0.25 - carrier.dribble * 0.2;
        p.hands = 10;
        p.cool = 90;
      }
      p.tx = px; p.tz = pz;
      return;
    }
  }
  p.tx = px; p.tz = pz;
  p.want = 4.5;
  p.faceBall = true;
}

/** The keeper's body: dives, catches, what his hands get to. */
export function stepKeeper(s: MatchState, p: Player) {
  const b = s.ball;
  if (p.act === Act.Dive) {
    p.actT += 1;
    if (p.actT < 30) p.air = 0.5 * (p.sub === 2 ? 1 : p.sub === 1 ? 0.6 : 0.1);
    else p.air *= 0.85;
    p.x += p.vx * TICK; p.z += p.vz * TICK;
    if (p.actT > 26) p.vz *= 0.9;
    if (b.owner >= 0 && b.owner !== p.i && p.actT === p.hands) {
      if (p.saves && dist(p.x, p.z, b.x, b.z) < 2.2) {
        // Smothered at the feet.
        const c = s.players[b.owner];
        c.cool = 40;
        holdBall(s, p);
        p.act = Act.Catch; p.actLen = 30;
        s.ev.push({ t: "save", p: p.i, held: true });
      }
    } else if (b.owner < 0 && p.saves && p.actT >= Math.max(1, p.hands - 1) && p.actT <= p.hands + 5) {
      const d = dist(p.x, p.z, b.x, b.z);
      if (d < 3 && b.y < 2.8) {
        p.saves = false;
        saveNow(s, p);
        return;
      }
    }
    if (p.actT >= p.actLen) {
      p.act = Act.Getup; p.actT = 0; p.actLen = 40; p.air = 0;
    }
    return;
  }
  if (p.act === Act.Catch) {
    p.actT += 1;
    if (b.owner < 0 && p.saves && p.actT >= p.hands - 1) {
      const d = dist(p.x, p.z, b.x, b.z);
      if (d < 1.6) {
        p.saves = false;
        saveNow(s, p);
        return;
      }
    }
    if (b.owner === p.i) {
      if (p.actT >= p.actLen) {
        p.act = Act.Hold; p.actT = 0; p.actLen = HOLD_MIN + Math.floor(rnd(s) * (HOLD_MAX - HOLD_MIN));
      }
    } else if (p.actT >= p.actLen) p.act = Act.None;
    return;
  }
  // Takes a loose ball he reaches, feet or hands.
  if (b.owner < 0 && p.cool === 0 && s.phase === Phase.Play && b.since > 6) {
    const gx = goalX(p);
    const inBox = (b.x - gx) * dirOf(p.team) < BOX_D && (b.x - gx) * dirOf(p.team) > -0.2 && Math.abs(b.z) < BOX_HALF;
    if (inBox && dist(p.x, p.z, b.x, b.z) < 1.15 && b.y < 2.6 && !(b.last === p.i)) {
      const pass = b.last >= 0 && s.players[b.last].team === p.team && b.kick !== Kick.Header;
      if (!pass) {
        s.ev.push({ t: "save", p: p.i, held: true });
        holdBall(s, p);
        p.act = Act.Catch; p.actLen = 36; p.sub = b.y > 1.2 ? 2 : 0;
      }
    }
  }
  if (p.act === Act.Hold) {
    p.actT += 1;
    b.x = p.x + p.hx * 0.3; b.z = p.z + p.hz * 0.3; b.y = 1.05;
  }
}

export const keeperSpot = (p: Player, s: MatchState) => {
  const gx = goalX(p);
  return { x: gx + dirOf(p.team) * 1.1, z: clamp(s.ball.z * 0.05, -2, 2) };
};
