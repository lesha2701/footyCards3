import type { CareerTableRow } from "@/api/career";
import type { MyPlayer } from "@/api/myPlayer";
import { api } from "@/lib/api";

export interface PlayerCareerClub {
  key: string;
  name: string;
  rating: number;
  is_demo: boolean;
  real_cards: number;
  reputation_needed: number;
  /** null = the player may sign for this club. */
  locked_reason: string | null;
  stars: string[];
}

export interface PlayerCareerMyRound {
  played: boolean;
  goals: number;
  assists: number;
  rating: number | null;
  own: number;
  opp: number;
  opponent: string;
}

export interface PlayerCareerSeason {
  id: number;
  status: "active" | "finished" | "cancelled";
  rounds_played: number;
  total_rounds: number;
  next_round_at: string | null;
  teams: { index: number; name: string; rating: number; is_mine: boolean }[];
  table: CareerTableRow[];
  rounds: {
    index: number; at: string | null; home: number | null; away: number | null;
    hs: number | null; away_score: number | null; me: PlayerCareerMyRound | null;
  }[];
  stats: { matches: number; goals: number; assists: number; avg_rating: number | null };
  scorers: { name: string; team: string; goals: number }[];
  final_place: number | null;
  coins_earned: number;
  awards: string[];
  offers: { key: string; name: string; rating: number }[];
}

export interface PlayerCareerView {
  enabled: boolean;
  has_player: boolean;
  player: MyPlayer | null;
  rating: number | null;
  reputation: number;
  career: { seasons: number; matches: number; goals: number; assists: number; titles: number; top_scorer: number; mvp: number } | null;
  club: PlayerCareerClub | null;
  clubs: PlayerCareerClub[];
  season: PlayerCareerSeason | null;
  can_change_club: boolean;
  rewards: { win: number; draw: number; goal: number; xp: number; places: number[] } | null;
}

export async function fetchPlayerCareer(): Promise<PlayerCareerView> {
  const { data } = await api.get<PlayerCareerView>("/player-career");
  return data;
}

export async function signPlayerCareerContract(clubKey: string): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>("/player-career/contract", { club_key: clubKey });
  return data;
}

export async function startPlayerCareerSeason(): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>("/player-career/seasons");
  return data;
}

export async function leavePlayerCareerSeason(): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>("/player-career/leave");
  return data;
}
