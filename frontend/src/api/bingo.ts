import { api } from "@/lib/api";
import type { BingoClaimResult, BingoCurrent } from "@/types";

export async function fetchCurrentBingo(): Promise<BingoCurrent> {
  const { data } = await api.get<BingoCurrent>("/bingo/current");
  return data;
}

export async function claimBingoReward(): Promise<BingoClaimResult> {
  const { data } = await api.post<BingoClaimResult>("/bingo/claim");
  return data;
}
