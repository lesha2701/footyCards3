import { api } from "@/lib/api";
import type {
  PersonalSquad,
  PlayerTournamentApplyResult,
  PlayerTournamentCurrent,
  PlayerTournamentDetail,
  PlayerTournamentMatchDetail,
  TournamentRatingRow,
  UserCoachCard,
} from "@/types";

export async function fetchPersonalSquads(): Promise<PersonalSquad[]> {
  const { data } = await api.get<PersonalSquad[]>("/player-tournaments/squads");
  return data;
}

export async function fetchPersonalSquadCoachCards(): Promise<UserCoachCard[]> {
  const { data } = await api.get<UserCoachCard[]>("/player-tournaments/squads/coach-cards");
  return data;
}

export async function setPersonalSquadCards(
  templateIndex: number, slots: { slot_code: string; user_card_id: number }[],
): Promise<PersonalSquad> {
  const { data } = await api.put<PersonalSquad>(`/player-tournaments/squads/${templateIndex}/cards`, { slots });
  return data;
}

export async function setPersonalSquadTactics(
  templateIndex: number, payload: { formation: string; mentality: string; playstyle: string },
): Promise<PersonalSquad> {
  const { data } = await api.put<PersonalSquad>(`/player-tournaments/squads/${templateIndex}/tactics`, payload);
  return data;
}

export async function setPersonalSquadCoach(templateIndex: number, userCoachCardId: number | null): Promise<PersonalSquad> {
  const { data } = await api.put<PersonalSquad>(
    `/player-tournaments/squads/${templateIndex}/coach`, { user_coach_card_id: userCoachCardId },
  );
  return data;
}

export async function renamePersonalSquad(templateIndex: number, name: string): Promise<PersonalSquad> {
  const { data } = await api.put<PersonalSquad>(`/player-tournaments/squads/${templateIndex}/name`, { name });
  return data;
}

export async function activatePersonalSquad(templateIndex: number): Promise<PersonalSquad> {
  const { data } = await api.post<PersonalSquad>(`/player-tournaments/squads/${templateIndex}/activate`);
  return data;
}

export async function applyToPlayerTournament(): Promise<PlayerTournamentApplyResult> {
  const { data } = await api.post<PlayerTournamentApplyResult>("/player-tournaments/apply");
  return data;
}

export async function fetchPlayerTournamentCurrent(): Promise<PlayerTournamentCurrent> {
  const { data } = await api.get<PlayerTournamentCurrent>("/player-tournaments/current");
  return data;
}

export async function fetchPlayerTournamentRating(): Promise<TournamentRatingRow[]> {
  const { data } = await api.get<TournamentRatingRow[]>("/player-tournaments/rating");
  return data;
}

export async function fetchPlayerTournamentDetail(id: number): Promise<PlayerTournamentDetail> {
  const { data } = await api.get<PlayerTournamentDetail>(`/player-tournaments/${id}`);
  return data;
}

export async function fetchPlayerTournamentMatch(matchId: number): Promise<PlayerTournamentMatchDetail> {
  const { data } = await api.get<PlayerTournamentMatchDetail>(`/player-tournaments/matches/${matchId}`);
  return data;
}
