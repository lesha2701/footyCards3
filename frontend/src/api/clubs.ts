import { api } from "@/lib/api";
import type {
  Club,
  ClubGameClaimResult,
  ClubGameStart,
  ClubGameSubmitResult,
  ClubJoinRequest,
  ClubMemberActivity,
  ClubMissingItemClaimResult,
  ClubMissingItemReveal,
  ClubMissingItemStart,
  ClubMissingItemSubmitResult,
  ClubSummary,
  TournamentApplyResult,
  TournamentCurrent,
  TournamentDetail,
  TournamentMatchDetail,
} from "@/types";

export async function fetchClubs(search?: string): Promise<ClubSummary[]> {
  const { data } = await api.get<ClubSummary[]>("/clubs", { params: { search: search || undefined } });
  return data;
}

export async function fetchMyClub(): Promise<Club> {
  const { data } = await api.get<Club>("/clubs/me");
  return data;
}

export async function fetchClub(id: number): Promise<Club> {
  const { data } = await api.get<Club>(`/clubs/${id}`);
  return data;
}

export async function fetchClubCreationCost(): Promise<number> {
  const { data } = await api.get<{ creation_cost_coins: number }>("/clubs/creation-cost");
  return data.creation_cost_coins;
}

export async function createClub(payload: {
  name: string;
  description: string;
  club_type: string;
  logo_shape: string;
  logo_color: string;
}): Promise<Club> {
  const { data } = await api.post<Club>("/clubs", payload);
  return data;
}

export async function joinClub(id: number): Promise<Club> {
  const { data } = await api.post<Club>(`/clubs/${id}/join`);
  return data;
}

export async function createJoinRequest(id: number): Promise<ClubJoinRequest> {
  const { data } = await api.post<ClubJoinRequest>(`/clubs/${id}/join-requests`);
  return data;
}

export async function fetchMyJoinRequests(): Promise<ClubJoinRequest[]> {
  const { data } = await api.get<ClubJoinRequest[]>("/clubs/me/join-requests");
  return data;
}

export async function acceptJoinRequest(requestId: number): Promise<Club> {
  const { data } = await api.post<Club>(`/clubs/me/join-requests/${requestId}/accept`);
  return data;
}

export async function rejectJoinRequest(requestId: number): Promise<void> {
  await api.post(`/clubs/me/join-requests/${requestId}/reject`);
}

export async function joinByInvite(inviteCode: string): Promise<Club> {
  const { data } = await api.post<Club>("/clubs/join-by-invite", { invite_code: inviteCode });
  return data;
}

export async function leaveClub(): Promise<void> {
  await api.post("/clubs/me/leave");
}

export async function kickMember(userId: number): Promise<Club> {
  const { data } = await api.post<Club>(`/clubs/me/members/${userId}/kick`);
  return data;
}

export async function fetchClubActivity(): Promise<ClubMemberActivity[]> {
  const { data } = await api.get<ClubMemberActivity[]>("/clubs/me/activity");
  return data;
}

export async function remindMember(userId: number): Promise<void> {
  await api.post(`/clubs/me/members/${userId}/remind`);
}

export async function appointAssistant(userId: number): Promise<Club> {
  const { data } = await api.post<Club>(`/clubs/me/assistants/${userId}/appoint`);
  return data;
}

export async function removeAssistant(userId: number): Promise<Club> {
  const { data } = await api.post<Club>(`/clubs/me/assistants/${userId}/remove`);
  return data;
}

export async function transferCaptain(userId: number): Promise<Club> {
  const { data } = await api.post<Club>("/clubs/me/transfer-captain", { user_id: userId });
  return data;
}

export async function updateClubType(clubType: "open" | "closed"): Promise<Club> {
  const { data } = await api.put<Club>("/clubs/me/type", { club_type: clubType });
  return data;
}

export async function disbandClub(): Promise<void> {
  await api.post("/clubs/me/disband");
}

export async function claimDailyReward(): Promise<Club> {
  const { data } = await api.post<Club>("/clubs/me/daily-claim");
  return data;
}

export async function applyToTournament(): Promise<TournamentApplyResult> {
  const { data } = await api.post<TournamentApplyResult>("/clubs/tournament/apply");
  return data;
}

export async function fetchTournamentCurrent(): Promise<TournamentCurrent> {
  const { data } = await api.get<TournamentCurrent>("/clubs/tournament/current");
  return data;
}

export async function fetchTournamentDetail(id: number): Promise<TournamentDetail> {
  const { data } = await api.get<TournamentDetail>(`/clubs/tournament/${id}`);
  return data;
}

export async function fetchTournamentMatch(tournamentId: number, matchId: number): Promise<TournamentMatchDetail> {
  const { data } = await api.get<TournamentMatchDetail>(`/clubs/tournament/${tournamentId}/matches/${matchId}`);
  return data;
}

export async function startClubGame(): Promise<ClubGameStart> {
  const { data } = await api.post<ClubGameStart>("/clubs/me/game/start");
  return data;
}

export async function submitClubGameRound(sessionId: number, answer: string[]): Promise<ClubGameSubmitResult> {
  const { data } = await api.post<ClubGameSubmitResult>(`/clubs/me/game/${sessionId}/submit`, { answer });
  return data;
}

export async function endClubGame(sessionId: number): Promise<ClubGameSubmitResult> {
  const { data } = await api.post<ClubGameSubmitResult>(`/clubs/me/game/${sessionId}/end`);
  return data;
}

export async function claimClubGameReward(sessionId: number): Promise<ClubGameClaimResult> {
  const { data } = await api.post<ClubGameClaimResult>(`/clubs/me/game/${sessionId}/claim`);
  return data;
}

export async function startMissingItemGame(): Promise<ClubMissingItemStart> {
  const { data } = await api.post<ClubMissingItemStart>("/clubs/me/missing-item/start");
  return data;
}

export async function revealMissingItemRound(sessionId: number): Promise<ClubMissingItemReveal> {
  const { data } = await api.post<ClubMissingItemReveal>(`/clubs/me/missing-item/${sessionId}/reveal`);
  return data;
}

export async function submitMissingItemRound(sessionId: number, answer: string): Promise<ClubMissingItemSubmitResult> {
  const { data } = await api.post<ClubMissingItemSubmitResult>(`/clubs/me/missing-item/${sessionId}/submit`, { answer });
  return data;
}

export async function endMissingItemGame(sessionId: number): Promise<ClubMissingItemSubmitResult> {
  const { data } = await api.post<ClubMissingItemSubmitResult>(`/clubs/me/missing-item/${sessionId}/end`);
  return data;
}

export async function claimMissingItemReward(sessionId: number): Promise<ClubMissingItemClaimResult> {
  const { data } = await api.post<ClubMissingItemClaimResult>(`/clubs/me/missing-item/${sessionId}/claim`);
  return data;
}
