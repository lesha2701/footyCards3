/** Geometry shared by the «Клубная база» map and its building art. */

/** The drawings are made for 10 visual steps; a building with any number
 * of levels (25 by default) maps onto them — the top level always looks
 * like the finished landmark. */
export function visualLevel(level: number, maxLevel: number): number {
  if (level <= 0) return 0;
  if (level >= maxLevel) return 10;
  return Math.min(9, Math.max(1, Math.ceil((level * 10) / Math.max(1, maxLevel))));
}

export function tier(level: number): 0 | 1 | 2 | 3 {
  if (level >= 10) return 3;
  if (level >= 7) return 2;
  if (level >= 4) return 1;
  return 0;
}

/** Height (iso z units) of the top of a drawn building at a visual level —
 * where the crane and the level badge go. Mirrors BaseArt.tsx. */
export function topZ(code: string, vl: number): number {
  switch (code) {
    case "hq": return 0.8 + 1.6 + vl * 0.5 + 2;
    case "hotel": return 1.6 + vl * 0.55;
    case "training": return 0.8 + vl * 0.1 + 1;
    case "medical": return 1.2 + vl * 0.32;
    case "analytics": return 1.4 + vl * 0.38 + 0.8;
    case "media": return 1.2 + vl * 0.3 + 1;
    case "marketing": return 1 + vl * 0.25 + 2;
    case "shop": return 1 + vl * 0.22;
    case "accounting": return 1.15 + vl * 0.22 + 0.6;
    case "academy": return 0.9 + vl * 0.28;
    default: return 2;
  }
}
