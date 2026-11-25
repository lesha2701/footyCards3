import { api } from "@/lib/api";
import type {
  CoinTransaction,
  OwnedBadge,
  Page,
  ProfilePrivate,
  ProfilePublic,
  ProfileSettingsUpdate,
  UserPublic,
  UserTrophy,
} from "@/types";

export async function fetchMyProfile(): Promise<ProfilePrivate> {
  const { data } = await api.get<ProfilePrivate>("/profile/me");
  return data;
}

export async function updateMySettings(payload: ProfileSettingsUpdate): Promise<ProfilePrivate> {
  const { data } = await api.patch<ProfilePrivate>("/profile/settings", payload);
  return data;
}

export async function fetchMyBadges(): Promise<OwnedBadge[]> {
  const { data } = await api.get<OwnedBadge[]>("/profile/badges");
  return data;
}

export async function fetchMyTrophies(): Promise<UserTrophy[]> {
  const { data } = await api.get<UserTrophy[]>("/profile/trophies");
  return data;
}

export async function fetchMyTransactions(page = 1): Promise<Page<CoinTransaction>> {
  const { data } = await api.get<Page<CoinTransaction>>("/profile/transactions", { params: { page } });
  return data;
}

export async function fetchPublicProfile(userId: number): Promise<ProfilePublic> {
  const { data } = await api.get<ProfilePublic>(`/users/${userId}`);
  return data;
}

export async function searchUsers(query: string): Promise<UserPublic[]> {
  const { data } = await api.get<UserPublic[]>("/users/search", { params: { q: query } });
  return data;
}

export interface Attention {
  incoming_trades: number;
  match_challenges: number;
  active_friend_matches: number;
  league_unseen_rewards: number;
  friend_requests: number;
  career_invites: number;
}

/** Badge counts for the bottom navigation (one cheap request). */
export async function fetchMyAttention(): Promise<Attention> {
  const { data } = await api.get<Attention>("/profile/me/attention");
  return data;
}

export interface ProfileFeedEvent {
  kind: "finish" | "trophy" | "collection";
  at: string;
  icon: string;
  text: string;
  image_path: string | null;
}

export interface ProfileSocial {
  respects: number;
  respected_today: boolean;
  can_respect: boolean;
  feed: ProfileFeedEvent[];
}

export async function fetchProfileSocial(userId: number): Promise<ProfileSocial> {
  const { data } = await api.get<ProfileSocial>(`/users/${userId}/social`);
  return data;
}

export async function giveRespect(userId: number): Promise<ProfileSocial> {
  const { data } = await api.post<ProfileSocial>(`/users/${userId}/respect`);
  return data;
}
