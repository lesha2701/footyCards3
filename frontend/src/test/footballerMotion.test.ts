import { describe, expect, it } from "vitest";

import type { CareerReplay } from "@/api/career";
import {
  DEFAULT_TIMING as T,
  RUN_AT,
  CATCH_WITHIN,
  RUN_FROM,
  keeperMove,
  keeperSlot,
  motionAt,
  playerAction,
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
        expect(act).toEqual({ clip: "wall_jump", time: T.jumpApex, speed: 1 });
      } else {
        expect(act).toEqual({ clip: "kick", time: T.kickContact, speed: 1 });
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

  it("players run at their speed or stand; the scorer's side celebrates after the goal", () => {
    let runs = 0;
    for (const ep of episodes) {
      for (let slot = 0; slot < 22; slot++) {
        const t = ep.f0 + 0.5;
        const act = playerAction(tl, replay, ep, slot, t, false);
        if (act.clip !== "run" && act.clip !== "idle" && act.clip !== "gk_idle") continue;
        const speed = motionAt(tl, slot, t, false).speed;
        if (speed >= RUN_FROM) {
          expect(act.clip).toBe("run");
          expect(act.speed).toBeCloseTo(Math.max(0.45, Math.min(1.35, speed / RUN_AT)));
          runs += 1;
        } else {
          expect(act.clip).toBe(slot === 0 || slot === 11 ? "gk_idle" : "idle");
        }
      }
      const mate = Array.from({ length: 22 }, (_, i) => i)
        .find((i) => (i < 11 ? "a" : "b") === ep.side && i !== 0 && i !== 11)!;
      const party = playerAction(tl, replay, ep, mate, ep.f1, false);
      expect(["run", "wall_jump"]).toContain(party.clip);
    }
    expect(runs).toBeGreaterThan(20);
  });

  it("is deterministic", () => {
    const ep = episodes[0];
    for (const t of [ep.f0, ep.shot - 0.3, ep.goal, ep.f1]) {
      expect(playerAction(tl, replay, ep, 5, t, false)).toEqual(playerAction(tl, replay, ep, 5, t, false));
    }
  });
});
