import { api } from "@/lib/api";
import type { PenaltyDirection, PenaltyMatch } from "@/types";

export async function createPenaltyChallenge(opponentUserId: number, userCardId: number): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>("/games/penalty/challenges", {
    opponent_user_id: opponentUserId, user_card_id: userCardId,
  });
  return data;
}

export async function acceptPenaltyChallenge(id: number, userCardId: number): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>(`/games/penalty/challenges/${id}/accept`, { user_card_id: userCardId });
  return data;
}

export async function declinePenaltyChallenge(id: number): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>(`/games/penalty/challenges/${id}/decline`);
  return data;
}

export async function cancelPenaltyChallenge(id: number): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>(`/games/penalty/challenges/${id}/cancel`);
  return data;
}

export async function submitPenaltyPick(id: number, zone: PenaltyDirection): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>(`/games/penalty/matches/${id}/pick`, { zone });
  return data;
}

export async function forfeitPenaltyMatch(id: number): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>(`/games/penalty/matches/${id}/forfeit`);
  return data;
}

export async function fetchPenaltyMatches(): Promise<PenaltyMatch[]> {
  const { data } = await api.get<PenaltyMatch[]>("/games/penalty/matches");
  return data;
}

export async function fetchPenaltyMatch(id: number): Promise<PenaltyMatch> {
  const { data } = await api.get<PenaltyMatch>(`/games/penalty/matches/${id}`);
  return data;
}
