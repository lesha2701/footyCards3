/** The footballers' heads. The team keeps a shape that breathes with the ball
 * (three flat lines of zones without it, a build-up from the back and a full box with it, the back line holding offside);
 * one man presses, one covers, and everybody else holds his zone and picks up
 * whoever is free in it, a few times a second; the
 * forwards time runs on the line; the man on the ball weighs a shot against
 * every pass and against carrying it on. */
import {
  TICK, Act, BOX_D, GOAL_HALF, HALF_L, HALF_W, Kick, Phase,
  clamp, dirOf, dist, dist2, predAt, rnd, rndN, segDist2,
  type Feint, type MatchState, type Player, type SetPiece,
} from "./core";
import {
  laneMargin, nearestOpp, offsideLine, planClear, planCross, planLob, planPass, planShot, planThrough, rollPace, rollTime, sprintOf, startFeint, startKick, startSlide, startTackle,
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

/** A man stands this far from the centre at a kick-off (the circle is 9.15 m). */
const CIRCLE_CLEAR = 10.2;
const JOG = 4.2;
/** A carrier under this pace (m/s) for a while after his touch is standing on it. */
const STILL = 2.2;
const STILL_AFTER = 50;
export const standing = (s: MatchState, c: Player) => s.ball.since > STILL_AFTER && c.vx * c.vx + c.vz * c.vz < STILL * STILL;
/** How far a foot gets round a man standing on the ball, the ball measured from the tackler (m). */
export const STILL_REACH = 2.1;
const RUN = 6.2;
/** Time for him to get to a point (s). */
const reachTime = (p: Player, x: number, z: number) => dist(p.x, p.z, x, z) / sprintOf(p) + 0.12;

// --- the team --------------------------------------------------------------------------------------

export function thinkTeam(s: MatchState, team: 0 | 1, slots: readonly Slot[]) {
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
  const ax = b.x * dirOf(team);
  // In front of the back four it's the midfield's ball: they don't step out for it.
  const hunting = pressingHigh(s, team);
  const high = ax > backLine(ax, hunting) + 9;
  const cost = (p: Player) => dist(p.x, p.z, b.x, b.z) + (high && (p.role === "CB" || p.role === "FB") ? 12 : 0);
  const byDist = [...outfield].sort((p, q) => cost(p) - cost(q));
  // Deep in their half the block waits; a man who just stands there gets closed down anyway.
  const pressing = ax < 20 || b.since > 150 || dist(byDist[0].x, byDist[0].z, b.x, b.z) < 26 ? 1 : 0;
  if (pressing && byDist[0]) byDist[0].duty = 1;
  if (byDist[1] && dist(byDist[1].x, byDist[1].z, b.x, b.z) < 16) byDist[1].duty = 2;
  // One presses and one covers, the zones hold. Nobody watches a man run past
  // him all the same: the ball comes within a stride and he steps in, and close
  // to our goal it's two on him. Never a third.
  if (ax < -28 && byDist[1] && dist(byDist[1].x, byDist[1].z, b.x, b.z) < 14) byDist[1].duty = 1;
  for (const m of outfield) {
    if (dist(m.x, m.z, b.x, b.z) < 3 && outfield.filter((q) => q.duty === 1).length < 2) m.duty = 1;
  }
  // Just lost it up the pitch: the two nearest go at once, before it gets away.
  if (s.tick - s.lostAt[team] < 150 && ax > -12 && byDist[1]) byDist[1].duty = 1;
  // The human called a second man: the nearest who isn't him goes at the ball.
  if (s.contain && s.user >= 0 && s.players[s.user].team === team) {
    const helper = byDist.find((m) => m.i !== s.user);
    if (helper) helper.duty = 1;
  }
  // The rest are zones: the most dangerous free man first, picked up by whoever
  // has him in his zone, measured from the zone and not from where he stands.
  const free = outfield.filter((m) => m.duty === 0);
  const dirT = dirOf(team);
  const danger = others
    .filter((o) => o.role !== "GK" && o.i !== carrier.i)
    .map((o) => ({ o, v: dist(o.x, o.z, -dirT * HALF_L, 0) * 0.6 + dist(o.x, o.z, b.x, b.z) * 0.4 }))
    .sort((p, q) => p.v - q.v || p.o.i - q.o.i);
  const reach = hunting ? 20 : 15;
  for (const { o } of danger) {
    let at = -1, near = reach;
    free.forEach((m, n) => {
      if (m.mark >= 0) return;
      const z = blockSpot(m, slots[m.slot], b.x, b.z, hunting);
      const d = dist(z.x, z.z, o.x, o.z) + dist(m.x, m.z, o.x, o.z) * 0.25;
      if (d < near) { near = d; at = n; }
    });
    if (at >= 0) free[at].mark = o.i;
  }
}

/** The ball in their third and not in their keeper's hands: we go and get it. */
function pressingHigh(s: MatchState, team: 0 | 1) {
  const b = s.ball;
  if (b.x * dirOf(team) < 16) return false;
  return !(b.owner >= 0 && s.players[b.owner].act === Act.Hold);
}

/** The back four's line without the ball, flat, up the pitch from their goal. */
function backLine(ax: number, high: boolean) {
  return clamp(ax - 22, -HALF_L + 9, high ? 5 : -7);
}

/** How far ahead of the back line each role keeps without the ball. */
const LINE_GAP: Record<Player["role"], number> = { GK: 0, CB: 0, FB: 0, DM: 7, CM: 13, W: 15, ST: 27 };

/** Without the ball: three lines, flat and close, sliding together to the ball.
 * High up they stretch and go wider, each man near one to press. */
function blockSpot(p: Player, slot: Slot, ballX: number, ballZ: number, high: boolean) {
  const dir = dirOf(p.team);
  const ax = Math.max(backLine(ballX * dir, high), -HALF_L + 5) + LINE_GAP[slot.role] * (high ? 1.25 : 1);
  const z = slot.z * (high ? 0.9 : 0.74) + clamp(ballZ, -26, 26) * (high ? 0.25 : 0.42);
  return { x: ax * dir, z: clamp(z, -HALF_W + 3, HALF_W - 3) };
}

/** Playing out from the back: the centre-backs split to the edges of the box,
 * the holding man drops between them, the full-backs go high and wide, the
 * midfield offers in the half-spaces, the front men pin the line. */
function buildSpot(s: MatchState, p: Player, slot: Slot) {
  const side = slot.z > 0 ? 1 : slot.z < 0 ? -1 : 0;
  let ax: number, z: number;
  switch (slot.role) {
    case "CB": ax = -38; z = side * 15; break;
    case "FB": ax = -24; z = side * 31; break;
    case "DM": ax = -31; z = clamp(s.ball.z * 0.25, -6, 6); break;
    case "CM": ax = slot.ax > -6 ? -15 : -24; z = side * (slot.ax > -6 ? 13 : 11); break;
    case "W": ax = slot.ax > 0 ? 4 : -8; z = side * 30; break;
    default: ax = 10; z = side * 8;
  }
  return { ax, z };
}

/** Where his place in the shape is right now. */
function shapeSpot(s: MatchState, p: Player, slot: Slot): { x: number; z: number } {
  const dir = dirOf(p.team);
  const b = s.ball;
  const ballAx = b.x * dir;
  const has = s.poss === p.team;
  if (!has) return blockSpot(p, slot, b.x, b.z, pressingHigh(s, p.team));
  const block = clamp(ballAx * 0.7 + 12, -20, 30);
  let ax = block + slot.ax * 1.05;
  const line = offsideLine(s, p.team);
  const back = -offsideLine(s, p.team === 0 ? 1 : 0);
  // The wide men hug the line on both flanks: that's what a switch of play goes to.
  let z = slot.role === "W" ? slot.z * 1.14 + clamp(b.z, -24, 24) * 0.06 : slot.z * 1.02 + clamp(b.z, -24, 24) * 0.2;
  if (slot.role === "CB" || slot.role === "FB") {
    ax = Math.max(ax, -HALF_L + 8);
    // The line holds together, a bit behind the block, never deep for no reason.
    ax = Math.min(ax, ballAx - 1 + (slot.role === "FB" ? 18 : 0));
  }
  ax = Math.min(ax, Math.max(line - 0.7, ballAx));
  if (slot.role !== "CB") ax = Math.max(ax, back);
  // Deep in his own third the team takes up its build-up shape.
  const deep = clamp((-ballAx - 14) / 16, 0, 1);
  if (deep > 0) {
    const q = buildSpot(s, p, slot);
    ax += (Math.min(q.ax, line - 0.7) - ax) * deep;
    z += (q.z - z) * deep;
  }
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
  // Only those near the ball come short for it: the rest keep the pitch big.
  const support = dist(p.x, p.z, b.x, b.z) < 24;
  for (let n = 0; n < offers; n++) {
    if ((n === 4 || n === 5) && !support) continue;
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
    let v = Math.min(Math.sqrt(near), 10) * 0.5 + Math.min(Math.sqrt(lane), 5) * 0.8
      + ((cx - b.x) * dir) * 0.09 - Math.abs(fromBall - 16) * 0.07 - dist(p.x, p.z, cx, cz) * 0.05 + rnd(s) * 1.4;
    // Two men in one place are one option: he goes where no team-mate is going.
    for (const m of s.players) {
      if (m.team !== p.team || m.i === p.i || m.role === "GK") continue;
      const at = m.i === b.owner ? 1e9 : dist(m.runX, m.runZ, cx, cz);
      const gap = Math.min(at, dist(m.x, m.z, cx, cz));
      if (gap < 11) v -= (11 - gap) * 0.32;
    }
    if (v > best) { best = v; bx = cx; bz = cz; }
  }
  p.runX = bx; p.runZ = bz; p.runT = 50 + Math.floor(rnd(s) * 60);
}

/** The gap in their back line nearest to him, where a run hurts most. */
function channel(s: MatchState, p: Player, line: number) {
  const dir = dirOf(p.team);
  let top = -1, at = p.z;
  for (const off of [0, -7, 7, -14, 14]) {
    const z = clamp(p.z + off, -HALF_W + 4, HALF_W - 4);
    let gap = 12;
    for (const o of s.players) {
      if (o.team === p.team || o.role === "GK") continue;
      if (Math.abs(o.x * dir - line) < 12) gap = Math.min(gap, Math.abs(o.z - z));
    }
    const v = gap - Math.abs(off) * 0.25;
    if (v > top) { top = v; at = z; }
  }
  return at;
}

/** How fast he gets back to his place: flat out when the ball is lost behind him. */
function recover(p: Player, x: number, z: number) {
  const d = dist(p.x, p.z, x, z);
  const out = (p.x - x) * dirOf(p.team) > 3;
  return d > 3 && out ? sprintOf(p) - 0.3 : d > 4 ? RUN : d > 1 ? JOG : 2;
}

export function thinkOffBall(s: MatchState, p: Player, slot: Slot) {
  const b = s.ball;
  const dir = dirOf(p.team);
  const home = shapeSpot(s, p, slot);
  const has = s.poss === p.team;
  p.faceBall = false;
  if (!has) p.dash = 0;

  if (p.duty === 1 && b.owner < 0) {
    // After the ball: where he can cut it off.
    // Where it comes down to him, not under it on its way over his head.
    let q = predAt(s, 168);
    for (let k = 6; k < 170; k += 8) {
      const c = predAt(s, k);
      if (c.y > 2.2) continue;
      q = c;
      if (reachTime(p, c.x, c.z) <= k * TICK + 0.1) break;
    }
    p.tx = q.x; p.tz = q.z; p.want = sprintOf(p);
    return;
  }

  if (has) {
    if (b.owner === p.i) return;
    // The ball out wide near the byline: the box fills, near post, far post, spot.
    if (b.owner >= 0 && Math.abs(b.z) > 13 && b.x * dir > HALF_L - 38 && (p.role === "ST" || p.role === "W" || p.role === "CM")) {
      const near = b.z > 0 ? 1 : -1;
      const hisSide = p.z * near > 8;
      if (!(p.role === "W" && hisSide)) {
        const lane = p.role === "ST" ? [6, near * 3] : p.role === "W" ? [7, -near * 5] : p.slot % 2 ? [12, -near * 2] : [20, near * 6];
        p.tx = Math.min(HALF_L - lane[0], Math.max(offsideLine(s, p.team) - 0.6, b.x * dir)) * dir;
        p.tz = lane[1];
        p.want = dist(p.x, p.z, p.tx, p.tz) > 3 ? sprintOf(p) - 0.5 : JOG;
        p.dash = 0;
        return;
      }
    }
    p.runT -= 12;
    if (p.dash > 0) {
      // Gone: he doesn't look back until the run is over.
      p.dash -= 12;
      p.tx = p.runX; p.tz = p.runZ; p.want = sprintOf(p);
      if (p.dash <= 0) p.runT = 0;
      return;
    }
    const line0 = offsideLine(s, p.team);
    const gap = line0 - p.x * dir;
    // Forwards go, a midfielder arrives late, a full-back overlaps on the ball's side.
    const overlap = p.role === "FB" && p.z * b.z > 0 && b.x * dir > -5 && (p.x - b.x) * dir > -14;
    const up = p.role === "ST" || p.role === "W" || overlap || (p.role === "CM" && b.x * dir > -5 && rnd(s) < 0.4);
    if (up && b.owner >= 0 && gap > -1 && gap < 16 && (p.x - b.x) * dir > (p.role === "ST" || p.role === "W" ? 1 : -14) && line0 < HALF_L - 9 && p.stamina > 0.3 && rnd(s) < 0.2) {
      let gone = 0;
      for (const m of s.players) if (m.team === p.team && m.dash > 0) gone += 1;
      if (gone < 2) {
        p.dash = 150;
        p.runX = clamp(line0 + 18, -HALF_L, HALF_L - 7) * dir;
        p.runZ = overlap ? Math.sign(p.z) * (HALF_W - 5) : channel(s, p, line0);
        p.tx = p.runX; p.tz = p.runZ; p.want = sprintOf(p);
        return;
      }
    }
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
    // Between him and the goal, a stride off, giving ground at his pace: the
    // carrier meets a body, not a man jogging beside him.
    const d = dist(p.x, p.z, c.x, c.z);
    // A man standing with it doesn't get a stride: he goes right up and takes it.
    const pace = Math.sqrt(c.vx * c.vx + c.vz * c.vz);
    const still = standing(s, c);
    const stand = still ? 0.4 : d < 5 ? 1.2 : 0.6;
    const lead = clamp(d * 0.09, 0.15, 0.6);
    p.tx = c.x + c.vx * lead + ((gx - c.x) / gd) * stand;
    p.tz = c.z + c.vz * lead + (-c.z / gd) * stand;
    p.want = d > 3.2 ? sprintOf(p) : Math.min(sprintOf(p), pace + (still ? 3 : 1.4));
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
    const box = m.x * dir < -30;
    const hunting = pressingHigh(s, p.team) && p.role !== "CB" && p.role !== "FB";
    // Goal-side of him: tight if he can get it next, a few strides off if not,
    // and never out of his zone. A back line drops with a runner, it doesn't step out.
    const live = dist(m.x, m.z, b.x, b.z) < 20;
    const close = box ? 1.6 : live ? 2 : 3.6;
    const back = p.role === "CB" || p.role === "FB";
    const reach = hunting ? 18 : box ? 12 : 10;
    const ahead = clamp((m.x + ((gx - m.x) / gd) * close - home.x) * dir, back && !box ? -4.5 : -reach, back ? 2.5 : reach);
    p.tx = home.x + ahead * dir;
    p.tz = home.z + clamp(m.z + (-m.z / gd) * close - home.z, -reach, reach);
    p.want = recover(p, p.tx, p.tz);
    p.faceBall = true;
    return;
  }
  p.tx = home.x; p.tz = home.z;
  p.want = has ? (dist(p.x, p.z, home.x, home.z) > 6 ? RUN : JOG) : recover(p, home.x, home.z);
  p.faceBall = true;
}

/** Defenders on their feet go in when they can, at their own judgement. */
export function thinkTackle(s: MatchState, p: Player) {
  const b = s.ball;
  if (b.owner < 0 || p.cool > 0 || p.act !== Act.None) return;
  const c = s.players[b.owner];
  if (c.team === p.team || c.act === Act.Hold) return;
  const d = dist(p.x, p.z, b.x, b.z);
  const still = standing(s, c);
  if (d < (still ? STILL_REACH : 1.4) && rnd(s) < 0.04 + p.defend * 0.08) startTackle(p);
  else if (p.i !== s.user && d < 3 && d > 1.6 && p.defend > 0.6 && p.vx * c.vx + p.vz * c.vz > 12 && rnd(s) < 0.015 && p.x * dirOf(p.team) > -36) startSlide(p);
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

type Option = { v: number; go: () => void };

/** A lofted ball needs the first metres clear: it is still low there. */
function blockedLob(s: MatchState, p: Player, x: number, z: number) {
  const d = dist(p.x, p.z, x, z) || 1;
  const ex = p.x + ((x - p.x) / d) * 8, ez = p.z + ((z - p.z) / d) * 8;
  for (const o of s.players) {
    if (o.team !== p.team && segDist2(p.x, p.z, ex, ez, o.x, o.z) < 5) return true;
  }
  return false;
}

/** Decisions are asked ten times a second: a big dice here means that sooner or
 * later every bad idea gets rolled. */
const NOISE = 0.25;
/** Nobody on him: this long (ticks) with it before he lays it off. A side that
 * plays everything first time gives everything away. */
const COMPOSED = 42;
const KEEP_GOING = 0.35;

/** What the ball is worth at a spot to the side going `dir`: little anywhere
 * deep, a lot close to goal, with a slope all the way so that forward is forward. */
const threat = (x: number, z: number, dir: number) => 10 / (1 + dist2(x, z, dir * HALF_L, 0) / 196) + (x * dir + HALF_L) * 0.03;
/** What it costs to lose it there. */
const exposure = (x: number, z: number, dir: number) => threat(x, z, -dir) * 0.7 + 0.6;
/** One way of playing it: getting there with chance `ok`, or losing it there. */
const worth = (ok: number, x: number, z: number, dir: number) => ok * threat(x, z, dir) - (1 - ok) * exposure(x, z, dir);

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
  const range = dist(p.x, p.z, gx, 0);
  // Close in he takes what's on. From further he has to fancy it, and it is
  // asked ten times a second, so rarely: otherwise everything gets hit.
  const fancy = range < 22 || (range < 30 && rnd(s) < 0.06 + p.shot * 0.06);
  const lim = range < 21 ? 0.05 : 0.025 + (1 - p.shot) * 0.04;
  if (fancy && shot.xg > lim + rnd(s) * (near < 4 ? 0.03 : 0.07) && !(wide && ax > 40)) {
    const power = clamp(0.45 + dist(p.x, p.z, gx, 0) * 0.021 + rnd(s) * 0.12, 0.4, 0.97);
    const curl = dist(p.x, p.z, gx, 0) > 15 && rnd(s) < 0.4 ? (p.z * dir > 0 ? 0.7 : -0.7) : 0;
    startKick(s, p, planShot(s, p, shot.aim + rndN(s) * 0.15, power, curl, false));
    return;
  }

  const options: Option[] = [];
  const line = offsideLine(s, p.team);
  // The longer they have had it, the less the safe ball is the right one: a
  // move is there to end in something.
  const urge = clamp((s.tick - s.lostAt[p.team === 0 ? 1 : 0] - 240) / 420, 0, 1);
  // Now and then he misjudges the line by a step, as people do.
  const misread = rnd(s) < 0.15 ? 1.4 : 0;
  for (const m of s.players) {
    if (m.team !== p.team || m.i === p.i || m.act === Act.Down || m.off) continue;
    const d0 = dist(p.x, p.z, m.x, m.z);
    if (d0 < 4) continue;
    const maxD = m.role === "GK" ? 22 : p.pass > 0.7 ? 44 : 36;
    if (d0 > maxD) continue;
    if (m.role === "GK" && (near > 3 || ax > -18)) continue;
    const aheadOfLine = m.x * dir > line + misread;
    if (aheadOfLine) continue;
    const pace = clamp(rollPace(d0, 8), 8, 24);
    const t = rollTime(pace, d0);
    const mx = m.x + m.vx * t * 0.8, mz = m.z + m.vz * t * 0.8;
    const margin = laneMargin(s, p, mx, mz, pace);
    let open = 1e9;
    for (const o of s.players) if (o.team !== p.team) open = Math.min(open, dist(o.x, o.z, mx, mz));
    const gain = (mx - p.x) * dir;
    const ok = clamp(0.62 + clamp(margin, -3, 1.2) * 0.24 + (Math.min(open, 7) - 3.5) * 0.05 - d0 * 0.003, 0.04, 0.96);
    let v = worth(ok, mx, mz, dir) + Math.min(open, 8) * 0.05 + rnd(s) * NOISE;
    // A little square ball with nobody on him gets the side nowhere.
    if (near > 4 && gain < 3) v -= 0.5;
    if (ax > 0) v += gain > 6 ? urge * 0.7 : gain < 0 ? -urge * 0.9 : 0;
    const lofted = d0 > 16 && !blockedLob(s, p, mx, mz);
    if (d0 < 32 && margin > 0) options.push({ v, go: () => startKick(s, p, planPass(s, p, m, clamp(d0 / 30 + 0.1, 0.25, 1))) });
    else if (lofted && open > 6.5 && gain > 6) {
      // Over the top: a coin toss, unless the man has room.
      const air = clamp(0.25 + (open - 5) * 0.06, 0.12, 0.5);
      options.push({ v: worth(air, mx, mz, dir) + rnd(s) * NOISE, go: () => startKick(s, p, planLob(s, p, mx, mz, m.i, 0.5)) });
    }
    // The other flank is empty when they all come over to this one: switch it.
    if (lofted && Math.abs(mz - p.z) > 24 && open > 8 && ax > -30) {
      let crowd = 0;
      for (const o of s.players) if (o.team !== p.team && dist(o.x, o.z, p.x, p.z) < 15) crowd += 1;
      const lead = 1.5;
      if (crowd >= 3) options.push({ v: worth(0.65, mx, mz, dir) + crowd * 0.12 + rnd(s) * NOISE, go: () => startKick(s, p, planLob(s, p, m.x + m.vx * lead, m.z + m.vz * lead, m.i, 0.5)) });
    }
    // The ball behind them for a man running on to it.
    const runner = m.dash > 0 || ((m.role === "ST" || m.role === "W" || m.role === "CM") && (m.x - p.x) * dir > 2);
    if (runner) {
      const plan = planThrough(s, p, m, 0.5);
      const mine = reachTime(m, plan.tx, plan.tz);
      let them = 1e9;
      for (const o of s.players) if (o.team !== p.team) them = Math.min(them, reachTime(o, plan.tx, plan.tz));
      const lm = laneMargin(s, p, plan.tx, plan.tz, plan.speed);
      if (mine < them + 0.8 && lm > -1 && plan.tx * dir > line - 10) {
        const in_ = clamp(0.5 + (them - mine) * 0.3 + lm * 0.1, 0.1, 0.85);
        options.push({ v: worth(in_, plan.tx, plan.tz, dir) + 1 + urge + (m.dash > 0 ? 0.8 : 0) + rnd(s) * NOISE, go: () => startKick(s, p, plan) });
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
      options.push({ v: worth(clamp(0.3 + men * 0.05, 0, 0.55), bx, bz, dir) + (ax - 30) * 0.05 + 0.8 + urge + rnd(s) * NOISE, go: () => startKick(s, p, plan) });
    }
  }

  // Carrying it: the best of eight ways against everyone near. The way he is
  // already going counts for something, or he changes his mind every stride.
  const held = near > 7 ? 0.97 : near > 4 ? 0.92 : near > 2.6 ? 0.8 : 0.62;
  let carryV = -1e9, ux = dir, uz = 0;
  for (let w = 0; w < 8; w++) {
    const cx = w === 0 || w === 1 || w === 7 ? 0.8 : w === 3 || w === 4 || w === 5 ? -0.8 : 0;
    const cz = w >= 1 && w <= 3 ? 0.8 : w >= 5 ? -0.8 : 0;
    const qx = p.x + cx * 7, qz = p.z + cz * 7;
    if (Math.abs(qz) > HALF_W - 1.5 || Math.abs(qx) > HALF_L - 1.5) continue;
    let room = 1e9, blocked = 0;
    for (const o of s.players) {
      if (o.team === p.team) continue;
      room = Math.min(room, dist2(o.x, o.z, qx, qz));
      // Not through a man: the way has to be free for the next few strides.
      if (o.role !== "GK" && segDist2(p.x, p.z, qx, qz, o.x, o.z) < 2.2) blocked += 1;
    }
    const safe = clamp(held - blocked * 0.2 + (Math.min(Math.sqrt(room), 9) - 4) * 0.012, 0.15, 0.97);
    let v = worth(safe, qx, qz, dir) + (cx * p.hx + cz * p.hz) * KEEP_GOING;
    // A wide man goes down the line to the byline, whatever the middle promises.
    if (Math.abs(p.z) > 14 && (p.role === "W" || p.role === "FB") && ax > HALF_L - 40) v += cx * dir * (ax < HALF_L - 7 ? 0.5 : -0.5);
    if (v > carryV) { carryV = v; ux = cx; uz = cz; }
  }
  // With room he takes it on: a first touch, a look, a few strides. Nobody who
  // isn't being closed down gets rid of it the moment it arrives.
  const room = near > 7 ? 0.7 : near > 4 ? 0.35 : 0;
  const settle = b.since < 60 && near > 3 ? 0.8 : 0;
  // A keeper doesn't go for a walk with it: a touch, a look, and it's gone.
  const carry = carryV + room + settle + p.dribble * 0.2 - (p.role === "GK" ? 1.5 : 0);

  let bestV = carry, go: (() => void) | null = null;
  for (const o of options) if (o.v > bestV) { bestV = o.v; go = o.go; }
  if (go && (b.since >= COMPOSED || near < 2.4)) {
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
    // Each in his own half, and only the taker inside the circle.
    let x = Math.min(slot.ax * 0.8 - 8, -1), z = slot.z * 0.9;
    if (attacking && slot.role === "ST") { x = -1.5; z = n % 2 ? 11 : -11; }
    const r = dist(0, 0, x, z) || 1;
    if (r < CIRCLE_CLEAR) { x *= CIRCLE_CLEAR / r; z *= CIRCLE_CLEAR / r; }
    return { x: x * dir, z };
  }
  if (set.kind === "penalty") {
    if (attacking) return { x: dir * (HALF_L - 20 + (n % 3)), z: (n - 5) * 3 };
    return { x: dir * -(HALF_L - 20 + (n % 3)), z: (n - 5) * 3 + 1 };
  }
  if (set.kind === "goalkick") {
    if (attacking) {
      const q = buildSpot(s, p, slot);
      return { x: q.ax * dir, z: q.z };
    }
    // Pressing it: up to the edge of their box and no further until it's kicked.
    const q = blockSpot(p, slot, set.x, set.z, true);
    return { x: clamp(q.x * dir, -HALF_L, HALF_L - BOX_D - 1) * dir, z: q.z };
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
      const q = open + (m.x - p.x) * dir * 0.1 + clamp(laneMargin(s, p, m.x, m.z, rollPace(d, 7)), -4, 1) * 3 + rnd(s) * 2;
      if (q > v) { v = q; best = m; }
    }
    return best;
  };
  if (set.kind === "kickoff") {
    const m = nearest(19) ?? mates[0];
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
    // Short when somebody is really free, long over the press when not.
    const m = nearest(30);
    if (m && laneMargin(s, p, m.x, m.z, rollPace(dist(p.x, p.z, m.x, m.z), 7)) > 0.4) startKick(s, p, planPass(s, p, m, 0.6));
    else {
      const fwd = mates.filter((q) => q.role === "ST" || q.role === "W");
      let t = fwd[0] ?? mates[0], room = -1;
      for (const f of fwd) {
        let open = 1e9;
        for (const o of s.players) if (o.team !== p.team) open = Math.min(open, dist(o.x, o.z, f.x, f.z));
        if (open + rnd(s) * 2 > room) { room = open; t = f; }
      }
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
