/**
 * The server replays every rewarded attack with a Python port of this
 * engine (backend/app/services/one_on_one_engine.py). Both test suites check
 * the same fixture, bit for bit, so the two can't drift apart.
 *
 * Regenerate after a deliberate engine change:
 *   ONE_ON_ONE_WRITE_FIXTURE=1 npx vitest run src/lib/oneOnOne/engine.fixture
 * then copy the file to backend/tests/fixtures/ (the test below compares
 * the copies when the backend is checked out next to the frontend).
 */
import type { QuantizedSwipe } from "@/lib/freeKick3d/trajectory";

import { ballOf, createEpisode, replayEpisode, type EpisodeEnd } from "./engine";
import { EpisodeRecorder } from "./recorder";

type Fs = {
  existsSync(path: string): boolean;
  readFileSync(path: string, encoding: "utf8"): string;
  writeFileSync(path: string, data: string): void;
};
const nodeFs = (): Promise<Fs> => import(/* @vite-ignore */ `node:${"fs"}`);
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const path = (rel: string) => decodeURIComponent(new URL(rel, import.meta.url).pathname);
const FIXTURE = path("./__fixtures__/one_on_one_episodes.json");
const BACKEND_COPY = path("../../../../backend/tests/fixtures/one_on_one_episodes.json");

const SWIPES: QuantizedSwipe[] = [
  { dx: 80, dy: -160, curve: 0, durationMs: 140 },
  { dx: -70, dy: -150, curve: 40, durationMs: 150 },
  { dx: 0, dy: -300, curve: 0, durationMs: 600 },
  { dx: 120, dy: -220, curve: -80, durationMs: 130 },
  { dx: -30, dy: -120, curve: 0, durationMs: 90 },
  { dx: 60, dy: -400, curve: 120, durationMs: 300 },
];

/** A scripted player, like a finger: weaves, lets go for a moment, feints
 * at some distance from the keeper (or never) and shoots some ticks later
 * (or never). */
function play(seed: number, rating: number, variant: number): EpisodeRecorder {
  const rec = new EpisodeRecorder(createEpisode(seed, rating));
  const feintAt = [null, 7, 4.5, 3, 5.5][variant % 5];
  const shootAfter = [12, 25, 40, null][variant % 4];
  const swipe = SWIPES[variant % SWIPES.length];
  const weave = [0, 300, -650, 1000][variant % 4];
  // The moment the plan starts: the feint, or (no feint) 6 m from him.
  let trigger: number | null = null;
  while (!rec.state.ended) {
    const s = rec.state;
    const steer = s.tick % 40 < 20 ? weave : -Math.floor(weave / 2);
    const hold = !(s.tick >= 30 && s.tick < 38 && variant % 3 === 0);
    const b = ballOf(s);
    const d = Math.hypot(b.x - s.kx, b.z - s.kz);
    let feint = 0;
    if (trigger === null && d < (feintAt ?? 6)) {
      trigger = s.tick;
      if (feintAt !== null) feint = variant % 2 === 0 ? 1 : -1;
    }
    const shoot = shootAfter !== null && trigger !== null && s.tick >= trigger + shootAfter;
    rec.step(hold, steer, feint, shoot ? swipe : null);
  }
  return rec;
}

const summary = (r: EpisodeEnd) => ({
  outcome: r.outcome,
  tick: r.tick,
  feint: r.feint,
  chip: r.chip,
  flight: r.flight
    ? {
        outcome: r.flight.outcome,
        keeper: r.flight.keeper,
        overY: r.flight.overY,
        events: r.flight.events.map((e) => e.type),
        end: r.flight.end,
      }
    : null,
});

function compute() {
  const seeds = [1, 2, 7, 42, 99, 4242, 77777, 345576453, 1116303195, 2147483647];
  const ratings = [55, 75, 88, 99];
  const out = [];
  for (let i = 0; i < seeds.length; i++) {
    for (let variant = 0; variant < 6; variant++) {
      const rating = ratings[(i + variant) % ratings.length];
      const rec = play(seeds[i], rating, variant + i);
      out.push({ seed: seeds[i], rating, timeline: rec.timeline, ...summary(rec.state.ended!) });
    }
  }
  return out;
}

describe("1-on-1 engine fixture (shared with the backend)", () => {
  it("live recording and the replay of its timeline agree", () => {
    for (const c of compute()) {
      expect(summary(replayEpisode(createEpisode(c.seed, c.rating), c.timeline))).toEqual({
        outcome: c.outcome, tick: c.tick, feint: c.feint, chip: c.chip, flight: c.flight,
      });
    }
  });

  it("matches the recorded episodes exactly", async () => {
    const fs = await nodeFs();
    const now = compute();
    if (env.ONE_ON_ONE_WRITE_FIXTURE) fs.writeFileSync(FIXTURE, JSON.stringify(now, null, 1) + "\n");
    const recorded = JSON.parse(fs.readFileSync(FIXTURE, "utf8"));
    expect(JSON.parse(JSON.stringify(now))).toEqual(recorded);
    // A spread of outcomes, so the fixture really exercises the engine.
    const outcomes = new Set(now.map((c) => c.outcome));
    for (const o of ["goal", "save", "tackle", "miss"]) expect(outcomes).toContain(o);
    const feints = new Set(now.map((c) => c.feint));
    for (const f of ["bit", "read", null]) expect(feints).toContain(f);
  });

  it("the backend's copy is the same file", async () => {
    const fs = await nodeFs();
    if (!fs.existsSync(BACKEND_COPY)) return;
    expect(fs.readFileSync(BACKEND_COPY, "utf8")).toBe(fs.readFileSync(FIXTURE, "utf8"));
  });
});
