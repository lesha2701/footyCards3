import { describe, expect, it } from "vitest";

import { SLIDE_LEN, planLob } from "./actions";
import { Act, BALL_R, FROM_SLIDE, HALF_W, HZ, Kick, MATCH_SECONDS, Phase, ballAt, dist, launch, predict, stepBall, type MatchState, type SceneOutcome } from "./core";
import { NO_INPUT, createMatch, sceneOf, stepMatch, type Input } from "./engine";

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
    // Over a few matches: one quiet match between two bots proves nothing.
    let shots = s.teams[0].shots + s.teams[1].shots;
    for (const seed of [71, 72, 73]) {
      const m = createMatch({ ...SETUP, seed }, null);
      while (m.phase !== Phase.FullTime && m.tick < HZ * 60 * 12) stepMatch(m, NO_INPUT);
      shots += m.teams[0].shots + m.teams[1].shots;
    }
    expect(shots).toBeGreaterThan(4);
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

  const waitForScene = (kind: "penalty" | "free", team: 0 | 1, x: number, z: number) => {
    const s = createMatch(SETUP, 0);
    for (let i = 0; i < 900 && s.phase !== Phase.Play; i++) stepMatch(s, NO_INPUT);
    const taker = s.players.find((p) => p.team === team && p.role === "ST")!;
    s.phase = Phase.Dead;
    s.ball.owner = -1;
    s.set = { kind, team, x, z, taker: taker.i, t: 0, ready: false, scene: -1 };
    if (team === 0) s.user = taker.i;
    for (let i = 0; i < 900 && !s.set?.ready; i++) stepMatch(s, NO_INPUT);
    return s;
  };
  const outcome = (s: MatchState, o: SceneOutcome | null) => stepMatch(s, { ...NO_INPUT, press: { k: "scene", outcome: o } });

  it("a penalty or a close free kick waits for the swipe scene and takes its outcome", () => {
    const s = waitForScene("penalty", 0, 41.5, 0);
    expect(sceneOf(s)).toMatchObject({ kind: "penalty" });
    const before = s.tick;
    for (let i = 0; i < 2000; i++) stepMatch(s, NO_INPUT);
    expect(s.phase).toBe(Phase.Dead);
    expect(s.tick).toBeGreaterThan(before);
    outcome(s, "goal");
    expect(s.phase).toBe(Phase.Goal);
    expect(s.teams[0].goals).toBe(1);
    expect(s.teams[0].onTarget).toBe(1);

    const f = waitForScene("free", 0, 30, -6);
    expect(sceneOf(f)).toMatchObject({ kind: "free", distance: 22.5, offset: -6 });
    outcome(f, "save");
    expect(f.phase).toBe(Phase.Play);
    expect(f.players[f.ball.owner].role).toBe("GK");
    expect(f.players[f.ball.owner].team).toBe(1);

    const m = waitForScene("free", 0, 30, 6);
    outcome(m, "miss");
    expect(m.set?.kind).toBe("goalkick");

    const w = waitForScene("free", 0, 30, 0);
    outcome(w, "wall");
    expect(w.phase).toBe(Phase.Play);
    expect(w.ball.owner).toBe(-1);
    expect(w.ball.x).toBeGreaterThan(30);
  });

  it("their penalty puts the human in goal, a far free kick stays in the match", () => {
    const k = waitForScene("penalty", 1, -41.5, 0);
    expect(sceneOf(k)).toMatchObject({ kind: "keep" });
    outcome(k, "save");
    expect(k.players[k.ball.owner].team).toBe(0);
    expect(sceneOf(waitForScene("free", 0, 5, 0))).toBeNull();
    expect(sceneOf(waitForScene("free", 1, -30, 0))).toBeNull();
  });

  it("a scene that fails leaves the kick to the match", () => {
    const s = waitForScene("penalty", 0, 41.5, 0);
    outcome(s, null);
    expect(sceneOf(s)).toBeNull();
    expect(s.phase).toBe(Phase.Dead);
    expect(s.set?.kind).toBe("penalty");
  });

  it("a tackle that wins it wins it: the man who stands still doesn't get it back", () => {
    const held: number[] = [];
    for (const seed of [61, 62, 63, 64]) {
      const s = createMatch({ ...SETUP, seed }, 0);
      let since = -1;
      while (s.phase !== Phase.FullTime && s.tick < HZ * 150) {
        stepMatch(s, NO_INPUT);
        const mine = s.phase === Phase.Play && s.ball.owner >= 0 && s.ball.owner === s.user;
        if (mine && since < 0) since = s.tick;
        else if (!mine && since >= 0) { held.push(s.tick - since); since = -1; }
      }
      if (since >= 0) held.push(s.tick - since);
    }
    expect(Math.max(...held)).toBeLessThan(HZ * 20);
  });

  it("a press with the ball on its way is played first time", () => {
    const from = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(from, -10, 5);
    const m = outfield(s, from)[0];
    m.x = 12; m.z = -6; m.vx = 0; m.vz = 0;
    clear(s, 12, -6, [from, m.i, ...outfield(s, from).slice(1, 3).map((p) => p.i)]);
    stepMatch(s, { ...NO_INPUT, press: { k: "pass", power: 0.5 } });
    for (let i = 0; i < 40 && s.ball.owner === from; i++) stepMatch(s, NO_INPUT);
    expect(s.ball.owner).toBe(-1);
    stepMatch(s, { ...NO_INPUT, mx: 1, press: { k: "pass", power: 0.5 } });
    expect(s.want?.k).toBe("pass");
    let passes = 0;
    for (let i = 0; i < 200 && s.phase === Phase.Play && !passes; i++) {
      stepMatch(s, NO_INPUT);
      if (s.ball.owner === s.user && s.players[s.user].act === Act.Kick) passes = 1;
    }
    expect(passes).toBe(1);
  });

  it("a feint on the ball starts a feint", () => {
    const from = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(from, -10, 5);
    stepMatch(s, { ...NO_INPUT, mx: 1, press: { k: "feint" } });
    expect(s.players[from].act).toBe(Act.Feint);
  });

  it("a keeper plays a back pass with his feet and can be the human's man", () => {
    const from = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(from, -30, 3);
    const k = s.players.find((p) => p.team === 0 && p.role === "GK")!;
    clear(s, 30, 0, [from]);
    k.x = -48; k.z = 0;
    for (let i = 0; i < 3; i++) stepMatch(s, NO_INPUT);
    const shots = s.teams[0].shots;
    stepMatch(s, { ...NO_INPUT, mx: -1, press: { k: "pass", power: 0.4 } });
    expect(s.ball.to === k.i || s.players[from].plan?.to === k.i).toBe(true);
    for (let i = 0; i < 240 && s.ball.owner !== k.i; i++) stepMatch(s, { ...NO_INPUT });
    expect(s.ball.owner).toBe(k.i);
    expect(k.act).not.toBe(Act.Hold);
    expect(k.act).not.toBe(Act.Dive);
    expect(s.user).toBe(k.i);
    // The stick still held back from the pass doesn't take it into his own net.
    for (let i = 0; i < 240; i++) stepMatch(s, { ...NO_INPUT, mx: -1, sprint: true });
    expect(s.teams[1].goals).toBe(0);
    expect(s.ball.owner).toBe(k.i);
    expect(s.ball.x).toBeGreaterThan(-52.5);
    // He runs with it and passes on, like anyone.
    for (let i = 0; i < 30; i++) stepMatch(s, { ...NO_INPUT, mx: 1 });
    expect(s.ball.owner).toBe(k.i);
    expect(k.vx).toBeGreaterThan(2);
    stepMatch(s, { ...NO_INPUT, mx: 1, press: { k: "pass", power: 0.4 } });
    for (let i = 0; i < 30 && s.ball.owner === k.i; i++) stepMatch(s, NO_INPUT);
    expect(s.ball.owner).toBe(-1);
    expect(s.teams[0].shots).toBe(shots);
  });

  it("a keeper stays on his feet while a long ball is still far from him", () => {
    const from = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(from, -20, 0);
    const k = s.players.find((p) => p.team === 1 && p.role === "GK")!;
    clear(s, -60, 0, [from]);
    const b = s.ball;
    b.owner = -1; b.last = from; b.kicker = from; b.kick = Kick.Clear; b.to = -1; b.since = 30;
    ballAt(b, 0, 0.5, 0);
    b.vx = 20; b.vy = 9; b.vz = 0.4;
    predict(s);
    let down = 0;
    for (let i = 0; i < 200 && s.phase === Phase.Play && s.ball.owner < 0; i++) {
      stepMatch(s, NO_INPUT);
      if (k.act === Act.Dive && dist(s.ball.x, s.ball.z, k.x, k.z) > 16) down += 1;
    }
    expect(down).toBe(0);
  });

  it("the ball rolls on from a touch, and its line bends when he turns", () => {
    const u = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(u, -20, 0);
    clear(s, 45, 25, [u]);
    let x = s.ball.x, z = s.ball.z, vx = 0, slowest = 1e9, jump = 0;
    const step = (mx: number, mz: number) => {
      stepMatch(s, { ...NO_INPUT, mx, mz, sprint: true });
      const dx = s.ball.x - x, dz = s.ball.z - z;
      x = s.ball.x; z = s.ball.z;
      return { dx, dz };
    };
    for (let i = 0; i < 40; i++) step(1, 0);
    for (let i = 0; i < 90; i++) {
      const { dx } = step(1, 0);
      slowest = Math.min(slowest, dx * HZ);
      // Nothing but a touch changes its pace, and a touch changes it by what a foot can.
      jump = Math.max(jump, Math.abs(dx * HZ - vx));
      vx = dx * HZ;
    }
    expect(s.ball.owner).toBe(u);
    expect(slowest).toBeGreaterThan(1.5);
    expect(jump).toBeLessThan(8.5);
    let widest = 0;
    for (let i = 0; i < 70; i++) {
      const { dx, dz } = step(-0.6, 0.8);
      widest = Math.max(widest, Math.sqrt(dx * dx + dz * dz));
    }
    expect(widest * HZ).toBeLessThan(15);
    expect(s.ball.owner).toBe(u);
    expect(dist(s.ball.x, s.ball.z, s.players[u].x, s.players[u].z)).toBeLessThan(2);
  });

  it("a corner cuts straight to everybody in place", () => {
    const from = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(from, 40, 20);
    const them = s.players.find((p) => p.team === 1 && p.role === "CB")!;
    const b = s.ball;
    b.owner = -1; b.last = them.i; b.kicker = them.i; b.kick = Kick.Clear; b.to = -1;
    ballAt(b, 53, 0.3, 20);
    b.vx = 4; b.vy = 0; b.vz = 0;
    predict(s);
    let cut = -1;
    for (let i = 0; i < 90 && !s.set?.ready; i++) {
      stepMatch(s, NO_INPUT);
      if (s.ev.some((e) => e.t === "cut")) cut = i;
    }
    expect(s.set?.kind).toBe("corner");
    expect(cut).toBeGreaterThan(0);
    expect(cut).toBeLessThan(60);
    expect(s.set?.ready).toBe(true);
    const t = s.players[s.set!.taker];
    expect(Math.abs(t.x)).toBeGreaterThan(50);
    expect(s.players.filter((p) => p.x > 30 && Math.abs(p.z) < 20).length).toBeGreaterThan(10);
  });

  /** A carrier of theirs jogging at x, the human's man `gap` metres goal-side of him. */
  const duel = (gap: number) => {
    const me = outfield(createMatch(SETUP, 0), -1)[0].i;
    const s = onBall(me, 0, 0);
    const c = s.players.find((p) => p.team === 1 && p.role === "CM")!;
    const u = s.players[me];
    clear(s, 40, 28, [me, c.i]);
    c.x = 0; c.z = 0; c.hx = -1; c.hz = 0; c.vx = -5; c.vz = 0; c.act = Act.None; c.cool = 0; c.plan = null;
    u.x = -gap; u.z = 0.3; u.hx = 1; u.hz = 0; u.vx = 0; u.vz = 0; u.act = Act.None; u.cool = 0;
    s.user = me;
    ballAt(s.ball, -0.5, BALL_R, 0);
    s.ball.owner = c.i; s.ball.last = c.i; s.ball.kick = Kick.None; s.ball.to = -1; s.ball.since = 90;
    return { s, u, c };
  };

  it("a tackle is a lunge at the ball, not a kick at the air on the spot", () => {
    const { s, u } = duel(2.2);
    const from = u.x;
    stepMatch(s, { ...NO_INPUT, press: { k: "tackle" } });
    expect(u.act).toBe(Act.Tackle);
    for (let i = 0; i < 8; i++) stepMatch(s, NO_INPUT);
    expect(u.x - from).toBeGreaterThan(0.3);
    expect(Math.sqrt(u.vx * u.vx + u.vz * u.vz)).toBeGreaterThan(4);
  });

  it("a tackle pressed from too far goes in as soon as he gets there", () => {
    const { s, u } = duel(6);
    stepMatch(s, { ...NO_INPUT, press: { k: "tackle" } });
    expect(u.act).toBe(Act.None);
    let went = false;
    for (let i = 0; i < 50 && !went; i++) {
      stepMatch(s, { ...NO_INPUT, mx: 1, mz: 0, sprint: true });
      went = u.act === Act.Tackle;
    }
    expect(went).toBe(true);
  });

  it("a slide goes along the ground, loses its pace there and he gets up from it", () => {
    const { s, u } = duel(3);
    u.vx = 7;
    stepMatch(s, { ...NO_INPUT, press: { k: "slide" } });
    expect(u.act).toBe(Act.Slide);
    const from = u.x;
    let down = 0;
    while (u.act === Act.Slide && down < 200) { stepMatch(s, NO_INPUT); down += 1; }
    expect(down).toBeGreaterThanOrEqual(SLIDE_LEN - 2);
    expect(u.x - from).toBeGreaterThan(2.5);
    if (u.act !== Act.None) {
      expect(u.act).toBe(Act.Getup);
      expect(u.sub).toBe(FROM_SLIDE);
    }
  });

  it("a ball hit as a man closes it down doesn't land at his feet", () => {
    let clean = 0, plays = 0;
    for (let n = 0; n < 24; n++) {
      const { s, u, c } = duel(1);
      c.vx = 0;
      const b = s.ball;
      b.owner = -1; b.last = c.i; b.kicker = c.i; b.kick = Kick.Pass; b.to = -1; b.since = 1;
      s.rng = (s.rng + n * 7919) | 0;
      ballAt(b, u.x + 1, BALL_R, u.z);
      b.vx = -10; b.vy = 0; b.vz = 0;
      predict(s);
      for (let i = 0; i < 8 && b.owner < 0; i++) stepMatch(s, NO_INPUT);
      plays += 1;
      if (b.owner === u.i) clean += 1;
    }
    expect(clean).toBeLessThan(plays / 2);
  });

  it("with the ball at their box the side has men in it", () => {
    let there = 0, samples = 0;
    for (const seed of [31, 32, 33, 34, 35, 36]) {
      const s = createMatch({ ...SETUP, seed }, null);
      while (s.phase !== Phase.FullTime && s.tick < HZ * 200) {
        stepMatch(s, NO_INPUT);
        if (s.phase !== Phase.Play || s.ball.owner < 0 || s.tick % 15) continue;
        const o = s.players[s.ball.owner], dir = o.team === 0 ? 1 : -1;
        if (o.x * dir < 28) continue;
        samples += 1;
        for (const m of s.players) if (m.team === o.team && m.i !== o.i && m.x * dir > 34 && Math.abs(m.z) < 22) there += 1;
      }
    }
    expect(samples).toBeGreaterThan(20);
    expect(there / samples).toBeGreaterThan(1);
  });

  it("a man running through the middle is met before the box, the line doesn't part for him", () => {
    for (const seed of [71, 72, 73]) {
      const s = createMatch({ ...SETUP, seed, }, 0);
      for (let i = 0; i < 900 && s.phase !== Phase.Play; i++) stepMatch(s, NO_INPUT);
      const me = s.players.find((p) => p.team === 0 && p.role === "CM")!;
      // Just won it in the middle: their midfield and forwards are behind him.
      for (const p of s.players) {
        if (p.team === 0 && p.i !== me.i) { p.x = -30 + p.i; p.vx = 0; p.vz = 0; }
        if (p.team === 1 && p.role !== "GK" && p.role !== "CB" && p.role !== "FB") { p.x = -8 - p.i * 0.5; p.vx = 0; p.vz = 0; }
        if (p.team === 1 && (p.role === "CB" || p.role === "FB")) { p.x = 30; p.vx = 0; p.vz = 0; }
      }
      me.x = 2; me.z = 0; me.vx = 7; me.vz = 0; me.hx = 1; me.hz = 0; me.act = Act.None;
      ballAt(s.ball, 2.5, BALL_R, 0);
      s.ball.owner = me.i; s.ball.last = me.i; s.ball.kick = Kick.None; s.ball.to = -1; s.ball.since = 30;
      s.user = me.i; s.poss = 0;
      predict(s);
      let met = 1e9;
      for (let i = 0; i < HZ * 7 && s.ball.owner === me.i && me.x < 37; i++) {
        stepMatch(s, { ...NO_INPUT, mx: 1, mz: 0, sprint: true });
        for (const o of s.players) {
          if (o.team === 1 && o.role !== "GK" && o.x > me.x - 0.5 && dist(o.x, o.z, me.x, me.z) < 2.5) met = Math.min(met, me.x);
        }
      }
      // Met, at the latest, at the edge of the box (x = 36).
      expect(met).toBeLessThan(36);
    }
  });

  it("the man on the ball keeps to a way, he doesn't weave", () => {
    const s = createMatch({ ...SETUP, seed: 88 }, null);
    let turns = 0, carried = 0, was = -1, ux = 0, uz = 0;
    while (s.phase !== Phase.FullTime && s.tick < HZ * 200) {
      stepMatch(s, NO_INPUT);
      const o = s.ball.owner >= 0 ? s.players[s.ball.owner] : null;
      if (!o || s.phase !== Phase.Play) { was = -1; continue; }
      if (o.i !== was) { was = o.i; ux = 0; uz = 0; }
      const v = Math.sqrt(o.vx * o.vx + o.vz * o.vz);
      if (v < 1) continue;
      carried += 1;
      if ((ux !== 0 || uz !== 0) && (ux * o.vx + uz * o.vz) / v < 0.5) turns += 1;
      ux = o.vx / v; uz = o.vz / v;
    }
    expect(carried).toBeGreaterThan(HZ * 10);
    expect(turns / (carried / (HZ * 10))).toBeLessThan(3);
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
