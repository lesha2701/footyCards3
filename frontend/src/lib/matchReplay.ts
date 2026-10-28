/** 2D career match replay (backend career_replay_service): decoding the
 * quantised key frames, the playback timeline (each frame lasts its
 * segment's ms at x1 — episodes in real time, bridges accelerated),
 * smooth interpolation between frames and the scoreboard figures at any
 * point of the show. Pure functions — the viewer only draws them. */
import type { CareerReplay } from "@/api/career";

export const PITCH_W = 68;
export const PITCH_L = 105;
export const SLOTS = 22;
const NO_HOLDER = 255;

export interface Point { x: number; y: number }

/** Kits of both viewers: the viewer's side in lime, the other in red;
 * keepers stand out. */
export const REPLAY_KITS = {
  mine: { fill: "#c6e63a", text: "#0b1a12", gk: "#22d3c4", shorts: "#14301f" },
  theirs: { fill: "#f87171", text: "#ffffff", gk: "#fb923c", shorts: "#f3f4f6" },
};

export interface Timeline {
  count: number;
  /** Playback time (ms at x1) at which each frame is shown. */
  starts: Float64Array;
  /** Game clock (seconds) at each frame. */
  clocks: Float64Array;
  total: number;
  bytes: Uint8Array;
  size: number;
  /** Cumulative frames with the ball held by side a / b (possession). */
  heldA: Uint32Array;
  heldB: Uint32Array;
}

export function decodeBase64(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function buildTimeline(replay: CareerReplay): Timeline {
  const bytes = decodeBase64(replay.frames);
  const size = replay.frame_size;
  const count = Math.floor(bytes.length / size);
  const starts = new Float64Array(count + 1);
  const clocks = new Float64Array(count);
  const heldA = new Uint32Array(count + 1);
  const heldB = new Uint32Array(count + 1);
  let t = 0;
  for (const [, f0, n, t0, t1, ms] of replay.segments) {
    for (let k = 0; k < n && f0 + k < count; k++) {
      starts[f0 + k] = t;
      clocks[f0 + k] = t0 + ((t1 - t0) * k) / Math.max(1, n);
      t += ms;
    }
  }
  starts[count] = t;
  for (let f = 0; f < count; f++) {
    const holder = bytes[f * size + 2];
    heldA[f + 1] = heldA[f] + (holder !== NO_HOLDER && holder < 11 ? 1 : 0);
    heldB[f + 1] = heldB[f] + (holder !== NO_HOLDER && holder >= 11 ? 1 : 0);
  }
  return { count, starts, clocks, total: count > 0 ? starts[count - 1] : 0, bytes, size, heldA, heldB };
}

/** The frame shown at playback time `ms` and how far (0-1) it is towards
 * the next one. */
export function frameAt(tl: Timeline, ms: number): { frame: number; frac: number } {
  if (tl.count === 0) return { frame: 0, frac: 0 };
  if (ms <= 0) return { frame: 0, frac: 0 };
  if (ms >= tl.total) return { frame: tl.count - 1, frac: 0 };
  let lo = 0;
  let hi = tl.count - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (tl.starts[mid] <= ms) lo = mid;
    else hi = mid - 1;
  }
  const span = tl.starts[lo + 1] - tl.starts[lo];
  return { frame: lo, frac: span > 0 ? Math.min(1, (ms - tl.starts[lo]) / span) : 0 };
}

function raw(tl: Timeline, frame: number, offset: number): Point {
  const f = Math.max(0, Math.min(tl.count - 1, frame));
  const base = f * tl.size + offset;
  return { x: (tl.bytes[base] / 255) * PITCH_W, y: (tl.bytes[base + 1] / 255) * PITCH_L };
}

export function ballAt(tl: Timeline, frame: number): Point {
  return raw(tl, frame, 0);
}

export function playerAt(tl: Timeline, frame: number, slot: number): Point {
  return raw(tl, frame, 3 + slot * 2);
}

export function holderAt(tl: Timeline, frame: number): number | null {
  if (tl.count === 0) return null;
  const h = tl.bytes[Math.max(0, Math.min(tl.count - 1, frame)) * tl.size + 2];
  return h === NO_HOLDER ? null : h;
}

/** Centripetal-free Catmull-Rom between p1 and p2 (players: smooth curves
 * through the key frames instead of a zig-zag). */
export function catmullRom(p0: number, p1: number, p2: number, p3: number, t: number): number {
  const t2 = t * t;
  const t3 = t2 * t;
  return 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3);
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function interpolatePlayer(tl: Timeline, frame: number, frac: number, slot: number): Point {
  const p0 = playerAt(tl, frame - 1, slot);
  const p1 = playerAt(tl, frame, slot);
  const p2 = playerAt(tl, frame + 1, slot);
  const p3 = playerAt(tl, frame + 2, slot);
  const clamp = (v: number, max: number) => Math.max(0, Math.min(max, v));
  return {
    x: clamp(catmullRom(p0.x, p1.x, p2.x, p3.x, frac), PITCH_W),
    y: clamp(catmullRom(p0.y, p1.y, p2.y, p3.y, frac), PITCH_L),
  };
}

/** The ball travels in straight lines between frames (passes and shots). */
export function interpolateBall(tl: Timeline, frame: number, frac: number): Point {
  const a = ballAt(tl, frame);
  const b = ballAt(tl, frame + 1);
  return { x: lerp(a.x, b.x, frac), y: lerp(a.y, b.y, frac) };
}

/** How far in front of a player the ball he has sits (metres; backend DRIBBLE). */
export const FOOT = 0.6;

function playerPos(tl: Timeline, slot: number, t: number): Point {
  const f = Math.floor(t);
  return interpolatePlayer(tl, f, t - f, slot);
}

/** The ball at a player's feet: a step ahead of him the way he runs (towards
 * the goal his side attacks when he stands). Follows the player's own
 * smooth path, so a dribbled ball never lags behind the foot. */
export function footBall(tl: Timeline, slot: number, t: number): Point {
  const p = playerPos(tl, slot, t);
  const q = playerPos(tl, slot, Math.min(tl.count - 1, t + 0.4));
  let dx = q.x - p.x;
  let dy = q.y - p.y;
  let d = Math.hypot(dx, dy);
  if (d < 0.2) {
    dx = 0;
    dy = slot < 11 ? 1 : -1;
    d = 1;
  }
  return {
    x: Math.max(0, Math.min(PITCH_W, p.x + (dx / d) * FOOT)),
    y: Math.max(0, Math.min(PITCH_L, p.y + (dy / d) * FOOT)),
  };
}

/** The ball on the grass at time `t` (fractional frame), for the 2D and
 * the 3D view. Players move along curves between key frames and a straight
 * line between two frames would drift off the foot: a held ball follows its
 * holder's own path, and a pass goes from the passer's foot to where the
 * receiver's foot is at that moment, arriving exactly there. Loose balls
 * (shots, clearances, the ball in the net) are the key frames' own. */
export function groundBall(tl: Timeline, t: number): Point {
  const f = Math.max(0, Math.min(tl.count - 1, Math.floor(t)));
  const frac = Math.max(0, Math.min(1, t - f));
  const h0 = holderAt(tl, f);
  const h1 = f + 1 < tl.count ? holderAt(tl, f + 1) : null;
  if (h0 !== null && (frac === 0 || h1 === h0)) return footBall(tl, h0, f + frac);
  const a = h0 !== null ? footBall(tl, h0, f) : ballAt(tl, f);
  if (frac === 0 || f + 1 >= tl.count) return a;
  const b = h1 !== null ? footBall(tl, h1, f + frac) : ballAt(tl, f + 1);
  return { x: lerp(a.x, b.x, frac), y: lerp(a.y, b.y, frac) };
}

export function clockAt(tl: Timeline, frame: number, frac: number): number {
  if (tl.count === 0) return 0;
  const a = tl.clocks[Math.max(0, Math.min(tl.count - 1, frame))];
  const b = frame + 1 < tl.count ? tl.clocks[frame + 1] : a;
  return b >= a ? lerp(a, b, frac) : a;
}

/** Football minute shown on the board: 0:00-0:59 → 1'. Stoppage time is
 * not drawn, so a half ends at 45' / 90'. */
export function minuteLabel(seconds: number, secondHalf: boolean): string {
  const m = Math.floor(seconds / 60) + 1;
  return `${secondHalf ? Math.max(46, Math.min(90, m)) : Math.min(45, m)}'`;
}

/** Which player stands on a pitch slot at `frame` (substitutions swap). */
export function rosterAt(replay: CareerReplay, frame: number): number[] {
  const roster = [...replay.roster];
  for (const [f, slot, player] of replay.swaps) {
    if (f <= frame) roster[slot] = player;
  }
  return roster;
}

export interface MatchEventLite {
  minute: number;
  event_type: string;
  team?: string;
  description?: string;
  payload?: Record<string, unknown> | null;
}

const SHOT_TYPES = new Set(["goal", "shot", "save", "blocked"]);

/** Indices of the events already shown at `frame` (in log order). */
export function revealedEvents(replay: CareerReplay, frame: number): number[] {
  return replay.marks.filter(([f]) => f <= frame).map(([, idx]) => idx).sort((a, b) => a - b);
}

export interface BoardStats {
  score: [number, number];
  shots: [number, number];
  possession: [number, number];
}

export function boardStats(tl: Timeline, replay: CareerReplay, events: MatchEventLite[], frame: number): BoardStats {
  const score: [number, number] = [0, 0];
  const shots: [number, number] = [0, 0];
  for (const idx of revealedEvents(replay, frame)) {
    const e = events[idx];
    if (!e) continue;
    if (e.team !== "a" && e.team !== "b") continue;
    const side = e.team === "a" ? 0 : 1;
    if (e.event_type === "goal") score[side] += 1;
    if (SHOT_TYPES.has(e.event_type)) shots[side] += 1;
  }
  const f = Math.max(0, Math.min(tl.count, frame + 1));
  const a = tl.heldA[f];
  const b = tl.heldB[f];
  const pa = a + b > 0 ? Math.round((a / (a + b)) * 100) : 50;
  return { score, shots, possession: [pa, 100 - pa] };
}

export type MomentKind = "goal" | "yellow" | "red" | "sub" | "chance";

export interface Moment { frame: number; ms: number; kind: MomentKind; team: string | undefined; event: number }

/** Markers on the timeline: goals, cards, substitutions and other chances. */
export function moments(tl: Timeline, replay: CareerReplay, events: MatchEventLite[]): Moment[] {
  const out: Moment[] = [];
  for (const [frame, idx] of replay.marks) {
    const e = events[idx];
    if (!e) continue;
    const card = e.payload?.card;
    let kind: MomentKind | null = null;
    if (e.event_type === "goal") kind = "goal";
    else if (card === "red") kind = "red";
    else if (card === "yellow") kind = "yellow";
    else if (e.event_type === "substitution") kind = "sub";
    else if (SHOT_TYPES.has(e.event_type)) kind = "chance";
    if (kind) out.push({ frame, ms: tl.starts[Math.min(frame, tl.count - 1)] ?? 0, kind, team: e.team, event: idx });
  }
  return out;
}

/** The pass drawn at `frame`: from the passer at its start to the receiver
 * at its end, fading out over two frames after the ball arrives. */
export function activePass(replay: CareerReplay, frame: number): { pass: [number, number, number, number]; fade: number } | null {
  for (let i = replay.passes.length - 1; i >= 0; i--) {
    const p = replay.passes[i];
    if (p[0] <= frame && frame <= p[1] + 2) {
      return { pass: p, fade: frame <= p[1] ? 1 : 1 - (frame - p[1]) / 3 };
    }
    if (p[1] + 2 < frame) break;
  }
  return null;
}

/** First frame of the second half (its kick-off), if the replay has one. */
export function secondHalfFrame(replay: CareerReplay): number | null {
  const kickoffs = replay.segments.filter((s) => s[0] === "kickoff");
  return kickoffs.length > 1 ? kickoffs[1][1] : null;
}
