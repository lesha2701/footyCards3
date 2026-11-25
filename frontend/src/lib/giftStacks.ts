import { specialRank, specialSerial } from "@/lib/giftSerial";
import type { Gift } from "@/types";

/** Identical collectibles (one gift set) as one tile: the copies sorted by
 * serial, pinned copies first; stacks keep the order of their newest copy. */
export interface GiftStack {
  setId: number;
  copies: Gift[];
  pinned: boolean;
  /** How many copies carry a special serial (lib/giftSerial). */
  special: number;
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
    copies: sortCopies(copies, "serial"),
    pinned: copies.some((c) => c.is_pinned),
    special: copies.filter((c) => specialSerial(c.serial_number) !== null).length,
  }));
}

export type CopySort = "serial" | "special";

/** Pinned first, then by serial — or the rarest serials first. */
export function sortCopies(copies: Gift[], sort: CopySort): Gift[] {
  const serial = (g: Gift) => g.serial_number ?? Infinity;
  return [...copies].sort(
    (a, b) =>
      Number(b.is_pinned) - Number(a.is_pinned)
      || (sort === "special" ? specialRank(a.serial_number) - specialRank(b.serial_number) : 0)
      || serial(a) - serial(b),
  );
}

/** «Найти №…»: the digits typed, anywhere in the serial. */
export function filterBySerial(copies: Gift[], query: string): Gift[] {
  const digits = query.replace(/\D/g, "");
  if (!digits) return copies;
  return copies.filter((g) => g.serial_number != null && String(g.serial_number).includes(digits));
}

/** «1 подарок», «2 подарка», «5 подарков». */
export function giftsWord(n: number): string {
  const d10 = n % 10, d100 = n % 100;
  const word = d10 === 1 && d100 !== 11 ? "подарок" : d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14) ? "подарка" : "подарков";
  return `${n} ${word}`;
}
