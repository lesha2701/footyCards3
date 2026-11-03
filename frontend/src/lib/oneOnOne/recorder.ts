import type { QuantizedSwipe } from "@/lib/freeKick3d/trajectory";

import { resolveShot, type ShotIntent } from "./aim";
import { advance, initState, type EpisodeSetup, type EpisodeState, type EpisodeTimeline } from "./engine";

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
  readonly timeline: EpisodeTimeline = { controls: [], feint: null, shot: null };
  private last: [number, number] | null = null;
  /** An aimed shot waiting for the feint in progress to finish. */
  private pending: ShotIntent | null = null;

  constructor(readonly setup: EpisodeSetup) {
    this.state = initState(setup);
  }

  /** One tick: stop / run / sprint (0 / 1 / 2, or a boolean for run),
   * steer in thousandths (already quantized), a feint this tick (−1 / 1, 0
   * for none), a shot released this tick — a swipe as it is, or an aim /
   * a tap resolved on the tick it is played (so after a feint, from where
   * the feint left the ball). */
  step(hold: number | boolean, steer: number, feint = 0, shot: QuantizedSwipe | ShotIntent | null = null): void {
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
    if (this.pending && !this.timeline.shot && s.feintTicks === 0 && !(this.timeline.feint?.tick === i)) {
      shot = resolveShot(this.setup, s, this.pending);
      this.pending = null;
    }
    if (shot && !this.timeline.shot) this.timeline.shot = { tick: i, ...shot };
    const tl = this.timeline;
    advance(this.setup, s, {
      hold: h,
      steer,
      feint: tl.feint && tl.feint.tick === i ? tl.feint.dir : 0,
      shot: tl.shot,
    });
  }
}
