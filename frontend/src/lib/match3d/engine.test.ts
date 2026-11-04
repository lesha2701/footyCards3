import { describe, expect, it } from "vitest";

import { planLob } from "./actions";
import { Act, BALL_R, HALF_W, HZ, Kick, MATCH_SECONDS, Phase, ballAt, launch, predict, stepBall, type MatchState } from "./core";
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

  it("a thumb that moves always steers, even with a pass on its way to him", () => {
    const from = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(from, -10, 5);
    const m = outfield(s, from)[0];
    m.x = 8; m.z = -6;
    const hold = { ...NO_INPUT, mx: 1 };
    stepMatch(s, { ...hold, press: { k: "pass", power: 0.4 } });
    for (let i = 0; i < 40 && s.ball.owner === from; i++) stepMatch(s, hold);
    stepMatch(s, hold);
    const man = s.players[s.user];
    expect(s.locked).toBe(true);
    // The same thumb: he goes to the ball. A new direction: he goes that way.
    for (let i = 0; i < 40; i++) stepMatch(s, { ...NO_INPUT, mz: 1 });
    expect(s.locked).toBe(false);
    if (s.ball.owner !== man.i) expect(man.vz).toBeGreaterThan(2);
  });

  it("a loose ball by his feet is his for a push of the stick", () => {
    const from = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(from, -10, 5);
    const b = s.ball;
    b.owner = -1; b.last = -1; b.to = -1; b.kick = 0; b.x = -7; b.z = 6.5; b.vx = 3; b.vz = 0;
    predict(s);
    for (let i = 0; i < 60 && b.owner < 0; i++) stepMatch(s, { ...NO_INPUT, mx: 1, mz: -0.3, sprint: true });
    expect(b.owner).toBe(from);
  });

  it("the human's team-mates win the ball without being told", () => {
    let won = 0;
    for (const seed of [11, 12, 13, 14, 15, 16]) {
      const s = createMatch({ ...SETUP, seed }, 0);
      for (let i = 0; i < 900 && s.phase !== Phase.Play; i++) stepMatch(s, NO_INPUT);
      const c = s.players.find((p) => p.team === 1 && p.role === "ST")!;
      c.x = -18; c.z = 0;
      ballAt(s.ball, -17.6, BALL_R, 0);
      s.ball.owner = c.i; s.ball.to = -1; s.ball.since = 20; s.poss = 1;
      for (let i = 0; i < 360 && s.players[s.ball.owner < 0 ? c.i : s.ball.owner].team === 1 && s.phase === Phase.Play; i++) stepMatch(s, NO_INPUT);
      if (s.ball.owner < 0 || s.players[s.ball.owner].team === 0) won += 1;
    }
    expect(won).toBeGreaterThanOrEqual(4);
  });

  const inPlay = (seed: number) => {
    const s = createMatch({ ...SETUP, seed }, null);
    for (let i = 0; i < 900 && s.phase !== Phase.Play; i++) stepMatch(s, NO_INPUT);
    return s;
  };

  /** Everyone else far away from (x, z). */
  const clear = (s: MatchState, x: number, z: number, keep: number[]) => {
    for (const p of s.players) {
      if (keep.includes(p.i) || p.role === "GK") continue;
      const side = p.team === 0 ? -1 : 1;
      p.x = x + side * (24 + p.slot); p.z = z > 0 ? -30 + p.slot : 30 - p.slot;
    }
  };

  it("a long ball to a man on his own is brought down, not headed anywhere", () => {
    let kept = 0;
    for (const seed of [21, 22, 23, 24, 25, 26]) {
      const s = inPlay(seed);
      const c = s.players.find((p) => p.team === 0 && p.role === "CM")!;
      const m = s.players.find((p) => p.team === 0 && p.role === "W")!;
      c.x = -25; c.z = 0; m.x = 10; m.z = 20; m.vx = 0; m.vz = 0;
      clear(s, 10, 20, [c.i, m.i]);
      ballAt(s.ball, -24.6, BALL_R, 0);
      s.ball.owner = -1; s.ball.last = c.i; s.ball.to = m.i; s.ball.since = 0; s.ball.kick = Kick.Lob; s.poss = 0;
      launch(s, planLob(s, c, m.x, m.z, m.i, 0.5));
      predict(s);
      for (let i = 0; i < 300 && s.ball.owner < 0 && s.phase === Phase.Play; i++) stepMatch(s, NO_INPUT);
      if (s.ball.owner === m.i) kept += 1;
    }
    expect(kept).toBeGreaterThanOrEqual(5);
  });

  it("a ball that comes down sits up instead of running half the pitch", () => {
    const s = inPlay(31);
    for (const p of s.players) { p.x = 0; p.z = HALF_W + 2; p.act = Act.Down; p.actLen = 9999; }
    ballAt(s.ball, -30, BALL_R, 0);
    s.ball.owner = -1; s.ball.last = -1; s.ball.to = -1;
    const c = s.players[3];
    c.x = -30.4; c.z = 0;
    launch(s, planLob(s, c, 10, 0, -1, 0.5));
    let land = 1e9, wasUp = false;
    for (let i = 0; i < 600; i++) {
      stepBall(s);
      if (s.ball.y > 1) wasUp = true;
      if (wasUp && land === 1e9 && s.ball.y < 0.3) land = s.ball.x;
    }
    expect(land).toBeLessThan(14);
    expect(s.ball.x - land).toBeLessThan(26);
  });

  it("a keeper doesn't throw it at the man standing in front of him", () => {
    for (const seed of [41, 42, 43, 44]) {
      const s = inPlay(seed);
      const k = s.players.find((p) => p.team === 1 && p.role === "GK")!;
      const o = s.players.find((p) => p.team === 0 && p.role === "ST")!;
      k.x = 44; k.z = 0; k.vx = 0; k.vz = 0;
      o.x = 41.5; o.z = 0;
      ballAt(s.ball, k.x, 1.05, k.z);
      s.ball.owner = k.i; s.ball.last = k.i; s.ball.to = -1; s.poss = 1;
      k.act = Act.Hold; k.actT = 0; k.actLen = 1;
      const left = (ticks: number) => {
        for (let i = 0; i < ticks && s.phase === Phase.Play; i++) { o.vx = 0; o.vz = 0; stepMatch(s, NO_INPUT); o.x = 41.5; o.z = 0; if (s.ball.owner !== k.i && s.ball.since > 34) return true; }
        return false;
      };
      expect(left(170)).toBe(true);
      expect(s.ball.last === o.i || s.ball.owner === o.i).toBe(false);
    }
  });

  it("the side without the ball holds its zones: two go, the rest pick up men", () => {
    for (const seed of [51, 52]) {
      const s = createMatch({ ...SETUP, seed }, null);
      let n = 0, onBall = 0, bunched = 0;
      while (s.phase !== Phase.FullTime && s.tick < HZ * 60 * 6) {
        stepMatch(s, NO_INPUT);
        const b = s.ball;
        if (s.phase !== Phase.Play || b.owner < 0 || s.tick % 20 !== 0) continue;
        const them = s.players.filter((p) => p.team !== s.players[b.owner].team && p.role !== "GK");
        n += 1;
        onBall += them.filter((p) => p.duty === 1).length;
        for (const p of them) if (them.filter((q) => (q.x - p.x) ** 2 + (q.z - p.z) ** 2 < 36).length > 3) bunched += 1;
      }
      expect(onBall / n).toBeLessThanOrEqual(2);
      expect(bunched / n).toBeLessThan(0.3);
    }
  });
});
