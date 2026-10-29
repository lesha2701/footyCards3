/** The tactics board's layout: where each slot of a formation stands for
 * the chosen block, and the tactic chips (pure; drawn by TacticBoard). */
import type { CareerSquadCard } from "@/api/career";
import { staticUrl } from "@/lib/api";
import { pitchRows } from "@/lib/formationLayout";

const PLACEHOLDER = "players/placeholder/player_placeholder.webp";
const CODES = ["GK", "DEF1", "DEF2", "DEF3", "DEF4", "DEF5", "MID1", "MID2", "MID3", "MID4", "MID5", "FWD1", "FWD2", "FWD3"];

// Vertical pitch (viewBox 100 × 140), our goal at the bottom; line heights by block.
export const LINE_Y: Record<string, { DEF: number; MID: number; FWD: number }> = {
  high: { DEF: 88, MID: 64, FWD: 38 },
  mid: { DEF: 100, MID: 76, FWD: 48 },
  low: { DEF: 110, MID: 90, FWD: 62 },
};

/** The board's chips: which axis, its group and a glyph. */
export const BOARD_AXES: { key: string; group: "attack" | "defence"; icon: string; short: string }[] = [
  { key: "direction", group: "attack", icon: "↗", short: "Атака" },
  { key: "buildup", group: "attack", icon: "⇢", short: "Пас" },
  { key: "on_win", group: "attack", icon: "⚡", short: "После отбора" },
  { key: "block", group: "defence", icon: "▬", short: "Линия обороны" },
  { key: "on_loss", group: "defence", icon: "⟲", short: "После потери" },
  { key: "tackling", group: "defence", icon: "🦶", short: "Отбор" },
];

function spread(count: number): number[] {
  if (count <= 0) return [];
  if (count === 1) return [50];
  const margin = count >= 5 ? 11 : count === 4 ? 15 : count === 3 ? 22 : 32;
  return Array.from({ length: count }, (_, i) => margin + ((100 - 2 * margin) * i) / (count - 1));
}

export interface BoardPlayer { code: string; x: number; y: number; entry: CareerSquadCard | undefined }

/** Where each slot of `formation` stands for `block` (top = attack). */
export function boardLayout(formation: string, block: string, lineup: Record<string, number>, squad: CareerSquadCard[]): BoardPlayer[] {
  const y = LINE_Y[block] ?? LINE_Y.mid;
  const rows = pitchRows(formation, CODES);
  const outfield = rows.filter((r) => r.category !== "GK");
  const byId = new Map(squad.map((s) => [s.card_id, s]));
  const out: BoardPlayer[] = [];
  outfield.forEach((row, i) => {
    const rowY = outfield.length > 1 ? y.FWD + ((y.DEF - y.FWD) * i) / (outfield.length - 1) : y.MID;
    spread(row.codes.length).forEach((x, k) => {
      const code = row.codes[k];
      out.push({ code, x, y: rowY, entry: lineup[code] !== undefined ? byId.get(lineup[code]) : undefined });
    });
  });
  out.push({ code: "GK", x: 50, y: 128, entry: lineup.GK !== undefined ? byId.get(lineup.GK) : undefined });
  return out;
}

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
