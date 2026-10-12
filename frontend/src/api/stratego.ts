import { api } from "@/lib/api";
import type {
  StrategoInfo,
  StrategoMatch,
  StrategoDifficulty,
  StrategoNoteTag,
  StrategoOpenChallengePreview,
  StrategoPuzzle,
  StrategoSearchStatus,
  StrategoSquad,
  StrategoStats,
} from "@/types";

export async function fetchStrategoInfo(): Promise<StrategoInfo> {
  const { data } = await api.get<StrategoInfo>("/stratego/info");
  return data;
}

export async function fetchStrategoStats(): Promise<StrategoStats> {
  const { data } = await api.get<StrategoStats>("/stratego/stats");
  return data;
}

export async function createStrategoOpenChallenge(stakeCoins: number): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>("/stratego/matches/open-challenge", { stake_coins: stakeCoins });
  return data;
}

export async function fetchStrategoOpenChallenge(id: number): Promise<StrategoOpenChallengePreview> {
  const { data } = await api.get<StrategoOpenChallengePreview>(`/stratego/matches/open/${id}`);
  return data;
}

export async function acceptStrategoOpenChallenge(id: number): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>(`/stratego/matches/open/${id}/accept`);
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

export async function createStrategoBotMatch(difficulty: Exclude<StrategoDifficulty, "normal"> = "hard"): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>("/stratego/matches/bot", { difficulty });
  return data;
}

export async function fetchStrategoPuzzle(): Promise<StrategoPuzzle> {
  const { data } = await api.get<StrategoPuzzle>("/stratego/puzzle");
  return data;
}

export async function startStrategoPuzzle(): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>("/stratego/puzzle/start");
  return data;
}

export async function startStrategoTutorial(): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>("/stratego/tutorial/start");
  return data;
}

export async function setStrategoNote(id: number, pieceId: number, tag: StrategoNoteTag | null): Promise<StrategoMatch> {
  const { data } = await api.post<StrategoMatch>(`/stratego/matches/${id}/notes`, { piece_id: pieceId, tag });
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
