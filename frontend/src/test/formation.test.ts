import { describe, expect, it } from "vitest";

import { CATEGORY_POSITIONS, FORMATION_SLOTS } from "@/lib/formation";

describe("formation", () => {
  it("has exactly 11 slots for a 4-3-3", () => {
    expect(FORMATION_SLOTS).toHaveLength(11);
  });

  it("has one goalkeeper, four defenders, three midfielders, three forwards", () => {
    const counts = FORMATION_SLOTS.reduce<Record<string, number>>((acc, s) => {
      acc[s.category] = (acc[s.category] ?? 0) + 1;
      return acc;
    }, {});
    expect(counts.GK).toBe(1);
    expect(counts.DEF).toBe(4);
    expect(counts.MID).toBe(3);
    expect(counts.FWD).toBe(3);
  });

  it("every slot's ideal position belongs to its own category", () => {
    for (const slot of FORMATION_SLOTS) {
      expect(CATEGORY_POSITIONS[slot.category]).toContain(slot.idealPosition);
    }
  });
});
