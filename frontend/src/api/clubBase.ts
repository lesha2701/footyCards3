import { api } from "@/lib/api";
import type { ClubBaseLook, ClubBaseState, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export async function fetchClubBase(): Promise<ClubBaseState> {
  const { data } = await api.get<ClubBaseState>("/club-base");
  return data;
}

export async function upgradeClubBaseBuilding(code: string, idempotencyKey: string): Promise<ClubBaseState> {
  const { data } = await api.post<ClubBaseState>(`/club-base/buildings/${code}/upgrade`, { idempotency_key: idempotencyKey });
  return data;
}

export async function claimClubBaseIncome(idempotencyKey: string): Promise<ClubBaseState> {
  const { data } = await api.post<ClubBaseState>("/club-base/income/claim", { idempotency_key: idempotencyKey });
  return data;
}

export async function setStadiumLook(look: Partial<ClubBaseLook>): Promise<ClubBaseState> {
  const { data } = await api.put<ClubBaseState>("/club-base/stadium/look", look);
  return data;
}

export async function createClubBaseSpeedupInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/club-base/speedup-invoice");
  return data;
}

export async function fetchClubBaseInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/club-base/stars-invoices/${payloadToken}`);
  return data;
}

export async function buyStadiumCosmetic(code: string, idempotencyKey: string): Promise<ClubBaseState> {
  const { data } = await api.post<ClubBaseState>(`/club-base/cosmetics/${code}/buy`, { idempotency_key: idempotencyKey });
  return data;
}

export async function createStadiumCosmeticInvoice(code: string): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/club-base/cosmetics/${code}/stars-invoice`);
  return data;
}
