import { api } from "@/lib/api";
import type { ArenaPreview, ArenaStats, Match, MatchActionKind, MatchDifficulty } from "@/types";

export async function playMatch(difficulty: MatchDifficulty): Promise<Match> {
  const { data } = await api.post<Match>("/matches/play", { difficulty });
  return data;
}

export async function actMatch(matchId: number, action: MatchActionKind): Promise<Match> {
  const { data } = await api.post<Match>(`/matches/${matchId}/act`, { action });
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
