/**
 * The server replays every team episode with a Python port of team.ts
 * (backend/app/services/team_attack_engine.py). Both test suites check the
 * same fixture, bit for bit.
 *
 * Regenerate after a deliberate engine change:
 *   TEAM_WRITE_FIXTURE=1 npx vitest run src/lib/oneOnOne/team.fixture
 * then copy the file to backend/tests/fixtures/.
 */
import type { QuantizedSwipe } from "@/lib/freeKick3d/trajectory";

import type { EpisodeEnd } from "./engine";
import { EpisodeRecorder } from "./recorder";
import { TEAM_KINDS, createTeamEpisode, replayTeam, type TeamKind } from "./team";

type Fs = {
  existsSync(path: string): boolean;
  readFileSync(path: string, encoding: "utf8"): string;
  writeFileSync(path: string, data: string): void;
};
const nodeFs = (): Promise<Fs> => import(/* @vite-ignore */ `node:${"fs"}`);
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const path = (rel: string) => decodeURIComponent(new URL(rel, import.meta.url).pathname);
const FIXTURE = path("./__fixtures__/team_episodes.json");
const BACKEND_COPY = path("../../../../backend/tests/fixtures/team_episodes.json");

const SWIPES: QuantizedSwipe[] = [
  { dx: 80, dy: -160, curve: 0, durationMs: 140 },
  { dx: -70, dy: -150, curve: 40, durationMs: 150 },
  { dx: 120, dy: -220, curve: -80, durationMs: 130 },
  { dx: -30, dy: -120, curve: 0, durationMs: 90 },
];

/** A scripted player: runs (weaving), feints or not, plays a pass at some
 * tick to some teammate, and shoots some ticks later (or never). */
function play(kind: TeamKind, seed: number, rating: number, variant: number): EpisodeRecorder {
  const setup = createTeamEpisode(kind, seed, rating);
  const rec = new EpisodeRecorder(setup);
  const passAt = [25, 60, 95, 130, 170, null][variant % 6];
  const shootAfter = [18, 40, 70, 110, null][variant % 5];
  const feintAt = [null, 30, null, 80][variant % 4];
  const weave = [0, 250, -500][variant % 3];
  const swipe = SWIPES[variant % SWIPES.length];
  while (!rec.state.ended) {
    const s = rec.state;
    const steer = s.tick % 50 < 25 ? weave : -Math.floor(weave / 2);
    const hold = variant % 4 === 3 && s.tick % 120 > 70 ? 3 : variant % 2 === 0 ? 2 : 1;
    // Every fifth a full-blooded cross: the ball the defence deals with.
    const full = variant % 5 === 0;
    const order = { target: variant % setup.team.men.length, mode: full ? 2 : (variant >> 1) % 4, power: full ? 100 : [30, 55, 80][variant % 3] };
    const pass = passAt !== null && s.tick === passAt ? order : null;
    const feint = feintAt !== null && s.tick === feintAt ? (variant % 2 ? 1 : -1) : 0;
    const shoot = shootAfter !== null && s.tick >= (passAt ?? 40) + shootAfter;
    rec.step(hold, steer, feint, shoot ? swipe : null, pass);
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
  for (const kind of TEAM_KINDS) {
    for (let i = 0; i < seeds.length; i++) {
      for (let variant = 0; variant < 12; variant++) {
        const rating = ratings[(i + variant) % ratings.length];
        const rec = play(kind, seeds[i], rating, variant + i);
        out.push({ kind, seed: seeds[i], rating, timeline: rec.timeline, ...summary(rec.state.ended!) });
      }
    }
  }
  return out;
}

describe("team episodes fixture (shared with the backend)", () => {
  it("live recording and the replay of its timeline agree", () => {
    for (const c of compute()) {
      expect(summary(replayTeam(createTeamEpisode(c.kind, c.seed, c.rating), c.timeline))).toEqual({
        outcome: c.outcome, tick: c.tick, feint: c.feint, chip: c.chip, flight: c.flight,
      });
    }
  });

  it("matches the recorded episodes exactly", async () => {
    const fs = await nodeFs();
    const now = compute();
    if (env.TEAM_WRITE_FIXTURE) fs.writeFileSync(FIXTURE, JSON.stringify(now, null, 1) + "\n");
    const recorded = JSON.parse(fs.readFileSync(FIXTURE, "utf8"));
    expect(JSON.parse(JSON.stringify(now))).toEqual(recorded);
    // A spread of outcomes, so the fixture really exercises the engine.
    const outcomes = new Set(now.map((c) => c.outcome));
    for (const o of ["goal", "save", "dispossessed", "intercepted", "offside", "cleared", "blocked"]) expect(outcomes).toContain(o);
  });

  it("the backend's copy is the same file", async () => {
    const fs = await nodeFs();
    if (!fs.existsSync(BACKEND_COPY)) return;
    expect(fs.readFileSync(BACKEND_COPY, "utf8")).toBe(fs.readFileSync(FIXTURE, "utf8"));
  });
});
