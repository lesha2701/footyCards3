/** Gesture → move and wave → arena helpers for «Замес» (no DOM). */
import type { Input, State } from "./engine";

const SWIPE_MIN = 34;

/** The arena of the wave: the parking lot first, under the stand later. */
export function arenaOf(s: Pick<State, "wave" | "mode">): "parking" | "tunnel" {
  const w = Math.max(1, s.wave);
  return s.mode === "derby" ? (w >= 4 ? "tunnel" : "parking") : Math.floor((w - 1) / 3) % 2 ? "tunnel" : "parking";
}

/** Turns a finished pointer path into a move: kick ←/→, spin ↑ or a circle, sweep ↓. */
export function classifySwipe(points: { x: number; y: number }[]): Input | null {
  if (points.length < 2) return null;
  const a = points[0];
  const b = points[points.length - 1];
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  let turn = 0;
  let path = 0;
  for (let i = 2; i < points.length; i++) {
    const p0 = points[i - 2];
    const p1 = points[i - 1];
    const p2 = points[i];
    const a1 = Math.atan2(p1.y - p0.y, p1.x - p0.x);
    const a2 = Math.atan2(p2.y - p1.y, p2.x - p1.x);
    let d = a2 - a1;
    while (d > Math.PI) d -= Math.PI * 2;
    while (d < -Math.PI) d += Math.PI * 2;
    if (Math.hypot(p2.x - p1.x, p2.y - p1.y) > 2) turn += d;
    path += Math.hypot(p2.x - p1.x, p2.y - p1.y);
  }
  if (Math.abs(turn) > 4.2 && path > 80) return { k: "spin" };
  if (Math.hypot(dx, dy) < SWIPE_MIN) return null;
  if (Math.abs(dx) >= Math.abs(dy)) return { k: "kick", dir: dx > 0 ? 1 : -1 };
  return dy < 0 ? { k: "spin" } : { k: "sweep" };
}
