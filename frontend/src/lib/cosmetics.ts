import type { CosmeticKind } from "@/types";

/** How each cosmetic `style_key` looks. Purely visual — the backend only
 * stores the key (admin picks it from STYLE_OPTIONS); nothing here touches
 * ratings or matches. Class strings are literal so Tailwind keeps them. */

/** Avatar ring: a gradient behind a 3px padding. */
export const FRAME_STYLES: Record<string, string> = {
  gold: "bg-gradient-to-br from-amber-200 via-amber-400 to-amber-700 shadow-[0_0_14px_rgba(251,191,36,0.45)]",
  neon: "bg-gradient-to-br from-cyan-300 via-fuchsia-400 to-violet-500 shadow-[0_0_16px_rgba(217,70,239,0.55)]",
  fire: "bg-gradient-to-t from-red-600 via-orange-500 to-yellow-300 shadow-[0_0_16px_rgba(249,115,22,0.6)]",
  club_pass: "bg-gradient-to-br from-emerald-300 via-lime-300 to-emerald-600 shadow-[0_0_16px_rgba(132,204,22,0.55)]",
  starter: "bg-gradient-to-br from-sky-300 via-blue-400 to-indigo-500 shadow-[0_0_14px_rgba(96,165,250,0.5)]",
  season: "bg-gradient-to-br from-rose-300 via-purple-400 to-indigo-500 shadow-[0_0_14px_rgba(168,85,247,0.5)]",
  diamond: "bg-gradient-to-br from-fuchsia-300 via-cyan-200 to-violet-500 shadow-[0_0_18px_rgba(103,232,249,0.6)]",
};

/** Profile header backgrounds. */
export const BACKGROUND_STYLES: Record<string, string> = {
  stadium_night: "bg-gradient-to-b from-indigo-950 via-slate-900 to-emerald-950",
  pitch: "bg-gradient-to-b from-emerald-700/70 via-emerald-900/70 to-bg-surface",
  sunset: "bg-gradient-to-b from-orange-500/50 via-rose-700/40 to-bg-surface",
  aurora: "bg-gradient-to-br from-teal-600/50 via-indigo-800/50 to-fuchsia-800/40",
  gold_rush: "bg-gradient-to-b from-amber-500/40 via-yellow-900/40 to-bg-surface",
};

/** Card frame skins: an extra outline around the player's own cards. */
export const CARD_SKIN_STYLES: Record<string, string> = {
  chrome: "ring-2 ring-slate-200/80 shadow-[0_0_10px_rgba(226,232,240,0.45)]",
  holo: "ring-2 ring-fuchsia-300/80 shadow-[0_0_12px_rgba(232,121,249,0.55)]",
  gold: "ring-2 ring-amber-300/90 shadow-[0_0_10px_rgba(252,211,77,0.5)]",
  emerald: "ring-2 ring-emerald-300/80 shadow-[0_0_10px_rgba(110,231,183,0.5)]",
};

export const STYLE_OPTIONS: Record<CosmeticKind, string[]> = {
  profile_frame: Object.keys(FRAME_STYLES),
  profile_background: Object.keys(BACKGROUND_STYLES),
  card_skin: Object.keys(CARD_SKIN_STYLES),
};

export const KIND_LABELS: Record<CosmeticKind, string> = {
  profile_frame: "Рамки профиля",
  profile_background: "Фоны профиля",
  card_skin: "Скины карточек",
};

export function frameClass(styleKey: string | null | undefined): string | null {
  return styleKey ? FRAME_STYLES[styleKey] ?? null : null;
}

export function backgroundClass(styleKey: string | null | undefined): string | null {
  return styleKey ? BACKGROUND_STYLES[styleKey] ?? null : null;
}

export function cardSkinClass(styleKey: string | null | undefined): string | null {
  return styleKey ? CARD_SKIN_STYLES[styleKey] ?? null : null;
}
