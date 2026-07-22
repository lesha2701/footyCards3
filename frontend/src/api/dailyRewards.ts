import { api } from "@/lib/api";
import type { DailyRewardCalendar, DailyRewardClaimResult } from "@/types";

export async function fetchDailyRewardCalendar(): Promise<DailyRewardCalendar> {
  const { data } = await api.get<DailyRewardCalendar>("/daily-rewards/calendar");
  return data;
}

export async function claimDailyReward(): Promise<DailyRewardClaimResult> {
  const { data } = await api.post<DailyRewardClaimResult>("/daily-rewards/claim");
  return data;
}
