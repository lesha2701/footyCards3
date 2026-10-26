import { api } from "@/lib/api";
import type { NewbieClaimResult, NewbieState, PackOpenResult } from "@/types";

export async function fetchNewbie(): Promise<NewbieState> {
  const { data } = await api.get<NewbieState>("/newbie");
  return data;
}

export async function openNewbieFirstPack(): Promise<PackOpenResult> {
  const { data } = await api.post<PackOpenResult>("/newbie/first-pack");
  return data;
}

export async function openNewbieSquadPack(): Promise<PackOpenResult> {
  const { data } = await api.post<PackOpenResult>("/newbie/squad-pack");
  return data;
}

export async function claimNewbieStep(code: string): Promise<NewbieClaimResult> {
  const { data } = await api.post<NewbieClaimResult>(`/newbie/claim/${encodeURIComponent(code)}`);
  return data;
}

export async function openNewbieArenaCard(): Promise<PackOpenResult> {
  const { data } = await api.post<PackOpenResult>("/newbie/arena-card");
  return data;
}
