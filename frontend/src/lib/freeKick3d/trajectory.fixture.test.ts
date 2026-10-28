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
import { playShot, type QuantizedSwipe } from "./trajectory";

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

function compute() {
  return cases().map(({ seed, rating, swipe }) => {
    const t = playShot(seed, swipe, true, rating);
    return { seed, rating, swipe, outcome: t.outcome, end: t.end, events: t.events.map((e) => e.type) };
  });
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
  });

  it("the backend's copy is the same file", async () => {
    const fs = await nodeFs();
    if (!fs.existsSync(BACKEND_COPY)) return;
    expect(fs.readFileSync(BACKEND_COPY, "utf8")).toBe(fs.readFileSync(FIXTURE, "utf8"));
  });
});
