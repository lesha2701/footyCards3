import { api } from "@/lib/api";
import type { TacticoMatch, TacticoSquad, TacticoStats } from "@/types";

export async function fetchTacticoStats(): Promise<TacticoStats> {
  const { data } = await api.get<TacticoStats>("/tactico/stats");
  return data;
}

export async function fetchTacticoSquad(): Promise<TacticoSquad> {
  const { data } = await api.get<TacticoSquad>("/tactico/squad");
  return data;
}

export async function setTacticoSquad(userCardIds: number[]): Promise<TacticoSquad> {
  const { data } = await api.put<TacticoSquad>("/tactico/squad", { user_card_ids: userCardIds });
  return data;
}

export async function createTacticoBotMatch(difficulty: "easy" | "medium" | "hard"): Promise<TacticoMatch> {
  const { data } = await api.post<TacticoMatch>("/tactico/matches/bot", { difficulty });
  return data;
}

export async function createTacticoChallenge(receiverId: number): Promise<TacticoMatch> {
  const { data } = await api.post<TacticoMatch>("/tactico/matches/challenge", { receiver_id: receiverId });
  return data;
}

export async function acceptTacticoChallenge(id: number): Promise<TacticoMatch> {
  const { data } = await api.post<TacticoMatch>(`/tactico/matches/${id}/accept`);
  return data;
}

export async function declineTacticoChallenge(id: number): Promise<TacticoMatch> {
  const { data } = await api.post<TacticoMatch>(`/tactico/matches/${id}/decline`);
  return data;
}

export async function cancelTacticoChallenge(id: number): Promise<TacticoMatch> {
  const { data } = await api.post<TacticoMatch>(`/tactico/matches/${id}/cancel`);
  return data;
}

export async function submitTacticoRound(id: number, userCardId: number): Promise<TacticoMatch> {
  const { data } = await api.post<TacticoMatch>(`/tactico/matches/${id}/rounds`, { user_card_id: userCardId });
  return data;
}

export async function forfeitTacticoMatch(id: number): Promise<TacticoMatch> {
  const { data } = await api.post<TacticoMatch>(`/tactico/matches/${id}/forfeit`);
  return data;
}

export async function fetchTacticoMatches(): Promise<TacticoMatch[]> {
  const { data } = await api.get<TacticoMatch[]>("/tactico/matches");
  return data;
}

export async function fetchTacticoMatch(id: number): Promise<TacticoMatch> {
  const { data } = await api.get<TacticoMatch>(`/tactico/matches/${id}`);
  return data;
}
