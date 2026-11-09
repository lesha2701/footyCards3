import { api } from "@/lib/api";
import type { LoyaltyStatus, StarsInvoiceCreate } from "@/types";

export async function fetchLoyaltyStatus(): Promise<LoyaltyStatus> {
  const { data } = await api.get<LoyaltyStatus>("/loyalty/status");
  return data;
}

export async function restoreStreakFree(): Promise<{ streak: number }> {
  const { data } = await api.post<{ streak: number }>("/loyalty/streak-save/free");
  return data;
}

export async function createStreakSaveInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/loyalty/streak-save/stars-invoice");
  return data;
}
