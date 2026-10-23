import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchCardFilterDefault, type CardFilterDefault } from "@/api/collection";
import type { Player, Rarity } from "@/types";

/** Card filter shared by «Мои карты», the album and the Forge. */
export interface CardFilter {
  rarity: Rarity | null;
  country: string | null;
  club: string | null;
  position: string | null;
  sort_by: "rating" | "rarity" | "acquired_at";
  has_skill: boolean;
}

export const EMPTY_FILTER: CardFilter = {
  rarity: null, country: null, club: null, position: null, sort_by: "acquired_at", has_skill: false,
};

export function fromSaved(saved: CardFilterDefault | null | undefined): CardFilter {
  return {
    rarity: saved?.rarity ?? null,
    country: saved?.country ?? null,
    club: saved?.club ?? null,
    position: saved?.position ?? null,
    sort_by: saved?.sort_by ?? "acquired_at",
    has_skill: !!saved?.has_skill,
  };
}

export function toSaved(filter: CardFilter): CardFilterDefault {
  return {
    rarity: filter.rarity, country: filter.country, club: filter.club, position: filter.position,
    sort_by: filter.sort_by === "acquired_at" ? null : filter.sort_by, has_skill: filter.has_skill || null,
  };
}

export function sameFilter(a: CardFilter, b: CardFilter): boolean {
  return (Object.keys(EMPTY_FILTER) as (keyof CardFilter)[]).every((k) => a[k] === b[k]);
}

/** How many narrowing fields are set (sort doesn't count). */
export function activeCount(filter: CardFilter): number {
  return [filter.rarity, filter.country, filter.club, filter.position].filter(Boolean).length + (filter.has_skill ? 1 : 0);
}

/** Client-side filter for lists already on the client (album, Forge). */
export function matchesPlayer(filter: Pick<CardFilter, "rarity" | "country" | "club" | "position">, player: Player): boolean {
  return (
    (!filter.rarity || player.rarity === filter.rarity)
    && (!filter.country || player.country === filter.country)
    && (!filter.club || player.club === filter.club)
    && (!filter.position || player.position === filter.position)
  );
}

/** The screen's current filter: starts from the player's saved default and
 * follows their changes from there (until the screen is left). */
export function useCardFilter() {
  const { data: saved, isFetched } = useQuery({
    queryKey: ["card-filter-default"],
    queryFn: fetchCardFilterDefault,
    staleTime: 5 * 60_000,
  });
  const [touched, setTouched] = useState<CardFilter | null>(null);
  const defaultFilter = fromSaved(saved);
  const filter = touched ?? defaultFilter;
  return { filter, setFilter: setTouched, defaultFilter, savedLoaded: isFetched };
}
