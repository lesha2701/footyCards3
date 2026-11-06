import { describe, expect, it } from "vitest";

import { feintBites } from "./actions";
import { thinkTeam } from "./brain";
import { Act, BALL_R, CLOCK_RATE, HALF_W, HZ, MATCH_SECONDS, Phase, Style, Trait, ballAt, dist, predict, type MatchState } from "./core";
import { NO_INPUT, SLOTS, createMatch, stepMatch } from "./engine";
import { lineOf, makePlan, reviewPlans } from "./gameplan";

const SETUP = { seed: 77, home: "A", away: "B", homeRating: 0.78, awayRating: 0.76 };

function inPlay(seed = 77, level?: 0 | 1 | 2) {
  const s = createMatch({ ...SETUP, seed, level }, 0);
  for (let i = 0; i < 900 && s.phase !== Phase.Play; i++) stepMatch(s, NO_INPUT);
  expect(s.phase).toBe(Phase.Play);
  return s;
}

/** Puts the ball at the feet of `who`, the rest stays where it is. */
function give(s: MatchState, who: number, x: number, z: number) {
  const p = s.players[who];
  p.x = x; p.z = z; p.vx = 0; p.vz = 0; p.act = Act.None;
  ballAt(s.ball, x + 0.4, BALL_R, z);
  s.ball.owner = who; s.ball.to = -1; s.ball.since = 20;
  predict(s);
}

const at = (s: MatchState, share: number) => { s.clock = MATCH_SECONDS * HZ * CLOCK_RATE * share; s.tick = 30 * 1000; };

describe("match3d, the AI's plan", () => {
  it("the AI side comes with a plan of its own and says so, the human's side doesn't", () => {
    const seen = new Set<Style>();
    for (let seed = 1; seed < 30; seed++) {
      const s = createMatch({ ...SETUP, seed }, 0);
      expect(s.plans[0].style).toBe(Style.Balanced);
      expect(s.plans[1].style).not.toBe(Style.Balanced);
      let said = 0;
      for (let i = 0; i < 200; i++) {
        stepMatch(s, NO_INPUT);
        said += s.ev.filter((e) => e.t === "plan" && e.kind === "style" && e.team === 1).length;
      }
      expect(said).toBe(1);
      seen.add(s.plans[1].style);
    }
    expect(seen.size).toBe(3);
  });

  it("a press stands higher than a block", () => {
    const s = createMatch(SETUP, 0);
    s.plans[1] = makePlan(Style.Press);
    const high = lineOf(s, 1);
    s.plans[1] = makePlan(Style.Block);
    expect(high).toBeGreaterThan(lineOf(s, 1) + 8);
  });

  it("behind late on they throw everyone forward, once, and the side ahead sits back", () => {
    const s = createMatch(SETUP, 0);
    s.teams[0].goals = 1;
    at(s, 0.1);
    reviewPlans(s);
    expect(s.plans[1].siege).toBe(0);
    s.ev.length = 0;
    at(s, 0.9);
    reviewPlans(s);
    expect(s.plans[1].siege).toBe(1);
    expect(s.plans[0].protect).toBeGreaterThan(0.9);
    expect(lineOf(s, 1)).toBeGreaterThan(s.plans[1].line + 10);
    expect(s.ev.filter((e) => e.t === "plan" && e.kind === "siege")).toHaveLength(1);
    s.ev.length = 0;
    reviewPlans(s);
    expect(s.ev.filter((e) => e.t === "plan")).toHaveLength(0);
  });

  it("a feint that keeps being tried stops selling", () => {
    const bites = (seen: number) => {
      let sold = 0;
      for (let n = 0; n < 300; n++) {
        const s = createMatch(SETUP, 0);
        s.rng = (s.rng + n * 7919) >>> 0;
        const c = s.players.find((p) => p.team === 0 && p.role === "W")!;
        const d = s.players.find((p) => p.team === 1 && p.role === "CM")!;
        give(s, c.i, 0, 0);
        d.x = 1.6; d.z = 0; d.act = Act.None; d.beat = 0;
        c.hx = 1; c.hz = 0; c.sub = 0; c.runUp = 0;
        s.scout[1].feints[0] = seen;
        feintBites(s, c);
        if (d.beat > 0) sold += 1;
      }
      return sold;
    };
    expect(bites(0)).toBeGreaterThan(bites(5) * 1.5);
  });

  it("everybody has his job", () => {
    const s = createMatch(SETUP, 0);
    const of = (t: Trait, team: 0 | 1) => s.players.filter((p) => p.trait === t && p.team === team).map((p) => p.role);
    for (const team of [0, 1] as const) {
      expect(of(Trait.Playmaker, team)).toEqual(["CM"]);
      expect(of(Trait.Target, team)).toEqual(["ST"]);
      expect(of(Trait.Dribbler, team).every((r) => r === "W")).toBe(true);
    }
    expect(of(Trait.Poacher, 1)).toEqual(["ST"]);
  });

  it("the best man gets a shadow, and the side remembers who hurt it", () => {
    const s = inPlay();
    const carrier = s.players.find((p) => p.team === 0 && p.role === "CM")!;
    const star = s.players.find((p) => p.team === 0 && p.role === "ST")!;
    give(s, carrier.i, -2, 0);
    s.scout[1].threat[star.slot] = 20;
    star.x = 20; star.z = 3;
    thinkTeam(s, 1, SLOTS[1]);
    const shadow = s.players.find((p) => p.team === 1 && p.tag);
    expect(shadow?.mark).toBe(star.i);
    expect(["CM", "DM"]).toContain(shadow?.role);
  });

  it("on the touchline a second and a third man shut him in", () => {
    const s = inPlay();
    const w = s.players.find((p) => p.team === 0 && p.role === "W")!;
    give(s, w.i, -10, HALF_W - 3);
    let k = 0;
    for (const p of s.players) {
      if (p.team !== 1 || p.role === "GK") continue;
      k += 1;
      p.x = -10 + k * 2.5; p.z = HALF_W - 5 - k * 1.5;
    }
    thinkTeam(s, 1, SLOTS[1]);
    expect(s.players.filter((p) => p.team === 1 && p.duty === 1).length).toBeGreaterThanOrEqual(1);
    expect(s.players.filter((p) => p.team === 1 && p.duty === 2).length).toBeGreaterThanOrEqual(1);
  });

  const wall = (x: number) => {
    const s = inPlay();
    const taker = s.players.find((p) => p.team === 0 && p.role === "ST")!;
    s.phase = Phase.Dead;
    s.ball.owner = -1;
    s.set = { kind: "free", team: 0, x, z: 0, taker: taker.i, t: 0, ready: false, scene: -1, routine: -1 };
    for (let i = 0; i < 600 && !s.set?.ready; i++) stepMatch(s, NO_INPUT);
    return s.players.filter((p) => p.team === 1 && p.role !== "GK" && Math.abs(dist(p.x, p.z, x, 0) - 9.15) < 0.9).length;
  };

  it("the nearer the free kick, the bigger the wall", () => {
    expect(wall(33)).toBeGreaterThanOrEqual(5);
    expect(wall(19)).toBeLessThanOrEqual(3);
    expect(wall(19)).toBeGreaterThanOrEqual(2);
  });

  it("a corner's routine is settled once and comes in several kinds", () => {
    const seen = new Set<number>();
    for (let seed = 1; seed < 20; seed++) {
      const s = inPlay(seed);
      const taker = s.players.find((p) => p.team === 1 && p.role === "W")!;
      s.phase = Phase.Dead;
      s.ball.owner = -1;
      s.set = { kind: "corner", team: 1, x: -52, z: HALF_W, taker: taker.i, t: 0, ready: false, scene: -1, routine: -1 };
      for (let i = 0; i < 30; i++) stepMatch(s, NO_INPUT);
      const first = s.set.routine;
      for (let i = 0; i < 30; i++) stepMatch(s, NO_INPUT);
      expect(first).toBeGreaterThanOrEqual(0);
      if (s.set) expect(s.set.routine).toBe(first);
      seen.add(first);
    }
    expect(seen.size).toBeGreaterThanOrEqual(3);
  });

  it("the level sets the AI side's sharpness and ratings, never the human's", () => {
    const easy = createMatch({ ...SETUP, level: 0 }, 0), hard = createMatch({ ...SETUP, level: 2 }, 0);
    expect(easy.skill[0]).toBe(1);
    expect(hard.skill[0]).toBe(1);
    expect(easy.skill[1]).toBeLessThan(1);
    expect(hard.skill[1]).toBeGreaterThan(1);
    expect(hard.players[15].pace).toBeGreaterThan(easy.players[15].pace);
    expect(hard.players[3].pace).toBe(easy.players[3].pace);
    expect(createMatch(SETUP, 0).skill[1]).toBe(1);
  });

  it("a whole match at each level is the same twice and finishes", () => {
    for (const level of [0, 1, 2] as const) {
      const run = () => {
        const s = createMatch({ ...SETUP, level }, null);
        while (s.phase !== Phase.FullTime) stepMatch(s, NO_INPUT);
        return s.players.reduce((h, p) => (Math.imul(h, 31) + Math.round(p.x * 1e4)) | 0, s.tick);
      };
      expect(run()).toBe(run());
    }
  });
});
