import type { SwipeInput } from "./trajectory";

export type SwipePoint = { x: number; y: number; t: number };

/** Below this (in viewport heights) a gesture is a tap, not a kick. */
const MIN_LENGTH = 0.08;
/** Leading jitter before the finger really starts moving is not part of the flick. */
const START_THRESHOLD = 0.015;

/** Pointer path (screen px, ms) → the swipe the trajectory understands, or
 * null when it isn't a kick (too short, or not upwards). */
export function swipeFromPoints(points: SwipePoint[], viewportHeight: number): SwipeInput | null {
  if (points.length < 2 || viewportHeight <= 0) return null;
  const h = viewportHeight;
  const origin = points[0];
  let start = 0;
  while (
    start < points.length - 2 &&
    Math.hypot(points[start + 1].x - origin.x, points[start + 1].y - origin.y) / h < START_THRESHOLD
  ) {
    start += 1;
  }
  const first = points[start];
  const last = points[points.length - 1];
  const cx = last.x - first.x;
  const cy = last.y - first.y;
  const chord = Math.hypot(cx, cy);
  if (chord / h < MIN_LENGTH || cy >= 0) return null;

  // Right-hand perpendicular of the chord in screen space (y grows down):
  // for an upward swipe it points to the screen's right.
  const rx = -cy / chord;
  const ry = cx / chord;
  let deviation = 0;
  for (let i = start + 1; i < points.length - 1; i++) {
    const d = (points[i].x - first.x) * rx + (points[i].y - first.y) * ry;
    if (Math.abs(d) > Math.abs(deviation)) deviation = d;
  }

  return {
    dx: cx / h,
    dy: cy / h,
    curve: deviation / chord,
    durationMs: Math.max(1, last.t - first.t),
  };
}
