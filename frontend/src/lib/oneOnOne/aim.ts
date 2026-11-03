/** Where the shot goes, worked out on the phone before it is written into
 * the timeline: the left stick's lean picks the spot across the goal, the
 * right thumb's swipe only its power, height and bend — or a tap, and the
 * shot picks itself. Either way the result is an ordinary swipe the server
 * replays like any other (it never sees the stick or the tap). */
import { GOAL_HALF_WIDTH, GRAVITY, type QuantizedSwipe } from "@/lib/freeKick3d/trajectory";

import { AIM_REF, ballOf, shoot, type EpisodeSetup, type EpisodeState } from "./engine";

/** A full lean of the stick: just inside the post (m off the centre). */
export const AIM_POST = GOAL_HALF_WIDTH - 0.5;
/** The tap's shot goes a little less wide: aiming yourself pays. */
const AUTO_SPOT = GOAL_HALF_WIDTH - 1.1;
/** The tap's drive (m/s, m high over the line), and its chip over a keeper
 * who is on top of him. */
const AUTO_SPEED = 25;
const AUTO_CROSS = 0.5;
const AUTO_CHIP: QuantizedSwipe = { dx: 0, dy: -300, curve: 0, durationMs: 600 };
const AUTO_CHIP_DIST = 3.2;
/** swipeToKick's aim: clamp(dx / up, ±0.8) · 0.35 · aimScale. */
const AIM_GAIN = 0.35;
const AIM_MAX = 0.8;
/** A thumb's arc is small: its bend counts this much more than a swipe's. */
const THUMB_CURL = 1.8;
/** The thumb's swipe is short and quick, the free kick's whole-screen
 * swipe scale makes it fly over the bar and come out weak. So it is read
 * on its own scale: its length (share of the height) is how high the ball
 * crosses the goal line, its pace (heights / s) how hard it is struck. */
const THUMB_LOW = 0.06;
const THUMB_HIGH = 0.3;
const CROSS_LOW = 0.25;
const CROSS_HIGH = 2.1;
const THUMB_SOFT = 0.9;
const THUMB_HARD = 2.6;
const SPEED_SOFT = 21;
const SPEED_HARD = 31;
/** Slower than this (heights / s) and at least this long: the chip, played
 * as swiped. Well below a calm shot's pace, so a placed shot is no chip. */
const THUMB_CHIP_PACE = 0.6;
const THUMB_CHIP_UP = 0.15;
/** swipeToKick's mapping, run backwards (shot min speed, lift scale, its
 * speed from the swipe, the ball's mean pace over a shot's drag). */
const KICK_MIN_SPEED = 11;
const KICK_LIFT_SCALE = 1.2;
const KICK_PACE = 7;
const DRAG_PACE = 0.93;
/** The estimate is then corrected against the real flight (drag, the
 * dip) this many times. */
const CROSS_FIXES = 3;

export type ShotIntent = { swipe: QuantizedSwipe; aim: number } | { auto: true };

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** The swipe's lean that sends the ball (before any bend — the bend ends on
 * the aim) to `tx` on the goal line, from where the ball is now. */
export function aimSwipe(s: EpisodeState, tx: number, q: QuantizedSwipe): QuantizedSwipe {
  const up = Math.max(0.02, -q.dy / 1000);
  return { ...q, dx: clamp(Math.round(leanFor(s, tx) * up * 1000), -1500, 1500) };
}

/** The swipe's dx / up that aims at `tx`. */
function leanFor(s: EpisodeState, tx: number): number {
  const b = ballOf(s);
  const len = Math.hypot(b.x, b.z);
  const fx = -b.x / len;
  const fz = -b.z / len;
  // The spot's offset across the line ball → goal centre, over the way along it.
  const yaw = (-tx * fz) / (len + tx * fx);
  return clamp(yaw / (AIM_GAIN * clamp(AIM_REF / len, 1, 3)), -AIM_MAX, AIM_MAX);
}

/** The thumb's swipe as the swipe that strikes the ball at `speed` (m/s)
 * to cross the goal line at `cross` m high, aimed at `tx`: estimated, then
 * corrected by flying it (with the keeper out of the way). */
function strike(setup: EpisodeSetup, s: EpisodeState, tx: number, speed: number, cross: number, curve: number): QuantizedSwipe {
  const clear: EpisodeState = { ...s, kx: 50, kMode: "wait", kTicks: 0 };
  let want = cross;
  let q = estimate(s, tx, speed, want, curve);
  for (let i = 0; i < CROSS_FIXES; i++) {
    const got = crossing(setup, clear, q);
    if (got === null || Math.abs(got - cross) < 0.05) break;
    want += cross - got;
    q = estimate(s, tx, speed, want, curve);
  }
  return q;
}

/** How high the ball crosses the goal line (null if it never gets there). */
function crossing(setup: EpisodeSetup, s: EpisodeState, q: QuantizedSwipe): number | null {
  const f = shoot(setup, s, q, 1);
  for (let i = 1; i < f.samples.length; i++) {
    const a = f.samples[i - 1].ball;
    const b = f.samples[i].ball;
    if (a.z > 0 && b.z <= 0) return a.y + ((b.y - a.y) * a.z) / (a.z - b.z);
  }
  return null;
}

function estimate(s: EpisodeState, tx: number, speed: number, cross: number, curve: number): QuantizedSwipe {
  const b = ballOf(s);
  const t = Math.hypot(b.x - tx, b.z) / (speed * DRAG_PACE);
  const lift = (cross - 0.11 + (GRAVITY * t * t) / 2) / t / speed;
  // swipeToKick: lift = (0.2 ∓ (0.2 − up)·k)·scale, k 1.6 below up 0.2, 0.8 above.
  const g = lift / KICK_LIFT_SCALE;
  const up = clamp(g <= 0.2 ? 0.2 - (0.2 - g) / 1.6 : 0.2 + (g - 0.2) / 0.8, 0.02, 1.5);
  const lean = leanFor(s, tx);
  const len = up * Math.sqrt(1 + lean * lean);
  const durationMs = clamp(Math.round((KICK_PACE * Math.sqrt(len * 0.4) * 1000) / (speed - KICK_MIN_SPEED)), 40, 2000);
  return { dx: clamp(Math.round(lean * up * 1000), -1500, 1500), dy: -Math.round(up * 1000), curve, durationMs };
}

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

/** The intent as the swipe the timeline carries. */
export function resolveShot(setup: EpisodeSetup, s: EpisodeState, intent: ShotIntent): QuantizedSwipe {
  if ("swipe" in intent) {
    const sw = intent.swipe;
    const tx = clamp(intent.aim, -1, 1) * AIM_POST;
    const curve = clamp(Math.round(sw.curve * THUMB_CURL), -500, 500);
    const up = -sw.dy / 1000;
    const pace = up / (sw.durationMs / 1000);
    if (pace < THUMB_CHIP_PACE && up >= THUMB_CHIP_UP) return aimSwipe(s, tx, { ...sw, curve });
    const power = clamp((pace - THUMB_SOFT) / (THUMB_HARD - THUMB_SOFT), 0, 1);
    const height = clamp((up - THUMB_LOW) / (THUMB_HIGH - THUMB_LOW), 0, 1);
    return strike(setup, s, tx, lerp(SPEED_SOFT, SPEED_HARD, power), lerp(CROSS_LOW, CROSS_HIGH, height), curve);
  }
  // The tap: over a keeper standing on top of him, else low to the side
  // he leaves open.
  const b = ballOf(s);
  const near = Math.hypot(s.kx - b.x, s.kz - b.z) < AUTO_CHIP_DIST;
  if (near && (s.kMode === "rush" || s.kMode === "set")) return AUTO_CHIP;
  const len = Math.hypot(b.x, b.z);
  const across = (s.kx - b.x) * (b.z / len) + (s.kz - b.z) * (-b.x / len);
  return strike(setup, s, (across > 0 ? -1 : 1) * AUTO_SPOT, AUTO_SPEED, AUTO_CROSS, 0);
}
