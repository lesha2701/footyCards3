import { describe, expect, it } from "vitest";

import { boardSide, cellCoord, formatMoney, isCorner, levelLabel, secondsLeft } from "@/components/magnate/magnateMeta";

describe("magnate board geometry", () => {
  for (const total of [24, 32]) {
    const side = boardSide(total);
    it(`puts ${total} cells on distinct perimeter squares of the ${side}×${side} grid`, () => {
      const coords = Array.from({ length: total }, (_, i) => cellCoord(i, total));
      expect(new Set(coords.map(({ row, col }) => `${row}:${col}`)).size).toBe(total);
      for (const { row, col } of coords) {
        expect(row === 1 || row === side || col === 1 || col === side).toBe(true);
      }
      for (let i = 0; i < total; i++) {
        const a = cellCoord(i, total);
        const b = cellCoord(i + 1, total);
        expect(Math.abs(a.row - b.row) + Math.abs(a.col - b.col)).toBe(1);
      }
    });
  }

  it("starts bottom-right and runs through the corners", () => {
    expect(cellCoord(0, 32)).toEqual({ row: 9, col: 9 });
    expect(cellCoord(8, 32)).toEqual({ row: 9, col: 1 });
    expect(cellCoord(16, 32)).toEqual({ row: 1, col: 1 });
    expect(cellCoord(24, 32)).toEqual({ row: 1, col: 9 });
    expect(cellCoord(31, 32)).toEqual({ row: 8, col: 9 });
    expect([0, 8, 16, 24].every((i) => isCorner(i, 32))).toBe(true);
    expect(isCorner(4, 32)).toBe(false);
    expect(cellCoord(6, 24)).toEqual({ row: 7, col: 1 });
  });
});

describe("magnate helpers", () => {
  it("counts the turn timer down using the server clock", () => {
    const server = "2026-10-12T12:00:00.000Z";
    const deadline = "2026-10-12T12:00:30.000Z";
    const fetchedAt = new Date("2026-10-12T11:59:50.000Z").getTime(); // client is 10 s behind
    expect(secondsLeft(deadline, server, fetchedAt, fetchedAt)).toBe(30);
    expect(secondsLeft(deadline, server, fetchedAt, fetchedAt + 25_000)).toBe(5);
    expect(secondsLeft(deadline, server, fetchedAt, fetchedAt + 60_000)).toBe(0);
    expect(secondsLeft(null, server, fetchedAt)).toBeNull();
  });

  it("formats the in-match budget and building levels", () => {
    expect(formatMoney(1500)).toBe("1 500 М");
    expect(levelLabel(0)).toBe("");
    expect(levelLabel(2)).toBe("Трибуны ×2");
    expect(levelLabel(4)).toBe("Арена");
  });
});
