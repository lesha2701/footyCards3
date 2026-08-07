import type { Pack } from "@/types";

export type PackSortDirection = "asc" | "desc";

export function sortPacksByPrice(packs: Pack[], direction: PackSortDirection = "asc"): Pack[] {
  const sorted = [...packs].sort((a, b) => a.price - b.price);
  return direction === "desc" ? sorted.reverse() : sorted;
}

export function sortPacksByStarsPrice(packs: Pack[], direction: PackSortDirection = "asc"): Pack[] {
  const sorted = [...packs].sort((a, b) => (a.stars_price ?? 0) - (b.stars_price ?? 0));
  return direction === "desc" ? sorted.reverse() : sorted;
}
