import { api } from "@/lib/api";
import type { ClubCoachPack, ClubCoachPackOpenResult } from "@/types";

export async function fetchClubCoachPacks(): Promise<ClubCoachPack[]> {
  const { data } = await api.get<ClubCoachPack[]>("/clubs/coach-packs");
  return data;
}

export async function openClubCoachPack(packId: number, idempotencyKey?: string): Promise<ClubCoachPackOpenResult> {
  const { data } = await api.post<ClubCoachPackOpenResult>(`/clubs/me/coach-packs/${packId}/open`, {
    idempotency_key: idempotencyKey ?? crypto.randomUUID(),
  });
  return data;
}
