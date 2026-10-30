/** Who does what in the career squad: a player's card info, the role of
 * his line and his duties (marking the star, set pieces). Pure. */
import type { CareerSeason, CareerSquadCard, TacticsCatalog } from "@/api/career";
import { staticUrl } from "@/lib/api";

const PLACEHOLDER = "players/placeholder/player_placeholder.webp";

export const TAKERS: { key: "corner_taker" | "free_kick_taker" | "penalty_taker"; label: string; icon: string }[] = [
  { key: "corner_taker", label: "Угловые", icon: "🚩" },
  { key: "free_kick_taker", label: "Штрафные", icon: "🎯" },
  { key: "penalty_taker", label: "Пенальти", icon: "⚽" },
];

export function playerInfo(entry: CareerSquadCard | undefined) {
  if (!entry) return null;
  if (entry.card) {
    const p = entry.card.player;
    return { name: p.display_name, short: p.last_name || p.display_name, position: p.position, rating: p.rating, image: staticUrl(p.image_path ?? PLACEHOLDER) };
  }
  if (entry.my_player) {
    const m = entry.my_player;
    return { name: m.name, short: m.name.split(" ").slice(-1)[0], position: m.position, rating: m.rating, image: staticUrl(PLACEHOLDER) };
  }
  return null;
}

/** One word for a role on a small card (the full label is in the card). */
const ROLE_SHORT: Record<string, string> = {
  crosser: "Навесы", inside: "Срезка", destroyer: "Отбор", playmaker: "Пас", attacking: "Атака", holding: "Оборона",
};

/** The role of the line a slot belongs to (by its ideal position, else the
 * player's own): its label and a one-word tag; null when none is set. */
export function roleLabel(season: CareerSeason, catalog: TacticsCatalog | null, code: string, position: string): { label: string; short: string } | null {
  const slot = season.slots.find((s) => s.code === code);
  const group = (catalog?.roles ?? []).find((g) => g.positions.includes(slot?.ideal_position ?? "") || g.positions.includes(position));
  const value = group ? season.roles?.[group.group] : undefined;
  const label = group && value ? group.values.find((v) => v.value === value)?.label : undefined;
  return label && value ? { label, short: ROLE_SHORT[value] ?? label.split(" ")[0] } : null;
}

/** Whether the slot's line can have a role at all. */
export function hasRole(season: CareerSeason, catalog: TacticsCatalog | null, code: string, position: string): boolean {
  const slot = season.slots.find((s) => s.code === code);
  return (catalog?.roles ?? []).some((g) => g.positions.includes(slot?.ideal_position ?? "") || g.positions.includes(position));
}

/** The player's duties as icons: marking the star, set pieces. */
export function dutiesOf(season: CareerSeason, cardId: number): string {
  const sp = season.set_pieces ?? null;
  return [
    season.scouting?.marking?.marker === cardId ? "👁" : "",
    ...TAKERS.map((t) => (sp?.[t.key] === cardId ? t.icon : "")),
  ].join("");
}

/** A row of cards on the «Состав» pitch, in px from its top. */
export interface Band { top: number; bottom: number; mid: number }

/** Where the defensive line is drawn for a block: pushed up towards the
 * midfield, between the lines, or dropped towards the keeper. */
export function lineY(block: string | undefined, mid: Band, def: Band, gk: Band | undefined): number {
  if (block === "high") return mid.bottom + (def.top - mid.bottom) * 0.25;
  if (block === "low") return def.bottom + ((gk?.top ?? def.bottom + 24) - def.bottom) * 0.55;
  return (mid.bottom + def.top) / 2;
}
