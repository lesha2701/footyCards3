/** «Мой игрок» gear for the 3D free kick and penalty (cosmetic codes from
 * my_player_service.COSMETICS): how the scene draws each one, and its
 * swatch in the style shop. A code missing here (or null) is the default. */

export type BallSkin = { light: string; dark: string; metalness: number; roughness: number };

export const BALL_SKINS: Record<string, BallSkin> = {
  classic: { light: "#f2f2f7", dark: "#101014", metalness: 0, roughness: 0.42 },
  ball_gold: { light: "#f5d36b", dark: "#7a5310", metalness: 0.65, roughness: 0.3 },
  ball_neon: { light: "#d9ff3a", dark: "#0f2a14", metalness: 0, roughness: 0.38 },
  ball_retro: { light: "#c98a4b", dark: "#5a3415", metalness: 0, roughness: 0.6 },
};

export function ballSkin(code: string | null | undefined): BallSkin {
  return (code && BALL_SKINS[code]) || BALL_SKINS.classic;
}

/** Boots: the colour the model's black boots take. */
export const BOOTS: Record<string, string> = {
  boots_red: "#e0312b",
  boots_neon: "#c8f53a",
  boots_gold: "#e6b84a",
};

/** Keeper's gloves; every keeper wears the default pair. */
export const GLOVES: Record<string, string> = {
  default: "#e9eef2",
  gloves_lime: "#b6f03c",
  gloves_pink: "#f25ba8",
  gloves_gold: "#e8b93e",
};

export function glovesColor(code: string | null | undefined): string {
  return (code && GLOVES[code]) || GLOVES.default;
}

/** The style shop's tile for a gear item: an emoji on its colours. */
export function gearSwatch(code: string): { emoji: string; from: string; to: string } | null {
  if (BALL_SKINS[code]) return { emoji: "⚽", from: BALL_SKINS[code].light, to: BALL_SKINS[code].dark };
  if (BOOTS[code]) return { emoji: "👟", from: BOOTS[code], to: "#111827" };
  if (GLOVES[code]) return { emoji: "🧤", from: GLOVES[code], to: "#111827" };
  return null;
}
