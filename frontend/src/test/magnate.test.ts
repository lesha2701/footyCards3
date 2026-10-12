import { describe, expect, it } from "vitest";

import { BOARD_SIDE, cellCoord, formatMoney, levelLabel, secondsLeft } from "@/components/magnate/magnateMeta";

describe("magnate board geometry", () => {
  it("puts the 24 cells on distinct perimeter squares of the 7×7 grid", () => {
    const coords = Array.from({ length: 24 }, (_, i) => cellCoord(i));
    const keys = new Set(coords.map(({ row, col }) => `${row}:${col}`));
    expect(keys.size).toBe(24);
    for (const { row, col } of coords) {
      expect(row === 1 || row === BOARD_SIDE || col === 1 || col === BOARD_SIDE).toBe(true);
    }
  });

  it("starts bottom-right and runs counter-clockwise through the corners", () => {
    expect(cellCoord(0)).toEqual({ row: 7, col: 7 });
    expect(cellCoord(1)).toEqual({ row: 7, col: 6 });
    expect(cellCoord(6)).toEqual({ row: 7, col: 1 });
    expect(cellCoord(12)).toEqual({ row: 1, col: 1 });
    expect(cellCoord(18)).toEqual({ row: 1, col: 7 });
    expect(cellCoord(23)).toEqual({ row: 6, col: 7 });
    expect(cellCoord(24)).toEqual(cellCoord(0));
  });

  it("neighbouring cells are adjacent squares", () => {
    for (let i = 0; i < 24; i++) {
      const a = cellCoord(i);
      const b = cellCoord(i + 1);
      expect(Math.abs(a.row - b.row) + Math.abs(a.col - b.col)).toBe(1);
    }
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
