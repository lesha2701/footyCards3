import { describe, expect, it } from "vitest";

import { specialSerial } from "@/lib/serials";

describe("«Редкий номер»", () => {
  it("marks the first copy, the last of an edition and famous numbers", () => {
    expect(specialSerial(1)).toBe("Первый номер");
    expect(specialSerial(100, 100)).toBe("Последний номер тиража");
    expect(specialSerial(10)).toBe("Культовый номер");
    expect(specialSerial(7, 50)).toBe("Культовый номер");
  });
  it("leaves ordinary numbers alone", () => {
    expect(specialSerial(42)).toBeNull();
    expect(specialSerial(null)).toBeNull();
    expect(specialSerial(0)).toBeNull();
  });
});
