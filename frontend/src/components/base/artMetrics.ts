/** Geometry shared by the «Клубная база» map and its building art. */

export const DX = 8;
export const DY = 6;

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

/** How tall the drawn building is (for the crane and the level badge). */
export function artHeight(code: string, level: number): number {
  switch (code) {
    case "hq": return 7 + (2 + Math.ceil(level / 2)) * 6 + 2 + 14;
    case "hotel": return (2 + Math.ceil(level * 0.6)) * 5.5 + 4;
    case "training": return 8 + level * 1.4 + 18;
    case "medical": return (1 + Math.ceil(level / 2.5)) * 6 + 8;
    case "analytics": return 12 + level * 2.6 + 6;
    case "media": return 12 + level * 2.2 + 8;
    case "marketing": return 10 + level * 2.2 + 18;
    case "shop": return 12 + level * 1.8 + 4;
    case "accounting": return 12 + level * 1.8 + 7;
    default: return 30;
  }
}
