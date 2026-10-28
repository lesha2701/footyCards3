/** Presentation-only helpers for the 3D free kick: slow motion and where the
 * ball hits the net. They read a finished trajectory and never feed back
 * into it, so the outcome stays the pure function's alone. */
import { BALL_RADIUS, GOAL_HALF_WIDTH, GOAL_HEIGHT, type ShotTrajectory } from "./trajectory";

export const NET_DEPTH = 2;

/** Slow motion window before a goal or a save (s of shot time). */
const SLOWMO_WINDOW = 0.28;
const SLOWMO_SCALE = 0.3;

/** How fast shot time runs at shot time `t`: 1 normally, eased down to
 * 0.3 just before a goal or a save is decided, back to 1 afterwards. */
export function replayTimeScale(traj: ShotTrajectory, t: number): number {
  if (traj.outcome !== "goal" && traj.outcome !== "save") return 1;
  const left = traj.end.t - t;
  if (left <= 0 || left >= SLOWMO_WINDOW) return 1;
  const k = left / SLOWMO_WINDOW; // 1 → 0 as the moment approaches
  return SLOWMO_SCALE + (1 - SLOWMO_SCALE) * k * k;
}

/** Where a goal meets the back of the net (x, y), continuing the decided
 * velocity in a straight line; null for anything but a goal. */
export function netImpact(traj: ShotTrajectory): { x: number; y: number } | null {
  if (traj.outcome !== "goal") return null;
  const { position: p, velocity: v } = traj.end;
  const dt = v.z < -0.1 ? (-NET_DEPTH - p.z) / v.z : 0;
  const clamp = (val: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, val));
  return {
    x: clamp(p.x + v.x * dt, -GOAL_HALF_WIDTH + BALL_RADIUS, GOAL_HALF_WIDTH - BALL_RADIUS),
    y: clamp(p.y + (v.y - 4.9 * dt) * dt, BALL_RADIUS, GOAL_HEIGHT - BALL_RADIUS),
  };
}

/** Net bulge at a point of the back net, `age` s after the impact. */
export function netBulge(dx: number, dy: number, age: number): number {
  if (age < 0 || age > 1.6) return 0;
  const falloff = Math.exp(-(dx * dx + dy * dy) / 0.35);
  return 0.55 * falloff * Math.exp(-age * 3.2) * Math.cos(age * 14);
}

/** When the crowd (and the result banner) react, in shot time: at the
 * decision, except a miss off the post or the bar — that one is plain the
 * moment it rings, while the ball may fly on for a long while before the
 * shot is formally over. */
export function reactionTime(traj: ShotTrajectory): number {
  if (traj.outcome === "miss") {
    const post = traj.events.find((e) => e.type === "post");
    if (post) return Math.min(post.t, traj.end.t);
  }
  return traj.end.t;
}

/** Should the keeper move at all? Not for a shot the wall stops, nor for
 * one flying clearly wide or over — he just watches it go. */
export function keeperGoesFor(traj: ShotTrajectory): boolean {
  if (traj.outcome === "wall") return false;
  if (traj.outcome !== "miss") return true;
  const p = traj.end.position;
  return Math.abs(p.x) < GOAL_HALF_WIDTH + 1 && p.y < GOAL_HEIGHT + 0.8;
}
