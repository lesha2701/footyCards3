import { beforeEach, describe, expect, it } from "vitest";

import { freshOnPage, markPageSeen } from "@/lib/albumSeen";

describe("album «NEW» stickers", () => {
  beforeEach(() => localStorage.clear());

  it("the first visit of a page marks nothing new", () => {
    expect(freshOnPage(1, [1, 2, 3]).size).toBe(0);
  });

  it("a card got since the last visit is new, once", () => {
    markPageSeen(1, [1, 2]);
    expect([...freshOnPage(1, [1, 2, 3])]).toEqual([3]);
    markPageSeen(1, [1, 2, 3]);
    expect(freshOnPage(1, [1, 2, 3]).size).toBe(0);
  });

  it("pages are tracked apart", () => {
    markPageSeen(1, [1]);
    expect(freshOnPage(2, [5]).size).toBe(0);
  });
});
