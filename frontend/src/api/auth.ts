import { api } from "@/lib/api";
import type { AuthResponse, UserMe } from "@/types";

export async function createSession(referralCode?: string): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>("/auth/session", null, {
    headers: referralCode ? { "X-Referral-Code": referralCode } : undefined,
  });
  return data;
}

export async function fetchMe(): Promise<UserMe> {
  const { data } = await api.get<UserMe>("/auth/me");
  return data;
}
