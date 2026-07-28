import { api } from "@/lib/api";
import type { ArenaStats, Match, MatchDifficulty } from "@/types";

export async function playMatch(difficulty: MatchDifficulty): Promise<Match> {
  const { data } = await api.post<Match>("/matches/play", { difficulty });
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
