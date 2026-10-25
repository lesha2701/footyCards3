import { api } from "@/lib/api";
import type { RankingMetric, WeeklyTopAward, WeeklyTopHall, WeeklyTopInfo } from "@/types";

/** «Зал славы»: last paid week's podium of one ranking. */
export async function fetchWeeklyTopHall(metric: RankingMetric): Promise<WeeklyTopHall> {
  const { data } = await api.get<WeeklyTopHall>("/weekly-top/hall", { params: { metric } });
  return data;
}

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
