import { describe, expect, it } from "vitest";

import { cardMedals } from "@/lib/cardMedals";

describe("cardMedals", () => {
  it("gives a copy its Arena medals by its own numbers", () => {
    expect(cardMedals(0, 0, 0)).toEqual([]);
    expect(cardMedals(64, 52, 11)).toEqual(["⚽ Бомбардир", "🎯 Распасовщик", "🏅 MVP"]);
    expect(cardMedals(120, 0, 30)).toEqual(["⚽ Легенда-бомбардир", "🏆 Звезда матчей"]);
  });
});
