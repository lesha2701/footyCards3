import { api } from "@/lib/api";
import type {
  ArenaActionKind, ArenaDefenseItem, ArenaPreview, ArenaStats, LineupTactic, Match, MatchDifficulty, MatchHistoryItem,
} from "@/types";

export async function playMatch(difficulty: MatchDifficulty, mode: "ladder" | "cup" = "ladder"): Promise<Match> {
  const { data } = await api.post<Match>("/matches/play", { difficulty, mode });
  return data;
}

export type MatchActExtra = {
  expected_seq?: number;
  style?: LineupTactic;
  swipe?: { dx: number; dy: number; curve: number; duration_ms: number };
  dive?: { x: number; y: number; reaction_ms: number } | null;
};

export async function actMatch(matchId: number, action: ArenaActionKind, extra: MatchActExtra = {}): Promise<Match> {
  const { data } = await api.post<Match>(`/matches/${matchId}/act`, { action, ...extra });
  return data;
}

/** The match still running, so a closed app can go back to it. */
export async function fetchActiveMatch(): Promise<Match | null> {
  const { data } = await api.get<Match | null>("/matches/active");
  return data;
}

export async function fetchMatch(matchId: number): Promise<Match> {
  const { data } = await api.get<Match>(`/matches/${matchId}`);
  return data;
}

export async function fetchRecentMatches(): Promise<MatchHistoryItem[]> {
  const { data } = await api.get<MatchHistoryItem[]>("/matches/recent");
  return data;
}

export async function fetchDefenseLog(): Promise<ArenaDefenseItem[]> {
  const { data } = await api.get<ArenaDefenseItem[]>("/matches/defense-log");
  return data;
}

export async function markDefenseSeen(): Promise<void> {
  await api.post("/matches/defense-log/seen");
}

export async function takeRevenge(matchId: number): Promise<ArenaPreview> {
  const { data } = await api.post<ArenaPreview>(`/matches/${matchId}/revenge`);
  return data;
}

export async function forfeitMatch(matchId: number): Promise<Match> {
  const { data } = await api.post<Match>(`/matches/${matchId}/forfeit`);
  return data;
}

export async function fetchMatchHistory(): Promise<Match[]> {
  const { data } = await api.get<Match[]>("/matches/history");
  return data;
}

export async function fetchArenaStats(): Promise<ArenaStats> {
  const { data } = await api.get<ArenaStats>("/matches/stats");
  return data;
}

/** The next opponent (found once and kept until that match is played). */
export async function fetchArenaOpponent(): Promise<ArenaPreview> {
  const { data } = await api.post<ArenaPreview>("/matches/opponent");
  return data;
}
