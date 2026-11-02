import type { QuantizedSwipe } from "@/lib/freeKick3d/trajectory";

import { FEINT_TICKS, MAX_RUN_TICKS, ballOf, createEpisode, replayEpisode, type EpisodeEnd } from "./engine";
import { EpisodeRecorder, quantizeSteer } from "./recorder";

const OPEN_SIDE: QuantizedSwipe = { dx: 60, dy: -140, curve: 0, durationMs: 140 };

/** Runs straight at the keeper; at `d` metres from him feints right (or
 * shoots, with `feint` false), shoots `after` ticks later. */
function attack(seed: number, d: number, opts: { feint?: boolean; after?: number; swipe?: QuantizedSwipe; rating?: number } = {}) {
  const { feint = true, after = 18, swipe = OPEN_SIDE, rating = 75 } = opts;
  const rec = new EpisodeRecorder(createEpisode(seed, rating));
  let at: number | null = null;
  while (!rec.state.ended) {
    const s = rec.state;
    const b = ballOf(s);
    const near = Math.hypot(b.x - s.kx, b.z - s.kz) < d;
    if (at === null && near) at = s.tick;
    rec.step(true, 0, feint && at === s.tick ? 1 : 0, at !== null && s.tick >= at + (feint ? after : 0) ? swipe : null);
  }
  return rec;
}

const share = (ends: EpisodeEnd[], pred: (e: EpisodeEnd) => boolean) => ends.filter(pred).length / ends.length;
const SEEDS = Array.from({ length: 100 }, (_, i) => i + 1);

describe("1-on-1 episode engine", () => {
  it("the server's replay of the recorded timeline is the live episode", () => {
    for (const seed of [3, 8, 13]) {
      const rec = attack(seed, 4.5);
      const replay = replayEpisode(createEpisode(seed), rec.timeline);
      expect(replay.outcome).toBe(rec.state.ended!.outcome);
      expect(replay.tick).toBe(rec.state.ended!.tick);
      expect(replay.flight?.end).toEqual(rec.state.ended!.flight?.end);
    }
  });

  it("standing still the chance is gone; running at him he takes the ball", () => {
    const still = replayEpisode(createEpisode(5), { controls: [], feint: null, shot: null });
    expect([still.outcome, still.tick]).toEqual(["lost", MAX_RUN_TICKS]);
    const run = replayEpisode(createEpisode(5), { controls: [[0, 1, 0]], feint: null, shot: null });
    expect(run.outcome).toBe("tackle");
  });

  it("a feint at the right distance gets the keeper to bite and go down; from afar he reads it", () => {
    const close = SEEDS.map((s) => attack(s, 4.5, { after: 30 }).state.ended!);
    expect(share(close, (e) => e.feint === "bit")).toBeGreaterThan(0.8);
    const far = SEEDS.map((s) => attack(s, 14, { after: 30 }).state.ended!);
    expect(share(far, (e) => e.feint === "read")).toBe(1);
  });

  it("the feint pays: after it the open side scores far more often than a plain shot from close", () => {
    const fooled = SEEDS.map((s) => attack(s, 4.5).state.ended!);
    const plain = SEEDS.map((s) => attack(s, 3, { feint: false, swipe: { dx: 80, dy: -160, curve: 0, durationMs: 140 } }).state.ended!);
    expect(share(fooled, (e) => e.outcome === "goal")).toBeGreaterThan(0.75);
    expect(share(plain, (e) => e.outcome === "goal")).toBeLessThan(0.3);
  });

  it("a shot released during the feint waits for the sidestep to finish", () => {
    const rec = attack(21, 4.5, { after: 2 });
    const tl = rec.timeline;
    expect(tl.shot!.tick).toBe(tl.feint!.tick + 2);
    expect(rec.state.ended!.tick).toBe(tl.feint!.tick + FEINT_TICKS);
  });

  it("a chip can go over a keeper who rushed out", () => {
    const chips = SEEDS.map((s) => attack(s, 6, { feint: false, swipe: { dx: 0, dy: -300, curve: 0, durationMs: 600 } }).state.ended!);
    expect(chips.some((e) => e.chip && e.outcome === "goal")).toBe(true);
  });

  it("a better card runs faster", () => {
    const tl = { controls: [[0, 1, 0]] as [number, number, number][], feint: null, shot: null };
    expect(replayEpisode(createEpisode(9, 99), tl).tick).toBeLessThan(replayEpisode(createEpisode(9, 55), tl).tick);
  });

  it("steer is sent in coarse integer steps", () => {
    expect(quantizeSteer(0.012)).toBe(0);
    expect(quantizeSteer(-0.012)).toBe(0);
    expect(quantizeSteer(0.33)).toBe(350);
    expect(quantizeSteer(7)).toBe(1000);
  });
});
