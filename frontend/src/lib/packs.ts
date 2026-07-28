import type { Pack } from "@/types";

export type PackSortDirection = "asc" | "desc";

export function sortPacksByPrice(packs: Pack[], direction: PackSortDirection = "asc"): Pack[] {
  const sorted = [...packs].sort((a, b) => a.price - b.price);
  return direction === "desc" ? sorted.reverse() : sorted;
}
