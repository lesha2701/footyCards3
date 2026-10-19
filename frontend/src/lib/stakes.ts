import { useQuery } from "@tanstack/react-query";

import { fetchFeatureFlags } from "@/api/featureFlags";

/** Largest stake per side in open chat challenges (Тактико, Стратего,
 * Пенальти) from the admin config; 0 = stakes are off, undefined = loading.
 * The server enforces it (stake_guard_service) — this only guides the input. */
export function useStakeMax(): number | undefined {
  const { data } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags });
  return data?.stake_max_coins;
}

export function stakeLabel(maxStake: number | undefined): string {
  if (maxStake === 0) return "Ставки сейчас отключены — вызов будет без ставки";
  if (maxStake) return `Ставка, монеты (0 — без ставки, максимум ${maxStake})`;
  return "Ставка, монеты (0 — без ставки)";
}

export function clampStake(raw: string, maxStake: number | undefined): number {
  const value = Math.max(0, Math.floor(Number(raw) || 0));
  return maxStake === undefined ? value : Math.min(maxStake, value);
}
