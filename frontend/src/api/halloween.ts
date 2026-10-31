import { api } from "@/lib/api";
import type { HalloweenBuyResult, HalloweenDoorResult, HalloweenState } from "@/types";

export async function fetchHalloween(): Promise<HalloweenState> {
  const { data } = await api.get<HalloweenState>("/halloween");
  return data;
}

export async function buyHalloweenItem(code: string, idempotencyKey: string): Promise<HalloweenBuyResult> {
  const { data } = await api.post<HalloweenBuyResult>(`/halloween/shop/${code}`, { idempotency_key: idempotencyKey });
  return data;
}

export async function openHalloweenDoor(door: number): Promise<HalloweenDoorResult> {
  const { data } = await api.post<HalloweenDoorResult>(`/halloween/doors/${door}`);
  return data;
}
