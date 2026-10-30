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
/** The hand-built run's natural speed (m/s), kept for the simple figures. */
export const RUN_AT = 7;
/** From this speed a player sprints (m/s). */
export const SPRINT_FROM = 6;
/** Up to this speed a player going back towards his goal with the ball in
 * front of him backpedals, facing it (m/s); faster, he turns and runs. */
export const BACKPEDAL_UP_TO = 3.5;

/** Key frames after the goal when the scorer's side stop where they are
 * and celebrate (the key frames go on running them off). */
export const CELEBRATE_AFTER = 5;

export type ClipName =
  | "idle" | "run" | "sprint" | "run_back" | "kick" | "wall_jump" | "header" | "celebrate" | "victory"
  | "gk_idle" | "gk_dive_left" | "gk_dive_right" | "gk_catch";

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
  /** Natural speeds of the run, the sprint and the backpedal (m/s): a
   * loop's time scale is the player's speed over it. */
  runSpeed: number;
  sprintSpeed: number;
  backSpeed: number;
  /** The header: the jump's top (head to the ball) and its length. */
  headerApex: number;
  headerDuration: number;
  celebrateDuration: number;
  victoryDuration: number;
  /** The victory pose starts calm: shown from when the arms go up. */
  victoryFrom: number;
}

/** Mixamo soccer clips of public/career-3d/footballer.glb (30 fps). */
export const DEFAULT_TIMING: ClipTiming = {
  kickContact: 22 / 30, kickDuration: 1.53, jumpApex: 0.9, jumpDuration: 1.93,
  diveStart: 0.5, diveReach: 1.2, diveDuration: 3.3, catchDuration: 1,
  runSpeed: 5, sprintSpeed: 7.5, backSpeed: 2.5,
  headerApex: 0.8, headerDuration: 1.6, celebrateDuration: 1.6, victoryDuration: 3, victoryFrom: 0,
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
export interface PlayerAction {
  clip: ClipName;
  time: number | null;
  speed: number;
  /** A kick: the frame the foot meets the ball. */
  strike?: number;
}

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
 * build-up (by the passer, the frame before the key frames have the ball
 * loose — when it leaves his foot, matchReplay.groundBall) and the shot. */
export function strikes(replay: CareerReplay, ep: GoalEpisode): { frame: number; slot: number; shot: boolean }[] {
  const out = replay.passes
    .filter(([p0, , from]) => p0 - 1 >= ep.f0 && p0 < ep.shot && from !== null)
    .map(([p0, , from]) => ({ frame: p0 - 1, slot: from, shot: false }));
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
  const loop = (): PlayerAction => {
    const v = motion.speed;
    if (v < RUN_FROM) return { clip: keeper ? "gk_idle" : "idle", time: null, speed: 1 };
    if (!keeper && t < ep.goal && v <= BACKPEDAL_UP_TO && backpedals(tl, ep, motion, t, flip)) {
      return { clip: "run_back", time: null, speed: clampTo(v / timing.backSpeed, 0.6, 1.5) };
    }
    if (v >= SPRINT_FROM) return { clip: "sprint", time: null, speed: clampTo(v / timing.sprintSpeed, 0.75, 1.3) };
    return { clip: "run", time: null, speed: clampTo(v / timing.runSpeed, 0.45, 1.35) };
  };

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
      const time = timing.headerApex + (t - k.frame) * STEP_S;
      if (time >= 0 && time <= timing.headerDuration) return { clip: "header", time, speed: 1 };
      continue;
    }
    const swing = k.shot ? 1 : 1.6;
    const time = timing.kickContact + (t - k.frame) * STEP_S * swing;
    // A pass shows only the strike itself, not the clip's run-up.
    const from = k.shot ? 0 : timing.kickContact - 0.35;
    if (time >= from && time <= timing.kickDuration) return { clip: "kick", time, speed: 1, strike: k.frame };
  }

  // After the goal the scorer's side celebrates: running off, then (or as
  // soon as they stop) the scorer's victory pose and his team-mates jumping
  // for joy — standing where they are (poseTime).
  const scoring = (slot < 11 ? "a" : "b") === ep.side;
  if (scoring && !keeper && t > ep.goal + 1) {
    if (motion.speed >= RUN_FROM && t <= ep.goal + CELEBRATE_AFTER) return loop();
    if (slot === ep.scorer) {
      const from = Math.min(timing.victoryFrom, timing.victoryDuration * 0.8);
      const time = from + ((t - ep.goal - 1) * STEP_S) % (timing.victoryDuration - from);
      return { clip: "victory", time, speed: 1 };
    }
    const time = ((t - ep.goal) * STEP_S + slot * 0.37) % timing.celebrateDuration;
    return { clip: "celebrate", time, speed: 1 };
  }
  return loop();
}

/** The key-frame time a player is drawn at: the scorer's side stand still
 * from CELEBRATE_AFTER frames after the goal, everyone else follows the
 * key frames. */
export function poseTime(ep: GoalEpisode, slot: number, t: number): number {
  const scoring = (slot < 11 ? "a" : "b") === ep.side && slot !== 0 && slot !== 11;
  return scoring ? Math.min(t, ep.goal + CELEBRATE_AFTER) : t;
}

/** Going back towards his own goal with the ball in front of him: he
 * backpedals facing it instead of turning his back on it. */
export function backpedals(tl: Timeline, ep: GoalEpisode, motion: Motion, t: number, flip: boolean): boolean {
  const ball = toWorld(ballState(tl, ep, t), flip);
  const bx = ball.x - motion.x;
  const bz = ball.z - motion.z;
  const d = Math.hypot(bx, bz);
  if (d < 2 || motion.speed < 1e-3) return false;
  return (motion.vx * bx + motion.vz * bz) / (motion.speed * d) < -0.6;
}

/** How much of a kick the body is placed by the ball rather than by the
 * key frames: eased in over the last 0.35 s of the swing, held through the
 * contact, eased out over the follow-through. */
export function strikeWeight(time: number, contact: number): number {
  const ease = (a: number, b: number, v: number) => {
    const u = clampTo((v - a) / (b - a), 0, 1);
    return u * u * (3 - 2 * u);
  };
  return ease(contact - 0.35, contact, time) * (1 - ease(contact + 0.15, contact + 0.45, time));
}

/** Where the kicker's body goes so that his striking toe — `toe`, in the
 * model's own frame (it faces +z) at the contact — is on the ball. */
export function placeForStrike(
  body: { x: number; z: number }, heading: number, ball: { x: number; z: number },
  toe: { x: number; z: number }, weight: number,
): { x: number; z: number } {
  const c = Math.cos(heading);
  const s = Math.sin(heading);
  // Rotation about the vertical axis: local +z → (sin h, cos h), +x → (cos h, -sin h).
  const tx = toe.x * c + toe.z * s;
  const tz = -toe.x * s + toe.z * c;
  return { x: body.x + (ball.x - tx - body.x) * weight, z: body.z + (ball.z - tz - body.z) * weight };
}
