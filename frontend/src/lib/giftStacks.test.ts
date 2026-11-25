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

describe("sortCopies / filterBySerial", () => {
  it("puts the rarest serials first on demand and finds a serial by its digits", async () => {
    const { filterBySerial, sortCopies } = await import("./giftStacks");
    const copies = [gift(1, 7, 42), gift(2, 7, 777), gift(3, 7, 5), gift(4, 7, 1)];
    expect(sortCopies(copies, "special").map((c) => c.serial_number)).toEqual([1, 777, 5, 42]);
    expect(sortCopies(copies, "serial").map((c) => c.serial_number)).toEqual([1, 5, 42, 777]);
    expect(filterBySerial(copies, "№7").map((c) => c.serial_number)).toEqual([777]);
    expect(filterBySerial(copies, "").length).toBe(4);
    expect(stackGifts(copies)[0].special).toBe(2);
  });
});

describe("giftsWord", () => {
  it("declines the word", async () => {
    const { giftsWord } = await import("./giftStacks");
    expect([1, 2, 5, 11, 12, 21, 22, 25, 111].map(giftsWord)).toEqual([
      "1 подарок", "2 подарка", "5 подарков", "11 подарков", "12 подарков", "21 подарок", "22 подарка", "25 подарков", "111 подарков",
    ]);
  });
});
