import type { Gift } from "@/types";

/** Identical collectibles (one gift set) as one tile: the copies sorted by
 * serial, pinned copies first; stacks keep the order of their newest copy. */
export interface GiftStack {
  setId: number;
  copies: Gift[];
  pinned: boolean;
}

export function stackGifts(gifts: Gift[]): GiftStack[] {
  const bySet = new Map<number, Gift[]>();
  for (const g of gifts) {
    const list = bySet.get(g.gift_set.id) ?? [];
    list.push(g);
    bySet.set(g.gift_set.id, list);
  }
  return [...bySet.entries()].map(([setId, copies]) => ({
    setId,
    copies: [...copies].sort(
      (a, b) => Number(b.is_pinned) - Number(a.is_pinned) || (a.serial_number ?? Infinity) - (b.serial_number ?? Infinity),
    ),
    pinned: copies.some((c) => c.is_pinned),
  }));
}
