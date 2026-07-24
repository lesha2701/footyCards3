import { api } from "@/lib/api";
import type { FreePackClaimResult, FreePackStatus } from "@/types";

export async function fetchFreePackStatus(): Promise<FreePackStatus> {
  const { data } = await api.get<FreePackStatus>("/free-pack/status");
  return data;
}

export async function claimFreePack(): Promise<FreePackClaimResult> {
  const { data } = await api.post<FreePackClaimResult>("/free-pack/claim");
  return data;
}
