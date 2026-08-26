import { api } from "@/lib/api";
import type { Club, ClubJoinRequest, ClubSummary } from "@/types";

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

export async function disbandClub(): Promise<void> {
  await api.post("/clubs/me/disband");
}

export async function claimDailyReward(): Promise<Club> {
  const { data } = await api.post<Club>("/clubs/me/daily-claim");
  return data;
}
