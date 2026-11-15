/**
 * «Моя вилла»: the isometric plot. A square grid of `grid` cells a side is
 * drawn as a rhombus: cell (x, y) has its top corner at
 * ((x − y)·TW/2, (x + y)·TH/2). A thing of w×h cells (h×w when turned) at
 * (x, y) covers x…x+w−1, y…y+h−1 — the same rule as the server's
 * town_villa_service.check_layout.
 *
 * Sprites: `assets/town/villa/<code>.webp` (the villa and the garage by level:
 * villa_1…villa_5, garage_1…garage_3), cut out, facing bottom-left, drawn with
 * their bottom on the footprint's front corner. Until a picture exists the
 * thing is drawn as a coloured block with its emoji.
 */
import type { VillaItem, VillaKind } from "@/api/town";

export const TW = 64;
export const TH = 32;
/** Room above the back row for tall things. */
export const HEADROOM = 150;

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

/** Screen point of a grid corner (gx, gy), the plot's top corner at (grid·TW/2, HEADROOM). */
export function corner(grid: number, gx: number, gy: number): [number, number] {
  return [grid * (TW / 2) + (gx - gy) * (TW / 2), HEADROOM + (gx + gy) * (TH / 2)];
}

export function rhombus(grid: number, x: number, y: number, w: number, h: number, lift = 0): string {
  const pts = [corner(grid, x, y), corner(grid, x + w, y), corner(grid, x + w, y + h), corner(grid, x, y + h)];
  return pts.map(([px, py]) => `${px},${py - lift}`).join(" ");
}

export function viewBox(grid: number): { width: number; height: number } {
  return { width: grid * TW, height: HEADROOM + grid * TH + 8 };
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
