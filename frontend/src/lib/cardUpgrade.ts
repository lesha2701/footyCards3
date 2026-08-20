import type { CardUpgradeRule } from "@/types";

// Mirrors the backend's _effective_success_chance (card_upgrade_service.py)
// — purely for a live UI preview before the request lands, the server is
// the actual source of truth for what chance gets used.
export function effectiveUpgradeChance(rule: CardUpgradeRule, cardCount: number): number {
  const base = rule.success_chance + Math.max(0, cardCount - 1) * rule.extra_card_bonus;
  return Math.min(rule.max_success_chance, base);
}
