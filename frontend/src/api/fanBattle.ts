import { api } from "@/lib/api";
import type { FanBattleState, FanClaimResult } from "@/types";

export async function fetchFanBattle(): Promise<FanBattleState> {
  const { data } = await api.get<FanBattleState>("/fans");
  return data;
}

export async function joinFanSide(side: string): Promise<FanBattleState> {
  const { data } = await api.post<FanBattleState>(`/fans/side/${side}`);
  return data;
}

export async function claimFanRewards(): Promise<FanClaimResult> {
  const { data } = await api.post<FanClaimResult>("/fans/claim");
  return data;
}
