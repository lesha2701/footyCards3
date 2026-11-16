/**
 * «Моя вилла»: the plot. A square grid of grid_max cells a side lies on the
 * lawn of the plot picture (corner(): the lawn in perspective, cell (0, 0)
 * at the back); the villa's level opens grid × grid of it from the back
 * corner, the rest is locked. A thing of w×h cells (h×w when turned) at
 * (x, y) covers x…x+w−1, y…y+h−1 — the same rule as the server's
 * town_villa_service.check_layout.
 *
 * Sprites: `assets/town/villa/<code>.webp` (the villa and the garage by level:
 * villa_1…villa_5, garage_1…garage_3), cut out, facing bottom-left, drawn with
 * their bottom on the footprint's front corner. Until a picture exists the
 * thing is drawn as a coloured block with its emoji.
 */
import type { VillaItem, VillaKind } from "@/api/town";

const ART = import.meta.glob<string>("@/assets/town/villa/*.webp", { eager: true, import: "default" });
const artUrl = (name: string): string | undefined => ART[`/src/assets/town/villa/${name}.webp`];

export function spriteOf(item: Pick<VillaItem, "code" | "level">): string | undefined {
  if (item.code === "villa" || item.code === "garage") return artUrl(`${item.code}_${item.level ?? 1}`) ?? artUrl(item.code);
  return artUrl(item.code);
}

export const plotArt = (): string | undefined => artUrl("plot");

export type Placed = { id: number; code: string; x: number | null; y: number | null; rot: number; w: number; h: number };

export function footprint(item: { w: number; h: number; rot: number }): [number, number] {
  return item.rot ? [item.h, item.w] : [item.w, item.h];
}

/** null when everything fits, else why not (the server checks the same). */
export function checkLayout(grid: number, items: Placed[]): string | null {
  const taken = new Set<string>();
  for (const it of items) {
    if (it.x == null || it.y == null) {
      if (it.code === "villa" || it.code === "garage") return "Виллу и гараж нельзя убрать на склад";
      continue;
    }
    const [w, h] = footprint(it);
    if (it.x < 0 || it.y < 0 || it.x + w > grid || it.y + h > grid) return "Предмет выходит за участок";
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

/** The plot picture (assets/town/villa/plot.webp) and its lawn: a quad
 * T(op) → R(ight) → B(ottom) → L(eft) in picture pixels (the walls' lines,
 * L and R lie past the picture's edges). The grid fills the lawn's
 * [INSET, 1 − INSET] part, so it keeps clear of the walls and the gate. */
export const PLOT_W = 900;
export const PLOT_H = 1200;
const LAWN = { T: [450, 305], R: [987, 589], B: [450, 983], L: [-87, 589] } as const;
const INSET = 0.11;

function lawnPoint(u: number, v: number): [number, number] {
  const { T, R, B, L } = LAWN;
  const k = [(1 - u) * (1 - v), u * (1 - v), u * v, (1 - u) * v];
  return [k[0] * T[0] + k[1] * R[0] + k[2] * B[0] + k[3] * L[0], k[0] * T[1] + k[1] * R[1] + k[2] * B[1] + k[3] * L[1]];
}

const toLawn = (grid: number, g: number) => INSET + (1 - 2 * INSET) * (g / grid);

/** Picture point of the grid corner (gx, gy), (0, 0) the plot's back corner;
 * `grid` is the whole lawn's cells a side (grid_max). */
export function corner(grid: number, gx: number, gy: number): [number, number] {
  return lawnPoint(toLawn(grid, gx), toLawn(grid, gy));
}

/** The grid point (fractional) under a picture point — the corner() inverse. */
export function unproject(grid: number, px: number, py: number): [number, number] {
  let u = 0.5;
  let v = 0.5;
  for (let i = 0; i < 12; i++) {
    const [x, y] = lawnPoint(u, v);
    const e = 1e-4;
    const [xu, yu] = lawnPoint(u + e, v);
    const [xv, yv] = lawnPoint(u, v + e);
    const a = (xu - x) / e, b = (xv - x) / e, c = (yu - y) / e, d = (yv - y) / e;
    const det = a * d - b * c || 1e-9;
    const dx = px - x;
    const dy = py - y;
    u += (d * dx - b * dy) / det;
    v += (a * dy - c * dx) / det;
  }
  const back = (t: number) => ((t - INSET) / (1 - 2 * INSET)) * grid;
  return [back(u), back(v)];
}

export function rhombus(grid: number, x: number, y: number, w: number, h: number, lift = 0): string {
  const pts = [corner(grid, x, y), corner(grid, x + w, y), corner(grid, x + w, y + h), corner(grid, x, y + h)];
  return pts.map(([px, py]) => `${px.toFixed(1)},${(py - lift).toFixed(1)}`).join(" ");
}

/** The view the plot opens at: the lawn with a strip of sea and the gate. */
export const HOME_VIEW = { x: 0, y: 170, w: PLOT_W, h: 860 };
export const MIN_VIEW_W = 280;

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

/** The free spot nearest the open plot's middle for thing `id` (as turned), or null. */
export function freeSpot(grid: number, items: Placed[], id: number): [number, number] | null {
  const mid = (grid - 1) / 2;
  const spots: [number, number][] = [];
  for (let y = 0; y < grid; y++) for (let x = 0; x < grid; x++) spots.push([x, y]);
  spots.sort((a, b) => Math.hypot(a[0] - mid, a[1] - mid) - Math.hypot(b[0] - mid, b[1] - mid));
  return spots.find(([x, y]) => checkLayout(grid, items.map((i) => (i.id === id ? { ...i, x, y } : i))) === null) ?? null;
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
  if (["pool", "pitch_mini", "path", "helipad"].includes(item.code)) return 3;
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
