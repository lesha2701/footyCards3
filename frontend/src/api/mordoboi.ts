import { api } from "@/lib/api";
import type {
  MordoboiAction,
  MordoboiBoxer,
  MordoboiInfo,
  MordoboiMatch,
  MordoboiSearchStatus,
  MordoboiStats,
} from "@/types";

export async function fetchMordoboiInfo(): Promise<MordoboiInfo> {
  const { data } = await api.get<MordoboiInfo>("/mordoboi/info");
  return data;
}

export async function fetchMordoboiStats(): Promise<MordoboiStats> {
  const { data } = await api.get<MordoboiStats>("/mordoboi/stats");
  return data;
}

export async function fetchMordoboiBoxer(): Promise<MordoboiBoxer> {
  const { data } = await api.get<MordoboiBoxer>("/mordoboi/boxer");
  return data;
}

export async function saveMordoboiBoxer(userCardId: number): Promise<MordoboiBoxer> {
  const { data } = await api.put<MordoboiBoxer>("/mordoboi/boxer", { user_card_id: userCardId });
  return data;
}

export async function createMordoboiBotMatch(difficulty: "easy" | "hard"): Promise<MordoboiMatch> {
  const { data } = await api.post<MordoboiMatch>("/mordoboi/matches/bot", { difficulty });
  return data;
}

export async function createMordoboiChallenge(receiverId: number): Promise<MordoboiMatch> {
  const { data } = await api.post<MordoboiMatch>("/mordoboi/matches/challenge", { receiver_id: receiverId });
  return data;
}

export async function acceptMordoboiChallenge(id: number): Promise<MordoboiMatch> {
  const { data } = await api.post<MordoboiMatch>(`/mordoboi/matches/${id}/accept`);
  return data;
}

export async function declineMordoboiChallenge(id: number): Promise<MordoboiMatch> {
  const { data } = await api.post<MordoboiMatch>(`/mordoboi/matches/${id}/decline`);
  return data;
}

export async function cancelMordoboiChallenge(id: number): Promise<MordoboiMatch> {
  const { data } = await api.post<MordoboiMatch>(`/mordoboi/matches/${id}/cancel`);
  return data;
}

export async function forfeitMordoboiMatch(id: number): Promise<MordoboiMatch> {
  const { data } = await api.post<MordoboiMatch>(`/mordoboi/matches/${id}/forfeit`);
  return data;
}

export async function pickMordoboiAction(id: number, action: MordoboiAction, version: number): Promise<MordoboiMatch> {
  const { data } = await api.post<MordoboiMatch>(`/mordoboi/matches/${id}/pick`, { action, version });
  return data;
}

export async function fetchMordoboiMatches(): Promise<MordoboiMatch[]> {
  const { data } = await api.get<MordoboiMatch[]>("/mordoboi/matches");
  return data;
}

export async function fetchMordoboiMatch(id: number): Promise<MordoboiMatch> {
  const { data } = await api.get<MordoboiMatch>(`/mordoboi/matches/${id}`);
  return data;
}

export async function startMordoboiSearch(): Promise<MordoboiSearchStatus> {
  const { data } = await api.post<MordoboiSearchStatus>("/mordoboi/matchmaking/search");
  return data;
}

export async function fetchMordoboiSearchStatus(): Promise<MordoboiSearchStatus> {
  const { data } = await api.get<MordoboiSearchStatus>("/mordoboi/matchmaking/status");
  return data;
}

export async function cancelMordoboiSearch(): Promise<void> {
  await api.post("/mordoboi/matchmaking/cancel");
}
