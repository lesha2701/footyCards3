/** Where the shot goes, worked out on the phone before it is written into
 * the timeline: the left stick's lean picks the spot across the goal, the
 * right thumb's swipe only its power, height and bend — or a tap, and the
 * shot picks itself. Either way the result is an ordinary swipe the server
 * replays like any other (it never sees the stick or the tap). */
import { GOAL_HALF_WIDTH, type QuantizedSwipe } from "@/lib/freeKick3d/trajectory";

import { AIM_REF, ballOf, type EpisodeState } from "./engine";

/** A full lean of the stick: just inside the post (m off the centre). */
export const AIM_POST = GOAL_HALF_WIDTH - 0.5;
/** The tap's shot goes a little less wide: aiming yourself pays. */
const AUTO_SPOT = GOAL_HALF_WIDTH - 1.1;
/** The tap's drive, and its chip over a keeper who is on top of him. */
const AUTO_DRIVE = { dy: -150, curve: 0, durationMs: 140 };
const AUTO_CHIP: QuantizedSwipe = { dx: 0, dy: -300, curve: 0, durationMs: 600 };
const AUTO_CHIP_DIST = 3.2;
/** swipeToKick's aim: clamp(dx / up, ±0.8) · 0.35 · aimScale. */
const AIM_GAIN = 0.35;
const AIM_MAX = 0.8;
/** A thumb's arc is small: its bend counts this much more than a swipe's. */
const THUMB_CURL = 1.8;

export type ShotIntent = { swipe: QuantizedSwipe; aim: number } | { auto: true };

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** The swipe's lean that sends the ball (before any bend — the bend ends on
 * the aim) to `tx` on the goal line, from where the ball is now. */
export function aimSwipe(s: EpisodeState, tx: number, q: QuantizedSwipe): QuantizedSwipe {
  const b = ballOf(s);
  const len = Math.hypot(b.x, b.z);
  const fx = -b.x / len;
  const fz = -b.z / len;
  // The spot's offset across the line ball → goal centre, over the way along it.
  const yaw = (-tx * fz) / (len + tx * fx);
  const lean = clamp(yaw / (AIM_GAIN * clamp(AIM_REF / len, 1, 3)), -AIM_MAX, AIM_MAX);
  const up = Math.max(0.02, -q.dy / 1000);
  return { ...q, dx: clamp(Math.round(lean * up * 1000), -1500, 1500) };
}

/** The intent as the swipe the timeline carries. */
export function resolveShot(s: EpisodeState, intent: ShotIntent): QuantizedSwipe {
  if ("swipe" in intent) {
    const q = { ...intent.swipe, curve: clamp(Math.round(intent.swipe.curve * THUMB_CURL), -500, 500) };
    return aimSwipe(s, clamp(intent.aim, -1, 1) * AIM_POST, q);
  }
  // The tap: over a keeper standing on top of him, else low to the side
  // he leaves open.
  const b = ballOf(s);
  const near = Math.hypot(s.kx - b.x, s.kz - b.z) < AUTO_CHIP_DIST;
  if (near && (s.kMode === "rush" || s.kMode === "set")) return AUTO_CHIP;
  const len = Math.hypot(b.x, b.z);
  const across = (s.kx - b.x) * (b.z / len) + (s.kz - b.z) * (-b.x / len);
  return aimSwipe(s, (across > 0 ? -1 : 1) * AUTO_SPOT, { dx: 0, ...AUTO_DRIVE });
}
