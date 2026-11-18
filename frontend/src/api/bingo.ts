import { api } from "@/lib/api";
import type { BingoClaimResult, BingoCurrent } from "@/types";

export async function fetchCurrentBingo(): Promise<BingoCurrent> {
  const { data } = await api.get<BingoCurrent>("/bingo/current");
  return data;
}

/** The player's own card: every closed line not paid yet, and the whole card. */
export async function claimBingoCard(): Promise<BingoClaimResult> {
  const { data } = await api.post<BingoClaimResult>("/bingo/card/claim");
  return data;
}

export async function claimBingoReward(): Promise<BingoClaimResult> {
  const { data } = await api.post<BingoClaimResult>("/bingo/claim");
  return data;
}
