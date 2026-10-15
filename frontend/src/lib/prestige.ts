/** «Академия» prestige tiers (1 = Бронза … 4 = Икона by default). Status
 * only: the colours/marks below, never a rating change. Names come from the
 * server (admin-editable); these are just the per-tier styles. */
const TIER_STYLES = [
  { mark: "text-amber-600", chip: "bg-amber-700/30 text-amber-500" },
  { mark: "text-slate-200", chip: "bg-slate-300/20 text-slate-200" },
  { mark: "text-amber-300", chip: "bg-amber-300/20 text-amber-300" },
  { mark: "text-fuchsia-300", chip: "bg-gradient-to-r from-fuchsia-400/30 via-cyan-300/30 to-amber-300/30 text-fuchsia-200" },
];

export function prestigeStyle(tier: number) {
  return TIER_STYLES[Math.max(0, Math.min(tier, TIER_STYLES.length) - 1)];
}

export function prestigeMarks(tier: number): string {
  return "◆".repeat(Math.max(0, tier));
}

/** Top tier («Икона»): an animated holo frame instead of the stage frame. */
export const ICON_FRAME =
  "from-fuchsia-400 via-cyan-300 to-amber-300 shadow-glow-diamond bg-[length:100%_400%] motion-safe:animate-diamond-shimmer";

export function isIconTier(tier: number | undefined, maxTier = 4): boolean {
  return !!tier && tier >= maxTier;
}
