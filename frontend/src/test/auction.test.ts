import { describe, expect, it } from "vitest";

import { formatTimeLeft, newIdempotencyKey } from "@/api/auction";

describe("auction helpers", () => {
  it("formats the countdown", () => {
    expect(formatTimeLeft(0)).toBe("Завершается…");
    expect(formatTimeLeft(65_000)).toBe("1:05");
    expect(formatTimeLeft(2 * 3600_000 + 5 * 60_000)).toBe("2 ч 05 мин");
  });

  it("makes distinct idempotency keys the backend accepts (8–64 chars)", () => {
    const a = newIdempotencyKey();
    const b = newIdempotencyKey();
    expect(a).not.toBe(b);
    expect(a.length).toBeGreaterThanOrEqual(8);
    expect(a.length).toBeLessThanOrEqual(64);
  });
});
