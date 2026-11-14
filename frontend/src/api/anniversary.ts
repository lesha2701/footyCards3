import { api } from "@/lib/api";
import type { AnniversaryClaimResult, AnniversaryRecap, AnniversaryState } from "@/types";

export async function fetchAnniversary(): Promise<AnniversaryState> {
  const { data } = await api.get<AnniversaryState>("/anniversary");
  return data;
}

export async function fetchAnniversaryRecap(): Promise<AnniversaryRecap> {
  const { data } = await api.get<AnniversaryRecap>("/anniversary/recap");
  return data;
}

export async function claimAnniversary(what: "calendar" | "community" | "recap"): Promise<AnniversaryClaimResult> {
  const { data } = await api.post<AnniversaryClaimResult>(`/anniversary/${what}/claim`);
  return data;
}
