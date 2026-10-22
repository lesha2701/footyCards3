import { describe, expect, it } from "vitest";

import { describeExchange, exchangeWinner, pct } from "@/components/mordoboi/mordoboiMeta";
import type { MordoboiExchange } from "@/types";

const exchange = (over: Partial<MordoboiExchange> = {}): MordoboiExchange => ({
  n: 1, round: 1, exchange: 1, my_action: "hook", opponent_action: "jab",
  my_outcome: "landed", opponent_outcome: "beaten", my_damage: 12, opponent_damage: 0,
  my_hp: 100, opponent_hp: 88, my_auto: false, opponent_auto: false, round_end: false, end: null,
  ...over,
});

describe("Мордобой: подписи обменов", () => {
  it("describes both sides with damage", () => {
    expect(describeExchange(exchange())).toEqual({ mine: "Хук · попал −12", theirs: "Джеб · не успел" });
  });

  it("marks the autopilot and the counter", () => {
    const d = describeExchange(exchange({
      my_action: "hook", my_outcome: "slipped", my_damage: 0,
      opponent_action: "dodge", opponent_outcome: "counter", opponent_damage: 5, opponent_auto: true,
    }));
    expect(d.mine).toBe("Хук · мимо — уклон");
    expect(d.theirs).toBe("Уклон (автопилот) · контратака −5");
  });

  it("picks the exchange winner by damage", () => {
    expect(exchangeWinner(exchange())).toBe("me");
    expect(exchangeWinner(exchange({ my_damage: 3, opponent_damage: 9 }))).toBe("opponent");
    expect(exchangeWinner(exchange({ my_damage: 0, opponent_damage: 0 }))).toBe("even");
  });

  it("clamps bar percentages", () => {
    expect(pct(50, 100)).toBe(50);
    expect(pct(-5, 100)).toBe(0);
    expect(pct(5, 0)).toBe(0);
  });
});
