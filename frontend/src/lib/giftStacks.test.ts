import { describe, expect, it } from "vitest";

import type { Gift } from "@/types";

import { stackGifts } from "./giftStacks";

const gift = (id: number, setId: number, serial: number | null, pinned = false) =>
  ({ id, serial_number: serial, is_pinned: pinned, gift_set: { id: setId } }) as unknown as Gift;

describe("stackGifts", () => {
  it("folds the copies of one set into a stack sorted by serial, pinned first", () => {
    const stacks = stackGifts([gift(1, 7, 30), gift(2, 8, 1), gift(3, 7, 4), gift(4, 7, 12, true)]);
    expect(stacks.map((s) => s.setId)).toEqual([7, 8]);
    expect(stacks[0].copies.map((c) => c.serial_number)).toEqual([12, 4, 30]);
    expect(stacks[0].pinned).toBe(true);
    expect(stacks[1].copies).toHaveLength(1);
    expect(stacks[1].pinned).toBe(false);
  });
});
