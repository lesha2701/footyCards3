import { describe, expect, it } from "vitest";

import { bossOf, createGame, step, waveList, type Fighter, type Input, type State } from "@/lib/zames/engine";
import { classifySwipe } from "@/lib/zames/gestures";

/** A greedy autopilot: walks to the nearest rival and mixes punches, kicks, spins. */
function autopilot(s: State, frame: number): Input[] {
  const target = s.enemies.find((e) => !e.ko && !e.out && !e.entering);
  if (!target || frame % 9 !== 0) return [];
  const roll = (frame / 9) % 7;
  if (s.rage >= 100) return [{ k: "rage" }];
  if (roll === 3) return [{ k: "kick", dir: target.x >= s.hero.x ? 1 : -1 }];
  if (roll === 5) return [{ k: "spin" }];
  return [{ k: "tap", x: target.x, z: target.z, target: target.id }];
}

function play(seed: number, mode: "derby" | "endless", seconds: number): State {
  const s = createGame(mode, seed);
  for (let f = 0; f < seconds * 60 && !s.finished; f++) {
    step(s, 1 / 60, autopilot(s, f));
    s.events.length = 0;
  }
  return s;
}

describe("zames engine", () => {
  it("is deterministic for a seed and inputs", () => {
    const a = play(7, "derby", 40);
    const b = play(7, "derby", 40);
    expect(a.knockouts).toBe(b.knockouts);
    expect(a.hero.hp).toBe(b.hero.hp);
    expect(a.wave).toBe(b.wave);
  });

  it("an active fighter clears waves and counts knockouts", () => {
    const s = play(11, "derby", 120);
    expect(s.wavesCleared).toBeGreaterThanOrEqual(2);
    expect(s.knockouts).toBeGreaterThanOrEqual(8);
    expect(s.bestCombo).toBeGreaterThan(2);
  });

  it("a fan who never fights back gets knocked out", () => {
    const s = createGame("endless", 3);
    for (let f = 0; f < 60 * 120 && !s.finished; f++) step(s, 1 / 60, []);
    expect(s.finished).toBe(true);
    expect(s.won).toBe(false);
    expect(s.hero.hp).toBe(0);
  });

  it("the derby ends with the boss, endless waves keep growing", () => {
    expect(waveList("derby", 6)).toContain("boss");
    expect(waveList("endless", 12).length).toBeGreaterThan(waveList("endless", 2).length);
    expect(waveList("endless", 6)[0]).toBe("boss");
  });

  it("blocking in front takes only chip damage", () => {
    const s = createGame("derby", 5);
    for (let f = 0; f < 60 * 3; f++) step(s, 1 / 60, []); // rivals walk in
    const hp0 = s.hero.hp;
    step(s, 1 / 60, [{ k: "hold" }]);
    for (let f = 0; f < 60 * 6; f++) {
      const near = s.enemies.find((e) => !e.ko);
      if (near) s.hero.face = near.x >= s.hero.x ? 1 : -1;
      step(s, 1 / 60, []);
    }
    expect(s.hero.act).toBe("block");
    expect(hp0 - s.hero.hp).toBeLessThan(15);
  });
});

/** One rival put straight into the arena, no waves around it. */
function lone(s: State, kind: Fighter["kind"], x: number, hp: number, scale: number): Fighter {
  s.pause = 999;
  const e: Fighter = {
    ...s.hero, id: 99, kind, x, act: "idle", entering: false, cool: 0, scale, maxHp: hp, hp, hit: [],
    face: x > s.hero.x ? -1 : 1,
  };
  s.enemies.push(e);
  return e;
}

describe("zames throwers", () => {
  it("a spit hurts a hero standing still", () => {
    const s = createGame("endless", 9);
    lone(s, "kuzmich", 20, 30, 0.95);
    const hp0 = s.hero.hp;
    for (let f = 0; f < 60 * 3; f++) step(s, 1 / 60, []);
    expect(s.hero.hp).toBeLessThan(hp0);
  });

  it("a kick sends the seat back into the thrower", () => {
    const s = createGame("endless", 9);
    const e = lone(s, "chair", s.hero.x + 24, 45, 1.05);
    let deflected = false;
    for (let f = 0; f < 60 * 4 && !deflected; f++) {
      const shot = s.shots[0];
      const kick = shot && !shot.mine && Math.abs(shot.x - s.hero.x) < 11 && s.hero.act === "idle";
      step(s, 1 / 60, kick ? [{ k: "kick", dir: 1 }] : []);
      deflected = s.events.some((ev) => ev.t === "deflect");
      s.events.length = 0;
    }
    expect(deflected).toBe(true);
    for (let f = 0; f < 60 * 2; f++) step(s, 1 / 60, []);
    expect(e.hp).toBeLessThan(45);
  });

  it("derby and endless bring the new rivals and Синяк", () => {
    expect(waveList("derby", 3)).toContain("kuzmich");
    expect(waveList("derby", 4)).toContain("chair");
    expect(bossOf({ mode: "endless", seed: 1, wave: 6 })).toBe("sinyak");
    expect(bossOf({ mode: "endless", seed: 1, wave: 12 })).toBe("boss");
  });
});

describe("zames gestures", () => {
  const line = (dx: number, dy: number) => Array.from({ length: 10 }, (_, i) => ({ x: 100 + (dx * i) / 9, y: 300 + (dy * i) / 9 }));
  it("reads swipes and circles", () => {
    expect(classifySwipe(line(120, 10))).toEqual({ k: "kick", dir: 1 });
    expect(classifySwipe(line(-90, -20))).toEqual({ k: "kick", dir: -1 });
    expect(classifySwipe(line(5, -100))).toEqual({ k: "spin" });
    expect(classifySwipe(line(0, 100))).toEqual({ k: "sweep" });
    const circle = Array.from({ length: 30 }, (_, i) => ({
      x: 200 + 50 * Math.cos((i / 29) * Math.PI * 2), y: 300 + 50 * Math.sin((i / 29) * Math.PI * 2),
    }));
    expect(classifySwipe(circle)).toEqual({ k: "spin" });
    expect(classifySwipe(line(10, 5))).toBeNull();
  });
});
