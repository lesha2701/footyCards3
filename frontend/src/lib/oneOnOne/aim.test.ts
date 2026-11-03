import { GOAL_HEIGHT } from "@/lib/freeKick3d/trajectory";

import { AIM_POST, aimSwipe, driveHeight, finesseBend, resolveShot, type ShotIntent } from "./aim";
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

/** Moves him across so the ball is `x` off the middle. */
function placeAt(rec: EpisodeRecorder, x: number) {
  rec.state.x += x - ballOf(rec.state).x;
  return rec;
}

/** Where the kick's launch line crosses the goal line. */
function launchX(rec: EpisodeRecorder, q: typeof DRIVE) {
  const f = shoot(rec.setup, rec.state, q);
  const v = f.kick.velocity;
  return f.from.x + v.x * (-f.from.z / v.z);
}

/** The flight with the keeper out of the way: how high and where it crosses
 * the line, how hard it left. */
function flyClear(rec: EpisodeRecorder, intent: ShotIntent) {
  rec.state.kx = 30;
  const q = resolveShot(rec.setup, rec.state, intent);
  const f = shoot(rec.setup, rec.state, q, 1);
  const v = f.kick.velocity;
  const at = f.samples.find((p) => p.ball.z <= 0.05) ?? f.samples[f.samples.length - 1];
  return { cross: at.ball.y, x: at.ball.x, speed: Math.hypot(v.x, v.y, v.z), outcome: f.outcome, q };
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
});

describe("the drive: the power bar", () => {
  it("harder is higher — low, then the top corner, then over the bar", () => {
    const at = (power: number) => flyClear(runFor(5, 45), { kind: "drive", power, aim: 0.7 });
    const soft = at(0.15);
    const top = at(0.88);
    const over = at(1);
    expect(soft.cross).toBeLessThan(0.8);
    expect(top.cross).toBeGreaterThan(1.7);
    expect(top.cross).toBeLessThan(GOAL_HEIGHT - 0.1);
    expect(top.outcome).toBe("goal");
    // Too much: off the bar or over it.
    expect(over.outcome).not.toBe("goal");
    expect(top.speed).toBeGreaterThan(soft.speed + 6);
    expect(driveHeight(0.5)).toBeLessThan(driveHeight(0.9));
  });

  it("never over the bar below the top of the bar, from any distance", () => {
    for (const ticks of [20, 50, 80]) {
      for (const power of [0, 0.3, 0.6, 0.85]) {
        expect(flyClear(runFor(5, ticks), { kind: "drive", power, aim: -0.8 }).cross).toBeLessThan(GOAL_HEIGHT - 0.2);
      }
    }
  });

  it("is struck with the laces into either corner", () => {
    const kindOf = (aim: number, power: number) => {
      const rec = runFor(9, 45);
      rec.step(1, 0, 0, { kind: "drive", power, aim });
      return techniqueOf(rec.state, rec.timeline)!.kind;
    };
    expect(kindOf(-1, 0.5)).toBe("instep");
    expect(kindOf(1, 0.5)).toBe("instep");
    expect(kindOf(-1, 0)).toBe("instep");
  });
});

describe("the finesse: a swipe off the button", () => {
  const SWIPE = { dx: 0, dy: -180, curve: 0, durationMs: 110 };

  it("bends into the far corner away from the keeper, in from outside the near post", () => {
    const s = placeAt(runFor(5, 45), 0).state;
    // From the middle: the left corner bends left, the right corner right.
    expect(finesseBend(s, -AIM_POST)).toBe(1);
    expect(finesseBend(s, AIM_POST)).toBe(-1);
    // Out on the left, the left post is the near one: in from outside it.
    s.x -= 2;
    expect(finesseBend(s, -AIM_POST)).toBe(-1);
    expect(finesseBend(s, AIM_POST)).toBe(-1);
  });

  it("lands on the aim, under the bar, curled with the inside (or the outside)", () => {
    const fin = flyClear(placeAt(runFor(5, 45), 0), { kind: "finesse", swipe: SWIPE, aim: -1 });
    expect(fin.q.curve).toBeGreaterThan(0);
    expect(fin.cross).toBeLessThan(GOAL_HEIGHT - 0.2);
    expect(fin.x).toBeLessThan(-1.8);
    const kindOf = (steer: number, ticks: number, x: number) => {
      const rec = placeAt(runFor(9, ticks, steer), x);
      rec.step(1, 0, 0, { kind: "finesse", swipe: SWIPE, aim: -1 });
      return techniqueOf(rec.state, rec.timeline)!;
    };
    expect(kindOf(0, 45, 0)).toEqual({ foot: "right", kind: "curl" });
    // Out on the left into the near post, wrapped in from outside it: the
    // right foot's outside, or the left's inside when he is cutting left.
    expect(kindOf(0, 45, -2)).toEqual({ foot: "right", kind: "outside" });
    expect(kindOf(-600, 60, -2)).toEqual({ foot: "left", kind: "curl" });
  });
});

describe("the chip button", () => {
  it("lifts it over a keeper who came out", () => {
    let over = 0;
    for (let seed = 1; seed <= 60; seed++) {
      const rec = new EpisodeRecorder(createEpisode(seed, 80));
      let shot = false;
      while (!rec.state.ended) {
        const s = rec.state;
        const b = ballOf(s);
        const go = !shot && Math.hypot(b.x - s.kx, b.z - s.kz) < 6;
        if (go) shot = true;
        rec.step(1, 0, 0, go ? { kind: "chip", power: 0.4, aim: 0 } : null);
      }
      if (rec.state.ended!.chip) over++;
    }
    expect(over).toBeGreaterThan(0);
  });
});

describe("a tap shoots by itself", () => {
  it("low to the side the keeper leaves open", () => {
    const rec = runFor(11, 50);
    const s = rec.state;
    s.kx = 0.8; // he has gone to the right of the line
    expect(launchX(rec, resolveShot(rec.setup, s, { kind: "auto" }))).toBeLessThan(-1);
    s.kx = -0.8;
    expect(launchX(rec, resolveShot(rec.setup, s, { kind: "auto" }))).toBeGreaterThan(1);
  });

  it("over a keeper who came out onto him", () => {
    const rec = runFor(11, 50);
    const s = rec.state;
    const b = ballOf(s);
    Object.assign(s, { kx: b.x, kz: b.z - 2, kMode: "rush" });
    expect(resolveShot(rec.setup, s, { kind: "auto" }).durationMs).toBeGreaterThan(400);
  });
});

describe("the recorder writes an aim down as a plain swipe", () => {
  it("resolved where the shot is played — after a feint, from where it left the ball", () => {
    const rec = new EpisodeRecorder(createEpisode(21, 80));
    for (let i = 0; i < 60; i++) rec.step(1, 0);
    rec.step(1, 0, 1);
    rec.step(1, 0, 0, { kind: "drive", power: 0.5, aim: 1 });
    while (!rec.state.ended) rec.step(1, 0);
    const tl = rec.timeline;
    expect(tl.shot!.tick).toBe(tl.feint!.tick + FEINT_TICKS);
    expect(tl.shot!.dx).not.toBe(0);
    const replay = replayEpisode(createEpisode(21, 80), tl);
    expect([replay.outcome, replay.tick]).toEqual([rec.state.ended!.outcome, rec.state.ended!.tick]);
  });
});
