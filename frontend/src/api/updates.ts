import { api } from "@/lib/api";
import type { UpdateBroadcastStatus } from "@/types";

export async function fetchUpdateStatus(): Promise<UpdateBroadcastStatus> {
  const { data } = await api.get<UpdateBroadcastStatus>("/updates/status");
  return data;
}
