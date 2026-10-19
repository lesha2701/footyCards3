import { RARITY_LABELS, RARITY_ORDER } from "@/lib/rarity";
import type { Pack, Rarity } from "@/types";

export const ODDS_COLORS: Record<Rarity, string> = {
  common: "bg-slate-400",
  rare: "bg-blue-500",
  epic: "bg-purple-500",
  legendary: "bg-amber-400",
  diamond: "bg-cyan-300",
};

/** «Академия» pack: its diamond slot is a path card. */
export function isPathSlot(pack: Pack, rarity: Rarity) {
  return pack.player_pool === "path" && rarity === "diamond";
}

export function oddsColor(pack: Pack, rarity: Rarity) {
  return isPathSlot(pack, rarity) ? "bg-emerald-400" : ODDS_COLORS[rarity];
}

export function rarityLabel(pack: Pack, rarity: Rarity) {
  return isPathSlot(pack, rarity) ? "🌱 Академия" : RARITY_LABELS[rarity];
}

/** Chances common → rarest. */
export function sortedOdds(pack: Pack) {
  return [...pack.rarity_probabilities].sort((a, b) => RARITY_ORDER[a.rarity] - RARITY_ORDER[b.rarity]);
}

export function pct(probability: number) {
  const v = probability * 100;
  return v >= 1 || v === 0 ? `${Math.round(v)}%` : `${v.toFixed(1)}%`;
}

/** The rarest slot with a real chance — the headline «Легендарная 3%». */
export function topChance(pack: Pack) {
  const odds = sortedOdds(pack).filter((rp) => rp.probability > 0);
  return odds[odds.length - 1] ?? null;
}

/** Can't be bought now: switched off, out of its window or over the limit. */
export function packBlocked(pack: Pack) {
  return !pack.is_available_now || (pack.purchase_limit_per_user !== null && pack.user_purchase_count >= pack.purchase_limit_per_user);
}

/** How many more the player may buy (null = no limit). */
export function packRemaining(pack: Pack) {
  return pack.purchase_limit_per_user !== null ? Math.max(0, pack.purchase_limit_per_user - pack.user_purchase_count) : null;
}

/** «2 дн.», «5 ч», «40 мин» until a limited pack leaves the shop; null for
 * packs without an end date or ending more than a week away. */
export function packEndsIn(pack: Pack, now = Date.now()): string | null {
  if (!pack.available_until) return null;
  const ms = new Date(pack.available_until).getTime() - now;
  if (ms <= 0 || ms > 7 * 86_400_000) return null;
  if (ms >= 86_400_000) return `${Math.floor(ms / 86_400_000)} дн.`;
  if (ms >= 3_600_000) return `${Math.floor(ms / 3_600_000)} ч`;
  return `${Math.max(1, Math.floor(ms / 60_000))} мин`;
}

/** What opening `quantity` coin packs costs — the server's ×10 discount
 * (Pack.bulk10_discount_pct) applied the same way, rounded for the player.
 * Informative only: the server charges. */
export function packTotal(pack: Pack, quantity: number): number {
  const gross = pack.price * quantity;
  const pct = quantity >= 10 ? pack.bulk10_discount_pct ?? 0 : 0;
  return gross - Math.floor((gross * pct) / 100);
}

/** «1 пак», «3 пака», «7 паков». */
export function packsWord(n: number): string {
  const d = n % 10;
  const dd = n % 100;
  if (d === 1 && dd !== 11) return "пак";
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return "пака";
  return "паков";
}
