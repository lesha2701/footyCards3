import { api } from "@/lib/api";
import type { ClubCard, ClubCoachCard, ClubLineup } from "@/types";

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

export async function setClubTactics(payload: { formation: string; mentality: string; playstyle: string }): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>("/clubs/me/tactics", payload);
  return data;
}

export async function fetchClubCoachCards(): Promise<ClubCoachCard[]> {
  const { data } = await api.get<ClubCoachCard[]>("/clubs/me/coach-cards");
  return data;
}

export async function setClubCoach(clubCoachCardId: number | null): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>("/clubs/me/coach", { club_coach_card_id: clubCoachCardId });
  return data;
}

export async function activateClubTraining(): Promise<ClubLineup> {
  const { data } = await api.post<ClubLineup>("/clubs/me/training");
  return data;
}

export async function fetchClubLineupTemplates(): Promise<ClubLineup[]> {
  const { data } = await api.get<ClubLineup[]>("/clubs/me/lineup/templates");
  return data;
}

export async function setClubLineupTemplate(
  templateIndex: number, slots: { slot_code: string; club_card_id: number }[],
): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>(`/clubs/me/lineup/templates/${templateIndex}`, { slots });
  return data;
}

export async function setClubTacticsTemplate(
  templateIndex: number, payload: { formation: string; mentality: string; playstyle: string },
): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>(`/clubs/me/tactics/templates/${templateIndex}`, payload);
  return data;
}

export async function setClubCoachTemplate(templateIndex: number, clubCoachCardId: number | null): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>(`/clubs/me/coach/templates/${templateIndex}`, { club_coach_card_id: clubCoachCardId });
  return data;
}

export async function renameClubLineupTemplate(templateIndex: number, name: string): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>(`/clubs/me/lineup/templates/${templateIndex}/name`, { name });
  return data;
}

export async function activateClubLineupTemplate(templateIndex: number): Promise<ClubLineup> {
  const { data } = await api.post<ClubLineup>(`/clubs/me/lineup/templates/${templateIndex}/activate`);
  return data;
}
