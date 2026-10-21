import type { ManagerLook } from "@/api/manager";

const KIT_BG: Record<string, (a: string, b: string) => string> = {
  plain: (a) => a,
  stripes: (a, b) => `repeating-linear-gradient(90deg, ${a} 0 8px, ${b} 8px 16px)`,
  hoops: (a, b) => `repeating-linear-gradient(0deg, ${a} 0 8px, ${b} 8px 16px)`,
  pinstripes: (a, b) => `repeating-linear-gradient(90deg, ${a} 0 6px, ${b} 6px 7px)`,
  halves: (a, b) => `linear-gradient(90deg, ${a} 50%, ${b} 50%)`,
  quarters: (a, b) => `conic-gradient(${a} 0 25%, ${b} 0 50%, ${a} 0 75%, ${b} 0)`,
  sash: (a, b) => `linear-gradient(135deg, ${a} 40%, ${b} 40% 60%, ${a} 60%)`,
  chevron: (a, b) => `conic-gradient(from 225deg at 50% 40%, ${b} 0 90deg, ${a} 0)`,
  checks: (a, b) => `repeating-conic-gradient(${a} 0 25%, ${b} 0 50%) 0 0 / 12px 12px`,
  gradient: (a, b) => `linear-gradient(180deg, ${a}, ${b})`,
};

/** CSS background of the club kit (pattern + two colours). */
export function kitBackground(look: Pick<ManagerLook, "kit" | "kit_color" | "kit_color2">): string {
  return (KIT_BG[look.kit] ?? KIT_BG.plain)(look.kit_color, look.kit_color2);
}

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
