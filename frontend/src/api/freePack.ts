import { api } from "@/lib/api";
import type { FreePackStatus, PackOpenResult } from "@/types";

export async function fetchFreePackStatus(): Promise<FreePackStatus> {
  const { data } = await api.get<FreePackStatus>("/free-pack/status");
  return data;
}

export async function claimFreePack(): Promise<PackOpenResult> {
  const { data } = await api.post<PackOpenResult>("/free-pack/claim");
  return data;
}
