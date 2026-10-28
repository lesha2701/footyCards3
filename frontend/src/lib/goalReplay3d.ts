/** 3D goal replays of a career match, over the same key frames as the 2D
 * view (backend career_replay_service). The episode of a goal is the part
 * of its "goal" segment from the build-up to the ball in the net plus the
 * celebration; players and the ball's ground position come straight from
 * the frames. The frames have no height, so the ball's flights (crosses,
 * long passes, the shot) get one here — deterministically from the event
 * (set piece, action, shot type) and its index, never at random, so a
 * replay looks the same every time. Pure functions; the scene only draws
 * them. Nothing here changes what happened in the match. */
import type { CareerReplay } from "@/api/career";
import {
  PITCH_L,
  PITCH_W,
  ballAt,
  groundBall,
  holderAt,
  lerp,
  type MatchEventLite,
  type Point,
  type Timeline,
} from "@/lib/matchReplay";

export const BALL_R = 0.11;
export const HEAD_H = 2.05;
export const GOAL_HALF = 3.66;
export const CROSSBAR = 2.44;
export const NET_DEPTH = 1.8;
/** career_replay_service._celebrate: dead(8) after the ball crosses the line. */
export const CELEBRATION_FRAMES = 8;
/** career_replay_service._reset_kickoff after a goal. */
const RESET_FRAMES = 6;
/** Build-up shown before the goal: 15 s of game time at most. */
export const MAX_LEAD_FRAMES = 30;
/** Ball resting in the net, metres behind the goal line. */
const NET_REST = 1.3;
/** Playback slows down around the shot (fraction of real time). */
export const SLOW_RATE = 0.4;

export type FinishKind = "shot" | "long_range" | "header" | "free_kick" | "penalty" | "empty_net";

export interface BallPos { x: number; y: number; h: number }

/** The ball flies from `from` (at frame f0) to `to` (at f1) in a straight
 * line over the ground with a parabola of `lift` metres on top of the
 * linear height change. Endpoints are key-frame positions, so a flight
 * starts and ends exactly where the 2D view has the ball. */
export interface Flight { f0: number; f1: number; from: BallPos; to: BallPos; lift: number }

export interface GoalEpisode {
  /** Index of the goal in the event log. */
  event: number;
  side: "a" | "b";
  minute: number;
  /** First and last frame shown (inclusive). */
  f0: number;
  f1: number;
  /** Frame the shot is struck from and the frame the ball crosses the line. */
  shot: number;
  goal: number;
  /** Pitch slot of the scorer (the holder when the shot is struck). */
  scorer: number | null;
  finish: FinishKind;
  flights: Flight[];
  /** Milliseconds per frame at x1 (the goal segment's). */
  msPerFrame: number;
}

/** Deterministic [0, 1) from integers (mulberry32 step). */
export function unit(...keys: number[]): number {
  let h = 0x9e3779b9;
  for (const k of keys) h = Math.imul(h ^ Math.floor(k), 0x85ebca6b) + 0x27d4eb2f;
  h = Math.imul(h ^ (h >>> 15), h | 1);
  h ^= h + Math.imul(h ^ (h >>> 7), h | 61);
  return ((h ^ (h >>> 14)) >>> 0) / 4294967296;
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export function finishKind(e: MatchEventLite | undefined): FinishKind {
  const p = (e?.payload ?? {}) as Record<string, unknown>;
  if (p.is_penalty || p.set_piece === "penalty") return "penalty";
  if (p.set_piece === "free_kick") return "free_kick";
  if (p.action === "header" || p.set_piece === "corner" || p.aerial_duel) return "header";
  if (p.shot_type === "empty_net") return "empty_net";
  if (p.shot_type === "long_range") return "long_range";
  return "shot";
}

/** Height the ball crosses the goal line at (always under the bar) and the
 * extra arc of the shot. */
export function shotProfile(finish: FinishKind, event: number): { h0: number; h1: number; lift: number } {
  const r = unit(event, 7);
  switch (finish) {
    case "penalty": return { h0: BALL_R, h1: lerp(0.25, 1.7, r), lift: 0.1 };
    case "free_kick": return { h0: BALL_R, h1: lerp(1.3, 2.15, r), lift: 2.3 };
    case "header": return { h0: HEAD_H, h1: lerp(0.3, 1.4, r), lift: 0 };
    case "long_range": return { h0: BALL_R, h1: lerp(0.8, 2.15, r), lift: 0.9 };
    case "empty_net": return { h0: BALL_R, h1: BALL_R, lift: 0 };
    default: return { h0: BALL_R, h1: lerp(0.15, 1.5, r), lift: 0.25 };
  }
}

const ground = (p: Point, h = BALL_R): BallPos => ({ x: p.x, y: p.y, h });
const dist = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);

function buildFlights(tl: Timeline, replay: CareerReplay, ep: Omit<GoalEpisode, "flights">): Flight[] {
  const flights: Flight[] = [];
  const { shot, goal, f0, f1, scorer, finish, event } = ep;
  const passes = replay.passes.filter(([p0, p1]) => p0 >= f0 && p1 <= shot);
  // A header: the last ball to the scorer is a cross that meets his head
  // when he strikes it (it absorbs the frames he "holds" it in 2D).
  const cross = finish === "header" && scorer !== null
    ? [...passes].reverse().find(([, , , to]) => to === scorer) ?? null
    : null;
  for (const pass of passes) {
    const [p0, p1] = pass;
    const a = groundBall(tl, p0);
    if (pass === cross) {
      const b = groundBall(tl, shot);
      flights.push({ f0: p0, f1: shot, from: ground(a), to: ground(b, HEAD_H), lift: clamp(dist(a, b) * 0.13, 2.5, 6) });
      continue;
    }
    const b = groundBall(tl, p1);
    const d = dist(a, b);
    if (d > 24 && p1 > p0) {
      flights.push({ f0: p0, f1: p1, from: ground(a), to: ground(b), lift: clamp(d * 0.11, 1.2, 6) });
    }
  }
  // The shot itself, then the ball settles in the net.
  const prof = shotProfile(finish, event);
  if (finish === "header" && cross === null) prof.h0 = BALL_R; // no cross drawn: a volley off the grass
  const s = groundBall(tl, shot);
  const g = ballAt(tl, goal);
  flights.push({ f0: shot, f1: goal, from: ground(s, prof.h0), to: ground(g, prof.h1), lift: prof.lift });
  const rest = netRest(g, ep.side);
  if (f1 > goal) {
    flights.push({ f0: goal, f1: goal + 1, from: ground(g, prof.h1), to: rest, lift: 0 });
    if (f1 > goal + 1) flights.push({ f0: goal + 1, f1, from: rest, to: rest, lift: 0 });
  }
  return flights;
}

/** Where the ball ends up inside the goal `side` scored in. */
export function netRest(line: Point, side: "a" | "b"): BallPos {
  const x = PITCH_W / 2 + clamp(line.x - PITCH_W / 2, -GOAL_HALF + 0.5, GOAL_HALF - 0.5) * 0.85;
  return { x, y: side === "a" ? PITCH_L + NET_REST : -NET_REST, h: BALL_R };
}

/** One episode per goal of the log that has a mark on the timeline, in
 * match order. */
export function goalEpisodes(tl: Timeline, replay: CareerReplay, events: MatchEventLite[]): GoalEpisode[] {
  const goals = replay.marks
    .filter(([, idx]) => events[idx]?.event_type === "goal")
    .sort((a, b) => a[0] - b[0]);
  const out: GoalEpisode[] = [];
  goals.forEach(([goal, event], i) => {
    const e = events[event];
    if (e.team !== "a" && e.team !== "b") return;
    const seg = replay.segments.find(([, s0, n]) => s0 <= goal && goal < s0 + n);
    if (!seg || goal < 2) return;
    const [, s0, n, , , ms] = seg;
    const prev = i > 0 && goals[i - 1][0] >= s0 ? goals[i - 1][0] : null;
    const f0 = Math.max(s0, prev !== null ? prev + 1 + CELEBRATION_FRAMES + RESET_FRAMES : s0, goal - MAX_LEAD_FRAMES);
    const f1 = Math.min(s0 + n - 1, goal + CELEBRATION_FRAMES, tl.count - 1);
    const shot = Math.max(f0, goal - 2);
    const base = {
      event, side: e.team, minute: e.minute, f0, f1, shot, goal,
      scorer: holderAt(tl, shot), finish: finishKind(e), msPerFrame: ms || 500,
    } as const;
    out.push({ ...base, flights: buildFlights(tl, replay, base) });
  });
  return out;
}

/** Ball at episode time `t` (fractional frame). */
export function ballState(tl: Timeline, ep: GoalEpisode, t: number): BallPos {
  for (let i = ep.flights.length - 1; i >= 0; i--) {
    const fl = ep.flights[i];
    if (fl.f0 <= t && t <= fl.f1) {
      const u = fl.f1 > fl.f0 ? (t - fl.f0) / (fl.f1 - fl.f0) : 1;
      return {
        x: lerp(fl.from.x, fl.to.x, u),
        y: lerp(fl.from.y, fl.to.y, u),
        h: lerp(fl.from.h, fl.to.h, u) + 4 * fl.lift * u * (1 - u),
      };
    }
  }
  return ground(groundBall(tl, t));
}

/** Playback speed around episode time `t`: slow motion for the strike. */
export function episodeRate(ep: GoalEpisode, t: number): number {
  return t >= ep.shot - 1 && t <= ep.goal + 1 ? SLOW_RATE : 1;
}

/** Advances episode time by `dtMs` of wall clock at `speed`. */
export function advance(ep: GoalEpisode, t: number, dtMs: number, speed = 1): number {
  return Math.min(ep.f1, t + (dtMs / ep.msPerFrame) * speed * episodeRate(ep, t));
}

/** Wall-clock length of the whole episode at x1 (ms). */
export function episodeDuration(ep: GoalEpisode): number {
  let t = ep.f0;
  let ms = 0;
  while (t < ep.f1 && ms < 600_000) {
    t = advance(ep, t, 16);
    ms += 16;
  }
  return ms;
}

/** Scene coordinates: X along the pitch (the viewer's team attacks +X),
 * Z across, Y up; the centre spot at the origin. */
export function toWorld(p: Point, flip: boolean): { x: number; z: number } {
  return flip
    ? { x: PITCH_L / 2 - p.y, z: PITCH_W / 2 - p.x }
    : { x: p.y - PITCH_L / 2, z: p.x - PITCH_W / 2 };
}

export type CameraMode = "tv" | "goal" | "top";

export interface CameraPose { pos: [number, number, number]; look: [number, number, number] }

/** Camera for a mode around the focus (scene X, Z) when the goal being
 * attacked is at scene X = goalX (±52.5). */
export function cameraPose(mode: CameraMode, fx: number, fz: number, goalX: number, portrait: boolean): CameraPose {
  const dir = Math.sign(goalX) || 1;
  if (mode === "goal") {
    return { pos: [goalX + dir * 5, portrait ? 6 : 4.5, fz * 0.3], look: [fx, 0.8, fz] };
  }
  if (mode === "top") {
    return { pos: [fx - dir * 6, portrait ? 62 : 44, fz + 14], look: [fx, 0, fz] };
  }
  const cx = clamp(fx, -40, 40);
  const back = portrait ? 66 : 46;
  return { pos: [cx, portrait ? 27 : 17, back], look: [cx, 0, fz * 0.5] };
}
