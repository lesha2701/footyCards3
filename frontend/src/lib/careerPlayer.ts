/** What a career player tile shows, from a squad entry or a collection
 * card: the same face on the pitch, the bench and in the season squad. */
import type { CareerCollectionCard, CareerSquadCard } from "@/api/career";
import { staticUrl } from "@/lib/api";
import { CATEGORY_POSITIONS } from "@/lib/formation";
import { personKey } from "@/lib/person";
import type { Rarity } from "@/types";

const PLACEHOLDER = "players/placeholder/player_placeholder.webp";

export type Line = "GK" | "DEF" | "MID" | "FWD";

export interface PlayerInfo {
  /** The footballer behind the card (one per XI, lib/person). */
  person: string;
  name: string;
  short: string;
  position: string;
  rating: number;
  club: string;
  country: string;
  image?: string;
  rarity: Rarity;
  mine: boolean;
}

/** Short label for a tile: the last word of the name (surname), never empty
 * — trailing spaces or a one-word name fall back to the whole name. */
export function shortName(...names: (string | null | undefined)[]): string {
  for (const n of names) {
    const words = (n ?? "").trim().split(/\s+/).filter(Boolean);
    if (words.length) return words[words.length - 1];
  }
  return "";
}

export function playerInfo(entry: Pick<CareerSquadCard | CareerCollectionCard, "card" | "my_player"> | undefined): PlayerInfo | null {
  if (!entry) return null;
  if (entry.card) {
    const p = entry.card.player;
    return {
      person: personKey(p), name: p.display_name, short: shortName(p.display_name, p.last_name, p.first_name), position: p.position, rating: p.rating,
      club: p.club, country: p.country, image: staticUrl(p.image_path ?? PLACEHOLDER), rarity: p.rarity, mine: false,
    };
  }
  if (entry.my_player) {
    const m = entry.my_player;
    return { person: personKey({ display_name: m.name }), name: m.name, short: shortName(m.name), position: m.position, rating: m.rating,
      club: m.club ?? "", country: m.country ?? "", image: staticUrl(PLACEHOLDER), rarity: "epic", mine: true };
  }
  return null;
}

export function lineOf(position: string): Line {
  return (Object.keys(CATEGORY_POSITIONS) as Line[]).find((c) => CATEGORY_POSITIONS[c].includes(position)) ?? "MID";
}

export function isOut(entry: CareerSquadCard): boolean {
  return entry.injured_rounds > 0 || entry.suspended_rounds > 0;
}
