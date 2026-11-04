/** The footballers' heads. The team keeps a shape that breathes with the ball
 * (compact without it, wide and high with it, the back line holding offside);
 * who presses, who covers and who marks is settled a few times a second; the
 * forwards time runs on the line; the man on the ball weighs a shot against
 * every pass and against carrying it on. */
import {
  TICK, Act, BOX_D, GOAL_HALF, HALF_L, HALF_W, Kick, Phase,
  clamp, dirOf, dist, dist2, predAt, rnd, rndN, segDist2,
  type Feint, type MatchState, type Player, type SetPiece,
} from "./core";
import {
  nearestOpp, offsideLine, planClear, planCross, planLob, planPass, planShot, planThrough, rollPace, rollTime, startFeint, startKick, startSlide, startTackle,
} from "./actions";
import { goalX, keeperSpot, thinkKeeper } from "./keeper";

/** A slot of the shape: x is up the pitch (own goal −52.5), z across, for
 * the ball on the centre spot. */
type Slot = { ax: number; z: number; role: Player["role"] };

export const FORMATIONS: Record<"433" | "442", Slot[]> = {
  "433": [
    { ax: -50, z: 0, role: "GK" },
    { ax: -20, z: -25, role: "FB" }, { ax: -26, z: -9, role: "CB" }, { ax: -26, z: 9, role: "CB" }, { ax: -20, z: 25, role: "FB" },
    { ax: -13, z: 0, role: "DM" }, { ax: -3, z: -13, role: "CM" }, { ax: -3, z: 13, role: "CM" },
    { ax: 15, z: -25, role: "W" }, { ax: 20, z: 0, role: "ST" }, { ax: 15, z: 25, role: "W" },
  ],
  "442": [
    { ax: -50, z: 0, role: "GK" },
    { ax: -20, z: -25, role: "FB" }, { ax: -26, z: -9, role: "CB" }, { ax: -26, z: 9, role: "CB" }, { ax: -20, z: 25, role: "FB" },
    { ax: -5, z: -26, role: "W" }, { ax: -9, z: -8, role: "CM" }, { ax: -9, z: 8, role: "CM" }, { ax: -5, z: 26, role: "W" },
    { ax: 17, z: -7, role: "ST" }, { ax: 19, z: 7, role: "ST" },
  ],
};

const JOG = 4.2;
const RUN = 6.2;
/** His top sprint (m/s). */
export const sprintOf = (p: Player) => 7.1 + p.pace * 1.5;

/** Time for him to get to a point (s). */
const reachTime = (p: Player, x: number, z: number) => dist(p.x, p.z, x, z) / sprintOf(p) + 0.12;

// --- the team --------------------------------------------------------------------------------------

export function thinkTeam(s: MatchState, team: 0 | 1) {
  const b = s.ball;
  const men = s.players.filter((p) => p.team === team);
  const others = s.players.filter((p) => p.team !== team);
  for (const m of men) { m.duty = 0; m.mark = -1; }
  const outfield = men.filter((m) => m.role !== "GK" && m.act !== Act.Down && m.act !== Act.Getup && m.act !== Act.Slide);

  if (b.owner < 0) {
    // First to the ball's path.
    let bestT = 1e9, best = -1;
    for (const m of outfield) {
      let t = 1e9;
      for (let k = 6; k < 170; k += 8) {
        const q = predAt(s, k);
        const when = k * TICK;
        if (q.y > 2.7) continue;
        if (reachTime(m, q.x, q.z) <= when + 0.1) {
          t = when;
          break;
        }
      }
      if (t === 1e9) t = 4 + reachTime(m, b.x, b.z);
      if (t < bestT) { bestT = t; best = m.i; }
    }
    if (b.to >= 0 && s.players[b.to].team === team && s.players[b.to].act !== Act.Down) best = b.to;
    s.chaser[team] = best;
    if (best >= 0) s.players[best].duty = 1;
    return;
  }
  s.chaser[team] = -1;
  const carrier = s.players[b.owner];
  if (carrier.team === team) return;

  // Without it: the nearest goes, the next covers; the rest pick up men.
  const byDist = [...outfield].sort((p, q) => dist2(p.x, p.z, b.x, b.z) - dist2(q.x, q.z, b.x, b.z));
  const ax = b.x * dirOf(team);
  const pressing = ax < 20 ? 1 : dist(byDist[0].x, byDist[0].z, b.x, b.z) < 26 ? 1 : 0;
  if (pressing && byDist[0]) byDist[0].duty = 1;
  if (byDist[1] && dist(byDist[1].x, byDist[1].z, b.x, b.z) < 16) byDist[1].duty = 2;
  // The human called a second man: the nearest who isn't him goes at the ball.
  if (s.contain && s.user >= 0 && s.players[s.user].team === team) {
    const helper = byDist.find((m) => m.i !== s.user);
    if (helper) helper.duty = 1;
  }
  const free = outfield.filter((m) => m.duty === 0);
  const danger = others
    .filter((o) => o.role !== "GK" && o.i !== carrier.i && o.x * dirOf(team) < 12)
    .sort((p, q) => p.x * dirOf(team) - q.x * dirOf(team));
  for (const o of danger) {
    let at = -1, near = 26;
    free.forEach((m, n) => {
      if (m.mark < 0) {
        const d = dist(m.x, m.z, o.x, o.z);
        if (d < near) { near = d; at = n; }
      }
    });
    if (at >= 0) free[at].mark = o.i;
  }
}

/** Where his place in the shape is right now. */
function shapeSpot(s: MatchState, p: Player, slot: Slot): { x: number; z: number } {
  const dir = dirOf(p.team);
  const b = s.ball;
  const ballAx = b.x * dir;
  const has = s.poss === p.team;
  const block = has ? clamp(ballAx * 0.62 + 9, -20, 26) : clamp(ballAx * 0.62 - 7, -27, 15);
  const compress = has ? 1.05 : 0.7;
  let ax = block + slot.ax * compress;
  const line = offsideLine(s, p.team);
  const back = -offsideLine(s, p.team === 0 ? 1 : 0);
  const wide = has ? 1.02 : 0.74;
  let z = slot.z * wide + clamp(b.z, -24, 24) * (has ? 0.2 : 0.42);
  if (slot.role === "CB" || slot.role === "FB") {
    if (!has) ax = Math.min(ax, ballAx - 2);
    ax = Math.max(ax, -HALF_L + 8);
    // The line holds together, a bit behind the block, never deep for no reason.
    if (has) ax = Math.min(ax, ballAx - 1 + (slot.role === "FB" ? 14 : 0));
  }
  if (!has) ax = Math.min(ax, ballAx + 18);
  ax = Math.min(ax, Math.max(line - 0.7, ballAx));
  if (has && slot.role !== "CB") ax = Math.max(ax, back);
  z = clamp(z, -HALF_W + 2, HALF_W - 2);
  return { x: ax * dir, z };
}

// --- without the ball ---------------------------------------------------------------------------------

/** A run: into the channel behind the line, or to where he's open. */
function chooseRun(s: MatchState, p: Player, home: { x: number; z: number }) {
  const dir = dirOf(p.team);
  const b = s.ball;
  const line = offsideLine(s, p.team);
  const opps = s.players.filter((o) => o.team !== p.team);
  let best = -1e9, bx = home.x, bz = home.z;
  const forward = p.role === "ST" || p.role === "W";
  const offers = forward ? 8 : 6;
  for (let n = 0; n < offers; n++) {
    let cx = home.x, cz = home.z;
    if (n === 1) { cx += dir * 6; }
    else if (n === 2) { cx += dir * 3; cz += 7; }
    else if (n === 3) { cx += dir * 3; cz -= 7; }
    else if (n === 4) { cx = b.x - dir * 6; cz = b.z + (home.z > b.z ? 10 : -10); }
    else if (n === 5) { cx = b.x + dir * 8; cz = b.z + (home.z > b.z ? 12 : -12); }
    else if (n === 6) { cx = (line - 0.6) * dir; cz = clamp(p.z + (p.z > 0 ? -6 : 6), -22, 22); }
    else if (n === 7) { cx = (line - 0.6) * dir; cz = clamp(home.z * 0.75, -26, 26); }
    cx = clamp(cx, -HALF_L + 2, HALF_L - 2);
    cz = clamp(cz, -HALF_W + 1.5, HALF_W - 1.5);
    if (cx * dir > line - 0.4) cx = (line - 0.5) * dir;
    let near = 1e9, lane = 1e9;
    for (const o of opps) {
      near = Math.min(near, dist2(o.x, o.z, cx, cz));
      if (o.role !== "GK") lane = Math.min(lane, segDist2(b.x, b.z, cx, cz, o.x, o.z));
    }
    const fromBall = dist(b.x, b.z, cx, cz);
    const v = Math.min(Math.sqrt(near), 10) * 0.5 + Math.min(Math.sqrt(lane), 5) * 0.8
      + ((cx - b.x) * dir) * 0.09 - Math.abs(fromBall - 16) * 0.07 - dist(p.x, p.z, cx, cz) * 0.05 + rnd(s) * 1.4;
    if (v > best) { best = v; bx = cx; bz = cz; }
  }
  p.runX = bx; p.runZ = bz; p.runT = 50 + Math.floor(rnd(s) * 60);
}

export function thinkOffBall(s: MatchState, p: Player, slot: Slot) {
  const b = s.ball;
  const dir = dirOf(p.team);
  const home = shapeSpot(s, p, slot);
  const has = s.poss === p.team;
  p.faceBall = false;

  if (p.duty === 1 && b.owner < 0) {
    // After the ball: where he can cut it off.
    let q = predAt(s, 0);
    for (let k = 6; k < 170; k += 8) {
      const c = predAt(s, k);
      q = c;
      if (reachTime(p, c.x, c.z) <= k * TICK + 0.1) break;
    }
    p.tx = q.x; p.tz = q.z; p.want = sprintOf(p);
    return;
  }

  if (has) {
    if (b.owner === p.i) return;
    p.runT -= 12;
    if (p.runT <= 0) chooseRun(s, p, home);
    const urgent = dist(p.x, p.z, p.runX, p.runZ) > 7;
    p.tx = p.runX; p.tz = p.runZ;
    p.want = urgent ? RUN : JOG;
    // Late into the channel: full pace once the line can be beaten.
    const line = offsideLine(s, p.team);
    if ((p.role === "ST" || p.role === "W") && Math.abs(p.runX * dir - (line - 0.5)) < 1.5 && b.owner >= 0) {
      p.want = sprintOf(p) - 0.6;
    }
    if (b.to === p.i) p.want = sprintOf(p);
    return;
  }

  // Defending.
  const c = b.owner >= 0 ? s.players[b.owner] : null;
  if (p.duty === 1 && c) {
    const gx = goalX(p);
    const gd = dist(c.x, c.z, gx, 0) || 1;
    const stand = dist(p.x, p.z, c.x, c.z) < 5 ? 1.2 : 0.6;
    p.tx = c.x + c.vx * 0.25 + ((gx - c.x) / gd) * stand;
    p.tz = c.z + c.vz * 0.25 + (-c.z / gd) * stand;
    const d = dist(p.x, p.z, c.x, c.z);
    p.want = d > 6 ? sprintOf(p) : d > 3 ? RUN : JOG + 1.4;
    p.faceBall = d < 5;
    return;
  }
  if (p.duty === 2 && c) {
    // Behind the presser, in the way of the likely pass.
    const gx = goalX(p);
    const gd = dist(c.x, c.z, gx, 0) || 1;
    p.tx = c.x + ((gx - c.x) / gd) * 6;
    p.tz = c.z + (-c.z / gd) * 6;
    p.want = RUN;
    p.faceBall = true;
    return;
  }
  if (p.mark >= 0) {
    const m = s.players[p.mark];
    const gx = goalX(p);
    const gd = dist(m.x, m.z, gx, 0) || 1;
    const close = m.x * dir < -28 ? 1.4 : 3;
    p.tx = m.x + ((gx - m.x) / gd) * close;
    p.tz = m.z + (-m.z / gd) * close;
    p.tx = p.tx * 0.7 + home.x * 0.3;
    p.tz = p.tz * 0.7 + home.z * 0.3;
    p.want = RUN;
    p.faceBall = true;
    return;
  }
  p.tx = home.x; p.tz = home.z;
  p.want = dist(p.x, p.z, home.x, home.z) > 6 ? RUN : JOG;
  p.faceBall = true;
}

/** Defenders on their feet go in when they can, at their own judgement. */
export function thinkTackle(s: MatchState, p: Player) {
  const b = s.ball;
  if (b.owner < 0 || p.cool > 0 || p.act !== Act.None) return;
  const c = s.players[b.owner];
  if (c.team === p.team || c.act === Act.Hold) return;
  const d = dist(p.x, p.z, b.x, b.z);
  if (d < 1.45 && rnd(s) < 0.1 + p.defend * 0.14) startTackle(p);
  else if (d < 3 && d > 1.6 && p.defend > 0.6 && p.vx * c.vx + p.vz * c.vz > 12 && rnd(s) < 0.015 && p.x * dirOf(p.team) > -36) startSlide(p);
}

// --- on the ball --------------------------------------------------------------------------------------

/** How good a shot is from here (an xG, more or less). */
export function shotValue(s: MatchState, p: Player): { xg: number; aim: number } {
  const dir = dirOf(p.team);
  const gx = dir * HALF_L;
  const a = HALF_L - p.x * dir;
  const d = dist(p.x, p.z, gx, 0);
  if (d > 36 || a < 0.5) return { xg: 0, aim: 0 };
  const seen = (2 * GOAL_HALF * a) / (d * d);
  let xg = clamp(seen * Math.sqrt(seen) * 0.85, 0.002, 0.6) * (0.5 + p.shot * 0.7);
  const k = s.players.find((q) => q.team !== p.team && q.role === "GK");
  // The side the keeper leaves open.
  let aim = k ? (k.z >= p.z * 0.1 ? -0.8 : 0.8) : 0.8;
  if (k && Math.abs(k.z) < 0.3) aim = p.z >= 0 ? -0.8 : 0.8;
  const tz = aim * GOAL_HALF;
  for (const o of s.players) {
    if (o.team === p.team || o.role === "GK") continue;
    const q = segDist2(p.x, p.z, gx, tz, o.x, o.z);
    if (q < 0.8) xg *= 0.5;
    else if (q < 2) xg *= 0.8;
  }
  const near = nearestOpp(s, p).d;
  if (near < 1.4) xg *= 0.72;
  if (k) {
    const off = dist(k.x, k.z, gx, 0);
    if (off > 7) xg *= 1.6;
  }
  return { xg, aim };
}

/** How safely a ball rolls from him to (x, z): above 0 it gets there first. */
function laneMargin(s: MatchState, p: Player, x: number, z: number, pace: number): number {
  const d = dist(p.x, p.z, x, z) || 1;
  let worst = 9;
  for (const o of s.players) {
    if (o.team === p.team) continue;
    const dx = x - p.x, dz = z - p.z;
    const u = clamp(((o.x - p.x) * dx + (o.z - p.z) * dz) / (d * d), 0.05, 1);
    const along = d * u;
    const time = rollTime(pace, along);
    const off = dist(p.x + dx * u, p.z + dz * u, o.x, o.z);
    const m = off - 0.9 - time * sprintOf(o) * 0.82;
    if (m < worst) worst = m;
  }
  return worst;
}

type Option = { v: number; go: () => void };

export function thinkCarrier(s: MatchState, p: Player) {
  const b = s.ball;
  const dir = dirOf(p.team);
  const ax = p.x * dir;
  const pressed = nearestOpp(s, p);
  const near = pressed.d;
  const gx = dir * HALF_L;

  // Deep and hunted: into the stands.
  if (ax < -36 && near < 2.2 && rnd(s) < 0.35) {
    startKick(s, p, planClear(s, p));
    return;
  }

  // Shooting.
  const shot = shotValue(s, p);
  const wide = Math.abs(p.z) > 22;
  const lim = dist(p.x, p.z, gx, 0) < 19 ? 0.09 : 0.025 + (1 - p.shot) * 0.07;
  if (shot.xg > lim + rnd(s) * (near < 4 ? 0.03 : 0.07) && !(wide && ax > 40)) {
    const power = clamp(0.45 + dist(p.x, p.z, gx, 0) * 0.021 + rnd(s) * 0.12, 0.4, 0.97);
    const curl = dist(p.x, p.z, gx, 0) > 15 && rnd(s) < 0.4 ? (p.z * dir > 0 ? 0.7 : -0.7) : 0;
    startKick(s, p, planShot(s, p, shot.aim + rndN(s) * 0.15, power, curl, false));
    return;
  }

  const options: Option[] = [];
  const line = offsideLine(s, p.team);
  for (const m of s.players) {
    if (m.team !== p.team || m.i === p.i || m.act === Act.Down || m.off) continue;
    const d0 = dist(p.x, p.z, m.x, m.z);
    if (d0 < 4) continue;
    const maxD = m.role === "GK" ? 22 : p.pass > 0.7 ? 44 : 36;
    if (d0 > maxD) continue;
    if (m.role === "GK" && (near > 3 || ax > -18)) continue;
    const aheadOfLine = m.x * dir > line;
    if (aheadOfLine) continue;
    const pace = clamp(rollPace(d0, 8), 8, 24);
    const t = rollTime(pace, d0);
    const mx = m.x + m.vx * t * 0.8, mz = m.z + m.vz * t * 0.8;
    const margin = laneMargin(s, p, mx, mz, pace);
    let open = 1e9;
    for (const o of s.players) if (o.team !== p.team) open = Math.min(open, dist(o.x, o.z, mx, mz));
    const gain = (mx - p.x) * dir;
    let v = gain * 0.16 + Math.min(open, 8) * 0.28 + clamp(margin, -3, 1.2) * 1.6 - d0 * 0.02 + rnd(s) * 1.1;
    if (mx * dir > HALF_L - 22 && Math.abs(mz) < 18) v += 1.1;
    if (near < 2.2) v += 1.2;
    if (d0 < 30 && margin > 0.2) options.push({ v, go: () => startKick(s, p, planPass(s, p, m, clamp(d0 / 34, 0.2, 0.9))) });
    else if (d0 >= 30 && margin > -1) {
      options.push({ v: v - 1.2, go: () => startKick(s, p, planLob(s, p, mx, mz, m.i, 0.5)) });
    } else if (margin < 0.2 && d0 > 14) {
      options.push({ v: v - 0.5 + Math.min(open, 8) * 0.1, go: () => startKick(s, p, planLob(s, p, mx, mz, m.i, 0.5)) });
    }
    // The ball behind them for a man running on to it.
    const runner = (m.role === "ST" || m.role === "W" || m.role === "CM") && (m.x - p.x) * dir > 2;
    if (runner) {
      const plan = planThrough(s, p, m, 0.5);
      const mine = reachTime(m, plan.tx, plan.tz);
      let them = 1e9;
      for (const o of s.players) if (o.team !== p.team) them = Math.min(them, reachTime(o, plan.tx, plan.tz));
      const lm = laneMargin(s, p, plan.tx, plan.tz, plan.speed);
      if (mine < them + 0.15 && lm > -0.4 && plan.tx * dir > line - 8) {
        options.push({ v: 2.9 + (plan.tx - p.x) * dir * 0.05 + lm * 0.4 + rnd(s) * 1.5, go: () => startKick(s, p, plan) });
      }
    }
  }
  // A cross when wide near the byline.
  if (Math.abs(p.z) > 12 && ax > HALF_L - 34) {
    let men = 0, bx = 0, bz = 0, bi = -1;
    for (const m of s.players) {
      if (m.team !== p.team || m.role === "GK" || m.i === p.i) continue;
      if (m.x * dir > HALF_L - 22 && Math.abs(m.z) < 14) {
        men += 1;
        if (bi < 0 || rnd(s) < 0.4) { bx = m.x + dir * 2; bz = m.z; bi = m.i; }
      }
    }
    if (men > 0) {
      const plan = planCross(s, p, bx, bz, bi, 0.6);
      options.push({ v: 1.9 + men * 0.42 + (ax - 30) * 0.05 + rnd(s), go: () => startKick(s, p, plan) });
    }
  }

  // Carrying it: the best of eight ways against everyone near.
  let carryV = -1e9, ux = dir, uz = 0;
  for (let w = 0; w < 8; w++) {
    const cx = w === 0 || w === 1 || w === 7 ? 0.8 : w === 3 || w === 4 || w === 5 ? -0.8 : 0;
    const cz = w >= 1 && w <= 3 ? 0.8 : w >= 5 ? -0.8 : 0;
    const qx = p.x + cx * 7, qz = p.z + cz * 7;
    if (Math.abs(qz) > HALF_W - 1.5 || Math.abs(qx) > HALF_L - 1.5) continue;
    let room = 1e9;
    for (const o of s.players) if (o.team !== p.team) room = Math.min(room, dist2(o.x, o.z, qx, qz));
    let v = Math.min(Math.sqrt(room), 9) * 0.26 + cx * dir * 1.4;
    if (ax > HALF_L - 30) v += (-Math.sign(p.z) * cz) * 0.5;
    if (v > carryV) { carryV = v; ux = cx; uz = cz; }
  }
  const carry = carryV * 0.9 + (near > 5 ? 1 : 0) + rnd(s) * 0.7 + p.dribble * 0.6 + (b.since < 24 ? 0.9 : 0);

  let bestV = carry, go: (() => void) | null = null;
  for (const o of options) if (o.v > bestV) { bestV = o.v; go = o.go; }
  if (go) {
    go();
    return;
  }

  // On he goes; a feint if someone stands in the way.
  p.tx = p.x + ux * 7; p.tz = p.z + uz * 7;
  p.want = near < 3 ? RUN : sprintOf(p) - (p.dribble < 0.75 ? 1.3 : 0.6);
  const inFront = pressed.o && (pressed.o.x - p.x) * p.hx + (pressed.o.z - p.z) * p.hz > 0.4;
  if (near < 2.8 && inFront && p.dribble > 0.68 && rnd(s) < 0.1 + p.dribble * 0.1) {
    const r = rnd(s);
    const kind = (r < 0.45 ? 0 : r < 0.75 ? 2 : r < 0.9 ? 3 : 1) as Feint;
    startFeint(s, p, kind, rnd(s) < 0.5 ? 1 : -1);
  }
}

// --- set pieces -----------------------------------------------------------------------------------------

/** Where he goes for the restart. */
export function setPieceSpot(s: MatchState, p: Player, slot: Slot, set: SetPiece): { x: number; z: number } {
  const dir = dirOf(p.team);
  const attacking = set.team === p.team;
  const n = p.slot;
  if (set.kind === "kickoff") {
    const home = { x: (slot.ax * 0.8 - 8) * dir, z: slot.z * 0.9 };
    home.x = Math.min(home.x * dir, -1) * dir;
    if (attacking && slot.role === "ST") return { x: -dir * 2, z: n % 2 ? 7 : -7 };
    return home;
  }
  if (set.kind === "penalty") {
    if (attacking) return { x: dir * (HALF_L - 20 + (n % 3)), z: (n - 5) * 3 };
    return { x: dir * -(HALF_L - 20 + (n % 3)), z: (n - 5) * 3 + 1 };
  }
  if (set.kind === "goalkick") {
    if (attacking) return { x: dir * clamp(slot.ax + 12, -36, 18), z: slot.z * 1.05 };
    return { x: dir * clamp(slot.ax + 12, -24, 30), z: slot.z * 0.9 };
  }
  if (set.kind === "corner") {
    const gx = set.x > 0 ? 1 : -1;
    const toGoal = (d: number, z: number) => ({ x: gx * (HALF_L - d), z });
    if (attacking) {
      const zones: [number, number][] = [[5, -2], [7, 4], [10, -6], [12, 1], [15, 7], [17, -3]];
      const role = slot.role;
      if (role === "CB" || role === "ST" || role === "W" || role === "CM") {
        const z = zones[n % zones.length];
        return toGoal(z[0], z[1] * (set.z > 0 ? 1 : -1));
      }
      if (role === "FB" || role === "DM") return toGoal(24 + n, n % 2 ? 10 : -10);
      return { x: -gx * 30, z: 0 };
    }
    const zones: [number, number][] = [[1.5, 4], [1.5, -4], [5, 3], [5, -3], [6, 0], [8, 6], [8, -6], [11, 0], [13, 8], [14, -8]];
    if (slot.role === "GK") return toGoal(1, 0);
    return (() => { const z = zones[(n - 1) % zones.length]; return toGoal(z[0], z[1]); })();
  }
  if (set.kind === "throw") {
    const home = shapeSpot(s, p, slot);
    if (attacking && dist(p.x, p.z, set.x, set.z) < 22) {
      return { x: clamp(set.x + dir * ((n % 3) * 7 - 5), -HALF_L + 2, HALF_L - 2), z: set.z * 0.72 + (n % 2) * 3 };
    }
    return { x: home.x * 0.6 + set.x * 0.4, z: home.z * 0.6 + set.z * 0.4 };
  }
  // A free kick.
  const home = shapeSpot(s, p, slot);
  const near = HALF_L - set.x * dirOf(set.team);
  if (!attacking && near < 32 && Math.abs(set.z) < 26 && n >= 1 && n <= 4) {
    // The wall.
    const gx = dirOf(set.team) * HALF_L;
    const d = dist(set.x, set.z, gx, 0) || 1;
    const ux = (gx - set.x) / d, uz = -set.z / d;
    return { x: set.x + ux * 9.15 - uz * (n - 2.5) * 0.7, z: set.z + uz * 9.15 + ux * (n - 2.5) * 0.7 };
  }
  if (attacking && near < 40 && (slot.role === "ST" || slot.role === "CB" || slot.role === "W")) {
    return { x: dirOf(set.team) * (HALF_L - 10 - (n % 5)), z: ((n * 7) % 24) - 12 };
  }
  return home;
}

/** What the AI taker does. */
export function takeSetPiece(s: MatchState, p: Player, set: SetPiece) {
  const dir = dirOf(p.team);
  const mates = s.players.filter((m) => m.team === p.team && m.i !== p.i && m.role !== "GK");
  const nearest = (lim: number) => {
    let best: Player | null = null, v = -1e9;
    for (const m of mates) {
      const d = dist(p.x, p.z, m.x, m.z);
      if (d > lim || d < 3) continue;
      let open = 1e9;
      for (const o of s.players) if (o.team !== p.team) open = Math.min(open, dist(o.x, o.z, m.x, m.z));
      const q = open + (m.x - p.x) * dir * 0.1 + rnd(s) * 2;
      if (q > v) { v = q; best = m; }
    }
    return best;
  };
  if (set.kind === "kickoff") {
    const m = nearest(14) ?? mates[0];
    startKick(s, p, planPass(s, p, m, 0.4));
    return;
  }
  if (set.kind === "penalty") {
    startKick(s, p, planShot(s, p, rnd(s) < 0.5 ? -0.8 : 0.8, 0.75, 0, false));
    return;
  }
  if (set.kind === "corner") {
    const box = mates.filter((m) => Math.abs(m.x) > HALF_L - BOX_D && Math.abs(m.z) < 16);
    const t = box.length ? box[Math.floor(rnd(s) * box.length)] : mates[0];
    startKick(s, p, planCross(s, p, t.x, t.z, t.i, 0.6, Kick.Corner));
    return;
  }
  if (set.kind === "throw") {
    const m = nearest(20) ?? mates[0];
    const d = dist(p.x, p.z, m.x, m.z);
    startKick(s, p, { kind: Kick.Throw, tx: m.x, ty: 0.9, tz: m.z, speed: clamp(d * 0.5 + 5, 8, 15), curl: 0, to: m.i, err: 0.1, ground: false });
    return;
  }
  if (set.kind === "goalkick") {
    const m = nearest(30);
    if (m) startKick(s, p, planPass(s, p, m, 0.6));
    else {
      const fwd = mates.filter((q) => q.role === "ST" || q.role === "W");
      const t = fwd[Math.floor(rnd(s) * fwd.length)] ?? mates[0];
      const plan = planLob(s, p, t.x, t.z, t.i, 0.8);
      startKick(s, p, { ...plan, speed: 24, kind: Kick.GkPunt });
    }
    return;
  }
  // A free kick: at goal from shooting range, else in to the box or short.
  const d = dist(p.x, p.z, dir * HALF_L, 0);
  if (d < 28 && Math.abs(p.z) < 22) {
    startKick(s, p, planShot(s, p, p.z >= 0 ? -0.75 : 0.75, 0.72, p.z * dir >= 0 ? 0.8 : -0.8, false));
    return;
  }
  if (d < 42) {
    const box = mates.filter((m) => m.x * dir > HALF_L - 20);
    if (box.length) {
      const t = box[Math.floor(rnd(s) * box.length)];
      startKick(s, p, planCross(s, p, t.x, t.z, t.i, 0.5));
      return;
    }
  }
  const m = nearest(26) ?? mates[0];
  startKick(s, p, planPass(s, p, m, 0.5));
}

export function thinkPlayer(s: MatchState, p: Player, slot: Slot) {
  if (p.role === "GK") {
    if (s.phase === Phase.Dead && s.set) {
      if (s.set.kind === "goalkick" && s.set.team === p.team) return;
      if (s.set.kind === "corner") {
        const sp = setPieceSpot(s, p, slot, s.set);
        p.tx = sp.x; p.tz = sp.z; p.want = 4;
        return;
      }
      const sp = keeperSpot(p, s);
      p.tx = sp.x; p.tz = sp.z; p.want = 4;
      p.faceBall = true;
      return;
    }
    thinkKeeper(s, p);
    return;
  }
  if (s.phase === Phase.Dead || s.phase === Phase.Kickoff) {
    const set = s.set;
    if (!set) return;
    if (set.taker === p.i) return;
    const sp = setPieceSpot(s, p, slot, set);
    p.tx = sp.x; p.tz = sp.z;
    const d = dist(p.x, p.z, sp.x, sp.z);
    p.want = d > 8 ? RUN : d > 1.5 ? JOG : 0;
    p.faceBall = d < 3;
    return;
  }
  thinkOffBall(s, p, slot);
}
