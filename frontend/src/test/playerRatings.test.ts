import { describe, expect, it } from "vitest";

import type { CareerReplay } from "@/api/career";
import type { MatchEventLite } from "@/lib/matchReplay";
import { manOfTheMatch, matchRatings, ratingTone } from "@/lib/playerRatings";

const players = [
  ...["GK", "DEF1", "DEF2", "DEF3", "DEF4", "MID1", "MID2", "MID3", "FWD1", "FWD2", "FWD3"].map((slot, i) => ({ s: "a" as const, n: i + 1, name: `A${i}`, slot, id: i })),
  ...["GK", "DEF1", "DEF2", "DEF3", "DEF4", "MID1", "MID2", "MID3", "FWD1", "FWD2", "FWD3"].map((slot, i) => ({ s: "b" as const, n: i + 1, name: `B${i}`, slot, id: 100 + i })),
  { s: "a" as const, n: 12, name: "Запасной", slot: "FWD3", id: 50 },
];
const replay = { players, roster: Array.from({ length: 22 }, (_, i) => i), swaps: [[40, 10, 22]] } as unknown as CareerReplay;
const ev = (event_type: string, team: string, payload: Record<string, unknown>): MatchEventLite => ({ minute: 10, event_type, team, payload });

describe("match ratings", () => {
  const events = [
    ev("goal", "a", { shooter: "A8", assist: "A6", shot_type: "in_box" }),
    ev("goal", "a", { shooter: "A8", shot_type: "long_range" }),
    ev("save", "b", { shooter: "B9" }),
    ev("save", "b", { shooter: "B9" }),
    ev("tackle_won", "a", { defender: "A2" }),
    ev("foul_stopped", "b", { defender: "B1", card: "yellow" }),
  ];
  const ratings = matchRatings(replay, events, [2, 0]);
  const of = (name: string) => ratings.find((r) => r.name === name)!;

  it("goals, assists, saves, tackles, cards, clean sheet and the result", () => {
    expect(of("A8")).toMatchObject({ goals: 2, assists: 0, rating: 9.1 }); // 6 + 2 × 1.4 + win
    expect(of("A6")).toMatchObject({ assists: 1, rating: 7 });
    expect(of("A0").rating).toBe(7.7); // keeper: two saves (B9's shots), clean sheet, win
    expect(of("A2").rating).toBe(6.9); // defender: tackle + clean sheet + win
    expect(of("B0").rating).toBe(5.1); // two conceded, defeat
    expect(of("B9").rating).toBe(6); // two shots on target, defeat
    expect(of("B1").rating).toBe(5.2); // foul with a yellow, defeat
    // A substitute who came on is rated too.
    expect(of("Запасной").rating).toBe(6.3);
  });

  it("the man of the match is the best rated; tones by band", () => {
    expect(manOfTheMatch(ratings)?.name).toBe("A8");
    expect(ratings[0].name).toBe("A8");
    expect([ratingTone(9.1), ratingTone(6), ratingTone(5.2)]).toEqual(["great", "good", "poor"]);
    expect(manOfTheMatch([])).toBeNull();
  });

  it("ratings stay within 3-10", () => {
    const many = Array.from({ length: 12 }, () => ev("goal", "a", { shooter: "A9" }));
    const r = matchRatings(replay, many, [12, 0]);
    expect(r.find((x) => x.name === "A9")!.rating).toBe(10);
    expect(r.find((x) => x.name === "B0")!.rating).toBeGreaterThanOrEqual(3);
  });
});
