import { useQuery } from "@tanstack/react-query";

import { fetchAnniversary, fetchAnniversaryRecap } from "@/api/anniversary";
import type { AnniversaryCommunity, AnniversaryState, RewardBundle } from "@/types";

/** «💯 Нам 100 дней!» art: drop files into src/assets/anniversary/ with these
 *  names (banner, recap-bg, gift, gift-final, badge-100 — .webp/.png) and they
 *  replace the drawn placeholders without code changes. */
const ART = import.meta.glob<string>("@/assets/anniversary/*.{webp,png}", { eager: true, import: "default" });

export function anniversaryArt(name: string): string | undefined {
  return ART[`/src/assets/anniversary/${name}.webp`] ?? ART[`/src/assets/anniversary/${name}.png`];
}

export const ANNIVERSARY_QUERY_KEY = ["anniversary"] as const;
export const ANNIVERSARY_RECAP_QUERY_KEY = ["anniversary", "recap"] as const;

export function useAnniversary(options: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: ANNIVERSARY_QUERY_KEY,
    queryFn: fetchAnniversary,
    staleTime: 30_000,
    refetchInterval: options.poll ? 60_000 : false,
    retry: false,
  });
}

export function useAnniversaryRecap(enabled = true) {
  return useQuery({
    queryKey: ANNIVERSARY_RECAP_QUERY_KEY,
    queryFn: fetchAnniversaryRecap,
    staleTime: 10 * 60_000,
    enabled,
    retry: false,
  });
}

/** What the home screen shows: the teaser before the start, the party while
 *  it runs, and the leftovers while rewards can still be taken. */
export function anniversaryPhase(
  state: AnniversaryState | undefined,
  now = Date.now(),
): "teaser" | "live" | "leftovers" | null {
  if (!state?.enabled) return null;
  if (state.active) return "live";
  const start = state.starts_at ? new Date(state.starts_at).getTime() : 0;
  if (!state.finished && start > now && start - now <= state.teaser_days * 86_400_000) return "teaser";
  if (state.finished && state.community?.claimable) return "leftovers";
  return null;
}

/** Anything waiting to be taken right now. */
export function anniversaryClaimable(state: AnniversaryState | undefined): number {
  if (!state?.active && !state?.finished) return 0;
  return (state.active && state.calendar_ready ? 1 : 0)
    + (state.community?.claimable ? 1 : 0)
    + (state.active && !state.recap_claimed && state.recap_coins > 0 ? 1 : 0);
}

/** Progress of the community goal, 0–100 with one decimal. */
export function communityPct(c: AnniversaryCommunity | null | undefined): number {
  if (!c || c.goal <= 0) return 0;
  return Math.min(100, Math.round((c.total * 1000) / c.goal) / 10);
}

/** The reward slot in a few words: «500 💰», «эпик-карта», «пак», «значок». */
export function bundleLabel(b: RewardBundle): string {
  const parts: string[] = [];
  if (b.coins) parts.push(`${b.coins.toLocaleString("ru-RU")} 💰`);
  if (b.card_rarity) parts.push(`${RARITY_SHORT[b.card_rarity] ?? b.card_rarity}-карта`);
  if (b.pack_name) parts.push(`пак «${b.pack_name}»`);
  if (b.badge) parts.push(`значок ${b.badge.icon}`);
  if (b.cosmetic) parts.push(b.cosmetic.name);
  return parts.join(" + ") || "сюрприз";
}

export function bundleEmoji(b: RewardBundle): string {
  if (b.badge) return b.badge.icon || "💯";
  if (b.pack_name) return "🎴";
  if (b.card_rarity) return "🃏";
  return "💰";
}

const RARITY_SHORT: Record<string, string> = {
  common: "обычная",
  rare: "редкая",
  epic: "эпик",
  legendary: "легенда",
  diamond: "алмаз",
};

/** «день / дня / дней». */
export function daysWord(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "дня";
  return "дней";
}
