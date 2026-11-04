import type { QuantizedSwipe } from "@/lib/freeKick3d/trajectory";

import { resolveShot, type ShotIntent } from "./aim";
import { advance, initState, type EpisodeSetup, type EpisodeState, type EpisodeTimeline } from "./engine";
import { initTeamState, strikeReady, teamAdvance, type PassOrder, type TeamSetup } from "./team";

/** Steer is sent in steps of this many thousandths: a finger's jitter
 * doesn't add a control change every tick. */
export const STEER_STEP = 50;

export function quantizeSteer(raw: number): number {
  const k = Math.round(Math.min(1, Math.max(-1, raw)) * (1000 / STEER_STEP));
  return k * STEER_STEP || 0;
}

/** Steps the episode live, tick by tick, from what the finger does now —
 * and writes down exactly the timeline the server will replay. */
export class EpisodeRecorder {
  readonly state: EpisodeState;
  readonly timeline: EpisodeTimeline;
  private last: [number, number] | null = null;
  /** An aimed shot waiting for the feint in progress to finish. */
  private pending: ShotIntent | null = null;

  /** A shot is waiting to be struck (a first-time finish on its way). */
  get shotWaiting(): boolean {
    return this.pending !== null;
  }

  constructor(readonly setup: EpisodeSetup) {
    const team = this.team;
    this.state = team ? initTeamState(team) : initState(setup);
    this.timeline = team ? { controls: [], feint: null, shot: null, passes: [] } : { controls: [], feint: null, shot: null };
  }

  private get team(): TeamSetup | null {
    return "team" in this.setup ? (this.setup as TeamSetup) : null;
  }

  /** Can the waiting shot be struck on this tick? */
  private canStrike(i: number): boolean {
    const s = this.state;
    if (this.timeline.feint?.tick === i) return false;
    return s.team ? strikeReady(s) : s.feintTicks === 0;
  }

  /** One tick: stop / run / sprint (0 / 1 / 2, or a boolean for run),
   * steer in thousandths (already quantized), a feint this tick (−1 / 1, 0
   * for none), a shot released this tick — a swipe as it is, or an aim /
   * a tap resolved on the tick it is played (so after a feint, from where
   * the feint left the ball; off a pass, when it reaches him), a pass to
   * a teammate. */
  step(hold: number | boolean, steer: number, feint = 0, shot: QuantizedSwipe | ShotIntent | null = null, pass: PassOrder | null = null): void {
    const s = this.state;
    if (s.ended) return;
    const i = s.tick;
    const h = hold === true ? 1 : hold === false ? 0 : hold;
    if (!this.last || this.last[0] !== h || this.last[1] !== steer) {
      this.timeline.controls.push([i, h, steer]);
      this.last = [h, steer];
    }
    if (feint !== 0 && !s.feintUsed && !this.timeline.feint && !this.timeline.shot) {
      this.timeline.feint = { tick: i, dir: feint > 0 ? 1 : -1 };
    }
    if (shot && !("dx" in shot)) {
      this.pending ??= shot;
      shot = null;
    }
    if (this.pending && !this.timeline.shot && this.canStrike(i)) {
      shot = resolveShot(this.setup, s, this.pending);
      this.pending = null;
    }
    if (shot && !this.timeline.shot) this.timeline.shot = { tick: i, ...shot };
    const tl = this.timeline;
    const input = {
      hold: h,
      steer,
      feint: tl.feint && tl.feint.tick === i ? tl.feint.dir : 0,
      shot: tl.shot,
    };
    const team = this.team;
    if (team && s.team) {
      if (pass && !s.team.pass && s.team.windup === 0) tl.passes?.push({ tick: i, ...pass });
      teamAdvance(team, s, { ...input, pass });
    } else advance(this.setup, s, input);
  }
}
