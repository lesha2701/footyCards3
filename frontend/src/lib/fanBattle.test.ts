import { describe, expect, it } from "vitest";

import { fanBattlePhase, pointsWord, tugShare } from "@/lib/fanBattle";
import type { FanBattleState } from "@/types";

const DAY = 86_400_000;
const base = { enabled: true, active: false, finished: false, teaser_days: 3, my_side: null, claimable: 0 } as unknown as FanBattleState;

describe("fanBattle", () => {
  it("phases", () => {
    const now = Date.now();
    expect(fanBattlePhase(undefined)).toBeNull();
    expect(fanBattlePhase({ ...base, enabled: false })).toBeNull();
    expect(fanBattlePhase({ ...base, active: true })).toBe("live");
    expect(fanBattlePhase({ ...base, starts_at: new Date(now + 2 * DAY).toISOString() }, now)).toBe("teaser");
    expect(fanBattlePhase({ ...base, starts_at: new Date(now + 5 * DAY).toISOString() }, now)).toBeNull();
    expect(fanBattlePhase({ ...base, finished: true, my_side: "fire", claimable: 1 })).toBe("results");
    expect(fanBattlePhase({ ...base, finished: true, my_side: "fire", claimable: 0 })).toBeNull();
  });

  it("tug share", () => {
    expect(tugShare(0, 0)).toBe(50);
    expect(tugShare(3, 1)).toBe(75);
    expect(tugShare(1, 2)).toBe(33.3);
  });

  it("points word", () => {
    expect([1, 2, 5, 11, 21, 22, 112].map(pointsWord)).toEqual(["очко", "очка", "очков", "очков", "очко", "очка", "очков"]);
  });
});
