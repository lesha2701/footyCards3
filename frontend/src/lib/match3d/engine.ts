/** The match, tick by tick: who moves how, who gets to the ball, the laws
 * (out of play, offside, fouls, restarts, the clock). `createMatch` and
 * `stepMatch` are the whole interface: the scene reads the state, feeds it
 * one `Input` per tick, and draws what happened. */
import {
  Act, BALL_R, CLOCK_RATE, END_MIN, GOAL_H, GOAL_HALF, HALF_L, HALF_W, Kick, PEN_SPOT, Phase, START_MIN, SIX_D, TICK,
  ballAt, clamp, dirOf, dist, dist2, freshState, predAt, predict, rnd, rndN, speedOf, stepBall,
  type Feint, type MatchState, type Player, type SceneKick, type SceneOutcome, type SetKind, type SetPiece, type Setup,
} from "./core";
import {
  feintBites, fell, inBox, laneMargin, offsideLine, planCross, planLob, planPass, planShot, planThrough, releaseKick, rollPace, sprintOf, startFeint, startKick, startSlide, startTackle, windupOf,
} from "./actions";
import { FORMATIONS, STILL_REACH, setPieceSpot, standing, takeSetPiece, thinkCarrier, thinkPlayer, thinkTackle, thinkTeam } from "./brain";
import { holdBall, keeperSpot, releaseHands, stepKeeper } from "./keeper";

/** What the human does this tick. Stick in world axes (−1..1). */
export type Input = {
  mx: number; mz: number;
  sprint: boolean;
  press: Press | null;
  /** A second man goes to the ball. */
  contain: boolean;
};

export type Press =
  | { k: "pass" | "through" | "lob"; power: number }
  | { k: "shot"; power: number; curl: number; chip: boolean }
  | { k: "feint" | "tackle" | "slide" | "switch" }
  /** A touch on a team-mate: the best ball to him, or, without it, him. */
  | { k: "to"; i: number }
  /** What the swipe scene's kick did; null: the scene failed. */
  | { k: "scene"; outcome: SceneOutcome | null };

export const NO_INPUT: Input = { mx: 0, mz: 0, sprint: false, press: null, contain: false };

const ACCEL = 8.5;
const BRAKE = 15;
const BODY = 0.78;
/** How far a footballer's foot gets to a low ball (m). */
const REACH = 0.85;
const GOAL_PAUSE = 150;
/** Ticks before a restart can be taken. */
const SET_MIN = 90;
/** What a stride of the carrier's pace takes off a tackle's chance, per m/s. */
const TACKLE_RUNNING = 0.05;
/** How long a press for the ball on its way holds (ticks). */
const FIRST_TIME = 60;
/** A free kick closer than this (m), not too wide, goes to the swipe scene. */
const FREE_SCENE_MAX = 30;
const FREE_SCENE_WIDE = 20;
const USER_WAIT = 420;
/** Past full time the referee waits this long at most for the ball to leave a dangerous place. */
const LATE_MAX = 240;
/** A full tank: ten seconds of sprint, twelve of walking to fill it. */
const STAMINA_DRAIN = 1 / 600;
const STAMINA_BACK = 1 / 720;

const SLOTS = [FORMATIONS["433"], FORMATIONS["442"]] as const;

export function createMatch(setup: Setup, userTeam: 0 | 1 | null = 0): MatchState {
  const players: Player[] = [];
  const mk = (team: 0 | 1, slot: number): Player => {
    const f = SLOTS[team][slot];
    const rating = team === 0 ? setup.homeRating : setup.awayRating;
    const seed = Math.imul(setup.seed ^ (team * 97 + slot * 13 + 5), 2654435761) >>> 0;
    const vary = (k: number) => clamp(rating + ((((seed >>> k) & 255) / 255) * 2 - 1) * 0.1, 0.4, 0.99);
    const fwd = f.role === "ST" || f.role === "W";
    const backs = f.role === "CB" || f.role === "FB" || f.role === "DM";
    return {
      i: team * 11 + slot, team, slot, role: f.role, num: [1, 2, 5, 4, 3, 6, 8, 10, 11, 9, 7][slot],
      pace: vary(0) + (f.role === "W" ? 0.08 : f.role === "CB" ? -0.08 : 0),
      shot: vary(8) + (fwd ? 0.08 : backs ? -0.15 : 0),
      pass: vary(16) + (f.role === "CM" || f.role === "DM" ? 0.08 : f.role === "CB" ? -0.08 : 0),
      dribble: vary(24) + (f.role === "W" ? 0.1 : backs ? -0.12 : 0),
      defend: vary(4) + (backs ? 0.1 : fwd ? -0.2 : 0),
      save: f.role === "GK" ? vary(12) : 0,
      x: f.ax * dirOf(team), z: f.z, vx: 0, vz: 0, hx: dirOf(team), hz: 0,
      tx: 0, tz: 0, want: 0, faceBall: false,
      act: Act.None, actT: 0, actLen: 0, side: 1, sub: 0, air: 0, plan: null, cool: 0,
      beat: 0, beatX: 0, beatZ: 0, off: false, stamina: 1, runUp: 0, dash: 0, touch: 0,
      runT: 0, runX: 0, runZ: 0, duty: 0, mark: -1, react: -1, saves: false, hands: 0,
    };
  };
  for (const team of [0, 1] as const) for (let n = 0; n < 11; n++) players.push(mk(team, n));
  const s = freshState(setup, players);
  s.user = userTeam === null ? -1 : players.find((p) => p.team === userTeam && p.role === "ST")!.i;
  restart(s, "kickoff", rnd(s) < 0.5 ? 0 : 1, 0, 0);
  lineUp(s);
  return s;
}

/** Everybody on his spot for a kick-off, at once: nobody walks back to it. */
function lineUp(s: MatchState) {
  for (const p of s.players) {
    const sp = setPieceSpot(s, p, SLOTS[p.team][p.slot], s.set!);
    if (p.role === "GK") { const g = keeperSpot(p, s); p.x = g.x; p.z = g.z; } else { p.x = sp.x; p.z = sp.z; }
    p.tx = p.x; p.tz = p.z; p.vx = 0; p.vz = 0; p.want = 0;
    p.act = Act.None; p.dash = 0;
    const d = dirOf(p.team);
    p.hx = d; p.hz = 0;
  }
  const t = s.players[s.set!.taker];
  t.x = t.team === 0 ? -0.5 : 0.5; t.z = 0;
  ballAt(s.ball, 0, BALL_R, 0);
}

export const userTeam = (s: MatchState): 0 | 1 | null => (s.user >= 0 ? s.players[s.user].team : null);

// --- restarts ---------------------------------------------------------------------------------------

function pickTaker(s: MatchState, kind: SetKind, team: 0 | 1, x: number, z: number): Player {
  const men = s.players.filter((p) => p.team === team);
  if (kind === "goalkick") return men.find((p) => p.role === "GK")!;
  if (kind === "penalty") return men.reduce((a, b) => (b.shot > a.shot ? b : a));
  const field = men.filter((p) => p.role !== "GK" && p.act !== Act.Down);
  if (kind === "kickoff") return field.find((p) => p.role === "ST")!;
  if (kind === "corner") return field.reduce((a, b) => (b.pass > a.pass ? b : a));
  const best = field.reduce((a, b) => (dist2(b.x, b.z, x, z) < dist2(a.x, a.z, x, z) ? b : a));
  if (kind === "free") {
    const d = dist(x, z, dirOf(team) * HALF_L, 0);
    if (d < 30) return field.reduce((a, b) => (b.shot > a.shot ? b : a));
  }
  return best;
}

function restart(s: MatchState, kind: SetKind, team: 0 | 1, x: number, z: number) {
  const b = s.ball;
  s.phase = kind === "kickoff" ? Phase.Kickoff : Phase.Dead;
  s.phaseT = 0;
  const taker = pickTaker(s, kind, team, x, z);
  s.set = { kind, team, x, z, taker: taker.i, t: 0, ready: false, scene: -1 };
  b.owner = -1; b.to = -1; b.kick = Kick.None; b.inNet = false;
  s.chaser = [-1, -1];
  for (const p of s.players) {
    p.off = false; p.plan = null; p.beat = 0; p.air = 0;
    if (p.act !== Act.Down && p.act !== Act.Getup) p.act = Act.None;
    p.duty = 0; p.mark = -1; p.react = -1;
  }
  s.ev.push({ t: "out", set: kind, team });
  const ut = userTeam(s);
  if (ut === team) s.user = taker.i;
}

function givePossession(s: MatchState, p: Player) {
  s.poss = p.team;
}

function toUser(s: MatchState, p: Player) {
  if (s.user >= 0 && s.players[s.user].team === p.team && s.user !== p.i && p.role !== "GK") {
    s.user = p.i;
    s.ev.push({ t: "switch", p: p.i });
  }
}

function afterBallOut(s: MatchState) {
  const b = s.ball;
  const lastTeam: 0 | 1 = b.last >= 0 ? s.players[b.last].team : 0;
  const other: 0 | 1 = lastTeam === 0 ? 1 : 0;
  if (Math.abs(b.z) > HALF_W + BALL_R) {
    restart(s, "throw", other, clamp(b.x, -HALF_L + 1, HALF_L - 1), Math.sign(b.z) * (HALF_W + 0.1));
    return;
  }
  const sideX = Math.sign(b.x);
  const atk: 0 | 1 = sideX > 0 ? 0 : 1;
  noteMiss(s);
  if (lastTeam === atk) {
    restart(s, "goalkick", other, sideX * (HALF_L - SIX_D), Math.abs(b.z) > 9 ? Math.sign(b.z) * 5 : 0);
  } else {
    s.teams[atk].corners += 1;
    restart(s, "corner", atk, sideX * (HALF_L - 0.4), Math.sign(b.z || 1) * (HALF_W - 0.4));
  }
}

function noteMiss(s: MatchState) {
  const b = s.ball;
  if (b.kick === Kick.Shot || b.kick === Kick.Header) s.ev.push({ t: "miss", p: b.kicker, near: Math.abs(b.z) < GOAL_HALF + 2.5 && b.y < GOAL_H + 2 });
}

function scored(s: MatchState, team: 0 | 1) {
  const b = s.ball;
  const t = s.teams[team];
  t.goals += 1;
  const by = b.last >= 0 ? s.players[b.last] : null;
  const own = by !== null && by.team !== team;
  const p = own || !by ? -1 : by.i;
  const long = dist(b.fromX, b.fromZ, dirOf(team) * HALF_L, 0) > 20;
  const assist = s.prevTouch >= 0 && s.prevTouch !== p && s.players[s.prevTouch].team === team ? s.prevTouch : -1;
  s.lastGoal = { tick: s.tick, team, p, kind: b.kick, long };
  s.ev.push({ t: "goal", team, p, kind: b.kick, long, assist });
  s.phase = Phase.Goal;
  s.phaseT = 0;
  s.set = null;
  for (const q of s.players) {
    q.plan = null; q.beat = 0;
    if (q.act === Act.Hold || q.act === Act.Kick) q.act = Act.None;
  }
}

// --- the human ---------------------------------------------------------------------------------------

/** Would he be off if the ball were played now? */
function offsideNow(s: MatchState, p: Player, m: Player) {
  const dir = dirOf(p.team);
  const v = m.x * dir;
  return v > offsideLine(s, p.team) + 0.1 && v > s.ball.x * dir + 0.1 && v > 0;
}

function bestMate(s: MatchState, p: Player, ux: number, uz: number, wantFwd: boolean, air = false): Player | null {
  const dir = dirOf(p.team);
  const stick = ux !== 0 || uz !== 0;
  let best: Player | null = null, top = -1e9;
  for (const m of s.players) {
    if (m.team !== p.team || m.i === p.i) continue;
    const dx = m.x - p.x, dz = m.z - p.z;
    const d = Math.sqrt(dx * dx + dz * dz) || 1;
    if (d < 3 || d > 60) continue;
    const along = stick ? (dx / d) * ux + (dz / d) * uz : (dx / d) * p.hx + (dz / d) * p.hz;
    let open = 1e9;
    for (const o of s.players) if (o.team !== p.team) open = Math.min(open, dist(o.x, o.z, m.x, m.z));
    // The stick says the direction; in that direction, whoever is really on.
    // Over the top the lane doesn't matter, and the far flank is as near as the next man.
    const lane = air ? 0 : clamp(laneMargin(s, p, m.x, m.z, rollPace(d, 7)), -4, 1);
    const v = along * 6 - d * (air ? 0.02 : 0.1) + Math.min(open, 6) * 0.35 + lane * 1.8 + (wantFwd ? (dx * dir) * 0.06 : 0) + (wantFwd && m.dash > 0 ? 2.5 : 0) - (m.role === "GK" ? 4 : 0) - (offsideNow(s, p, m) ? 4 : 0);
    if (v > top) { top = v; best = m; }
  }
  return best;
}

/** The best ball to a man he picked by hand: in behind him if he's off and
 * running on to it, along the ground if it's on, over them if it isn't. */
function bestBall(s: MatchState, p: Player, m: Player) {
  const d = dist(p.x, p.z, m.x, m.z);
  const dir = dirOf(p.team);
  const running = m.vx * m.vx + m.vz * m.vz > 25 && m.vx * dir > 2 && (m.x - p.x) * dir > 2;
  if (running) {
    const t = planThrough(s, p, m, 0.5);
    if (laneMargin(s, p, t.tx, t.tz, t.speed) > -0.5) return t;
  }
  const power = clamp(d / 34, 0.2, 0.9);
  const plan = planPass(s, p, m, power);
  if (d < 34 && laneMargin(s, p, plan.tx, plan.tz, plan.speed) > -0.3) return plan;
  return planLob(s, p, m.x + m.vx * 1.5, m.z + m.vz * 1.5, m.i, 0.5);
}

function userPress(s: MatchState, p: Player, inp: Input) {
  const press = inp.press;
  if (!press) return;
  const b = s.ball;
  const has = b.owner === p.i;
  const free = p.act === Act.None || p.act === Act.Trap;
  const l = Math.sqrt(inp.mx * inp.mx + inp.mz * inp.mz);
  const ux = l > 0.2 ? inp.mx / l : 0, uz = l > 0.2 ? inp.mz / l : 0;
  const dir = dirOf(p.team);

  if (press.k === "switch") {
    if (p.act === Act.Hold) return;
    switchUser(s);
    s.switchT = s.tick + 45;
    return;
  }
  const taking = !!s.set && s.set.taker === p.i && s.set.ready && (s.phase === Phase.Dead || s.phase === Phase.Kickoff);
  if (press.k === "to") {
    const m = s.players[press.i];
    if (m.team !== p.team || m.i === p.i) return;
    if (p.act === Act.Hold) {
      const d = dist(p.x, p.z, m.x, m.z);
      releaseHands(s, p, m, d, d > 42);
    } else if (taking && s.set!.kind === "throw") {
      const d = dist(p.x, p.z, m.x, m.z);
      startKick(s, p, { kind: Kick.Throw, tx: m.x, ty: 0.9, tz: m.z, speed: clamp(d * 0.5 + 5, 8, 15), curl: 0, to: m.i, err: 0.1, ground: false });
    } else if (taking || (has && free)) startKick(s, p, bestBall(s, p, m));
    else if (!has && !s.set && m.role !== "GK") {
      toMan(s, m.i);
      s.switchT = s.tick + 45;
    }
    return;
  }
  if (taking) {
    userSetPiece(s, p, inp, ux, uz);
    return;
  }
  if (p.act === Act.Hold) {
    const long = press.k === "shot" || press.k === "lob";
    if (long || press.k === "pass" || press.k === "through") {
      const m = bestMate(s, p, ux, uz, long);
      if (m) releaseHands(s, p, m, dist(p.x, p.z, m.x, m.z), long);
    }
    return;
  }
  if (!has) {
    // The ball on its way: whatever he asks for is played first time.
    if (b.owner < 0 && (press.k === "pass" || press.k === "through" || press.k === "lob" || press.k === "shot")) {
      const shot = press.k === "shot";
      s.want = { k: press.k, power: press.power, curl: shot ? press.curl : 0, chip: shot && press.chip };
      s.wantX = ux; s.wantZ = uz; s.wantT = s.tick + FIRST_TIME;
      if (shot) s.wantShot = FIRST_TIME;
      return;
    }
    if (press.k === "tackle" && free && p.cool === 0) startTackle(p);
    else if (press.k === "slide" && free && p.cool === 0) startSlide(p);
    return;
  }
  if (!free) return;
  switch (press.k) {
    case "pass": {
      const m = bestMate(s, p, ux, uz, false);
      if (m) startKick(s, p, planPass(s, p, m, press.power));
      return;
    }
    case "through": {
      const m = bestMate(s, p, ux, uz, true);
      if (m) startKick(s, p, planThrough(s, p, m, press.power));
      return;
    }
    case "lob": {
      const wide = Math.abs(p.z) > 12 && p.x * dir > HALF_L - 34;
      if (wide) {
        const near = uz !== 0 ? uz : -Math.sign(p.z);
        const tz = clamp(p.z * 0.1 + near * (2 + press.power * 6), -9, 9);
        const tx = dir * (HALF_L - 6 - press.power * 6);
        let to = -1, top = 1e9;
        for (const m of s.players) {
          if (m.team === p.team && m.role !== "GK" && m.i !== p.i) {
            const d = dist(m.x, m.z, tx, tz);
            if (d < top) { top = d; to = m.i; }
          }
        }
        startKick(s, p, planCross(s, p, tx, tz, to, press.power));
        return;
      }
      const m = bestMate(s, p, ux, uz, true, true);
      if (m) startKick(s, p, planLob(s, p, m.x + m.vx * 1.5, m.z + m.vz * 1.5, m.i, press.power));
      return;
    }
    case "shot": {
      // The stick across picks the corner; straight at goal, the far one.
      const aim = Math.abs(uz) > 0.25 ? clamp(uz * 1.05, -1, 1) : (p.z >= 0 ? -0.55 : 0.55);
      startKick(s, p, planShot(s, p, aim, press.power, press.curl, press.chip));
      return;
    }
    case "feint": {
      // Along the stick: on = over the ball, back = pulled back, across = rolled.
      const along = ux * p.hx + uz * p.hz;
      const across = p.hx * uz - p.hz * ux;
      let kind: Feint = 0, side = across >= 0 ? 1 : -1;
      if (l > 0.2 && along < -0.5) kind = 1;
      else if (l > 0.2 && Math.abs(across) > 0.6) kind = 2;
      else if (l > 0.2 && along > 0.5) { kind = 3; side = rnd(s) < 0.5 ? 1 : -1; }
      startFeint(s, p, kind, side);
      return;
    }
    default:
  }
}

function userSetPiece(s: MatchState, p: Player, inp: Input, ux: number, uz: number) {
  const set = s.set!;
  const press = inp.press!;
  const dir = dirOf(p.team);
  if (!("power" in press)) return;
  const power = press.power;
  if (set.kind === "corner" || (set.kind === "free" && press.k === "lob")) {
    // Near post, the spot or the far post by the stick; the power picks how deep.
    const gx = dir * HALF_L;
    const across = uz * Math.sign(-(set.z || 1));
    const tz = clamp(Math.sign(set.z) * (4 - (across + 1) * 4.4), -10, 10);
    const tx = gx - dir * (4 + power * 8);
    let to = -1, top = 1e9;
    for (const m of s.players) {
      if (m.team === p.team && m.role !== "GK" && m.i !== p.i) {
        const d = dist(m.x, m.z, tx, tz);
        if (d < top) { top = d; to = m.i; }
      }
    }
    startKick(s, p, planCross(s, p, tx, tz, to, power, set.kind === "corner" ? Kick.Corner : Kick.Cross));
    return;
  }
  if (press.k === "shot" && (set.kind === "free" || set.kind === "penalty")) {
    const aim = uz !== 0 ? clamp(uz * 1.05, -1, 1) : (p.z >= 0 ? -0.6 : 0.6);
    startKick(s, p, planShot(s, p, aim, power, press.curl, press.chip));
    return;
  }
  if (set.kind === "throw") {
    const m = bestMate(s, p, ux, uz, false);
    if (m) {
      const d = dist(p.x, p.z, m.x, m.z);
      startKick(s, p, { kind: Kick.Throw, tx: m.x, ty: 0.9, tz: m.z, speed: clamp(d * 0.5 + 5, 8, 15), curl: 0, to: m.i, err: 0.1, ground: false });
    }
    return;
  }
  const m = bestMate(s, p, ux, uz, press.k !== "pass");
  if (m) startKick(s, p, press.k === "through" ? planThrough(s, p, m, power) : press.k === "lob" || press.k === "shot" ? planLob(s, p, m.x, m.z, m.i, power) : planPass(s, p, m, power));
}

function switchUser(s: MatchState) {
  const u = s.players[s.user];
  const b = s.ball;
  let best = -1, top = 1e9;
  for (const m of s.players) {
    if (m.team !== u.team || m.role === "GK" || m.i === s.user || m.act === Act.Down) continue;
    const d = dist(m.x, m.z, b.x, b.z) + (m.duty ? -3 : 0);
    if (d < top) { top = d; best = m.i; }
  }
  if (best >= 0) {
    s.user = best;
    s.ev.push({ t: "switch", p: best });
  }
}

/** The game changes his man: the thumb that was down isn't steering this one. */
function toMan(s: MatchState, i: number) {
  s.user = i;
  s.ev.push({ t: "switch", p: i });
  s.locked = s.stickX !== 0 || s.stickZ !== 0;
  s.lockX = s.stickX; s.lockZ = s.stickZ;
}

/** Is the stick steering? Off it, or locked, the man plays by himself. */
function readStick(s: MatchState, inp: Input) {
  const l = Math.sqrt(inp.mx * inp.mx + inp.mz * inp.mz);
  if (s.locked) {
    const lk = Math.sqrt(s.lockX * s.lockX + s.lockZ * s.lockZ) || 1;
    if (l === 0 || (inp.mx * s.lockX + inp.mz * s.lockZ) / (l * lk) < 0.8) s.locked = false;
  }
  s.stickX = inp.mx; s.stickZ = inp.mz;
}

/** The ball is on its way to the human's man (who is not the keeper). */
function receiver(s: MatchState): Player | null {
  const b = s.ball;
  if (s.user < 0 || b.owner >= 0 || b.to < 0 || s.phase !== Phase.Play) return null;
  const r = s.players[b.to];
  return r.team === s.players[s.user].team && r.role !== "GK" && r.act !== Act.Down ? r : null;
}

function userAutoSwitch(s: MatchState) {
  if (s.user < 0) return;
  const u = s.players[s.user];
  const b = s.ball;
  if (b.owner === s.user) return;
  // The ball on its way to a team-mate: he takes over the receiver.
  const r = receiver(s);
  if (r) {
    if (r.i !== s.user) toMan(s, r.i);
    return;
  }
  // A team-mate has it, the keeper too: nothing to switch to but him.
  if (b.owner >= 0 && s.players[b.owner].team === u.team) {
    s.user = b.owner;
    return;
  }
  if (u.role === "GK") {
    switchUser(s);
    return;
  }
  // Theirs or loose: always the man nearest to where the ball is going.
  if (u.act !== Act.None || s.tick < s.switchT || s.tick % 4 !== 0) return;
  const bx = b.x + b.vx * 0.3, bz = b.z + b.vz * 0.3;
  const dir = dirOf(u.team);
  const reach = (m: Player) => dist(m.x, m.z, bx, bz) + ((m.x - bx) * dir < 0 ? -1.5 : 0);
  const here = reach(u);
  let best = -1, top = here - 2.2;
  for (const m of s.players) {
    if (m.team !== u.team || m.role === "GK" || m.act !== Act.None || m.i === s.user) continue;
    const d = reach(m);
    if (d < top) { top = d; best = m.i; }
  }
  if (best >= 0) {
    toMan(s, best);
    s.switchT = s.tick + 24;
  }
}

/** Where he meets the ball: the first point on its path he gets to in time. */
function meetPoint(s: MatchState, p: Player) {
  let q = predAt(s, 0);
  const top = sprintOf(p);
  for (let k = 0; k < 240; k += 6) {
    const c = predAt(s, k);
    if (c.y > 1.9) continue;
    q = c;
    if (dist(p.x, p.z, c.x, c.z) / top <= k * TICK + 0.05) break;
  }
  return q;
}

/** The pass assist: a ball rolling to the human's man bends on to him and
 * never dies short of him, as long as it has not gone past him. */
function assistPass(s: MatchState) {
  const r = receiver(s);
  if (!r) return;
  const b = s.ball;
  if (s.tick % 6 === 0) predict(s);
  const rolling = b.kick === Kick.Pass || b.kick === Kick.Through || b.kick === Kick.GkRoll;
  if (!rolling || b.y > BALL_R + 0.01) return;
  const dx = r.x + r.vx * 0.25 - b.x, dz = r.z + r.vz * 0.25 - b.z;
  const d = Math.sqrt(dx * dx + dz * dz);
  const v = Math.sqrt(b.vx * b.vx + b.vz * b.vz);
  if (d < 0.4) return;
  if (v > 0.5 && dx * b.vx + dz * b.vz < 0) {
    if (d > 2) b.to = -1;
    return;
  }
  const through = b.kick === Kick.Through;
  const k = through ? (d < 8 ? 0.05 : 0) : d < 15 ? 0.08 : 0.035;
  const pace = Math.max(v, through ? 3.5 : 5.5);
  const nx = b.vx + ((dx / d) * pace - b.vx) * k, nz = b.vz + ((dz / d) * pace - b.vz) * k;
  const l = Math.sqrt(nx * nx + nz * nz) || 1;
  b.vx = (nx / l) * pace; b.vz = (nz / l) * pace;
}

// --- bodies -------------------------------------------------------------------------------------------

function faceTo(p: Player, ux: number, uz: number, k: number) {
  const x = p.hx + (ux - p.hx) * k, z = p.hz + (uz - p.hz) * k;
  const l = Math.sqrt(x * x + z * z);
  if (l > 1e-4) { p.hx = x / l; p.hz = z / l; }
}

/** Heads for (tx, tz) at `want`, as fast as his legs change pace. */
function steer(s: MatchState, p: Player, tx: number, tz: number, want: number) {
  let dx = tx - p.x, dz = tz - p.z;
  const d = Math.sqrt(dx * dx + dz * dz);
  let vx = 0, vz = 0;
  if (d > 0.08) {
    const arrive = d < 3 ? Math.max(0.9, want * (d / 3)) : want;
    dx /= d; dz /= d;
    vx = dx * arrive; vz = dz * arrive;
  }
  moveToward(p, vx, vz, ACCEL);
}

function moveToward(p: Player, vx: number, vz: number, accel: number, brake = BRAKE) {
  const ax = vx - p.vx, az = vz - p.vz;
  const a = Math.sqrt(ax * ax + az * az);
  const speedUp = vx * vx + vz * vz > p.vx * p.vx + p.vz * p.vz;
  const lim = (speedUp ? accel : brake) * TICK;
  if (a <= lim) { p.vx = vx; p.vz = vz; } else { p.vx += (ax / a) * lim; p.vz += (az / a) * lim; }
}

function stepKick(s: MatchState, p: Player) {
  const plan = p.plan;
  p.actT += 1;
  // Turns to where it goes, slowing into it.
  if (plan) {
    const dx = plan.tx - p.x, dz = plan.tz - p.z;
    const d = Math.sqrt(dx * dx + dz * dz) || 1;
    faceTo(p, dx / d, dz / d, 0.22);
    p.vx *= 0.93; p.vz *= 0.93;
    if (p.actT >= windupOf(p)) releaseKick(s, p);
  } else {
    p.vx *= 0.96; p.vz *= 0.96;
    if (p.i === s.user && p.actT >= windupOf(p) + 7) p.actT = p.actLen;
  }
  if (p.actT >= p.actLen) { p.act = Act.None; p.plan = null; }
}

function stepTackle(s: MatchState, p: Player) {
  p.actT += 1;
  const b = s.ball;
  const c = b.owner >= 0 ? s.players[b.owner] : null;
  if (p.actT === 8 && c && c.team !== p.team) {
    const d = dist(p.x, p.z, b.x, b.z);
    if (d < (standing(s, c) ? STILL_REACH + 0.1 : 1.55)) {
      // A ball out of his stride is there to be won; one at a man on the move isn't, so much.
      const exposed = clamp(speedOf(b) / 8, 0, 1) * 0.12;
      const going = Math.sqrt(c.vx * c.vx + c.vz * c.vz);
      const chance = 0.32 + p.defend * 0.46 - c.dribble * 0.28 + exposed - Math.min(going, 8) * TACKLE_RUNNING;
      const behind = c.hx * p.hx + c.hz * p.hz > 0.5;
      if (behind && rnd(s) < 0.22) {
        foul(s, p, c);
      } else if (rnd(s) < chance) {
        // Won: he comes away with it, or it squirts loose his way. Either way
        // the man who lost it is out of it for a moment.
        c.cool = 34;
        c.beat = 26; c.beatX = 0; c.beatZ = 0;
        b.owner = -1; b.last = p.i; b.kick = Kick.Tackle; b.kicker = p.i; b.to = -1; b.since = 14;
        s.teams[p.team].tackles += 1;
        s.ev.push({ t: "tackle", p: p.i, won: true });
        if (rnd(s) < 0.6) take(s, p);
        else {
          const l = dist(p.x, p.z, c.x, c.z) || 1;
          const tx = (p.x - c.x) / l, tz = (p.z - c.z) / l, off = rndN(s) * 0.9, v = 3 + rnd(s) * 3.5;
          b.vx = (tx - tz * off) * v; b.vz = (tz + tx * off) * v;
          predict(s);
        }
      } else {
        p.cool = 54;
        s.ev.push({ t: "tackle", p: p.i, won: false });
      }
    } else p.cool = 40;
  }
  p.vx *= 0.92; p.vz *= 0.92;
  if (p.actT >= p.actLen) { p.act = Act.None; if (p.cool < 20) p.cool = 20; }
}

function stepSlide(s: MatchState, p: Player) {
  p.actT += 1;
  const b = s.ball;
  p.vx *= 0.97; p.vz *= 0.97;
  if (p.actT > 6 && p.actT < 32) {
    const c = b.owner >= 0 ? s.players[b.owner] : null;
    const db = dist(p.x + p.vx * 0.05, p.z + p.vz * 0.05, b.x, b.z);
    if (db < 1.15 && b.y < 0.6 && (c ? c.team !== p.team : true) && p.plan === null) {
      if (c) {
        // Ball first: it's knocked away, and he goes over.
        b.owner = -1;
        c.cool = 40;
        c.beat = 26; c.beatX = 0; c.beatZ = 0;
        if (dist(p.x, p.z, c.x, c.z) < 0.9 && rnd(s) < 0.3) fell(s, c, false);
        s.teams[p.team].tackles += 1;
        s.ev.push({ t: "tackle", p: p.i, won: true });
      }
      b.last = p.i; b.kick = Kick.Tackle; b.kicker = p.i; b.to = -1; b.since = 0;
      const l = Math.sqrt(p.vx * p.vx + p.vz * p.vz) || 1;
      const side = rndN(s) * 3;
      b.vx = (p.vx / l) * 7 - (p.vz / l) * side;
      b.vz = (p.vz / l) * 7 + (p.vx / l) * side;
      p.actT = Math.max(p.actT, 32);
      predict(s);
    } else if (c && c.team !== p.team && dist(p.x, p.z, c.x, c.z) < 0.95) {
      foul(s, p, c);
    }
  }
  if (p.actT >= p.actLen) {
    p.act = Act.Getup; p.actT = 0; p.actLen = 30; p.cool = 40;
  }
}

function foul(s: MatchState, p: Player, c: Player) {
  const team = c.team;
  const dir = dirOf(team);
  s.teams[p.team].fouls += 1;
  s.ev.push({ t: "foul", p: p.i, on: c.i });
  fell(s, c, true);
  const x = s.ball.x, z = s.ball.z;
  if (inBox(x, z, dir)) restart(s, "penalty", team, dir * (HALF_L - PEN_SPOT), 0);
  else restart(s, "free", team, x, z);
}

function stepFeint(s: MatchState, p: Player) {
  p.actT += 1;
  const t = p.actT;
  const right = { x: -p.hz * p.side, z: p.hx * p.side };
  if (p.sub === 0) {
    // Over the ball: hips one way, then away the other.
    const away = t > 16 ? 5.5 : 0;
    moveToward(p, p.hx * 3.5 - right.x * away, p.hz * 3.5 - right.z * away, 20);
  } else if (p.sub === 1) {
    // Drag back: stops, turns round.
    if (t < 14) moveToward(p, 0, 0, 22);
    else {
      if (t === 14) { p.hx = -p.hx; p.hz = -p.hz; }
      moveToward(p, p.hx * 5.5, p.hz * 5.5, 16);
    }
  } else if (p.sub === 2) {
    moveToward(p, right.x * 5.5 + p.hx * 2, right.z * 5.5 + p.hz * 2, 20);
  } else {
    // The roulette: round the defender.
    moveToward(p, p.hx * 3 + right.x * 3.5, p.hz * 3 + right.z * 3.5, 16);
  }
  if (t === 16) feintBites(s, p);
  if (t >= p.actLen || s.ball.owner !== p.i) p.act = Act.None;
}

function stepAct(s: MatchState, p: Player) {
  switch (p.act) {
    case Act.Kick: stepKick(s, p); break;
    case Act.Tackle: stepTackle(s, p); break;
    case Act.Slide: stepSlide(s, p); break;
    case Act.Feint: stepFeint(s, p); break;
    case Act.Trap:
      p.actT += 1;
      p.vx *= 0.95; p.vz *= 0.95;
      // The human's man never stands waiting for the end of a clip.
      if (p.actT >= (p.i === s.user ? Math.min(p.actLen, 7) : p.actLen)) p.act = Act.None;
      break;
    case Act.Down:
      p.actT += 1;
      p.vx *= 0.88; p.vz *= 0.88;
      if (p.actT >= p.actLen) { p.act = Act.Getup; p.actT = 0; p.actLen = 38; }
      break;
    case Act.Getup:
      p.actT += 1;
      p.vx = 0; p.vz = 0;
      if (p.actT >= p.actLen) p.act = Act.None;
      break;
    case Act.Header:
    case Act.Volley:
      p.actT += 1;
      p.vx *= 0.94; p.vz *= 0.94;
      p.air = p.act === Act.Header ? 0.45 * clamp(1 - Math.abs(p.actT - 12) / 14, 0, 1) : 0;
      if (p.actT >= p.actLen) { p.act = Act.None; p.air = 0; }
      break;
    case Act.GkThrow:
    case Act.GkKick: {
      p.actT += 1;
      const contact = p.act === Act.GkKick ? 22 : 16;
      if (p.actT === contact && p.plan) {
        s.ball.y = p.act === Act.GkKick ? 0.5 : 1.3;
        s.ball.owner = p.i;
        releaseKick(s, p);
      }
      if (p.actT >= p.actLen) p.act = Act.None;
      break;
    }
    case Act.Celebrate:
    case Act.Dejected:
      p.actT += 1;
      break;
    default:
  }
}

function stepPlayers(s: MatchState, inp: Input) {
  const b = s.ball;
  const userP = s.user;
  const meets = receiver(s);
  const live = (inp.mx !== 0 || inp.mz !== 0) && !s.locked;
  for (const p of s.players) {
    if (p.cool > 0) p.cool -= 1;
    if (p.role === "GK") stepKeeper(s, p);
    if (p.act !== Act.None && p.role === "GK" && (p.act === Act.Dive || p.act === Act.Catch || p.act === Act.Hold)) {
      p.x += p.act === Act.Dive ? 0 : p.vx * TICK;
      p.z += p.act === Act.Dive ? 0 : p.vz * TICK;
      continue;
    }
    if (p.act !== Act.None) stepAct(s, p);
    const free = p.act === Act.None;
    if (free) {
      if (p.beat > 0) {
        // Off balance: carried the wrong way for a moment.
        p.beat -= 1;
        moveToward(p, p.beatX * 2.4, p.beatZ * 2.4, 20);
      } else if (p === meets && !live) {
        // Until the thumb says otherwise he goes to the ball by himself.
        const q = meetPoint(s, p);
        steer(s, p, q.x, q.z, sprintOf(p));
      } else if (p.i === userP && !(s.set && s.set.taker === p.i) && (live || b.owner === p.i)) {
        const has = b.owner === p.i;
        const l = Math.sqrt(inp.mx * inp.mx + inp.mz * inp.mz);
        let ux = inp.mx / (l || 1), uz = inp.mz / (l || 1);
        // Steering roughly at a loose ball means steering at the ball.
        if (!has && b.owner < 0 && b.y < 1.3) {
          const dx = b.x + b.vx * 0.15 - p.x, dz = b.z + b.vz * 0.15 - p.z;
          const d = Math.sqrt(dx * dx + dz * dz) || 1;
          if (d < 6 && (ux * dx + uz * dz) / d > 0.1) {
            const nx = ux + (dx / d - ux) * 0.8, nz = uz + (dz / d - uz) * 0.8;
            const n = Math.sqrt(nx * nx + nz * nz) || 1;
            ux = nx / n; uz = nz / n;
          }
        }
        const top = inp.sprint ? sprintOf(p) * (has ? 0.94 : 1) : has ? 5.4 : 6;
        const v = top * clamp(l * 1.25, 0, 1);
        const fast = has && p.vx * p.vx + p.vz * p.vz > 42;
        moveToward(p, ux * v, uz * v, has ? ACCEL * 0.9 : ACCEL, fast ? BRAKE * 0.5 : BRAKE);
      } else steer(s, p, p.tx, p.tz, p.want);
    }
    p.x += p.vx * TICK;
    p.z += p.vz * TICK;
    // Facing.
    const v2 = p.vx * p.vx + p.vz * p.vz;
    p.stamina = clamp(p.stamina + (v2 > 42 ? -STAMINA_DRAIN : v2 < 26 ? STAMINA_BACK : STAMINA_BACK * 0.3), 0, 1);
    if (p.act === Act.None) {
      if (p.faceBall && p.i !== userP && v2 < 30) {
        const dx = b.x - p.x, dz = b.z - p.z;
        const d = Math.sqrt(dx * dx + dz * dz) || 1;
        faceTo(p, dx / d, dz / d, 0.1);
      } else if (v2 > 0.4) {
        const v = Math.sqrt(v2);
        const k = v > 6 ? 0.1 : 0.17;
        faceTo(p, p.vx / v, p.vz / v, k);
      }
    } else if (p.act === Act.Slide && v2 > 1) {
      const v = Math.sqrt(v2);
      faceTo(p, p.vx / v, p.vz / v, 0.3);
    }
  }
  // Keep apart.
  const ps = s.players;
  for (let i = 0; i < ps.length; i++) {
    const a = ps[i];
    for (let j = i + 1; j < ps.length; j++) {
      const c = ps[j];
      const dx = a.x - c.x, dz = a.z - c.z;
      if (dx > BODY || dx < -BODY || dz > BODY || dz < -BODY) continue;
      const q = dx * dx + dz * dz;
      if (q >= BODY * BODY || q < 1e-6) continue;
      if (a.act === Act.Down || c.act === Act.Down || a.act === Act.Slide || c.act === Act.Slide || a.act === Act.Dive || c.act === Act.Dive) continue;
      const d = Math.sqrt(q);
      const push = BODY - d;
      const ux = dx / d, uz = dz / d;
      // A man with the ball runs into a body and pays for it: he gives way
      // and loses his pace, the defender holds his ground.
      const rival = a.team !== c.team;
      const aHas = rival && b.owner === a.i, cHas = rival && b.owner === c.i;
      const ka = aHas ? 0.85 : cHas ? 0.15 : 0.5;
      a.x += ux * push * ka; a.z += uz * push * ka;
      c.x -= ux * push * (1 - ka); c.z -= uz * push * (1 - ka);
      if (aHas) { a.vx *= 0.93; a.vz *= 0.93; }
      if (cHas) { c.vx *= 0.93; c.vz *= 0.93; }
    }
  }
  for (const p of ps) {
    p.x = clamp(p.x, -HALF_L - 3, HALF_L + 3);
    p.z = clamp(p.z, -HALF_W - 3, HALF_W + 3);
  }
}

// --- the ball at his feet -----------------------------------------------------------------------------

function stepCarried(s: MatchState) {
  const b = s.ball;
  const p = s.players[b.owner];
  if (p.act === Act.Hold || p.act === Act.Catch || p.act === Act.GkThrow || p.act === Act.GkKick) {
    const up = p.act === Act.GkKick ? 0.9 : 1.05;
    b.x = p.x + p.hx * 0.32; b.z = p.z + p.hz * 0.32; b.y = up;
    b.vx = 0; b.vy = 0; b.vz = 0;
    return;
  }
  if (s.phase === Phase.Dead || s.phase === Phase.Kickoff) return;
  const v = Math.sqrt(p.vx * p.vx + p.vz * p.vz);
  p.touch -= 1;
  const period = v > 7 ? 26 : v > 4.5 ? 21 : 18;
  if (p.touch <= 0) p.touch = period;
  const phase = p.touch / period;
  const lead = p.act === Act.Kick ? 0.55
    : p.act === Act.Feint ? (p.sub === 1 ? 0.3 : 0.42)
      : 0.46 + v * 0.05 + phase * v * 0.075 + (v > 6.5 ? (v - 6.5) * 0.16 : 0);
  const ux = v > 0.5 ? p.vx / v : p.hx, uz = v > 0.5 ? p.vz / v : p.hz;
  const tx = p.x + ux * lead, tz = p.z + uz * lead;
  const k = p.act === Act.Feint ? 0.28 : 0.4;
  const nx = b.x + (tx - b.x) * k, nz = b.z + (tz - b.z) * k;
  b.vx = (nx - b.x) / TICK; b.vz = (nz - b.z) / TICK; b.vy = 0;
  // Brought down off the chest or the thigh, not teleported to his feet.
  b.x = nx; b.z = nz; b.y = b.y > BALL_R + 0.02 ? BALL_R + (b.y - BALL_R) * 0.8 : BALL_R;
  b.roll += Math.sqrt(b.vx * b.vx + b.vz * b.vz) * TICK / BALL_R;
  s.teams[p.team].possTicks += 1;
}

// --- contacts -----------------------------------------------------------------------------------------

function take(s: MatchState, p: Player) {
  const b = s.ball;
  const was = b.last;
  const speed = speedOf(b);
  if (p.off) {
    offside(s, p);
    return;
  }
  // A pass reached its man.
  if (b.last >= 0 && s.players[b.last].team === p.team && (b.kick === Kick.Pass || b.kick === Kick.Through || b.kick === Kick.Lob || b.kick === Kick.Cross || b.kick === Kick.GkRoll || b.kick === Kick.GkPunt || b.kick === Kick.Throw || b.kick === Kick.Corner)) {
    s.teams[p.team].passesOk += 1;
  }
  if (was >= 0 && was !== p.i) s.prevTouch = was;
  if (s.poss !== p.team) s.lostAt[s.poss] = s.tick;
  b.owner = p.i; b.last = p.i; b.kick = Kick.None; b.to = -1; b.since = 0;
  b.vy = 0;
  p.touch = 8;
  givePossession(s, p);
  toUser(s, p);
  for (const m of s.players) m.off = false;
  if (speed > 5 && p.act === Act.None) {
    p.act = Act.Trap; p.actT = 0; p.actLen = speed > 11 ? 20 : 14;
    p.side = p.hx * (b.z - p.z) - p.hz * (b.x - p.x) > 0 ? 1 : -1;
  }
  const w = s.want;
  s.want = null;
  if (w && p.i === s.user && s.tick <= s.wantT) {
    const press: Press = w.k === "shot" ? { k: "shot", power: w.power, curl: w.curl, chip: w.chip } : { k: w.k, power: w.power };
    userPress(s, p, { mx: s.wantX, mz: s.wantZ, sprint: false, press, contain: false });
  }
}

function offside(s: MatchState, p: Player) {
  s.ev.push({ t: "offside", p: p.i });
  const other: 0 | 1 = p.team === 0 ? 1 : 0;
  restart(s, "free", other, clamp(p.x, -HALF_L + 2, HALF_L - 2), p.z);
}

/** The team-mate worth a header: near enough, up the pitch, with some room. */
function headedTo(s: MatchState, p: Player): Player | null {
  const dir = dirOf(p.team);
  let best: Player | null = null, top = 0;
  for (const m of s.players) {
    if (m.team !== p.team || m.i === p.i || m.role === "GK" || m.act === Act.Down) continue;
    const d = dist(p.x, p.z, m.x, m.z);
    if (d < 5 || d > 19) continue;
    if (offsideNow(s, p, m)) continue;
    let open = 1e9;
    for (const o of s.players) if (o.team !== p.team) open = Math.min(open, dist(o.x, o.z, m.x, m.z));
    if (open < 3) continue;
    const v = Math.min(open, 8) + (m.x - p.x) * dir * 0.2 + 2;
    if (v > top) { top = v; best = m; }
  }
  return best;
}

/** Struck first time: on goal or away, whoever it is. */
function headOrVolley(s: MatchState, p: Player, foot: boolean) {
  const b = s.ball;
  const dir = dirOf(p.team);
  const x = p.x * dir;
  const human = p.i === s.user;
  const asked = human && s.wantShot > 0;
  if (p.off) {
    offside(s, p);
    return;
  }
  b.last = p.i; b.kicker = p.i; b.since = 0; b.to = -1;
  b.owner = -1;
  p.act = foot ? Act.Volley : Act.Header; p.actT = 0; p.actLen = 26;
  p.cool = 14;
  b.fromX = b.x; b.fromZ = b.z;
  const want = human && s.tick <= s.wantT ? s.want : null;
  s.want = null;
  const elsewhere = want !== null && want.k !== "shot";
  const near = !elsewhere && (x > HALF_L - 18 || (asked && x > HALF_L - 30)) && Math.abs(p.z) < 16;
  const gx = dir * HALF_L;
  if (near) {
    const k = s.players.find((q) => q.team !== p.team && q.role === "GK");
    const aim = k ? (k.z > 0 ? -1 : 1) : 1;
    const tz = aim * (2 + rnd(s) * 1.4) + rndN(s) * (asked ? 1.2 : 2.2) * (1.2 - p.shot);
    const ty = foot ? 0.5 : 0.4 + rnd(s) * 1.7;
    const d = dist(b.x, b.z, gx, tz) || 1;
    const pace = (foot ? 20 : 12.5) + rnd(s) * 6 + (asked ? 3 : 0);
    const t = d / pace;
    b.vx = ((gx - b.x) / d) * pace; b.vz = ((tz - b.z) / d) * pace;
    b.vy = (ty - b.y) / t + 4.9 * t;
    b.kick = Kick.Shot;
    s.teams[p.team].shots += 1;
    if (Math.abs(tz) < GOAL_HALF) s.teams[p.team].onTarget += 1;
  } else {
    // Nodded on to a team-mate if one is there, else away from danger.
    const to = elsewhere ? bestMate(s, p, s.wantX, s.wantZ, want.k !== "pass") : x > -HALF_L + 22 ? headedTo(s, p) : null;
    if (to) {
      const d = dist(b.x, b.z, to.x, to.z) || 1;
      const pace = clamp(d / 0.95, 7, 15);
      const off = rndN(s) * 0.12;
      const ux = (to.x - b.x) / d, uz = (to.z - b.z) / d;
      b.vx = (ux - uz * off) * pace; b.vz = (uz + ux * off) * pace; b.vy = 3.6;
      b.to = to.i;
    } else {
      const pace = foot ? 12 : 8 + rnd(s) * 4;
      let ux = dir, uz = rndN(s);
      if (x < -20) uz += p.z > 0 ? 0.6 : -0.6;
      // Under pressure at his own goal he gets anything on it: behind, for a corner.
      if (x < -HALF_L + 16 && rnd(s) < 0.4) ux = -dir * (0.7 + rnd(s) * 0.5);
      const l = Math.sqrt(ux * ux + uz * uz);
      ux /= l; uz /= l;
      b.vx = ux * pace; b.vz = uz * pace; b.vy = 1.5 + rnd(s) * 3;
    }
    b.kick = Kick.Header;
  }
  b.sx = 0; b.sy = 0; b.sz = 0;
  for (const m of s.players) m.off = false;
  predict(s);
  s.ev.push({ t: "kick", p: p.i, kind: foot ? Kick.Shot : Kick.Header, speed: speedOf(b) });
}

/** Blocks, interceptions and touches on the free ball. */
function contacts(s: MatchState) {
  const b = s.ball;
  if (b.inNet) return;
  const fast = speedOf(b);
  const keeperBall = b.last >= 0 && s.players[b.last].role === "GK" && b.since < 26 && b.y > 0.5 && (b.kick === Kick.GkPunt || b.kick === Kick.Lob);
  let best: Player | null = null, top = 1e9;
  for (const p of s.players) {
    if (p.role === "GK") continue;
    if (p.act === Act.Down || p.act === Act.Getup || p.act === Act.Slide) continue;
    if (p.i === b.last && b.since < 14) continue;
    if (p.cool > 0 && p.act === Act.Tackle) continue;
    // He just lost it: it isn't his to pick straight back up.
    if (p.beat > 0 && b.kick === Kick.Tackle) continue;
    // Out of the keeper's hands it goes over a man standing in front of him.
    if (keeperBall && p.team !== s.players[b.last].team) continue;
    const dx = b.x - p.x, dz = b.z - p.z;
    const q = dx * dx + dz * dz;
    if (q > 2.6) continue;
    const r = q + (p.i === b.to ? -0.6 : 0);
    if (r < top) { top = r; best = p; }
  }
  if (!best) return;
  const p = best;
  const d = Math.sqrt(top < 0 ? 0 : top);
  if (b.y < 0.75) {
    if (d > REACH + (p.i === b.to || p.i === s.user ? 0.55 : 0.25)) return;
    const mine = b.last >= 0 && s.players[b.last].team === p.team;
    if (fast > 13 && !mine) {
      // A hard ball at an opponent: it comes off him more often than he stops it.
      const stop = clamp(0.62 + p.defend * 0.25 - (fast - 13) * 0.045, 0.1, 0.9);
      if (b.kick === Kick.Shot || rnd(s) > stop) {
        const ux = rndN(s), uz = rndN(s);
        b.vx = b.vx * -0.25 + ux * 4; b.vz = b.vz * -0.25 + uz * 5; b.vy = 1 + rnd(s) * 3.5;
        b.last = p.i; b.since = 0; b.kicker = p.i; b.to = -1;
        if (b.kick !== Kick.Shot) b.kick = Kick.Tackle;
        predict(s);
        s.ev.push({ t: "kick", p: p.i, kind: Kick.Tackle, speed: 6 });
        p.cool = 12;
        return;
      }
    }
    // A low cross in the box is a first-time chance.
    const dir = dirOf(p.team);
    const box = inBox(p.x, p.z, dir) && Math.abs(p.z) < 15 && (b.kick === Kick.Cross || b.kick === Kick.Corner || b.kick === Kick.Save) && mine === (b.kick !== Kick.Save);
    if (box && b.y > 0.3) {
      headOrVolley(s, p, true);
      return;
    }
    if (p.act === Act.Kick) return;
    // A poor first touch off a hot pass.
    if (fast > 12 && !(mine && p.i === s.user) && rnd(s) > 0.55 + p.dribble * 0.4) {
      b.vx = b.vx * 0.3 + rndN(s) * 3; b.vz = b.vz * 0.3 + rndN(s) * 3; b.vy = 1;
      b.last = p.i; b.since = 2; b.kick = Kick.None;
      p.cool = 16;
      predict(s);
      return;
    }
    take(s, p);
    return;
  }
  if (b.y < 2.75 && d < 1.3) {
    if (b.since < 6) return;
    // Nobody on him: he brings it down, chest or thigh, however it comes.
    let alone = true;
    for (const o of s.players) {
      if (o.team !== p.team && o.role !== "GK" && dist(o.x, o.z, b.x, b.z) < (p.i === b.to ? 1.3 : 1.8)) alone = false;
    }
    const ours = b.last >= 0 && s.players[b.last].team === p.team;
    const crossed = b.kick === Kick.Cross || b.kick === Kick.Corner;
    const chance = crossed && inBox(p.x, p.z, dirOf(p.team)) && Math.abs(p.z) < 15;
    if (alone && !(chance && ours) && (p.act === Act.None || p.act === Act.Trap)) {
      if (b.y < 2.1 && fast < 25) {
        take(s, p);
        return;
      }
      // It is coming down to him: he waits for it rather than heading it at nobody.
      if (b.vy < 0) return;
    }
    if (d > 1.05) return;
    // The nearest of each side jumps: the better one gets there first.
    let rival: Player | null = null, rv = 1.5;
    for (const o of s.players) {
      if (o.team === p.team || o.role === "GK") continue;
      const e = dist(o.x, o.z, b.x, b.z);
      if (e < rv) { rv = e; rival = o; }
    }
    let win = p;
    // The man it was hit to knows it's coming: he has the better of the jump.
    const edge = rival && rival.i === b.to ? 0.17 : p.i === b.to ? -0.17 : 0;
    if (rival && rnd(s) < 0.45 + edge + (rival.defend - p.defend) * 0.5) win = rival;
    const high = b.y > 1.35;
    headOrVolley(s, win, !high);
  }
}

// --- rules ------------------------------------------------------------------------------------------

function laws(s: MatchState) {
  const b = s.ball;
  if (s.phase !== Phase.Play || b.owner >= 0) return;
  const inMouth = Math.abs(b.z) < GOAL_HALF - BALL_R && b.y < GOAL_H - BALL_R;
  if (Math.abs(b.x) > HALF_L + BALL_R) {
    if (inMouth || b.inNet) {
      if (!b.inNet) {
        b.inNet = true;
        s.ev.push({ t: "net" });
        scored(s, b.x > 0 ? 0 : 1);
      }
      return;
    }
    afterBallOut(s);
    return;
  }
  if (Math.abs(b.z) > HALF_W + BALL_R) afterBallOut(s);
}

function runRestart(s: MatchState, inp: Input) {
  const set = s.set!;
  const b = s.ball;
  set.t += 1;
  const t = s.players[set.taker];
  const spot = set.kind === "kickoff" ? { x: t.team === 0 ? -0.5 : 0.5, z: 0 } : { x: set.x, z: set.z };
  const dx = spot.x - t.x, dz = spot.z - t.z;
  const d = Math.sqrt(dx * dx + dz * dz);
  // The ball is back on its spot.
  if (set.t === 45 || (set.t < 45 && d < 2)) ballAt(b, set.x, BALL_R, set.z);
  if (set.kind === "throw" && set.ready) b.y = 2.05;
  if (!set.ready) {
    t.tx = spot.x; t.tz = spot.z; t.want = d > 6 ? 6.5 : 4.2;
    if (d < 0.5 && set.t > SET_MIN * 0.6) {
      set.ready = true;
      t.vx = 0; t.vz = 0;
      const gx = dirOf(t.team) * HALF_L;
      const l = dist(t.x, t.z, gx, 0) || 1;
      t.hx = (gx - t.x) / l; t.hz = -t.z / l;
      if (set.kind === "throw") { t.hx = 0; t.hz = -Math.sign(set.z); }
      b.owner = t.i;
      ballAt(b, set.x + t.hx * 0.45, set.kind === "throw" ? 2.05 : BALL_R, set.z + t.hz * 0.45);
      b.owner = t.i;
      s.ev.push({ t: "whistle", n: 1 });
      if (sceneKick(s, set)) set.scene = Math.floor(rnd(s) * 2147483647);
    }
    return;
  }
  t.want = 0;
  // The swipe scene has it: the match waits for the outcome, and has no clock
  // of its own on it. No outcome (the scene failed): it is played right here.
  if (set.scene >= 0) {
    if (inp.press?.k !== "scene") return;
    if (inp.press.outcome) {
      sceneResult(s, t, inp.press.outcome);
      return;
    }
    set.scene = -1;
    set.t = SET_MIN;
    return;
  }
  const human = s.user === t.i;
  if (human) {
    if (inp.mx !== 0 || inp.mz !== 0) s.idle = 0;
    if (set.t > SET_MIN + USER_WAIT) goSet(s, t);
    else if (inp.press) {
      const was = t.act;
      userPress(s, t, inp);
      if (t.act !== was) startPlay(s);
    }
    return;
  }
  if (set.t > SET_MIN + (set.kind === "corner" || set.kind === "free" ? 110 : 30)) goSet(s, t);
}

/** Does this restart go to the scene? The human's own close free kick, and
 * every penalty he is in. */
function sceneKick(s: MatchState, set: SetPiece) {
  const ut = userTeam(s);
  if (ut === null) return false;
  if (set.kind === "penalty") return true;
  if (set.kind !== "free" || set.team !== ut) return false;
  const distance = HALF_L - set.x * dirOf(set.team);
  return distance > 16 && distance < FREE_SCENE_MAX && Math.abs(set.z) < FREE_SCENE_WIDE;
}

/** What the scene needs for the kick waiting on it, if one is. */
export function sceneOf(s: MatchState): SceneKick | null {
  const set = s.set;
  if (!set || set.scene < 0) return null;
  const dir = dirOf(set.team);
  return {
    kind: set.team !== userTeam(s) ? "keep" : set.kind === "penalty" ? "penalty" : "free",
    seed: set.scene,
    rating: clamp(Math.round(s.players[set.taker].shot * 100), 55, 95),
    distance: HALF_L - set.x * dir,
    // Looking at the goal, the scene's right is the attackers' right.
    offset: set.z * dir,
  };
}

/** The scene's kick comes back as what it did to the match. */
function sceneResult(s: MatchState, t: Player, outcome: SceneOutcome) {
  const set = s.set!;
  const b = s.ball;
  const team = set.team;
  const other: 0 | 1 = team === 0 ? 1 : 0;
  const dir = dirOf(team);
  const tm = s.teams[team];
  const keeper = s.players.find((p) => p.team === other && p.role === "GK")!;
  tm.shots += 1;
  if (outcome === "goal" || outcome === "save") tm.onTarget += 1;
  b.owner = -1; b.last = t.i; b.kicker = t.i; b.kick = Kick.Shot; b.to = -1; b.since = 0;
  b.fromX = set.x; b.fromZ = set.z;
  if (outcome === "goal") {
    ballAt(b, dir * (HALF_L + 0.8), 1, 0);
    b.inNet = true;
    s.ev.push({ t: "net" });
    scored(s, team);
    s.lastGoal!.scene = true;
    return;
  }
  if (outcome === "miss") {
    s.ev.push({ t: "miss", p: t.i, near: true });
    restart(s, "goalkick", other, dir * (HALF_L - SIX_D), 0);
    return;
  }
  if (outcome === "save") {
    s.ev.push({ t: "save", p: keeper.i, held: true });
    ballAt(b, keeper.x, 1.05, keeper.z);
    holdBall(s, keeper);
    startPlay(s);
    return;
  }
  // Off the wall and loose in front of it.
  const gx = dir * HALF_L;
  const d = dist(set.x, set.z, gx, 0) || 1;
  const ux = (gx - set.x) / d, uz = -set.z / d;
  ballAt(b, set.x + ux * 8, 0.5, set.z + uz * 8);
  b.vx = -ux * (5 + rnd(s) * 4) + uz * rndN(s) * 3;
  b.vz = -uz * (5 + rnd(s) * 4) - ux * rndN(s) * 3;
  b.vy = 2;
  b.kick = Kick.Tackle;
  predict(s);
  startPlay(s);
  s.poss = other;
}

function goSet(s: MatchState, t: Player) {
  takeSetPiece(s, t, s.set!);
  startPlay(s);
}

function startPlay(s: MatchState) {
  s.phase = Phase.Play;
  s.phaseT = 0;
  s.set = null;
  s.poss = s.players[s.ball.owner >= 0 ? s.ball.owner : 0].team;
}

/** Who a pass goes to with the stick as it is now (for the mark on the pitch). */
export function passTarget(s: MatchState, mx: number, mz: number): number {
  if (s.user < 0) return -1;
  const p = s.players[s.user];
  if (s.ball.owner !== p.i && !(s.set && s.set.taker === p.i && s.set.ready)) return -1;
  const l = Math.sqrt(mx * mx + mz * mz);
  const m = bestMate(s, p, l > 0.2 ? mx / l : 0, l > 0.2 ? mz / l : 0, false);
  return m ? m.i : -1;
}

// --- the tick ---------------------------------------------------------------------------------------

export function stepMatch(s: MatchState, inp: Input) {
  s.tick += 1;
  s.phaseT += 1;
  s.ev.length = 0;
  if (s.phase === Phase.FullTime) {
    stepPlayers(s, NO_INPUT);
    return;
  }
  if (s.wantShot > 0) s.wantShot -= 1;
  s.idle = inp.mx !== 0 || inp.mz !== 0 || inp.press ? 0 : s.idle + 1;
  s.contain = inp.contain;
  readStick(s, inp);

  if (s.phase !== Phase.Goal) s.clock += CLOCK_RATE;

  if (s.phase === Phase.Goal) {
    celebrate(s);
    stepPlayers(s, NO_INPUT);
    stepBall(s);
    if (s.phaseT >= GOAL_PAUSE) {
      const g = s.lastGoal!;
      resetAfterGoal(s);
      restart(s, "kickoff", g.team === 0 ? 1 : 0, 0, 0);
      lineUp(s);
    }
    return;
  }

  // Brains.
  if (s.tick % 6 === 0) { thinkTeam(s, 0, SLOTS[0]); thinkTeam(s, 1, SLOTS[1]); }
  for (const p of s.players) {
    const slot = SLOTS[p.team][p.slot];
    if (p.role === "GK") { thinkPlayer(s, p, slot); continue; }
    // The man on the ball re-reads it every few ticks, the rest a few times a second.
    if (((s.tick + p.i * 3) % 12 === 0 || (p.duty === 1 && s.tick % 3 === 0)) && p.act === Act.None) thinkPlayer(s, p, slot);
  }

  if (s.phase === Phase.Dead || s.phase === Phase.Kickoff) {
    runRestart(s, inp);
  } else {
    const b = s.ball;
    if (b.owner >= 0 && b.owner !== s.user && (s.tick + b.owner) % 6 === 0) {
      const c = s.players[b.owner];
      if (c.act === Act.None && c.role !== "GK" && b.since > 8) thinkCarrier(s, c);
      else if (c.act === Act.None && c.role === "GK") thinkCarrier(s, c);
    }
    if (b.owner >= 0) {
      b.since += 1;
    }
    for (const p of s.players) {
      if (p.act === Act.None && p.role !== "GK") thinkTackle(s, p);
    }
    userAutoSwitch(s);
    if (s.user >= 0 && inp.press) userPress(s, s.players[s.user], inp);
  }

  stepPlayers(s, inp);

  if (s.ball.owner >= 0) stepCarried(s);
  else if (s.phase === Phase.Play) {
    stepBall(s);
    assistPass(s);
  }
  if (s.phase === Phase.Play && s.ball.owner < 0) contacts(s);
  laws(s);

  const regular = (END_MIN - START_MIN) * 60;
  if (s.added === 0 && s.clock >= regular) {
    // The board goes up: for the goals and stoppages of these ten minutes.
    const a = s.teams[0], c = s.teams[1];
    s.added = Math.min(150, 45 + (a.goals + c.goals) * 30 + (a.fouls + c.fouls) * 10);
    s.ev.push({ t: "added", seconds: s.added });
  }
  const end = regular + s.added;
  if (s.phase === Phase.Play && s.clock >= end) {
    const ax = Math.abs(s.ball.x);
    const late = s.clock - end > (LATE_MAX * CLOCK_RATE);
    if (ax < HALF_L - 25 || late) {
      s.phase = Phase.FullTime;
      s.phaseT = 0;
      s.ev.push({ t: "whistle", n: 3 });
      const a = s.teams[0].goals, c = s.teams[1].goals;
      for (const p of s.players) {
        p.plan = null;
        p.want = 0; p.tx = p.x; p.tz = p.z;
        if (a === c) p.act = Act.None;
        else p.act = (p.team === 0) === (a > c) ? Act.Celebrate : Act.Dejected;
        p.actT = 0;
      }
    }
  }
}

function celebrate(s: MatchState) {
  const g = s.lastGoal!;
  for (const p of s.players) {
    if (p.team === g.team) {
      if (p.i === g.p) {
        if (s.phaseT === 1) {
          const out = Math.sign(p.z || 1);
          p.tx = dirOf(p.team) * (HALF_L - 6);
          p.tz = out * (HALF_W - 4);
        }
        p.want = 6.5;
        if (dist(p.x, p.z, p.tx, p.tz) < 2 && p.act !== Act.Celebrate) { p.act = Act.Celebrate; p.actT = 0; }
      } else if (p.role !== "GK") {
        if (g.p >= 0) { const c = s.players[g.p]; p.tx = c.x; p.tz = c.z; }
        p.want = dist(p.x, p.z, p.tx, p.tz) > 3 ? 5.5 : 0;
      }
    } else if (p.act === Act.None) {
      p.want = 0;
      if (s.phaseT === 30 && p.role !== "GK" && dist(p.x, p.z, s.ball.x, s.ball.z) < 30) { p.act = Act.Dejected; p.actT = 0; }
    }
  }
}

function resetAfterGoal(s: MatchState) {
  const b = s.ball;
  ballAt(b, 0, BALL_R, 0);
  b.inNet = false; b.owner = -1; b.last = -1;
  for (const p of s.players) {
    if (p.act === Act.Celebrate || p.act === Act.Dejected) p.act = Act.None;
    p.air = 0;
  }
}

export const clockText = (s: MatchState) => {
  const total = START_MIN * 60 + s.clock;
  const m = Math.floor(total / 60);
  const sec = Math.floor(total - m * 60);
  return `${m}:${sec < 10 ? "0" : ""}${sec}`;
};
