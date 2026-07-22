import { describe, expect, it } from "vitest";

import { RARITY_LABELS, RARITY_ORDER, POSITION_LABELS } from "@/lib/rarity";

describe("rarity utils", () => {
  it("has a label for every rarity", () => {
    expect(RARITY_LABELS.common).toBe("Обычная");
    expect(RARITY_LABELS.legendary).toBe("Легендарная");
  });

  it("orders rarities from common to legendary", () => {
    expect(RARITY_ORDER.common).toBeLessThan(RARITY_ORDER.rare);
    expect(RARITY_ORDER.rare).toBeLessThan(RARITY_ORDER.epic);
    expect(RARITY_ORDER.epic).toBeLessThan(RARITY_ORDER.legendary);
  });

  it("has a Russian label for every position", () => {
    expect(POSITION_LABELS.GK).toBeDefined();
    expect(POSITION_LABELS.ST).toBeDefined();
    expect(Object.keys(POSITION_LABELS)).toHaveLength(12);
  });
});
