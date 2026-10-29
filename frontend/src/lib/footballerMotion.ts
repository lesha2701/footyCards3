/** What each footballer of a 3D goal replay is doing at episode time `t`
 * (fractional key frame): which animation clip and, for one-off moves,
 * how far into it — so a kick's foot meets the ball on the frame the ball
 * leaves, a header's jump peaks when the ball arrives and the keeper's
 * dive reaches out as it crosses the line. Pure: decided from the key
 * frames and the episode only, the same at every replay and when scrubbing. */
import type { CareerReplay } from "@/api/career";
import { ballState, toWorld, type GoalEpisode } from "@/lib/goalReplay3d";
import { interpolatePlayer, type Timeline } from "@/lib/matchReplay";

/** Game seconds per key frame (career_replay_service.STEP). */
export const STEP_S = 0.5;
/** Below this a player stands (m/s). */
export const RUN_FROM = 0.9;
/** The run clip's natural speed (m/s): its time scale is speed / RUN_AT. */
export const RUN_AT = 7;

export type ClipName = "idle" | "run" | "kick" | "wall_jump" | "gk_idle" | "gk_dive_left" | "gk_dive_right" | "gk_catch";

/** Timing of the one-off clips, read from the model when it loads. */
export interface ClipTiming {
  kickContact: number;
  kickDuration: number;
  jumpApex: number;
  jumpDuration: number;
  /** Dive: when the hips start going sideways and when the arms are out. */
  diveStart: number;
  diveReach: number;
  diveDuration: number;
  catchDuration: number;
}

/** Mixamo soccer clips of public/career-3d/footballer.glb (30 fps). */
export const DEFAULT_TIMING: ClipTiming = {
  kickContact: 22 / 30, kickDuration: 1.53, jumpApex: 0.9, jumpDuration: 1.93,
  diveStart: 0.5, diveReach: 1.2, diveDuration: 3.3, catchDuration: 1,
};

/** How far sideways the hips get in each dive at the reach (m, measured on
 * the model): the keeper is nudged by the rest so his hands meet the ball. */
export const DIVE_REACH = { gk_dive_left: 2.56, gk_dive_right: 2.98 };
/** Closer to him than this, the keeper doesn't dive: he takes it standing. */
export const CATCH_WITHIN = 1.0;
/** Further than this he can't get there: no hopeless dive, he just watches it in. */
export const DIVE_MAX = 3.8;

/** `time` is the clip time to show for a one-off move, null for a loop
 * (the mixer plays it); `speed` is the loop's time scale. */
export interface PlayerAction { clip: ClipName; time: number | null; speed: number }

export interface Motion { x: number; z: number; vx: number; vz: number; speed: number }

/** Scene position and velocity (m/s of game time) of a pitch slot. */
export function motionAt(tl: Timeline, slot: number, t: number, flip: boolean): Motion {
  const f = Math.floor(t);
  const p = toWorld(interpolatePlayer(tl, f, t - f, slot), flip);
  const t2 = Math.min(tl.count - 1, t + 0.4);
  const f2 = Math.floor(t2);
  const q = toWorld(interpolatePlayer(tl, f2, t2 - f2, slot), flip);
  const span = Math.max(1e-3, (t2 - t) * STEP_S);
  const vx = (q.x - p.x) / span;
  const vz = (q.z - p.z) / span;
  return { x: p.x, z: p.z, vx, vz, speed: Math.hypot(vx, vz) };
}

/** Moments a player strikes the ball in the episode: the passes of the
 * build-up (by the passer, when it leaves him) and the shot. */
export function strikes(replay: CareerReplay, ep: GoalEpisode): { frame: number; slot: number; shot: boolean }[] {
  const out = replay.passes
    .filter(([p0, , from]) => p0 >= ep.f0 && p0 < ep.shot && from !== null)
    .map(([p0, , from]) => ({ frame: p0, slot: from, shot: false }));
  if (ep.scorer !== null) out.push({ frame: ep.shot, slot: ep.scorer, shot: true });
  return out;
}

const clampTo = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** The defending keeper's pitch slot for this goal. */
export function keeperSlot(ep: GoalEpisode): number {
  return ep.side === "a" ? 11 : 0;
}

export interface KeeperMove {
  clip: "gk_dive_left" | "gk_dive_right" | "gk_catch";
  /** Where the ball crosses the line, sideways from him (m, + = his left). */
  lateral: number;
  /** His left in scene X/Z (along the goal line). */
  left: { x: number; z: number };
  /** His facing for the move: square to the goal line, towards the pitch. */
  heading: number;
}

/** The beaten keeper's move: square to his line, a dive along it to the
 * side the ball goes, or standing to take it when it comes straight at him. */
export function keeperMove(tl: Timeline, ep: GoalEpisode, flip: boolean): KeeperMove {
  const k = motionAt(tl, keeperSlot(ep), ep.shot, flip);
  const goal = toWorld(ballState(tl, ep, ep.goal), flip);
  // Facing the pitch from his goal (scene X = ±52.5), the goal line along Z.
  const fx = -(Math.sign(goal.x) || 1);
  const fz = 0;
  // The model faces +z with its left at +x: left of a facing (fx, fz) is (fz, -fx).
  const left = { x: fz, z: -fx };
  const lateral = (goal.z - k.z) * left.z;
  const clip = Math.abs(lateral) < CATCH_WITHIN ? "gk_catch" : lateral > 0 ? "gk_dive_left" : "gk_dive_right";
  return { clip, lateral, left, heading: Math.atan2(fx, fz) };
}

export function playerAction(
  tl: Timeline, replay: CareerReplay, ep: GoalEpisode, slot: number, t: number, flip: boolean,
  timing: ClipTiming = DEFAULT_TIMING, kicks = strikes(replay, ep),
): PlayerAction {
  const keeper = slot === 0 || slot === 11;
  const motion = motionAt(tl, slot, t, flip);
  const loop = (): PlayerAction => motion.speed >= RUN_FROM
    ? { clip: "run", time: null, speed: clampTo(motion.speed / RUN_AT, 0.45, 1.35) }
    : { clip: keeper ? "gk_idle" : "idle", time: null, speed: 1 };

  // The keeper who is beaten: dives as the ball comes, then stays down
  // (the dive's last frame).
  const move = slot === keeperSlot(ep) ? keeperMove(tl, ep, flip) : null;
  if (move && Math.abs(move.lateral) <= DIVE_MAX && t >= ep.goal - 1.2) {
    const clip = move.clip;
    if (clip === "gk_catch") {
      // Hands up to it as it arrives (the clip's middle at the goal frame).
      const time = timing.catchDuration * 0.5 + (t - ep.goal) * STEP_S;
      return { clip, time: Math.max(0, Math.min(timing.catchDuration, time)), speed: 1 };
    }
    // Arms out (the reach) exactly when the ball crosses the line.
    const rate = (timing.diveReach - timing.diveStart) / (1.2 * STEP_S);
    const time = timing.diveStart + (t - (ep.goal - 1.2)) * STEP_S * rate;
    return { clip, time: Math.min(time, timing.diveDuration), speed: 1 };
  }

  // Strikes: the foot meets the ball on the frame it leaves (passes are
  // quicker swings than the shot); a header jumps to meet the cross.
  for (const k of kicks) {
    if (k.slot !== slot) continue;
    const header = k.shot && ep.finish === "header";
    if (header) {
      const time = timing.jumpApex + (t - k.frame) * STEP_S;
      if (time >= 0 && time <= timing.jumpDuration) return { clip: "wall_jump", time, speed: 1 };
      continue;
    }
    const swing = k.shot ? 1 : 1.6;
    const time = timing.kickContact + (t - k.frame) * STEP_S * swing;
    // A pass shows only the strike itself, not the clip's run-up.
    const from = k.shot ? 0 : timing.kickContact - 0.35;
    if (time >= from && time <= timing.kickDuration) return { clip: "kick", time, speed: 1 };
  }

  // After the goal the scorer's side celebrates: running to the corner,
  // jumping once they get there.
  const scoring = (slot < 11 ? "a" : "b") === ep.side;
  if (scoring && !keeper && t > ep.goal + 1) {
    if (motion.speed >= RUN_FROM) return loop();
    const time = ((t - ep.goal) * STEP_S + slot * 0.37) % timing.jumpDuration;
    return { clip: "wall_jump", time, speed: 1 };
  }
  return loop();
}
