import { api } from "@/lib/api";
import type { ClubPack, ClubPackOpenResult } from "@/types";

export async function fetchClubPacks(): Promise<ClubPack[]> {
  const { data } = await api.get<ClubPack[]>("/clubs/packs");
  return data;
}

export async function openClubPack(packId: number, idempotencyKey?: string): Promise<ClubPackOpenResult> {
  const { data } = await api.post<ClubPackOpenResult>(`/clubs/me/packs/${packId}/open`, {
    idempotency_key: idempotencyKey ?? crypto.randomUUID(),
  });
  return data;
}
