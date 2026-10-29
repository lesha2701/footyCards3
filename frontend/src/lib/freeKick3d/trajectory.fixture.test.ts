/**
 * The server replays every rewarded shot with a Python port of this engine
 * (backend/app/services/free_kick_3d_engine.py). Both test suites check the
 * same fixture, bit for bit, so the two can't drift apart.
 *
 * Regenerate after a deliberate engine change:
 *   FK3D_WRITE_FIXTURE=1 npx vitest run src/lib/freeKick3d/trajectory.fixture
 * then copy the file to backend/tests/fixtures/ (the test below compares
 * the copies when the backend is checked out next to the frontend).
 */
import {
  createPenaltySetup,
  penaltyBotShot,
  playShot,
  playerKeeperSetup,
  simulateShot,
  swipeToKick,
  type QuantizedDive,
  type QuantizedSwipe,
  type ShotTrajectory,
} from "./trajectory";

// The app's tsconfig has no Node types; the test runs in Node all the same.
type Fs = {
  existsSync(path: string): boolean;
  readFileSync(path: string, encoding: "utf8"): string;
  writeFileSync(path: string, data: string): void;
};
const nodeFs = (): Promise<Fs> => import(/* @vite-ignore */ `node:${"fs"}`);
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const path = (rel: string) => decodeURIComponent(new URL(rel, import.meta.url).pathname);
const FIXTURE = path("./__fixtures__/free_kick_3d_shots.json");
const BACKEND_COPY = path("../../../../backend/tests/fixtures/free_kick_3d_shots.json");

type Case = { seed: number; rating: number; swipe: QuantizedSwipe };

function cases(): Case[] {
  const out: Case[] = [];
  const seeds = [1, 5, 12, 99, 4242, 345576453, 1116303195, 2147483647];
  const ratings = [55, 75, 88, 99];
  const swipes: QuantizedSwipe[] = [
    { dx: 0, dy: -360, curve: 0, durationMs: 170 },
    { dx: 50, dy: -300, curve: 40, durationMs: 180 },
    { dx: -60, dy: -280, curve: -100, durationMs: 150 },
    { dx: 40, dy: -100, curve: 100, durationMs: 150 },
    { dx: 90, dy: -260, curve: 100, durationMs: 150 },
    { dx: -200, dy: -300, curve: 0, durationMs: 120 },
    { dx: 0, dy: -600, curve: 250, durationMs: 400 },
    { dx: 10, dy: -150, curve: -30, durationMs: 90 },
  ];
  seeds.forEach((seed, i) => {
    for (let j = 0; j < swipes.length; j++) out.push({ seed, rating: ratings[(i + j) % ratings.length], swipe: swipes[j] });
  });
  return out;
}

const summary = (t: ShotTrajectory) => ({ outcome: t.outcome, end: t.end, events: t.events.map((e) => e.type) });

function compute() {
  const freeKicks = cases().map(({ seed, rating, swipe }) => ({ mode: "free_kick", seed, rating, swipe, ...summary(playShot(seed, swipe, true, rating)) }));
  // Penalties: the player's kick against the bot keeper…
  const kicks = [3, 17, 4242, 99991, 2147483000].flatMap((seed, i) =>
    [
      { dx: 50, dy: -110, curve: 0, durationMs: 160 },
      { dx: -60, dy: -160, curve: 30, durationMs: 170 },
      { dx: 95, dy: -230, curve: 0, durationMs: 150 },
      { dx: 0, dy: -150, curve: 0, durationMs: 160 },
      { dx: 0, dy: -260, curve: 0, durationMs: 900 },
      { dx: 140, dy: -120, curve: 0, durationMs: 170 },
    ].map((swipe, j) => {
      const rating = [55, 75, 90, 99][(i + j) % 4];
      const setup = createPenaltySetup(seed, rating);
      return { mode: "penalty_kick", seed, rating, swipe, ...summary(simulateShot(setup, swipeToKick(setup, swipe))) };
    }),
  );
  // …and the bot's kick against the player's dive (none, early, on time, late).
  const dives: (QuantizedDive | null)[] = [
    null,
    { x: 2200, y: 900, reactionMs: -150 },
    { x: -2200, y: 600, reactionMs: 120 },
    { x: 2000, y: 1400, reactionMs: 240 },
    { x: 0, y: 1900, reactionMs: 200 },
    { x: -1800, y: 300, reactionMs: 420 },
  ];
  const saves = [1, 2, 5, 12, 77, 345576453].flatMap((seed) =>
    dives.map((dive) => {
      const setup = playerKeeperSetup(seed, dive);
      const { kind, swipe } = penaltyBotShot(seed);
      return { mode: "penalty_save", seed, dive, kind, swipe, ...summary(simulateShot(setup, swipeToKick(setup, swipe))) };
    }),
  );
  return [...freeKicks, ...kicks, ...saves];
}

describe("free kick 3D engine fixture (shared with the backend)", () => {
  it("matches the recorded shots exactly", async () => {
    const fs = await nodeFs();
    const now = compute();
    if (env.FK3D_WRITE_FIXTURE) fs.writeFileSync(FIXTURE, JSON.stringify(now, null, 1) + "\n");
    const recorded = JSON.parse(fs.readFileSync(FIXTURE, "utf8"));
    expect(now).toEqual(recorded);
    // A spread of outcomes, so the fixture really exercises the engine.
    const outcomes = new Set(now.map((c) => c.outcome));
    for (const o of ["goal", "save", "wall", "miss"]) expect(outcomes).toContain(o);
    for (const mode of ["penalty_kick", "penalty_save"]) {
      const penalty = new Set(now.filter((c) => c.mode === mode).map((c) => c.outcome));
      for (const o of ["goal", "save"]) expect(penalty).toContain(o);
    }
  });

  it("the backend's copy is the same file", async () => {
    const fs = await nodeFs();
    if (!fs.existsSync(BACKEND_COPY)) return;
    expect(fs.readFileSync(BACKEND_COPY, "utf8")).toBe(fs.readFileSync(FIXTURE, "utf8"));
  });
});
