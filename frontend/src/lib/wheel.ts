import type { Rarity, WheelPrize } from "@/types";

/** Shared helpers for the prize wheels («Колесо фортуны» and the «21»
 * golden/jackpot reward wheels) — see components/wheel/WheelReel.tsx. */

export type WheelTheme = "regular" | "golden" | "jackpot";

export const WHEEL_SPIN_MS = 2600;

// Fisher-Yates — callers memoize the result per distinct prize set so the
// reel's visual order stays stable across spins within a session.
export function shuffle<T>(items: T[]): T[] {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

const RARITY_PRIZE_LABELS: Record<Rarity, string> = {
  common: "Обычная карта",
  rare: "Редкая карта",
  epic: "Эпическая карта",
  legendary: "Легендарная карта",
  diamond: "Бриллиантовая карта",
};

export function prizeLabel(prize: WheelPrize): string {
  if (prize.prize_type === "coins") return `+${prize.coins_amount} монет`;
  if (prize.prize_type === "pack") return prize.pack?.name ?? "Пак";
  if (prize.prize_type === "card_rarity") return RARITY_PRIZE_LABELS[prize.card_rarity ?? "rare"];
  return prize.badge?.name ?? "Значок";
}

/** Chance of each prize as shown to players — the server sends only active
 * prizes of one pool, and rolls by relative weight among exactly those. */
export function prizeOdds(prizes: WheelPrize[]): { prize: WheelPrize; percent: number }[] {
  const total = prizes.reduce((sum, p) => sum + p.weight, 0);
  if (!total) return [];
  return [...prizes]
    .sort((a, b) => b.weight - a.weight)
    .map((prize) => ({ prize, percent: (prize.weight / total) * 100 }));
}

export function formatPercent(percent: number): string {
  if (percent >= 10) return `${Math.round(percent)}%`;
  if (percent >= 1) return `${percent.toFixed(1)}%`;
  return `${percent.toFixed(2)}%`;
}

const GLYPH_BG: Record<Exclude<WheelPrize["prize_type"], "card_rarity">, string> = {
  coins: "bg-accent-lime/12 text-accent-lime",
  pack: "bg-accent/12 text-accent",
  badge: "bg-amber-400/12 text-amber-300",
};

// Matches this rarity's actual color language (see lib/rarity.ts's
// RARITY_TEXT/RARITY_GRADIENTS) instead of a fixed color for every
// card_rarity prize regardless of which rarity it actually rolls.
const RARITY_GLYPH_BG: Record<Rarity, string> = {
  common: "bg-slate-400/12 text-slate-300",
  rare: "bg-blue-500/12 text-blue-400",
  epic: "bg-purple-500/12 text-purple-400",
  legendary: "bg-amber-400/12 text-amber-400",
  diamond: "bg-cyan-400/12 text-cyan-300",
};

export function glyphBgClass(prize: WheelPrize): string {
  if (prize.prize_type === "card_rarity") return RARITY_GLYPH_BG[prize.card_rarity ?? "common"];
  return GLYPH_BG[prize.prize_type];
}
