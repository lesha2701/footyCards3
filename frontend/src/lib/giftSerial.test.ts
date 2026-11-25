import { describe, expect, it } from "vitest";

import { specialRank, specialSerial } from "./giftSerial";

// The same cases as backend tests/test_gifts.py SPECIAL_CASES.
const CASES: Record<number, string | null> = {
  1: "first", 7: "lucky", 77: "lucky", 777: "lucky", 10: "jubilee", 100: "jubilee", 1000: "jubilee",
  11: "twins", 222: "twins", 300: "round", 1200: "round", 121: "mirror", 1001: "mirror",
  2: null, 12: null, 42: null, 101: "mirror", 150: null,
};

describe("specialSerial", () => {
  it("matches the backend twin", () => {
    for (const [n, code] of Object.entries(CASES)) expect(specialSerial(Number(n))).toBe(code);
  });
  it("ranks the rarest first and the ordinary last", () => {
    expect(specialRank(1)).toBeLessThan(specialRank(777));
    expect(specialRank(121)).toBeLessThan(specialRank(42));
  });
});
