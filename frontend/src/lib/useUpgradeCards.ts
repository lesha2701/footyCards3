import { useInfiniteQuery } from "@tanstack/react-query";

import { fetchUpgradeableCards } from "@/api/collection";
import type { CardFilter } from "@/lib/cardFilter";
import type { Rarity } from "@/types";

export const UPGRADE_PAGE = 60;

/** The Forge list a page at a time (strongest first): a big collection has
 * tens of thousands of commons — too many to send and draw at once. The
 * position / country / club filter runs on the server. */
export function useUpgradeCards(
  rarity: Rarity | null,
  filter: Pick<CardFilter, "position" | "country" | "club">,
  enabled = true,
) {
  const narrow = { position: filter.position, country: filter.country, club: filter.club };
  const query = useInfiniteQuery({
    queryKey: ["upgrade-cards", rarity, narrow],
    queryFn: ({ pageParam }) => fetchUpgradeableCards(rarity!, { ...narrow, limit: UPGRADE_PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => (last.length === UPGRADE_PAGE ? pages.length * UPGRADE_PAGE : undefined),
    enabled: enabled && !!rarity,
  });
  return { ...query, cards: query.data?.pages.flat() };
}
