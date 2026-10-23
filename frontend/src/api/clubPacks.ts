import { api } from "@/lib/api";
import type { ClubPack, ClubPackOpenResult } from "@/types";

export async function fetchClubPacks(): Promise<ClubPack[]> {
  const { data } = await api.get<ClubPack[]>("/clubs/packs");
  return data;
}

/** Opens `quantity` copies (1–20) in one request: one budget debit for all. */
export async function openClubPack(packId: number, idempotencyKey?: string, quantity = 1): Promise<ClubPackOpenResult> {
  const { data } = await api.post<ClubPackOpenResult>(`/clubs/me/packs/${packId}/open`, {
    idempotency_key: idempotencyKey ?? crypto.randomUUID(),
    quantity,
  });
  return data;
}
