import { api } from "@/lib/api";
import type { WeeklyTopAward, WeeklyTopInfo } from "@/types";

export async function fetchWeeklyTopAwards(): Promise<WeeklyTopAward[]> {
  const { data } = await api.get<WeeklyTopAward[]>("/weekly-top/awards");
  return data;
}

export async function markWeeklyTopSeen(ids: number[]): Promise<void> {
  await api.post("/weekly-top/awards/seen", { ids });
}

export async function fetchWeeklyTopInfo(): Promise<WeeklyTopInfo> {
  const { data } = await api.get<WeeklyTopInfo>("/weekly-top/info");
  return data;
}
