import { api } from "@/lib/api";
import type { Lineup } from "@/types";

export async function fetchActiveLineup(): Promise<Lineup> {
  const { data } = await api.get<Lineup>("/lineups/active");
  return data;
}

export async function setActiveLineup(slots: { slot_code: string; user_card_id: number }[]): Promise<Lineup> {
  const { data } = await api.put<Lineup>("/lineups/active", { slots });
  return data;
}
