import { api } from "@/lib/api";
import type { ArenaLeaderboardEntry, MemoryLeaderboardEntry, RankingMetric, RankingResult } from "@/types";

export async function fetchArenaLeaderboard(): Promise<ArenaLeaderboardEntry[]> {
  const { data } = await api.get<ArenaLeaderboardEntry[]>("/leaderboard/arena");
  return data;
}

export async function fetchMemoryLeaderboard(): Promise<MemoryLeaderboardEntry[]> {
  const { data } = await api.get<MemoryLeaderboardEntry[]>("/leaderboard/memory");
  return data;
}

export async function fetchRanking(metric: RankingMetric): Promise<RankingResult> {
  const { data } = await api.get<RankingResult>("/leaderboard/ranking", { params: { metric } });
  return data;
}
