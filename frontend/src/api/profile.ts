import { api } from "@/lib/api";
import type { CoinTransaction, Page, ProfilePrivate, ProfilePublic, UserPublic } from "@/types";

export async function fetchMyProfile(): Promise<ProfilePrivate> {
  const { data } = await api.get<ProfilePrivate>("/profile/me");
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
