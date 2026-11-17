/**
 * «Моя вилла»: the plot. The meadow of the plot picture is cut into
 * isometric cells (PLOT_CELLS, centre first — lib/villaPlot.ts, the twin of
 * the server's town_villa_plot.py); the villa's level opens the first
 * cells_open of them, so the plot grows outwards in a round shape, the rest
 * is locked. A thing of w×h cells (h×w when turned) at
 * (x, y) covers x…x+w−1, y…y+h−1 — the same rule as the server's
 * town_villa_service.check_layout.
 *
 * Sprites: `assets/town/villa/<code>.webp` (the villa and the garage by level:
 * villa_1…villa_5, garage_1…garage_3), cut out, facing bottom-left, drawn with
 * their bottom on the footprint's front corner. Until a picture exists the
 * thing is drawn as a coloured block with its emoji.
 */
import type { VillaItem, VillaKind } from "@/api/town";
import { PLOT_CELLS, PLOT_ORIGIN, PLOT_TH, PLOT_TW } from "@/lib/villaPlot";

const ART = import.meta.glob<string>("@/assets/town/villa/*.webp", { eager: true, import: "default" });
const artUrl = (name: string): string | undefined => ART[`/src/assets/town/villa/${name}.webp`];

/** Fence sections join their neighbours of the same fence; rot = 1 — a gate. */
export const FENCES = ["fence_stone", "fence_iron", "fence_hedge", "fence_picket"];
export const isFence = (code: string): boolean => FENCES.includes(code);
/** Flat path tiles: they lie under everything and join up with tiles of the same kind. */
export const PATHS = ["path", "path_gravel", "path_terracotta", "path_deck", "path_stepping"];
export const isPath = (code: string): boolean => PATHS.includes(code);

/** The picture's name (SPRITE_GROUND key): by level for the villa / garage, a fence by its straight section. */
export function spriteKey(item: Pick<VillaItem, "code" | "level">): string {
  if (item.code === "villa" || item.code === "garage") return `${item.code}_${item.level ?? 1}`;
  if (isFence(item.code)) return `${item.code}_a`;
  return item.code;
}

export function spriteOf(item: Pick<VillaItem, "code" | "level">): string | undefined {
  return artUrl(spriteKey(item)) ?? artUrl(item.code);
}

export const artOf = artUrl;

/** Which fence pieces a section at (x, y) is drawn with: the halves towards its
 * neighbours of the same fence (n: y−1, s: y+1 — the "a" section, e: x+1,
 * w: x−1 — the "b" one), a post where it ends or turns, or a gate. */
export function fencePieces(cells: Set<string>, x: number, y: number, gate: boolean):
  { full?: "a" | "b" | "gate" | "gate_b"; halves: ("n" | "s" | "e" | "w")[]; post: boolean } {
  const n = cells.has(`${x}:${y - 1}`); const s = cells.has(`${x}:${y + 1}`);
  const e = cells.has(`${x + 1}:${y}`); const w = cells.has(`${x - 1}:${y}`);
  const alongX = e || w; const alongY = n || s;
  if (gate) return { full: alongX && !alongY ? "gate_b" : "gate", halves: [], post: false };
  if (!alongX && !alongY) return { full: "a", halves: [], post: false };
  if (n && s && !alongX) return { full: "a", halves: [], post: false };
  if (e && w && !alongY) return { full: "b", halves: [], post: false };
  const halves = ([["n", n], ["s", s], ["e", e], ["w", w]] as const).filter(([, on]) => on).map(([k]) => k);
  return { halves, post: true };
}

export const plotArt = (): string | undefined => artUrl("plot");

export type Placed = { id: number; code: string; x: number | null; y: number | null; rot: number; w: number; h: number };

export function footprint(item: { w: number; h: number; rot: number }): [number, number] {
  return item.rot ? [item.h, item.w] : [item.w, item.h];
}

/** The cells open at cells_open, centre first. */
export const openCells = (count: number): [number, number][] => PLOT_CELLS.slice(0, count);
export const cellSet = (cells: [number, number][]): Set<string> => new Set(cells.map(([x, y]) => `${x}:${y}`));

/** null when everything fits on the open cells, else why not (the server checks the same). */
export function checkLayout(open: Set<string>, items: Placed[]): string | null {
  const taken = new Set<string>();
  for (const it of items) {
    if (it.x == null || it.y == null) {
      if (it.code === "villa" || it.code === "garage") return "Виллу и гараж нельзя убрать на склад";
      continue;
    }
    const [w, h] = footprint(it);
    for (let dx = 0; dx < w; dx++) {
      for (let dy = 0; dy < h; dy++) if (!open.has(`${it.x + dx}:${it.y + dy}`)) return "Предмет выходит за участок";
    }
    for (let dx = 0; dx < w; dx++) {
      for (let dy = 0; dy < h; dy++) {
        const key = `${it.x + dx}:${it.y + dy}`;
        if (taken.has(key)) return "Клетки уже заняты";
        taken.add(key);
      }
    }
  }
  return null;
}

/** The plot picture (assets/town/villa/plot.webp) is drawn in strict 2:1
 * isometry (no perspective): grid point (0, 0) sits at ORIGIN, a cell is
 * TW × TH picture pixels. */
export const PLOT_W = 1086;
export const PLOT_H = 1448;
const ORIGIN = PLOT_ORIGIN;
export const TW = PLOT_TW;
export const TH = PLOT_TH;

/** Picture point of the grid corner (gx, gy). */
export function corner(gx: number, gy: number): [number, number] {
  return [ORIGIN[0] + (gx - gy) * (TW / 2), ORIGIN[1] + (gx + gy) * (TH / 2)];
}

/** The grid point (fractional) under a picture point — the corner() inverse. */
export function unproject(px: number, py: number): [number, number] {
  const a = (px - ORIGIN[0]) / (TW / 2);
  const b = (py - ORIGIN[1]) / (TH / 2);
  return [(a + b) / 2, (b - a) / 2];
}

export function rhombus(x: number, y: number, w: number, h: number, lift = 0): string {
  const pts = [corner(x, y), corner(x + w, y), corner(x + w, y + h), corner(x, y + h)];
  return pts.map(([px, py]) => `${px.toFixed(1)},${(py - lift).toFixed(1)}`).join(" ");
}

/** The view the plot opens at: the meadow with a strip of the bay above. */
export const HOME_VIEW = { x: 0, y: 250, w: PLOT_W, h: 960 };
export const MIN_VIEW_W = 320;

export type View = { x: number; y: number; w: number; h: number };

/** Zooms the view by `factor` (> 1 — closer) around the picture point (cx, cy), kept inside the picture. */
export function zoomView(view: View, factor: number, cx: number, cy: number): View {
  const w = Math.min(PLOT_W, Math.max(MIN_VIEW_W, view.w / factor));
  const h = w * (HOME_VIEW.h / HOME_VIEW.w);
  const k = w / view.w;
  return clampView({ x: cx - (cx - view.x) * k, y: cy - (cy - view.y) * k, w, h });
}

export function clampView(view: View): View {
  return {
    ...view,
    x: Math.min(PLOT_W - view.w, Math.max(0, view.x)),
    y: Math.min(PLOT_H - view.h, Math.max(0, view.y)),
  };
}

/** Paths join up: which sides of a path cell have no path next to them
 * (n: y−1, e: x+1, s: y+1, w: x−1) — those get a kerb. */
export function pathKerbs(cells: Set<string>, x: number, y: number): { n: boolean; e: boolean; s: boolean; w: boolean } {
  return {
    n: !cells.has(`${x}:${y - 1}`), e: !cells.has(`${x + 1}:${y}`), s: !cells.has(`${x}:${y + 1}`), w: !cells.has(`${x - 1}:${y}`),
  };
}

/** The free spot nearest the plot's centre for thing `id` (as turned), or null. */
export function freeSpot(open: [number, number][], items: Placed[], id: number): [number, number] | null {
  const room = cellSet(open);
  return open.find(([x, y]) => checkLayout(room, items.map((i) => (i.id === id ? { ...i, x, y } : i))) === null) ?? null;
}

/** Back things first: by the front corner, then left to right. */
export function drawOrder<T extends Placed>(items: T[]): T[] {
  return items
    .filter((i) => i.x != null && i.y != null)
    .sort((a, b) => {
      const [aw, ah] = footprint(a);
      const [bw, bh] = footprint(b);
      return (a.x! + aw + a.y! + ah) - (b.x! + bw + b.y! + bh) || a.x! - b.x!;
    });
}

/** Block height of a placeholder (no picture yet). */
export function blockHeight(item: Pick<VillaItem, "code" | "kind" | "level">): number {
  if (item.code === "villa") return 54 + (item.level ?? 1) * 10;
  if (item.code === "garage") return 26 + (item.level ?? 1) * 4;
  if (["palm", "cypress", "olive"].includes(item.code)) return 44;
  if (["pool", "pitch_mini", "helipad"].includes(item.code) || isPath(item.code)) return 3;
  if (item.kind === "car") return 12;
  if (item.code === "lamp") return 34;
  return 18;
}

export const KIND_COLOR: Record<VillaKind, [string, string, string]> = {
  // top, left side, right side
  villa: ["#f6efe2", "#d9cdb8", "#c4b69c"],
  garage: ["#cfd6dd", "#a9b3bd", "#939ea9"],
  car: ["#ffd84d", "#d6ae1f", "#b8940f"],
  yard: ["#7fd08a", "#56a862", "#45904f"],
  premium: ["#ffe08a", "#e0b84a", "#c79d31"],
};

export const CODE_COLOR: Record<string, string> = {
  pool: "#5fd3e8", pitch_mini: "#4fb35d", path: "#e3dccd", helipad: "#9aa3ad",
  palm: "#3f9b4c", cypress: "#2f7a3a", olive: "#7a9a4c", flowers: "#ef8fc0", hedge: "#3d8a46",
};

export const KIND_LABEL: Record<string, string> = {
  car: "🚗 Машины", yard: "🌴 Двор", premium: "⭐ Премиум",
};

export const CAR_EMOJI: Record<string, string> = {
  car_hatch: "🚗", car_jeep: "🚙", car_van: "🚐", car_cabrio: "🚘", car_sport: "🏎️", car_bus: "🚌", car_classic: "🏁",
};
