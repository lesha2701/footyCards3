import { describe, expect, it } from "vitest";

import { autoLayout, legalTargets } from "@/components/stratego/strategoMeta";
import type { StrategoPiece } from "@/types";

const piece = (over: Partial<StrategoPiece>): StrategoPiece => ({
  id: 1, mine: true, row: 4, col: 0, hidden: false, revealed: false, moved: false,
  role: "regular", power: 60, card: null, ...over,
});

describe("stratego legalTargets", () => {
  it("steps one cell orthogonally and never onto own pieces", () => {
    const me = piece({});
    const friend = piece({ id: 2, row: 4, col: 1 });
    const targets = legalTargets([me, friend], me, 6);
    expect(targets).toEqual(expect.arrayContaining([[3, 0], [5, 0]]));
    expect(targets).not.toContainEqual([4, 1]);
    expect(targets).toHaveLength(2);
  });

  it("lets the speedster run until blocked, attacking the first enemy", () => {
    const me = piece({ role: "speedster", row: 5 });
    const enemy = piece({ id: 3, mine: false, hidden: true, role: null, power: null, row: 1, col: 0 });
    const targets = legalTargets([me, enemy], me, 6);
    expect(targets).toContainEqual([1, 0]);
    expect(targets).not.toContainEqual([0, 0]);
  });

  it("stops at lakes", () => {
    const me = piece({ role: "speedster", row: 6, col: 1 });
    const targets = legalTargets([me], me, 8, [[4, 1], [3, 1]]);
    expect(targets).toContainEqual([5, 1]);
    expect(targets).not.toContainEqual([4, 1]);
    expect(targets).not.toContainEqual([2, 1]);
  });

  it("keeps cup and walls in place", () => {
    expect(legalTargets([piece({ role: "cup" })], piece({ role: "cup" }), 6)).toEqual([]);
    expect(legalTargets([piece({ role: "wall" })], piece({ role: "wall" }), 6)).toEqual([]);
  });
});

describe("stratego autoLayout", () => {
  it("fills all 16 cells of an 8-wide home zone", () => {
    const slots = ["cup", "wall_1", "wall_2", "star", "tackler_1", "tackler_2", "provocateur", "speedster_1", "speedster_2",
      "tackler_3", ...Array.from({ length: 6 }, (_, i) => `regular_${i + 1}`)];
    const layout = autoLayout(slots, 8);
    expect(new Set(Object.values(layout).map(([r, c]) => `${r}:${c}`)).size).toBe(16);
  });

  it("places every slot in the two home rows with the cup on the back row", () => {
    const slots = ["cup", "wall_1", "wall_2", "star", "tackler", "provocateur", "speedster", "regular_1"];
    for (let i = 0; i < 20; i++) {
      const layout = autoLayout(slots, 6);
      expect(Object.keys(layout).sort()).toEqual([...slots].sort());
      const cells = Object.values(layout).map(([r, c]) => `${r}:${c}`);
      expect(new Set(cells).size).toBe(slots.length);
      expect(layout.cup[0]).toBe(1);
      Object.values(layout).forEach(([r, c]) => {
        expect([0, 1]).toContain(r);
        expect(c).toBeGreaterThanOrEqual(0);
        expect(c).toBeLessThan(6);
      });
    }
  });
});
