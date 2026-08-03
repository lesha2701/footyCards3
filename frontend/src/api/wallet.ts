import { api } from "@/lib/api";
import type { StarsCoinRate, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export async function fetchStarsCoinRate(): Promise<StarsCoinRate> {
  const { data } = await api.get<StarsCoinRate>("/wallet/stars-coin-rate");
  return data;
}

export async function createCoinInvoice(starsAmount: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/wallet/stars-invoice", { stars_amount: starsAmount });
  return data;
}

export async function fetchCoinInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/wallet/stars-invoices/${payloadToken}`);
  return data;
}
