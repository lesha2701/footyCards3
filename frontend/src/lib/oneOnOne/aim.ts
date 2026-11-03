/** Where the shot goes, worked out on the phone before it is written into
 * the timeline — the controls as in FIFA: the left stick's lean picks the
 * spot across the goal; the shot button held and let go is a drive, its
 * power bar how hard and so how high (full — over the bar); a swipe up off
 * it is the finesse, bent the way his place on the pitch calls for; the
 * chip button lifts it over; a tap and the shot picks itself. Whatever it
 * was, the result is an ordinary swipe the server replays like any other
 * (it never sees the stick or the buttons). */
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
/** The drive by its power bar (0…1): struck this hard (m/s), crossing the
 * line this high (m) — up to the top corner at POWER_TOP, then over the bar. */
const DRIVE_SOFT = 21;
const DRIVE_HARD = 32;
const DRIVE_LOW = 0.3;
const DRIVE_TOP = 2.15;
const DRIVE_OVER = 3.1;
const POWER_TOP = 0.9;
/** The finesse: the thumb's swipe read on its own scale (it is short and
 * quick) — its pace (heights / s) how hard, its length (share of the
 * height) how high; bent this much. */
const THUMB_SOFT = 0.9;
const THUMB_HARD = 2.6;
const THUMB_LOW = 0.06;
const THUMB_HIGH = 0.3;
const FINESSE_SOFT = 20;
const FINESSE_HARD = 27;
const FINESSE_LOW = 0.6;
const FINESSE_HIGH = 1.9;
const FINESSE_CURVE = 320;
/** Closer to a post than this (m across): the finesse into that near post
 * bends in from outside it; else it bends away from the keeper into the far one. */
const NEAR_SIDE = 1;
/** The chip by its power bar: the swipe that scoops it (free-kick scale). */
const CHIP_UP_SOFT = 0.24;
const CHIP_UP_HARD = 0.36;
const CHIP_MS = 600;
/** swipeToKick's mapping, run backwards (shot min speed, lift scale, its
 * speed from the swipe, the ball's mean pace over a shot's drag). */
const KICK_MIN_SPEED = 11;
const KICK_LIFT_SCALE = 1.2;
const KICK_PACE = 7;
const DRAG_PACE = 0.93;
/** The estimate is then corrected against the real flight (drag, the
 * dip) this many times. */
const CROSS_FIXES = 3;
/** A post met the ball this close to the line (m): read the crossing on from it. */
const CROSS_NEAR = 1.5;

/** `aim` is the stick's lean (−1 … 1), `power` the bar (0 … 1). */
export type ShotIntent =
  | { kind: "drive"; power: number; aim: number }
  | { kind: "finesse"; swipe: QuantizedSwipe; aim: number }
  | { kind: "chip"; power: number; aim: number }
  | { kind: "auto" };

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
  // The bend doesn't land exactly on the chord, drag and dip pull it down:
  // the spot and the height are corrected against the real flight.
  let wantX = tx;
  let wantY = cross;
  let q = estimate(s, wantX, speed, wantY, curve);
  for (let i = 0; i < CROSS_FIXES; i++) {
    const got = crossing(setup, clear, q);
    if (!got || (Math.abs(got.y - cross) < 0.05 && Math.abs(got.x - tx) < 0.1)) break;
    wantX += tx - got.x;
    wantY += cross - got.y;
    q = estimate(s, wantX, speed, wantY, curve);
  }
  return q;
}

/** Where the ball crosses the goal line — straight on from the flight
 * before it if a post or the bar met it first (null if it never gets near). */
function crossing(setup: EpisodeSetup, s: EpisodeState, q: QuantizedSwipe): { x: number; y: number } | null {
  const f = shoot(setup, s, q, 1);
  const hit = f.events.length ? f.events[0].t : Infinity;
  for (let i = 1; i < f.samples.length; i++) {
    const a = f.samples[i - 1].ball;
    const b = f.samples[i].ball;
    const late = f.samples[i].t >= hit;
    if ((a.z > 0 && b.z <= 0) || (late && a.z > 0 && a.z < CROSS_NEAR)) {
      const k = a.z / (a.z - b.z || 1e-6);
      return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
    }
    if (late) return null;
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

/** How high the drive crosses the line for its power bar (m). */
export function driveHeight(power: number): number {
  const p = clamp(power, 0, 1);
  return p <= POWER_TOP ? lerp(DRIVE_LOW, DRIVE_TOP, p / POWER_TOP) : lerp(DRIVE_TOP, DRIVE_OVER, (p - POWER_TOP) / (1 - POWER_TOP));
}

/** Which way the finesse bends (the swipe's curve sign: > 0 bends left).
 * Into the near post he wraps it in from outside it; into the far one —
 * or the middle — away from the keeper, from where he stands. */
export function finesseBend(s: EpisodeState, tx: number): 1 | -1 {
  const bx = ballOf(s).x;
  if (tx < -0.3) return bx < -NEAR_SIDE ? -1 : 1;
  if (tx > 0.3) return bx > NEAR_SIDE ? 1 : -1;
  return bx >= 0 ? 1 : -1;
}

/** The intent as the swipe the timeline carries. */
export function resolveShot(setup: EpisodeSetup, s: EpisodeState, intent: ShotIntent): QuantizedSwipe {
  if (intent.kind !== "auto") {
    const tx = clamp(intent.aim, -1, 1) * AIM_POST;
    if (intent.kind === "drive") {
      const p = clamp(intent.power, 0, 1);
      return strike(setup, s, tx, lerp(DRIVE_SOFT, DRIVE_HARD, Math.min(1, p / POWER_TOP)), driveHeight(p), 0);
    }
    if (intent.kind === "chip") {
      const up = lerp(CHIP_UP_SOFT, CHIP_UP_HARD, clamp(intent.power, 0, 1));
      return aimSwipe(s, tx, { dx: 0, dy: -Math.round(up * 1000), curve: 0, durationMs: CHIP_MS });
    }
    const sw = intent.swipe;
    const up = -sw.dy / 1000;
    const pace = up / (sw.durationMs / 1000);
    const power = clamp((pace - THUMB_SOFT) / (THUMB_HARD - THUMB_SOFT), 0, 1);
    const height = clamp((up - THUMB_LOW) / (THUMB_HIGH - THUMB_LOW), 0, 1);
    const curve = finesseBend(s, tx) * FINESSE_CURVE;
    return strike(setup, s, tx, lerp(FINESSE_SOFT, FINESSE_HARD, power), lerp(FINESSE_LOW, FINESSE_HIGH, height), curve);
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
