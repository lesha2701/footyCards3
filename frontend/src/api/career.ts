import { api } from "@/lib/api";
import type { MatchEvent, UserCard } from "@/types";

export interface CareerTeam {
  index: number;
  name: string;
  is_bot: boolean;
  user_id: number | null;
  strength: number | null;
}

export interface CareerTableRow {
  team_index: number;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  points: number;
}

export interface CareerMatch {
  home: number;
  away: number;
  hs: number | null;
  as: number | null;
  has_events: boolean;
}

export interface CareerRound {
  index: number;
  at: string | null;
  matches: CareerMatch[];
}

export interface CareerSquadCard {
  card: UserCard | null;
  card_id: number;
  fatigue: number;
  injured_rounds: number;
  owned: boolean;
}

export interface CareerSlot {
  code: string;
  category: "GK" | "DEF" | "MID" | "FWD";
  ideal_position: string;
}

export interface CareerSeason {
  id: number;
  status: "pending" | "active" | "finished" | "cancelled";
  difficulty: string;
  difficulty_label: string;
  rounds_played: number;
  total_rounds: number;
  schedule: string[];
  next_round_at: string | null;
  invite_expires_at: string | null;
  is_creator: boolean;
  my_status: "invited" | "accepted" | "declined" | "left";
  my_team_index: number;
  final_place: number | null;
  coins_earned: number;
  participants: { user_id: number; name: string; status: string; team_index: number }[];
  teams: CareerTeam[];
  table: CareerTableRow[];
  rounds: CareerRound[];
  squad: CareerSquadCard[];
  lineup: Record<string, number>;
  slots: CareerSlot[];
  formation: string;
  mentality: string;
  playstyle: string;
}

export interface CareerView {
  enabled: boolean;
  difficulties: { code: string; label: string; reward_pct: number }[];
  place_rewards: number[];
  slots: string[];
  season: CareerSeason | null;
  invite: { season_id: number; difficulty_label: string; from_name: string; expires_at: string | null } | null;
}

export async function fetchCareer(): Promise<CareerView> {
  const { data } = await api.get<CareerView>("/career");
  return data;
}

export async function createCareerSeason(difficulty: string, friendId?: number): Promise<CareerView> {
  const { data } = await api.post<CareerView>("/career/seasons", { difficulty, friend_id: friendId ?? null });
  return data;
}

export async function respondCareerInvite(seasonId: number, accept: boolean): Promise<CareerView> {
  const { data } = await api.post<CareerView>(`/career/seasons/${seasonId}/invite`, { accept });
  return data;
}

export async function startCareerWithoutFriend(seasonId: number): Promise<CareerView> {
  const { data } = await api.post<CareerView>(`/career/seasons/${seasonId}/start`);
  return data;
}

export async function setCareerLineup(payload: {
  slots: Record<string, number>;
  formation: string;
  mentality: string;
  playstyle: string;
}): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/lineup", payload);
  return data;
}

export async function leaveCareer(): Promise<void> {
  await api.post("/career/leave");
}

export interface CareerMatchEvents {
  home_name: string;
  away_name: string;
  home_score: number;
  away_score: number;
  events: MatchEvent[];
}

export async function fetchCareerMatch(seasonId: number, round: number, match: number): Promise<CareerMatchEvents> {
  const { data } = await api.get<CareerMatchEvents>(`/career/seasons/${seasonId}/rounds/${round}/matches/${match}`);
  return data;
}
