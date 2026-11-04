import { describe, expect, it } from "vitest";

import { Act, BALL_R, HZ, MATCH_SECONDS, Phase, ballAt, predict, type MatchState } from "./core";
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

  /** Open play with team 0's `who` on the ball at (x, z), everybody else far off. */
  const onBall = (who: number, x: number, z: number) => {
    const s = createMatch(SETUP, 0);
    for (let i = 0; i < 900 && s.phase !== Phase.Play; i++) stepMatch(s, NO_INPUT);
    expect(s.phase).toBe(Phase.Play);
    s.set = null;
    for (const p of s.players) if (p.team === 1 && p.role !== "GK") { p.x = 45; p.z = p.i - 16; p.vx = 0; p.vz = 0; }
    const p = s.players[who];
    p.x = x; p.z = z; p.vx = 0; p.vz = 0; p.act = Act.None;
    ballAt(s.ball, x + 0.4, BALL_R, z);
    s.ball.owner = who; s.ball.to = -1; s.ball.since = 20;
    s.user = who;
    predict(s);
    return s;
  };
  const outfield = (s: MatchState, not: number) => s.players.filter((p) => p.team === 0 && p.role !== "GK" && p.i !== not);

  it("a human's pass gets to his man, whatever the stick does meanwhile", () => {
    const from = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(from, -10, 5);
    const m = outfield(s, from)[0];
    m.x = 4; m.z = -6;
    stepMatch(s, { ...NO_INPUT, mx: (m.x - s.players[from].x) / 18, mz: (m.z - s.players[from].z) / 18, press: { k: "pass", power: 0.4 } });
    const away = { ...NO_INPUT, mx: -1, mz: 0, sprint: true };
    for (let i = 0; i < 240 && (s.ball.owner < 0 || s.ball.owner === from); i++) stepMatch(s, away);
    expect(s.players[s.ball.owner].team).toBe(0);
    expect(s.user).toBe(s.ball.owner);
  });

  it("the human decides what his keeper does with the ball", () => {
    const s = createMatch(SETUP, 0);
    for (let i = 0; i < 900 && s.phase !== Phase.Play; i++) stepMatch(s, NO_INPUT);
    const gk = s.players.find((p) => p.team === 0 && p.role === "GK")!;
    const b = s.ball;
    b.owner = gk.i; b.last = gk.i; b.to = -1;
    gk.act = Act.Hold; gk.actT = 0; gk.actLen = 40;
    stepMatch(s, NO_INPUT);
    expect(s.user).toBe(gk.i);
    for (let i = 0; i < 200; i++) stepMatch(s, NO_INPUT);
    expect(gk.act).toBe(Act.Hold);
    stepMatch(s, { ...NO_INPUT, mx: 1, press: { k: "pass", power: 0.4 } });
    expect([Act.GkThrow, Act.GkKick]).toContain(s.players[gk.i].act as number);
    for (let i = 0; i < 40 && b.owner === gk.i; i++) stepMatch(s, NO_INPUT);
    expect(b.to).toBeGreaterThanOrEqual(0);
    expect(s.players[b.to].team).toBe(0);
    stepMatch(s, NO_INPUT);
    expect(s.user).toBe(b.to);
  });

  it("in defence the human gets the man nearest to the ball", () => {
    const s = createMatch(SETUP, 0);
    for (let i = 0; i < 900 && s.phase !== Phase.Play; i++) stepMatch(s, NO_INPUT);
    s.set = null;
    const c = s.players.find((p) => p.team === 1 && p.role !== "GK")!;
    ballAt(s.ball, c.x, BALL_R, c.z);
    s.ball.owner = c.i; s.ball.to = -1;
    const near = outfield(s, -1)[0], far = outfield(s, -1)[1];
    near.x = c.x + 3; near.z = c.z;
    far.x = c.x + 30; far.z = c.z + 10;
    s.user = far.i;
    s.switchT = 0;
    for (let i = 0; i < 6; i++) stepMatch(s, { ...NO_INPUT, mz: 1 });
    expect(s.user).toBe(near.i);
  });

  it("a sprint spends the legs and walking gives them back", () => {
    const from = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(from, -40, 0);
    const p = s.players[from];
    const fresh = Math.abs(p.stamina - 1) < 1e-9;
    for (let i = 0; i < 180; i++) stepMatch(s, { ...NO_INPUT, mx: 1, sprint: true });
    const spent = p.stamina;
    for (let i = 0; i < 120; i++) stepMatch(s, NO_INPUT);
    expect(fresh).toBe(true);
    expect(spent).toBeLessThan(0.9);
    expect(p.stamina).toBeGreaterThan(spent);
  });

  it("after a goal everybody is on his spot for the kick-off at once", () => {
    const s = createMatch(SETUP, 0);
    for (let i = 0; i < 900 && s.phase !== Phase.Play; i++) stepMatch(s, NO_INPUT);
    const p = s.players.find((q) => q.team === 0 && q.role === "ST")!;
    ballAt(s.ball, 53.2, 0.5, 0);
    s.ball.vx = 12; s.ball.owner = -1; s.ball.last = p.i;
    for (let i = 0; i < 400 && s.phase !== Phase.Kickoff; i++) stepMatch(s, NO_INPUT);
    expect(s.phase).toBe(Phase.Kickoff);
    for (const q of s.players) expect(q.x * (q.team === 0 ? 1 : -1)).toBeLessThanOrEqual(0.51);
  });

  it("a touch on a team-mate plays the ball to him", () => {
    const from = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(from, -10, 5);
    const m = outfield(s, from)[3];
    stepMatch(s, { ...NO_INPUT, press: { k: "to", i: m.i } });
    expect(s.players[from].act).toBe(Act.Kick);
    expect(s.players[from].plan?.to).toBe(m.i);
  });

  it("without the ball the back four keep a line", () => {
    const s = createMatch(SETUP, null);
    let n = 0, deep = 0;
    while (s.phase !== Phase.FullTime) {
      stepMatch(s, NO_INPUT);
      const c = s.ball.owner >= 0 ? s.players[s.ball.owner] : null;
      if (s.phase !== Phase.Play || !c || c.team !== 1 || s.tick % 30) continue;
      const xs = s.players.filter((p) => p.team === 0 && (p.role === "CB" || p.role === "FB") && !p.duty).map((p) => p.x);
      n += 1; deep += Math.max(...xs) - Math.min(...xs);
    }
    expect(n).toBeGreaterThan(20);
    expect(deep / n).toBeLessThan(7);
  });

  it("at a kick-off only the taker is in the circle, everybody in his own half", () => {
    for (const seed of [1, 2, 3]) {
      const s = createMatch({ ...SETUP, seed }, 0);
      for (const p of s.players) {
        if (p.i === s.set!.taker) continue;
        expect(Math.sqrt(p.x * p.x + p.z * p.z)).toBeGreaterThan(9.15);
        expect(p.x * (p.team === 0 ? 1 : -1)).toBeLessThan(0);
      }
    }
  });

  it("at a goal kick he has men near him and the other side waits outside the box", () => {
    const s = createMatch(SETUP, null);
    for (let i = 0; i < 700 && s.phase !== Phase.Play; i++) stepMatch(s, NO_INPUT);
    ballAt(s.ball, -53.4, BALL_R, 20);
    s.ball.owner = -1; s.ball.vx = -1; s.ball.vz = 0; s.ball.last = s.players.find((p) => p.team === 1)!.i;
    for (let i = 0; i < 240 && !(s.set && s.set.kind === "goalkick"); i++) stepMatch(s, NO_INPUT);
    expect(s.set?.kind).toBe("goalkick");
    for (let i = 0; i < 200 && s.set; i++) {
      stepMatch(s, NO_INPUT);
      if (s.set && s.set.t === 100) {
        const gk = s.players[s.set.taker];
        const near = s.players.filter((p) => p.team === gk.team && p.i !== gk.i && Math.abs(p.x - gk.x) < 26 && Math.abs(p.z - gk.z) < 22);
        expect(near.length).toBeGreaterThanOrEqual(3);
      }
    }
  });
});
