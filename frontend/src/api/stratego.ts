import { api } from "@/lib/api";
import type { StrategoInfo, StrategoMatch, StrategoSearchStatus, StrategoSquad } from "@/types";

export async function fetchStrategoInfo(): Promise<StrategoInfo> {
  const { data } = await api.get<StrategoInfo>("/stratego/info");
  return data;
}

export async function fetchStrategoSquad(): Promise<StrategoSquad> {
  const { data } = await api.get<StrategoSquad>("/stratego/squad");
  return data;
}

export async function saveStrategoSquad(
  cards: Record<string, number>,
  layout: Record<string, [number, number]>,
): Promise<StrategoSquad> {
  const { data } = await api.put<StrategoSquad>("/stratego/squad", { cards, layout });
  return data;
}

export async function createStrategoBotMatch(): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>("/stratego/matches/bot");
  return data;
}

export async function createStrategoChallenge(receiverId: number): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>("/stratego/matches/challenge", { receiver_id: receiverId });
  return data;
}

export async function acceptStrategoChallenge(id: number): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>(`/stratego/matches/${id}/accept`);
  return data;
}

export async function declineStrategoChallenge(id: number): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>(`/stratego/matches/${id}/decline`);
  return data;
}

export async function cancelStrategoChallenge(id: number): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>(`/stratego/matches/${id}/cancel`);
  return data;
}

export async function forfeitStrategoMatch(id: number): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>(`/stratego/matches/${id}/forfeit`);
  return data;
}

export async function submitStrategoMove(
  id: number, from: [number, number], to: [number, number],
): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>(`/stratego/matches/${id}/move`, {
    from_row: from[0], from_col: from[1], to_row: to[0], to_col: to[1],
  });
  return data;
}

export async function fetchStrategoMatches(): Promise<StrategoMatch[]> {
  const { data } = await api.get<StrategoMatch[]>("/stratego/matches");
  return data;
}

export async function fetchStrategoMatch(id: number): Promise<StrategoMatch> {
  const { data } = await api.get<StrategoMatch>(`/stratego/matches/${id}`);
  return data;
}

export async function startStrategoSearch(): Promise<StrategoSearchStatus> {
  const { data } = await api.post<StrategoSearchStatus>("/stratego/matchmaking/search");
  return data;
}

export async function fetchStrategoSearchStatus(): Promise<StrategoSearchStatus> {
  const { data } = await api.get<StrategoSearchStatus>("/stratego/matchmaking/status");
  return data;
}

export async function cancelStrategoSearch(): Promise<void> {
  await api.post("/stratego/matchmaking/cancel");
}
