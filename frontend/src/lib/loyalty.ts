import { useQuery } from "@tanstack/react-query";

import { fetchLoyaltyStatus } from "@/api/loyalty";

export function useLoyaltyStatus() {
  return useQuery({ queryKey: ["loyalty-status"], queryFn: fetchLoyaltyStatus, staleTime: 60_000 });
}

/** Clock time a streak save ends at, e.g. «до 21:40». */
export function saveDeadline(until: string): string {
  return new Date(until).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

/** Where the progress bar puts a milestone (0–100 %). */
export function milestonePct(days: number, goal: number): number {
  return Math.max(0, Math.min(100, Math.round((days / goal) * 100)));
}
