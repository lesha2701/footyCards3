import { describe, expect, it } from "vitest";

import { milestonePct } from "@/lib/loyalty";
import { isBoundForever } from "@/lib/cardLocks";

describe("Путь к Центуриону", () => {
  it("places milestones on the bar and clamps", () => {
    expect(milestonePct(30, 100)).toBe(30);
    expect(milestonePct(150, 100)).toBe(100);
    expect(milestonePct(-1, 100)).toBe(0);
  });

  it("tells a forever-bound keepsake from a newbie gift", () => {
    expect(isBoundForever({ bound_until: "2099-12-31T00:00:00Z" })).toBe(true);
    expect(isBoundForever({ bound_until: "2026-11-20T00:00:00Z" })).toBe(false);
    expect(isBoundForever({ bound_until: null })).toBe(false);
  });
});
