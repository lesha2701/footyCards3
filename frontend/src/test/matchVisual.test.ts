import { describe, expect, it } from "vitest";

import { KICKOFF_FRAME, currentFrame, frameForEvent, matchStats, pendingFrame, pressure } from "@/lib/matchVisual";
import type { MatchEvent } from "@/types";

const ev = (event_type: string, team: string, payload: Record<string, unknown> | null = null, minute = 10): MatchEvent => ({
  minute, event_type, team, description: "", payload,
});

describe("frameForEvent", () => {
  it("puts the user's goal in the right-hand net and the opponent's in the left", () => {
    const mine = frameForEvent(ev("goal", "user", { shot_type: "in_box" }), 0);
    const theirs = frameForEvent(ev("goal", "opponent", { shot_type: "in_box" }), 0);
    expect(mine.ball.x).toBeGreaterThan(95);
    expect(theirs.ball.x).toBeLessThan(5);
    expect(mine.goalSide).toBe("opponent");
    expect(theirs.goalSide).toBe("user");
    expect(mine.label).toBe("ГОЛ!");
  });

  it("starts long-range shots further from goal than in-box shots", () => {
    const inBox = frameForEvent(ev("shot", "user", { shot_type: "in_box" }), 0);
    const longRange = frameForEvent(ev("shot", "user", { shot_type: "long_range" }), 0);
    expect(longRange.from!.x).toBeLessThan(inBox.from!.x);
  });

  it("credits saves, blocks and tackles to the defending side", () => {
    expect(frameForEvent(ev("save", "opponent"), 0).tone).toBe("user");
    expect(frameForEvent(ev("blocked", "user"), 0).tone).toBe("opponent");
    const tackle = frameForEvent(ev("tackle_won", "opponent"), 0);
    expect(tackle.tone).toBe("user");
    // The tackle happens in the user's own half (the opponent was attacking left).
    expect(tackle.ball.x).toBeLessThan(50);
  });

  it("keeps the ball where it was for a booking", () => {
    const corner = frameForEvent(ev("corner", "user"), 0);
    const booked = frameForEvent(ev("yellow_card", "opponent"), 1, corner);
    expect(booked.ball).toEqual(corner.ball);
    expect(booked.label).toBe("Жёлтая");
    expect(booked.kind).toBe("card");
  });

  it("labels the foul with the card the defender received", () => {
    expect(frameForEvent(ev("foul_stopped", "opponent", { card: "red" }), 0).label).toBe("Фол · красная");
    expect(frameForEvent(ev("foul_stopped", "opponent", { card: "yellow" }), 0).label).toBe("Фол · жёлтая");
  });

  it("ignores events without a known side and unknown event types", () => {
    expect(frameForEvent(ev("goal", "Динамо"), 0).ball).toEqual(KICKOFF_FRAME.ball);
    const weird = frameForEvent(ev("something_new", "user"), 0);
    expect(weird.label).toBeNull();
    expect(weird.ball).toEqual(KICKOFF_FRAME.ball);
  });

  it("keeps every frame on the pitch", () => {
    const types = ["goal", "shot", "save", "blocked", "tackle_won", "foul_stopped", "pass_failed", "corner", "offside", "possession"];
    for (const team of ["user", "opponent"]) {
      types.forEach((t, i) => {
        const f = frameForEvent(ev(t, team, { shot_type: "long_range" }), i);
        expect(f.ball.x).toBeGreaterThanOrEqual(0);
        expect(f.ball.x).toBeLessThanOrEqual(100);
        expect(f.ball.y).toBeGreaterThanOrEqual(0);
        expect(f.ball.y).toBeLessThanOrEqual(60);
      });
    }
  });
});

describe("pendingFrame", () => {
  it("shows an opponent chance in the user's half and a user chance in theirs", () => {
    const threat = pendingFrame("opponent", "in_box", 0)!;
    const mine = pendingFrame("user", "long_range", 0)!;
    expect(threat.ball.x).toBeLessThan(30);
    expect(threat.label).toBe("Угроза!");
    expect(mine.ball.x).toBeGreaterThan(60);
    expect(mine.label).toBe("Твой момент");
    expect(pendingFrame("Динамо", "in_box", 0)).toBeNull();
  });
});

describe("currentFrame", () => {
  it("returns kickoff for an empty log and the latest frame otherwise", () => {
    expect(currentFrame([])).toBe(KICKOFF_FRAME);
    expect(currentFrame([ev("possession", "user"), ev("goal", "opponent")]).kind).toBe("goal");
  });
});

describe("pressure", () => {
  it("is 0 with no attacking events and moves toward the attacking side", () => {
    expect(pressure([])).toBe(0);
    expect(pressure([ev("yellow_card", "user")])).toBe(0);
    expect(pressure([ev("corner", "user"), ev("shot", "user")])).toBe(1);
    expect(pressure([ev("goal", "opponent")])).toBe(-1);
    const mixed = pressure([ev("possession", "user"), ev("shot", "opponent")]);
    expect(mixed).toBeLessThan(0);
    expect(mixed).toBeGreaterThan(-1);
  });

  it("only looks at the most recent window", () => {
    const old = Array.from({ length: 6 }, () => ev("goal", "opponent"));
    expect(pressure([...old, ev("possession", "user")], 1)).toBe(1);
  });
});

describe("matchStats", () => {
  it("counts shots, shots on target, corners and offsides per attacking side", () => {
    const s = matchStats([
      ev("goal", "user"), ev("save", "user"), ev("shot", "user"), ev("blocked", "user"),
      ev("shot", "opponent"), ev("corner", "user"), ev("offside", "opponent"),
    ]);
    expect(s.user).toMatchObject({ shots: 4, onTarget: 2, corners: 1 });
    expect(s.opponent).toMatchObject({ shots: 1, onTarget: 0, offsides: 1 });
  });

  it("credits tackles and foul bookings to the defending side", () => {
    const s = matchStats([
      ev("tackle_won", "opponent"),
      ev("foul_stopped", "opponent", { card: "yellow" }),
      ev("foul_stopped", "user", { card: "red" }),
      ev("yellow_card", "user"),
    ]);
    expect(s.user.tacklesWon).toBe(1);
    expect(s.user.yellow).toBe(2);
    expect(s.opponent.red).toBe(1);
  });
});
