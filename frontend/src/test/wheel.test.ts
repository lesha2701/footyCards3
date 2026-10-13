import { describe, expect, it } from "vitest";

import { formatPercent, prizeOdds } from "@/lib/wheel";
import type { WheelPrize } from "@/types";

function prize(id: number, weight: number): WheelPrize {
  return {
    id, weight, prize_type: "coins", pool: "golden", is_active: true, sort_order: 0, coins_amount: 100 * id,
    pack_id: null, pack: null, card_rarity: null, badge_id: null, badge: null,
  };
}

describe("prizeOdds", () => {
  it("turns relative weights into percentages, most likely first", () => {
    const odds = prizeOdds([prize(1, 1), prize(2, 3)]);
    expect(odds.map((o) => o.prize.id)).toEqual([2, 1]);
    expect(odds.map((o) => o.percent)).toEqual([75, 25]);
  });

  it("is empty for an empty pool", () => {
    expect(prizeOdds([])).toEqual([]);
  });

  it("formats small chances with more precision", () => {
    expect(formatPercent(35)).toBe("35%");
    expect(formatPercent(2.5)).toBe("2.5%");
    expect(formatPercent(0.25)).toBe("0.25%");
  });
});
