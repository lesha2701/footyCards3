import { api } from "@/lib/api";
import type { CalendarClaimResult, LoginCalendar, StarsInvoiceCreate } from "@/types";

/** «Календарь наград» — the monthly login calendar. */
export async function fetchDailyRewardCalendar(): Promise<LoginCalendar> {
  const { data } = await api.get<LoginCalendar>("/daily-rewards/calendar");
  return data;
}

export async function claimDailyReward(): Promise<CalendarClaimResult> {
  const { data } = await api.post<CalendarClaimResult>("/daily-rewards/claim");
  return data;
}

/** Catch up a missed day of this month for coins — or, `free`, with one of
 * the club pass's free catch-ups. */
export async function catchUpDay(date: string, free = false): Promise<CalendarClaimResult> {
  const { data } = await api.post<CalendarClaimResult>("/daily-rewards/catch-up", { date, free });
  return data;
}

export async function createCatchUpStarsInvoice(date: string): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/daily-rewards/catch-up/stars-invoice", { date });
  return data;
}
