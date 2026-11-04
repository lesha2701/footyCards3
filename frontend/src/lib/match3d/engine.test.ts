import { describe, expect, it } from "vitest";

import { HZ, MATCH_SECONDS, Phase, type MatchState } from "./core";
import { NO_INPUT, createMatch, stepMatch, type Input } from "./engine";

const SETUP = { seed: 1234, home: "A", away: "B", homeRating: 0.78, awayRating: 0.76 };

/** A scripted human: pure in the tick, so a replay feeds it again. */
function scripted(tick: number): Input {
  const swing = ((tick >> 6) & 3) - 1.5;
  const press = tick % 97 === 0 ? { k: "pass" as const, power: 0.4 } : tick % 431 === 0 ? { k: "shot" as const, power: 0.8, curl: 0.3, chip: false } : tick % 211 === 0 ? { k: "feint" as const } : null;
  return { mx: 0.8, mz: swing / 2, sprint: (tick & 256) !== 0, press, contain: (tick & 512) !== 0 };
}

const hash = (s: MatchState) => {
  let h = 0;
  const mix = (v: number) => { h = (Math.imul(h, 31) + Math.round(v * 1e6)) | 0; };
  for (const p of s.players) { mix(p.x); mix(p.z); mix(p.act); }
  mix(s.ball.x); mix(s.ball.y); mix(s.ball.z); mix(s.teams[0].goals); mix(s.teams[1].goals); mix(s.clock);
  return h;
};

const play = (user: 0 | null) => {
  const s = createMatch(SETUP, user);
  const marks: number[] = [];
  while (s.phase !== Phase.FullTime && s.tick < HZ * 60 * 12) {
    stepMatch(s, user === null ? NO_INPUT : scripted(s.tick));
    if (s.tick % 600 === 0) marks.push(hash(s));
  }
  return { s, marks };
};

describe("match3d engine", () => {
  it("is a pure function of the setup and the inputs", () => {
    expect(play(0).marks).toEqual(play(0).marks);
  });

  it("plays to the final whistle, in at least the promised time", () => {
    const { s } = play(null);
    expect(s.phase).toBe(Phase.FullTime);
    expect(s.tick / HZ).toBeGreaterThanOrEqual(MATCH_SECONDS);
    expect(s.teams[0].shots + s.teams[1].shots).toBeGreaterThan(0);
  });

  it("starts at 0:0", () => {
    const s = createMatch(SETUP, 0);
    expect(s.teams[0].goals + s.teams[1].goals).toBe(0);
  });

  it("uses only operations that give the same bits everywhere", () => {
    const sources = import.meta.glob("./*.ts", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    const files = Object.entries(sources).filter(([name]) => !name.endsWith(".test.ts"));
    expect(files.length).toBeGreaterThan(3);
    for (const [name, text] of files) {
      const code = text.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
      expect(code, name).not.toMatch(/Math\.(sin|cos|tan|atan|atan2|asin|acos|pow|exp|log|hypot|cbrt|random)\b|\*\*|Date\.now|performance\./);
    }
  });
});
