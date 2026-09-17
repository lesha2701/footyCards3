import { api } from "@/lib/api";
import type { Pack, PackBulkOpenResult, PackOpenResult, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export async function fetchPacks(): Promise<Pack[]> {
  const { data } = await api.get<Pack[]>("/packs");
  return data;
}

export async function openPack(packId: number, idempotencyKey: string): Promise<PackOpenResult> {
  const { data } = await api.post<PackOpenResult>(`/packs/${packId}/open`, { idempotency_key: idempotencyKey });
  return data;
}

export async function openPackBulk(packId: number, quantity: number, idempotencyKey: string): Promise<PackBulkOpenResult> {
  const { data } = await api.post<PackBulkOpenResult>(`/packs/${packId}/open-bulk`, {
    quantity, idempotency_key: idempotencyKey,
  });
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
