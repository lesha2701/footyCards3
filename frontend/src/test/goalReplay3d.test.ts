import { describe, expect, it } from "vitest";

import type { CareerReplay } from "@/api/career";
import {
  BALL_R,
  CELEBRATION_FRAMES,
  CROSSBAR,
  GOAL_HALF,
  HEAD_H,
  VOLLEY_H,
  MAX_LEAD_FRAMES,
  SLOW_RATE,
  advance,
  ballState,
  cameraPose,
  episodeDuration,
  episodeRate,
  FPS_JUDGE,
  finishKind,
  goalEpisodes,
  isCross,
  judgeFps,
  toWorld,
  type GoalEpisode,
} from "@/lib/goalReplay3d";
import {
  DRIBBLE_ROLL,
  FOOT,
  PITCH_L,
  PITCH_W,
  buildTimeline,
  footBall,
  groundBall,
  holderAt,
  interpolatePlayer,
  rosterAt,
  type MatchEventLite,
} from "@/lib/matchReplay";

import fixture from "./__fixtures__/career_goal_replay.json";

// A real replay from backend career_replay_service.build_replay for a log
// with every kind of goal (tools/career-replay-3d/gen_fixture.py).
const replay = fixture.replay as unknown as CareerReplay;
const events = fixture.events as MatchEventLite[];
const tl = buildTimeline(replay);
const episodes = goalEpisodes(tl, replay, events);
const byFinish = (kind: GoalEpisode["finish"]) => episodes.find((ep) => ep.finish === kind)!;

function segmentAt(frame: number) {
  return replay.segments.find(([, f0, n]) => f0 <= frame && frame < f0 + n)!;
}

describe("goal episodes: frames", () => {
  it("one episode per goal of the log, in match order", () => {
    const goals = events.map((e, i) => (e.event_type === "goal" ? i : -1)).filter((i) => i >= 0);
    expect(episodes.map((ep) => ep.event)).toEqual(goals);
    expect(episodes.map((ep) => ep.finish)).toEqual(
      ["header", "long_range", "header", "free_kick", "penalty", "shot", "shot", "volley", "empty_net"],
    );
  });

  it("from the build-up of the goal segment to the goal plus the celebration", () => {
    for (const ep of episodes) {
      const mark = replay.marks.find(([, idx]) => idx === ep.event)![0];
      expect(ep.goal).toBe(mark);
      const seg = segmentAt(ep.goal);
      expect(seg[0]).toBe("goal");
      expect(ep.f0).toBeGreaterThanOrEqual(seg[1]);
      expect(ep.f1).toBeLessThan(seg[1] + seg[2]);
      expect(ep.goal - ep.f0).toBeLessThanOrEqual(MAX_LEAD_FRAMES);
      expect(ep.f1 - ep.goal).toBe(CELEBRATION_FRAMES);
      expect(ep.shot).toBe(ep.goal - 2);
      expect(ep.msPerFrame).toBe(500);
    }
  });

  it("two goals in one minute: the second starts after the first's celebration and kick-off", () => {
    const [first, second] = episodes.filter((ep) => ep.minute === 70);
    expect(segmentAt(first.goal)).toBe(segmentAt(second.goal));
    expect(first.f0).toBe(segmentAt(first.goal)[1]);
    expect(second.f0).toBeGreaterThan(first.f1);
    expect(second.side).toBe("b");
  });

  it("the scorer is the player on the ball when it is struck — the same as the log", () => {
    for (const ep of episodes) {
      expect(ep.scorer).toBe(holderAt(tl, ep.shot));
      const player = replay.players[rosterAt(replay, ep.shot)[ep.scorer!]];
      expect(player.s).toBe(ep.side);
      expect(player.name).toBe(events[ep.event].payload?.shooter);
    }
  });

  it("is deterministic", () => {
    expect(goalEpisodes(tl, replay, events)).toEqual(episodes);
  });
});

describe("goal episodes: the ball in 3D", () => {
  it("crosses the line between the posts and under the bar, then rests in the net", () => {
    for (const ep of episodes) {
      const line = ballState(tl, ep, ep.goal);
      expect(line.y).toBeCloseTo(ep.side === "a" ? PITCH_L : 0, 5);
      expect(Math.abs(line.x - PITCH_W / 2)).toBeLessThan(GOAL_HALF);
      expect(line.h).toBeGreaterThanOrEqual(BALL_R);
      expect(line.h).toBeLessThan(CROSSBAR - BALL_R);
      const rest = ballState(tl, ep, ep.f1);
      expect(ep.side === "a" ? rest.y > PITCH_L : rest.y < 0).toBe(true);
      expect(Math.abs(rest.x - PITCH_W / 2)).toBeLessThan(GOAL_HALF);
      expect(rest.h).toBe(BALL_R);
    }
  });

  it("a loose ball on the grass is exactly where the 2D key frames have it", () => {
    const inPass = (f: number) => replay.passes.some(([p0, p1]) => p0 - 1 <= f && f <= p1);
    for (const ep of episodes) {
      for (let f = ep.f0; f <= ep.goal; f++) {
        if (holderAt(tl, f) !== null || inPass(f)) continue;
        if (ep.flights.some((fl) => fl.f0 < f && f < fl.f1)) continue;
        const b = ballState(tl, ep, f);
        const raw = { x: (tl.bytes[f * tl.size] / 255) * PITCH_W, y: (tl.bytes[f * tl.size + 1] / 255) * PITCH_L };
        expect(b.x).toBeCloseTo(raw.x, 5);
        expect(b.y).toBeCloseTo(raw.y, 5);
      }
    }
  });

  it("a dribbled ball is ahead of the player, pushed on with touches; a pass arrives at the receiver's foot", () => {
    let held = 0;
    let received = 0;
    for (const ep of episodes) {
      for (let f = ep.f0; f < ep.shot; f++) {
        const h = holderAt(tl, f);
        if (h === null) continue;
        const next = holderAt(tl, f + 1);
        for (const frac of next === h ? [0, 0.25, 0.5, 0.75] : [0]) {
          const t = f + frac;
          const p = interpolatePlayer(tl, f, frac, h);
          const t2 = Math.min(tl.count - 1, t + 0.4);
          const q = interpolatePlayer(tl, Math.floor(t2), t2 - Math.floor(t2), h);
          const b = groundBall(tl, t);
          const gap = Math.hypot(b.x - p.x, b.y - p.y);
          expect(gap).toBeGreaterThanOrEqual(FOOT - 0.05);
          expect(gap).toBeLessThanOrEqual(FOOT + DRIBBLE_ROLL + 1e-6);
          // In front of him: along the way he runs, never between or behind his feet.
          if (Math.hypot(q.x - p.x, q.y - p.y) > 0.2) {
            expect((b.x - p.x) * (q.x - p.x) + (b.y - p.y) * (q.y - p.y)).toBeGreaterThan(0);
          }
          held += 1;
        }
        const prev = holderAt(tl, f - 1);
        if (prev !== h) {
          const before = groundBall(tl, f - 0.001);
          const at = footBall(tl, h, f);
          expect(Math.hypot(before.x - at.x, before.y - at.y)).toBeLessThan(0.2);
          received += 1;
        }
      }
    }
    expect(held).toBeGreaterThan(50);
    expect(received).toBeGreaterThan(5);
  });

  it("a pass is fast off the boot and slows as it rolls", () => {
    let checked = 0;
    for (const [p0, p1] of replay.passes) {
      const s = p0 - 1;
      const e = p1 - 1;
      if (s < 0 || e - s < 2) continue;
      const a = groundBall(tl, s);
      const m = groundBall(tl, (s + e) / 2);
      const z = groundBall(tl, e);
      const first = Math.hypot(m.x - a.x, m.y - a.y);
      const second = Math.hypot(z.x - m.x, z.y - m.y);
      if (first + second < 6) continue;
      expect(first).toBeGreaterThan(second);
      checked += 1;
    }
    expect(checked).toBeGreaterThan(5);
  });

  it("moves continuously — no teleports at flight boundaries", () => {
    for (const ep of episodes) {
      let prev = ballState(tl, ep, ep.f0);
      for (let t = ep.f0; t <= ep.f1; t += 0.05) {
        const b = ballState(tl, ep, t);
        expect(Math.hypot(b.x - prev.x, b.y - prev.y, b.h - prev.h)).toBeLessThan(1.6);
        expect(b.h).toBeGreaterThanOrEqual(BALL_R - 1e-9);
        prev = b;
      }
    }
  });

  it("headers meet the head after a lofted cross; free kicks clear the wall; empty net rolls", () => {
    const header = byFinish("header");
    expect(ballState(tl, header, header.shot).h).toBeCloseTo(HEAD_H);
    const cross = header.flights.find((fl) => fl.f1 === header.shot)!;
    expect(cross.from.h).toBe(BALL_R);
    expect(ballState(tl, header, (cross.f0 + cross.f1) / 2).h).toBeGreaterThan(2.5);

    const fk = byFinish("free_kick");
    const shot = fk.flights.find((fl) => fl.f0 === fk.shot)!;
    // The wall stands 9.15 m out: the ball is above head height there.
    const travel = Math.hypot(shot.to.x - shot.from.x, shot.to.y - shot.from.y);
    expect(ballState(tl, fk, fk.shot + (9.15 / travel) * (fk.goal - fk.shot)).h).toBeGreaterThan(1.9);

    const empty = byFinish("empty_net");
    for (let t = empty.shot; t <= empty.goal; t += 0.25) expect(ballState(tl, empty, t).h).toBeCloseTo(BALL_R);

    const pen = byFinish("penalty");
    expect(ballState(tl, pen, pen.shot).h).toBe(BALL_R);
  });

  it("a cross is in the air from the passer's foot to the scorer's head or foot", () => {
    const crosses = episodes.filter((ep) => isCross(events[ep.event]) || ep.finish === "header");
    expect(crosses.length).toBeGreaterThanOrEqual(3);
    for (const ep of crosses.filter((c) => c.finish === "header" || c.finish === "volley")) {
      const last = [...replay.passes].reverse().find(([p0, p1, , to]) => p0 >= ep.f0 && p1 <= ep.shot && to === ep.scorer)!;
      const flight = ep.flights.find((fl) => fl.f1 === ep.shot)!;
      // Leaves the grass the moment the pass is played, no run along the ground first.
      expect(flight.f0).toBe(last[0]);
      expect(flight.from.h).toBe(BALL_R);
      expect(flight.to.h).toBe(ep.finish === "header" ? HEAD_H : VOLLEY_H);
      expect(ballState(tl, ep, (flight.f0 + flight.f1) / 2).h).toBeGreaterThan(2.5);
    }
  });

  it("finish kind from the event payload", () => {
    expect(finishKind({ minute: 1, event_type: "goal", payload: { is_penalty: true, set_piece: "penalty" } })).toBe("penalty");
    expect(finishKind({ minute: 1, event_type: "goal", payload: { set_piece: "corner", action: "header" } })).toBe("header");
    expect(finishKind({ minute: 1, event_type: "goal", payload: { shot_type: "in_box", aerial_duel: {} } })).toBe("header");
    expect(finishKind({ minute: 1, event_type: "goal", payload: { shot_type: "in_box" } })).toBe("shot");
    // A cross from the wing is finished in the air: headed or volleyed, by event.
    const cross = { minute: 1, event_type: "goal", payload: { shot_type: "in_box", zone: "wing_attack", assist: "X" } };
    const kinds = new Set(Array.from({ length: 30 }, (_, i) => finishKind(cross, i)));
    expect(kinds).toEqual(new Set(["header", "volley"]));
    expect(finishKind(cross, 4)).toBe(finishKind(cross, 4));
    expect(finishKind({ ...cross, payload: { shot_type: "in_box", zone: "central_attack", assist: "X" } }, 4)).toBe("shot");
    expect(finishKind({ minute: 1, event_type: "goal" })).toBe("shot");
  });
});

describe("goal episodes: playback and camera", () => {
  const ep = episodes[0];

  it("slows down for the strike and stops at the end", () => {
    expect(episodeRate(ep, ep.f0)).toBe(1);
    expect(episodeRate(ep, ep.shot)).toBe(SLOW_RATE);
    expect(episodeRate(ep, ep.goal + 0.5)).toBe(SLOW_RATE);
    expect(advance(ep, ep.f0, 500)).toBeCloseTo(ep.f0 + 1);
    expect(advance(ep, ep.shot, 500)).toBeCloseTo(ep.shot + SLOW_RATE);
    expect(advance(ep, ep.f1 - 0.1, 5000)).toBe(ep.f1);
    const plain = (ep.f1 - ep.f0) * ep.msPerFrame;
    expect(episodeDuration(ep)).toBeGreaterThan(plain);
    expect(episodeDuration(ep)).toBeLessThan(plain * 2.5);
  });

  it("world coordinates put the viewer's attack towards +X", () => {
    expect(toWorld({ x: PITCH_W / 2, y: PITCH_L }, false)).toEqual({ x: PITCH_L / 2, z: 0 });
    expect(toWorld({ x: PITCH_W / 2, y: PITCH_L }, true)).toEqual({ x: -PITCH_L / 2, z: 0 });
    expect(toWorld({ x: 0, y: 0 }, true)).toEqual({ x: PITCH_L / 2, z: PITCH_W / 2 });
  });

  it("cameras: TV from the touchline, behind the attacked goal, from above", () => {
    const tv = cameraPose("tv", 10, 5, 52.5, false);
    expect(tv.pos[2]).toBeGreaterThan(PITCH_W / 2);
    expect(tv.pos[0]).toBe(10);
    const goal = cameraPose("goal", 40, 0, 52.5, false);
    expect(goal.pos[0]).toBeGreaterThan(52.5 + 1.8); // behind the net
    expect(cameraPose("goal", -40, 0, -52.5, false).pos[0]).toBeLessThan(-52.5);
    const top = cameraPose("top", 0, 0, 52.5, true);
    expect(top.pos[1]).toBeGreaterThan(40);
  });
});

describe("fps judge", () => {
  const on = { dpr: 1.5, ready: true, visible: true };
  const run = (fpsList: number[], opts = on) => {
    let s = FPS_JUDGE;
    const actions: string[] = [];
    for (const fps of fpsList) {
      const v = judgeFps(s, fps, opts);
      s = v.state;
      actions.push(v.action);
    }
    return actions;
  };

  it("ignores loading, hidden pages and the first two windows", () => {
    expect(run([10, 10, 10], { ...on, ready: false })).toEqual(["none", "none", "none"]);
    expect(run([10, 10, 10], { ...on, visible: false })).toEqual(["none", "none", "none"]);
    expect(run([10, 10])).toEqual(["none", "none"]);
  });

  it("first the pixel ratio, then the models after two slow windows running; a fast phone keeps both", () => {
    expect(run([10, 10, 45, 35, 45, 35, 35])).toEqual(["none", "none", "dpr", "none", "none", "none", "simple"]);
    expect(run([120, 120, 120, 120, 120])).toEqual(["none", "none", "none", "none", "none"]);
  });
});
