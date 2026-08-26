import { api } from "@/lib/api";
import type { ClubCard, ClubLineup } from "@/types";

export async function fetchClubLineup(): Promise<ClubLineup> {
  const { data } = await api.get<ClubLineup>("/clubs/me/lineup");
  return data;
}

export async function setClubLineup(slots: { slot_code: string; club_card_id: number }[]): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>("/clubs/me/lineup", { slots });
  return data;
}

export async function fetchClubCards(): Promise<ClubCard[]> {
  const { data } = await api.get<ClubCard[]>("/clubs/me/cards");
  return data;
}
