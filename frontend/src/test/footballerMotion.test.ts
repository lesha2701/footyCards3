import { describe, expect, it } from "vitest";

import type { CareerReplay } from "@/api/career";
import {
  DEFAULT_TIMING as T,
  BACKPEDAL_UP_TO,
  CELEBRATE_AFTER,
  poseTime,
  CATCH_WITHIN,
  RUN_FROM,
  SPRINT_FROM,
  backpedals,
  keeperMove,
  keeperSlot,
  motionAt,
  placeForStrike,
  playerAction,
  strikeWeight,
  strikes,
} from "@/lib/footballerMotion";
import { goalEpisodes } from "@/lib/goalReplay3d";
import { buildTimeline, type MatchEventLite } from "@/lib/matchReplay";

import fixture from "./__fixtures__/career_goal_replay.json";

const replay = fixture.replay as unknown as CareerReplay;
const events = fixture.events as MatchEventLite[];
const tl = buildTimeline(replay);
const episodes = goalEpisodes(tl, replay, events);

describe("footballer motion in a goal replay", () => {
  it("the scorer's foot meets the ball on the frame it leaves; a header peaks then", () => {
    for (const ep of episodes) {
      const act = playerAction(tl, replay, ep, ep.scorer!, ep.shot, false);
      if (ep.finish === "header") {
        expect(act).toEqual({ clip: "header", time: T.headerApex, speed: 1 });
      } else {
        expect(act).toEqual({ clip: "kick", time: T.kickContact, speed: 1, strike: ep.shot });
        // The run-up is shown before, the follow-through after.
        expect(playerAction(tl, replay, ep, ep.scorer!, ep.shot - 1, false).time).toBeCloseTo(T.kickContact - 0.5);
      }
    }
  });

  it("every pass of the build-up is a strike by the passer when the ball leaves him", () => {
    for (const ep of episodes) {
      for (const k of strikes(replay, ep).filter((s) => !s.shot)) {
        if (k.slot === keeperSlot(ep)) continue;
        expect(playerAction(tl, replay, ep, k.slot, k.frame, false)).toMatchObject({ clip: "kick", time: T.kickContact });
      }
    }
  });

  it("the beaten keeper's arms are out as the ball crosses the line, and he stays down", () => {
    for (const ep of episodes) {
      const k = keeperSlot(ep);
      const at = playerAction(tl, replay, ep, k, ep.goal, false);
      if (at.clip === "gk_catch") continue;
      expect(at.clip === "gk_dive_left" || at.clip === "gk_dive_right").toBe(true);
      expect(at.time).toBeCloseTo(T.diveReach);
      const later = playerAction(tl, replay, ep, k, ep.f1, false);
      expect(later.clip).toBe(at.clip);
      expect(later.time).toBeLessThanOrEqual(T.diveDuration);
      // Same answer in the mirrored view: the side is the keeper's own.
      expect(playerAction(tl, replay, ep, k, ep.goal, true).clip).toBe(at.clip);
    }
  });

  it("goals go past the keeper: he dives towards the ball, sideways by about where it crosses", () => {
    for (const ep of episodes) {
      if (ep.finish === "empty_net") continue;
      const move = keeperMove(tl, ep, false);
      expect(Math.abs(move.lateral)).toBeGreaterThanOrEqual(CATCH_WITHIN);
      expect(move.clip).toBe(move.lateral > 0 ? "gk_dive_left" : "gk_dive_right");
      expect(Math.hypot(move.left.x, move.left.z)).toBeCloseTo(1);
    }
  });

  it("players run, sprint or backpedal at their speed, or stand; the scorer's side celebrates after the goal", () => {
    const seen = new Set<string>();
    for (const ep of episodes) {
      for (let slot = 0; slot < 22; slot++) {
        for (const t of [ep.f0 + 0.5, (ep.f0 + ep.shot) / 2, ep.shot - 1]) {
          const act = playerAction(tl, replay, ep, slot, t, false);
          if (!["run", "sprint", "run_back", "idle", "gk_idle"].includes(act.clip)) continue;
          const m = motionAt(tl, slot, t, false);
          const keeper = slot === 0 || slot === 11;
          seen.add(act.clip);
          if (m.speed < RUN_FROM) {
            expect(act.clip).toBe(keeper ? "gk_idle" : "idle");
          } else if (!keeper && m.speed <= BACKPEDAL_UP_TO && backpedals(tl, ep, m, t, false)) {
            expect(act).toEqual({ clip: "run_back", time: null, speed: Math.max(0.6, Math.min(1.5, m.speed / T.backSpeed)) });
          } else if (m.speed >= SPRINT_FROM) {
            expect(act).toEqual({ clip: "sprint", time: null, speed: Math.max(0.75, Math.min(1.3, m.speed / T.sprintSpeed)) });
          } else {
            expect(act).toEqual({ clip: "run", time: null, speed: Math.max(0.45, Math.min(1.35, m.speed / T.runSpeed)) });
          }
        }
      }
      const mate = Array.from({ length: 22 }, (_, i) => i)
        .find((i) => (i < 11 ? "a" : "b") === ep.side && i !== 0 && i !== 11 && i !== ep.scorer)!;
      expect(["run", "sprint", "celebrate"]).toContain(playerAction(tl, replay, ep, mate, ep.f1, false).clip);
      // After CELEBRATE_AFTER frames the scorer stands in his victory pose,
      // arms already up, and the team-mates jump where they stopped.
      const scorer = playerAction(tl, replay, ep, ep.scorer!, ep.f1, false);
      expect(scorer.clip).toBe("victory");
      expect(scorer.time).toBeGreaterThanOrEqual(T.victoryFrom);
      expect(playerAction(tl, replay, ep, mate, ep.f1, false).clip).toBe("celebrate");
      expect(poseTime(ep, ep.scorer!, ep.f1)).toBe(ep.goal + CELEBRATE_AFTER);
      expect(poseTime(ep, keeperSlot(ep), ep.f1)).toBe(ep.f1);
    }
    expect(seen.has("run")).toBe(true);
    expect(seen.has("idle")).toBe(true);
  });

  it("a pass is struck the moment the ball leaves the passer's foot", () => {
    for (const ep of episodes) {
      for (const k of strikes(replay, ep).filter((x) => !x.shot)) {
        const pass = replay.passes.find(([p0, , from]) => p0 - 1 === k.frame && from === k.slot);
        expect(pass).toBeDefined();
      }
    }
  });

  it("at the contact the striking toe is on the ball, wherever the body was", () => {
    expect(strikeWeight(T.kickContact, T.kickContact)).toBe(1);
    expect(strikeWeight(T.kickContact - 1, T.kickContact)).toBe(0);
    expect(strikeWeight(T.kickContact + 1, T.kickContact)).toBe(0);
    const toe = { x: 0.2, z: 0.5 };
    const ball = { x: 10, z: -3 };
    for (const heading of [0, 0.7, -2, Math.PI]) {
      const body = placeForStrike({ x: 7, z: 1 }, heading, ball, toe, 1);
      const tx = toe.x * Math.cos(heading) + toe.z * Math.sin(heading);
      const tz = -toe.x * Math.sin(heading) + toe.z * Math.cos(heading);
      expect(body.x + tx).toBeCloseTo(ball.x);
      expect(body.z + tz).toBeCloseTo(ball.z);
      expect(placeForStrike({ x: 7, z: 1 }, heading, ball, toe, 0)).toEqual({ x: 7, z: 1 });
    }
  });

  it("is deterministic", () => {
    const ep = episodes[0];
    for (const t of [ep.f0, ep.shot - 0.3, ep.goal, ep.f1]) {
      expect(playerAction(tl, replay, ep, 5, t, false)).toEqual(playerAction(tl, replay, ep, 5, t, false));
    }
  });
});
