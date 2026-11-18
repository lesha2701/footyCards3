import { api } from "@/lib/api";
import type { LuckyBoardSpin, LuckyBoardStatus, StarsInvoiceCreate } from "@/types";

export async function fetchLuckyBoardStatus(): Promise<LuckyBoardStatus> {
  const { data } = await api.get<LuckyBoardStatus>("/lucky-board/status");
  return data;
}

/** `key` makes a retried request return the same spin instead of spending another one. */
export async function spinLuckyBoard(key: string): Promise<LuckyBoardSpin> {
  const { data } = await api.post<LuckyBoardSpin>("/lucky-board/spin", null, { headers: { "Idempotency-Key": key } });
  return data;
}

export async function createLuckyBoardInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/lucky-board/stars-invoice");
  return data;
}
