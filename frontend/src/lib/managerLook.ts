/** The club colour theme: Tailwind gradient classes of the club header and card. */
export const THEMES: Record<string, string> = {
  night: "from-accent-lime/15 via-bg-surface to-bg-surface",
  ocean: "from-sky-500/30 via-blue-900/40 to-bg-surface",
  forest: "from-emerald-500/30 via-green-900/40 to-bg-surface",
  sunset: "from-orange-500/35 via-rose-700/30 to-bg-surface",
  royal: "from-violet-500/35 via-indigo-900/40 to-bg-surface",
  gold: "from-amber-400/40 via-yellow-800/30 to-bg-surface",
};

export function themeClass(theme: string | undefined): string {
  return THEMES[theme ?? "night"] ?? THEMES.night;
}

/** Share-card frame colours (same as the server's share_card_service.MANAGER_FRAMES). */
export const FRAME_COLORS: Record<string, string> = {
  classic: "#c6e63a", retro: "#f59e0b", neon: "#22d3ee", gold: "#facc15",
  ruby: "#e11d48", ice: "#7dd3fc", fire: "#f97316", galaxy: "#8b5cf6",
};
