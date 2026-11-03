import { AIM_POST, aimSwipe, resolveShot } from "./aim";
import { FEINT_TICKS, ballOf, createEpisode, replayEpisode, shoot } from "./engine";
import { EpisodeRecorder } from "./recorder";

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

  it("the swipe keeps its power and height; the bend counts more for a thumb", () => {
    const rec = runFor(3, 40);
    // The swipe leant right, the stick left: the stick wins.
    const q = resolveShot(rec.state, { swipe: { dx: 400, dy: -220, curve: 0, durationMs: 180 }, aim: -1 });
    expect([q.dy, q.durationMs]).toEqual([-220, 180]);
    expect(launchX(rec, q)).toBeLessThan(-2);
    // (A bent shot launches off the aim on purpose and bends back onto it.)
    expect(resolveShot(rec.state, { swipe: { ...q, curve: 100 }, aim: -1 }).curve).toBeGreaterThan(100);
  });
});

describe("a tap shoots by itself", () => {
  it("low to the side the keeper leaves open", () => {
    const rec = runFor(11, 50);
    const s = rec.state;
    s.kx = 0.8; // he has gone to the right of the line
    const q = resolveShot(s, { auto: true });
    expect(launchX(rec, q)).toBeLessThan(-1);
    s.kx = -0.8;
    expect(launchX(rec, resolveShot(s, { auto: true }))).toBeGreaterThan(1);
  });

  it("over a keeper who came out onto him", () => {
    const rec = runFor(11, 50);
    const s = rec.state;
    const b = ballOf(s);
    Object.assign(s, { kx: b.x, kz: b.z - 2, kMode: "rush" });
    expect(resolveShot(s, { auto: true }).durationMs).toBeGreaterThan(400);
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
