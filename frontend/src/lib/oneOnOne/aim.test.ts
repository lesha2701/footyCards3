import { AIM_POST, aimSwipe, resolveShot } from "./aim";
import { GOAL_HEIGHT } from "@/lib/freeKick3d/trajectory";

import { FEINT_TICKS, ballOf, createEpisode, replayEpisode, shoot } from "./engine";
import { EpisodeRecorder } from "./recorder";
import { techniqueOf } from "./technique";

const DRIVE = { dx: 0, dy: -150, curve: 0, durationMs: 140 };

/** Runs straight for `ticks` (sideways by `steer`). */
function runFor(seed: number, ticks: number, steer = 0) {
  const rec = new EpisodeRecorder(createEpisode(seed, 80));
  for (let i = 0; i < ticks; i++) rec.step(1, steer);
  return rec;
}

/** Where the kick's launch line crosses the goal line. */
function launchX(rec: EpisodeRecorder, q: typeof DRIVE) {
  const f = shoot(rec.setup, rec.state, q);
  const v = f.kick.velocity;
  return f.from.x + v.x * (-f.from.z / v.z);
}

describe("the stick aims the shot", () => {
  it("its lean picks the spot across the goal from wherever the ball is", () => {
    for (const [ticks, steer] of [[40, 0], [70, 300], [90, -400]] as const) {
      const rec = runFor(7, ticks, steer);
      expect(ballOf(rec.state).z).toBeGreaterThan(3);
      for (const tx of [-AIM_POST, 0, 1.5, AIM_POST]) {
        expect(launchX(rec, aimSwipe(rec.state, tx, DRIVE))).toBeCloseTo(tx, 0);
      }
    }
  });

  it("the stick wins over the swipe's own lean; the bend counts more for a thumb", () => {
    const rec = runFor(3, 40);
    // The swipe leant right, the stick left: the stick wins.
    const q = resolveShot(rec.setup, rec.state, { swipe: { dx: 400, dy: -220, curve: 0, durationMs: 180 }, aim: -1 });
    expect(launchX(rec, q)).toBeLessThan(-2);
    // (A bent shot launches off the aim on purpose and bends back onto it.)
    expect(resolveShot(rec.setup, rec.state, { swipe: { ...q, curve: 100 }, aim: -1 }).curve).toBeGreaterThan(100);
  });
});

describe("the thumb's swipe on its own scale", () => {
  /** The flight with the keeper out of the way: how high it crosses the line, how hard it left. */
  function strikeOf(seed: number, ticks: number, swipe: typeof DRIVE, aim = 0.6) {
    const rec = runFor(seed, ticks);
    rec.state.kx = 30;
    const q = resolveShot(rec.setup, rec.state, { swipe, aim });
    const f = shoot(rec.setup, rec.state, q);
    const v = f.kick.velocity;
    const at = f.samples.find((p) => p.ball.z <= 0.3) ?? f.samples[f.samples.length - 1];
    return { cross: at.ball.y, speed: Math.hypot(v.x, v.y, v.z), outcome: f.outcome };
  }
  const swipes = [0.08, 0.15, 0.25, 0.4].flatMap((up) => [90, 150, 250].map((ms) => ({ dx: 0, dy: -up * 1000, curve: 0, durationMs: ms })));

  it("however long and quick the swipe, a straight shot stays under the bar", () => {
    for (const ticks of [20, 50, 80]) {
      for (const sw of swipes) {
        if (-sw.dy / sw.durationMs < 0.6 && -sw.dy >= 150) continue; // the chip
        const { cross } = strikeOf(5, ticks, sw);
        expect(cross).toBeLessThan(GOAL_HEIGHT - 0.2);
      }
    }
  });

  it("a quick flick is a drive, a calm one placed; longer goes higher", () => {
    const hard = strikeOf(5, 40, { dx: 0, dy: -200, curve: 0, durationMs: 80 });
    const calm = strikeOf(5, 40, { dx: 0, dy: -200, curve: 0, durationMs: 220 });
    expect(hard.speed).toBeGreaterThan(28);
    expect(calm.speed).toBeLessThan(24);
    const low = strikeOf(5, 40, { dx: 0, dy: -70, curve: 0, durationMs: 50 });
    const high = strikeOf(5, 40, { dx: 0, dy: -300, curve: 0, durationMs: 150 });
    expect(low.cross).toBeLessThan(0.7);
    expect(high.cross).toBeGreaterThan(1.5);
    expect(high.outcome).toBe("goal");
  });
});

describe("how the aimed shot looks", () => {
  it("a quick flick into either corner is struck with the laces; a calm one is placed", () => {
    const kindOf = (aim: number, durationMs: number) => {
      const rec = runFor(9, 45);
      rec.step(1, 0, 0, { swipe: { dx: 0, dy: -180, curve: 0, durationMs }, aim });
      return techniqueOf(rec.state, rec.timeline)!.kind;
    };
    expect(kindOf(-1, 70)).toBe("instep");
    expect(kindOf(1, 70)).toBe("instep");
    expect(kindOf(-1, 260)).toBe("side");
  });
});

describe("a tap shoots by itself", () => {
  it("low to the side the keeper leaves open", () => {
    const rec = runFor(11, 50);
    const s = rec.state;
    s.kx = 0.8; // he has gone to the right of the line
    const q = resolveShot(rec.setup, s, { auto: true });
    expect(launchX(rec, q)).toBeLessThan(-1);
    s.kx = -0.8;
    expect(launchX(rec, resolveShot(rec.setup, s, { auto: true }))).toBeGreaterThan(1);
  });

  it("over a keeper who came out onto him", () => {
    const rec = runFor(11, 50);
    const s = rec.state;
    const b = ballOf(s);
    Object.assign(s, { kx: b.x, kz: b.z - 2, kMode: "rush" });
    expect(resolveShot(rec.setup, s, { auto: true }).durationMs).toBeGreaterThan(400);
  });
});

describe("the recorder writes an aim down as a plain swipe", () => {
  it("resolved where the shot is played — after a feint, from where it left the ball", () => {
    const rec = new EpisodeRecorder(createEpisode(21, 80));
    for (let i = 0; i < 60; i++) rec.step(1, 0);
    rec.step(1, 0, 1);
    rec.step(1, 0, 0, { swipe: DRIVE, aim: 1 });
    while (!rec.state.ended) rec.step(1, 0);
    const tl = rec.timeline;
    expect(tl.shot!.tick).toBe(tl.feint!.tick + FEINT_TICKS);
    expect(tl.shot!.dx).not.toBe(0);
    const replay = replayEpisode(createEpisode(21, 80), tl);
    expect([replay.outcome, replay.tick]).toEqual([rec.state.ended!.outcome, rec.state.ended!.tick]);
  });
});
