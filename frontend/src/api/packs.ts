import { api } from "@/lib/api";
import type { Pack, PackOpenResult, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export async function fetchPacks(): Promise<Pack[]> {
  const { data } = await api.get<Pack[]>("/packs");
  return data;
}

export async function openPack(packId: number, idempotencyKey: string): Promise<PackOpenResult> {
  const { data } = await api.post<PackOpenResult>(`/packs/${packId}/open`, { idempotency_key: idempotencyKey });
  return data;
}

export async function createStarsInvoice(packId: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/packs/${packId}/stars-invoice`);
  return data;
}

export async function fetchStarsInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/packs/stars-invoices/${payloadToken}`);
  return data;
}
