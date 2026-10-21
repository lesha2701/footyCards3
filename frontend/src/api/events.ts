import { api } from "@/lib/api";
import type { RewardBundle } from "@/types";

// --- «Неделя мини-игры» ---

export interface WeeklyCupRow {
  place: number;
  user_id: number;
  name: string;
  points: number;
  games: number;
  prize: number;
  is_me: boolean;
}

export interface WeeklyCup {
  enabled: boolean;
  week_start: string;
  ends_at: string;
  game: string;
  title: string;
  path: string;
  unit: string;
  best_of: number;
  prizes: number[];
  participants: number;
  me: { place: number; points: number; games: number } | null;
  top: WeeklyCupRow[];
  last_week: { title: string; place: number; points: number; prize: number; claimed: boolean } | null;
  unclaimed_coins: number;
}

export async function fetchWeeklyCup(): Promise<WeeklyCup> {
  const { data } = await api.get<WeeklyCup>("/weekly-cup");
  return data;
}

export async function claimWeeklyCup(): Promise<{ coins: number; new_balance: number }> {
  const { data } = await api.post("/weekly-cup/claim");
  return data;
}

// --- «Матч дня» ---

export interface MatchDayFixture {
  id: number;
  home: string;
  away: string;
  league: string | null;
  kickoff_at: string;
  open: boolean;
  home_score: number | null;
  away_score: number | null;
  prediction: { home: number; away: number } | null;
  reward: number | null;
  reward_kind: "exact" | "diff" | "outcome" | "miss" | null;
  claimed: boolean;
  split: { home: number; draw: number; away: number; total: number } | null;
}

export interface MatchDay {
  enabled: boolean;
  rewards: { exact: number; diff: number; outcome: number };
  current: MatchDayFixture | null;
  recent: MatchDayFixture[];
  unclaimed: number;
}

export async function fetchMatchDay(): Promise<MatchDay> {
  const { data } = await api.get<MatchDay>("/match-day");
  return data;
}

export async function predictMatchDay(id: number, home: number, away: number): Promise<MatchDay> {
  const { data } = await api.put<MatchDay>(`/match-day/${id}/prediction`, { home, away });
  return data;
}

export async function claimMatchDay(id: number): Promise<{ coins: number; new_balance: number }> {
  const { data } = await api.post(`/match-day/${id}/claim`);
  return data;
}

// --- «Клубный рейд» ---

export interface ClubRaid {
  enabled: boolean;
  boss: { code: string; name: string; emoji: string; line: string };
  hp: number;
  damage: number;
  defeated: boolean;
  ends_at: string;
  attacks_left: number;
  attacks_per_day: number;
  shots: number;
  strength: number;
  chance_pct: number;
  reward: RewardBundle;
  reward_budget: number;
  members: { user_id: number; name: string; damage: number; attacks: number; goals: number; is_me: boolean }[];
  recent: { name: string; goals: number; shots: number; damage: number; at: string }[];
  last: { shots: boolean[]; goals: number; damage: number; defeated_now: boolean } | null;
}

export async function fetchClubRaid(): Promise<ClubRaid> {
  const { data } = await api.get<ClubRaid>("/clubs/me/raid");
  return data;
}

export async function attackClubRaid(): Promise<ClubRaid> {
  const { data } = await api.post<ClubRaid>("/clubs/me/raid/attack");
  return data;
}

// --- admin ---

export interface AdminFixture {
  id: number;
  home: string;
  away: string;
  league: string | null;
  kickoff_at: string;
  home_score: number | null;
  away_score: number | null;
  predictions: number;
  claimed: number;
}
