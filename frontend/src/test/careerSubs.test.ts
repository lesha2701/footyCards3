import { describe, expect, it } from "vitest";

import { TIRED_AT, benchFor, byFatigue, lineOf, suggestSubs } from "@/lib/careerSubs";

const p = (card_id: number, position: string, fatigue = 30, rating = 80) => ({ card_id, name: `P${card_id}`, position, rating, fatigue });

describe("half-time substitutions", () => {
  const on = [p(1, "ST", 80), p(2, "CB", 75), p(3, "CM", 20), p(4, "GK", 90)];
  const bench = [p(10, "CM", 0, 70), p(11, "ST", 5, 75), p(12, "LB", 0, 72), p(13, "GK", 0, 70), p(14, "RW", 0, 82)];

  it("lines of positions", () => {
    expect([lineOf("LWB"), lineOf("CAM"), lineOf("RW"), lineOf("GK"), lineOf(null)]).toEqual(["DEF", "MID", "FWD", "GK", null]);
  });

  it("the bench for a player: same position, then same line, then rating; keepers only for keepers", () => {
    expect(benchFor(on[0], bench, []).map((b) => b.card_id)).toEqual([11, 14, 12, 10]);
    expect(benchFor(on[3], bench, []).map((b) => b.card_id)).toEqual([13]);
    expect(benchFor(on[1], bench, []).map((b) => b.card_id).slice(0, 1)).toEqual([12]);
    // Already used ones are not offered again.
    expect(benchFor(on[0], bench, [{ out: 9, in: 11 }]).map((b) => b.card_id)[0]).toBe(14);
  });

  it("most tired first", () => {
    expect(byFatigue(on).map((x) => x.card_id)).toEqual([4, 1, 2, 3]);
  });

  it("replaces the tired by their best fit, keepers only by keepers, up to the subs left", () => {
    expect(suggestSubs(on, bench, [], 3)).toEqual([{ out: 4, in: 13 }, { out: 1, in: 11 }, { out: 2, in: 12 }]);
    expect(suggestSubs(on, bench, [], 2)).toHaveLength(2);
    // Keeps the coach's own choices and doesn't double up.
    expect(suggestSubs(on, bench, [{ out: 1, in: 14 }], 3)).toEqual([{ out: 1, in: 14 }, { out: 4, in: 13 }, { out: 2, in: 12 }]);
    // Nobody tired: nothing proposed.
    expect(suggestSubs([p(3, "CM", TIRED_AT - 1)], bench, [], 3)).toEqual([]);
  });
});
