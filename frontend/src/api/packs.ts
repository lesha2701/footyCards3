import { api } from "@/lib/api";
import type { Pack, PackOpenResult } from "@/types";

export async function fetchPacks(): Promise<Pack[]> {
  const { data } = await api.get<Pack[]>("/packs");
  return data;
}

export async function openPack(packId: number, idempotencyKey: string): Promise<PackOpenResult> {
  const { data } = await api.post<PackOpenResult>(`/packs/${packId}/open`, { idempotency_key: idempotencyKey });
  return data;
}
