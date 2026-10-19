/** Isometric (2:1 dimetric) projection of the «Клубная база» map.
 *
 * World: a square ground of GRID×GRID units; x grows to the screen's
 * lower-right, y to the lower-left, z up. One ground unit is ISO_C px
 * across and ISO_S px down per axis; one height unit is ISO_Z px. The
 * viewer looks from +x/+y, so the faces at x+w ("right") and y+d ("left")
 * of a box are the visible walls. */

export const GRID = 26;
export const ISO_C = 360 / (2 * GRID);
export const ISO_S = ISO_C / 2;
export const ISO_Z = 5.2;
export const ISO_OX = 180;
export const ISO_OY = 50;
export const VIEW_W = 360;
export const VIEW_H = Math.ceil(ISO_OY + 2 * GRID * ISO_S + 6);

export type Pt = [number, number];

export function pt(x: number, y: number, z = 0): Pt {
  return [ISO_OX + (x - y) * ISO_C, ISO_OY + (x + y) * ISO_S - z * ISO_Z];
}

export function pts(points: Pt[]): string {
  return points.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(" ");
}

/** A circle of radius r on a horizontal plane, projected: ellipse radii. */
export function ellipseR(r: number): [number, number] {
  return [r * ISO_C * Math.SQRT2, r * ISO_S * Math.SQRT2];
}

/** Lighter (f > 1) or darker (f < 1) shade of a #rrggbb colour. */
export function shade(hex: string, f: number): string {
  const n = parseInt(hex.slice(1), 16);
  const ch = (v: number) => {
    const out = f >= 1 ? v + (255 - v) * (f - 1) : v * f;
    return Math.max(0, Math.min(255, Math.round(out)));
  };
  const r = ch((n >> 16) & 255);
  const g = ch((n >> 8) & 255);
  const b = ch(n & 255);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

/** Point on the visible "left" wall (plane y = y0) of a box: u along x, v up. */
export function onLeft(x0: number, y0: number, z0: number, u: number, v: number): Pt {
  return pt(x0 + u, y0, z0 + v);
}

/** Point on the visible "right" wall (plane x = x0): u along y, v up. */
export function onRight(x0: number, y0: number, z0: number, u: number, v: number): Pt {
  return pt(x0, y0 + u, z0 + v);
}
