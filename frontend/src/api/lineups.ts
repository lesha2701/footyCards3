import { api } from "@/lib/api";
import type { Lineup, LineupTactic, UserCoachCard } from "@/types";

export async function fetchActiveLineup(): Promise<Lineup> {
  const { data } = await api.get<Lineup>("/lineups/active");
  return data;
}

export async function setActiveLineup(slots: { slot_code: string; user_card_id: number }[]): Promise<Lineup> {
  const { data } = await api.put<Lineup>("/lineups/active", { slots });
  return data;
}

export async function setLineupTactic(tactic: LineupTactic): Promise<Lineup> {
  const { data } = await api.post<Lineup>("/lineups/tactic", { tactic });
  return data;
}

export async function setLineupCoach(userCoachCardId: number | null): Promise<Lineup> {
  const { data } = await api.put<Lineup>("/lineups/coach", { user_coach_card_id: userCoachCardId });
  return data;
}

export async function fetchUserCoachCards(): Promise<UserCoachCard[]> {
  const { data } = await api.get<UserCoachCard[]>("/lineups/coach-cards");
  return data;
}

export async function fetchLineupTemplates(): Promise<Lineup[]> {
  const { data } = await api.get<Lineup[]>("/lineups/templates");
  return data;
}

export async function setLineupTemplate(
  templateIndex: number, slots: { slot_code: string; user_card_id: number }[],
): Promise<Lineup> {
  const { data } = await api.put<Lineup>(`/lineups/templates/${templateIndex}`, { slots });
  return data;
}

export async function setLineupTemplateTactic(templateIndex: number, tactic: LineupTactic): Promise<Lineup> {
  const { data } = await api.post<Lineup>(`/lineups/templates/${templateIndex}/tactic`, { tactic });
  return data;
}

export async function setLineupTemplateCoach(templateIndex: number, userCoachCardId: number | null): Promise<Lineup> {
  const { data } = await api.put<Lineup>(`/lineups/templates/${templateIndex}/coach`, { user_coach_card_id: userCoachCardId });
  return data;
}

export async function renameLineupTemplate(templateIndex: number, name: string): Promise<Lineup> {
  const { data } = await api.put<Lineup>(`/lineups/templates/${templateIndex}/name`, { name });
  return data;
}

export async function activateLineupTemplate(templateIndex: number): Promise<Lineup> {
  const { data } = await api.post<Lineup>(`/lineups/templates/${templateIndex}/activate`);
  return data;
}
