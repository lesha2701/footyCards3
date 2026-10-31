import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";

import { fetchFanBattle } from "@/api/fanBattle";
import type { FanBattleState, FanSide } from "@/types";

/** «⚔️ Битва фанатов» art: drop files into src/assets/fans/ with these names
 *  (banner, side-<code> e.g. side-fire / side-ice, badge-fan, badge-champion —
 *  .webp/.png) and they replace the drawn placeholders without code changes. */
const ART = import.meta.glob<string>("@/assets/fans/*.{webp,png}", { eager: true, import: "default" });

export function fanArt(name: string): string | undefined {
  return ART[`/src/assets/fans/${name}.webp`] ?? ART[`/src/assets/fans/${name}.png`];
}

export const FAN_BATTLE_QUERY_KEY = ["fan-battle"] as const;

export function useFanBattle(options: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: FAN_BATTLE_QUERY_KEY,
    queryFn: fetchFanBattle,
    staleTime: 30_000,
    refetchInterval: options.poll ? 30_000 : false,
    retry: false,
  });
}

/** What the home screen shows: the teaser before the start, the battle
 *  while it runs, and the results while rewards are still to be taken. */
export function fanBattlePhase(
  state: FanBattleState | undefined,
  now = Date.now(),
): "teaser" | "live" | "results" | null {
  if (!state?.enabled) return null;
  if (state.active) return "live";
  const start = state.starts_at ? new Date(state.starts_at).getTime() : 0;
  if (!state.finished && start > now && start - now <= state.teaser_days * 86_400_000) return "teaser";
  if (state.finished && state.my_side && state.claimable > 0) return "results";
  return null;
}

/** Share of the first side in the points tug-of-war, 0–100 (50 when nobody scored). */
export function tugShare(a: number, b: number): number {
  const total = a + b;
  return total > 0 ? Math.round((a * 1000) / total) / 10 : 50;
}

export function sideByCode(sides: FanSide[], code: string | null | undefined): FanSide | undefined {
  return sides.find((s) => s.code === code);
}

/** «очко / очка / очков». */
export function pointsWord(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "очко";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "очка";
  return "очков";
}

/** The colour of the viewer's side — the frame of «Капитаны» cards. */
export const FanColorContext = createContext<string | null>(null);

export function useFanColor(): string | null {
  return useContext(FanColorContext);
}
