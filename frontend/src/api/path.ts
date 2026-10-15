import { api } from "@/lib/api";
import type { PathCatalog, PathState, StarsInvoiceCreate, StarsInvoiceStatus, UserCard } from "@/types";

export async function fetchPathCatalog(): Promise<PathCatalog> {
  const { data } = await api.get<PathCatalog>("/path/catalog");
  return data;
}

export async function fetchPathState(cardId: number): Promise<PathState> {
  const { data } = await api.get<PathState>(`/path/cards/${cardId}`);
  return data;
}

export async function buyPathAttempt(cardId: number, idempotencyKey: string): Promise<PathState & { new_balance: number }> {
  const { data } = await api.post<PathState & { new_balance: number }>(`/path/cards/${cardId}/buy-attempt`, { idempotency_key: idempotencyKey });
  return data;
}

export async function createPathStarsInvoice(cardId: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/path/cards/${cardId}/stars-invoice`);
  return data;
}

export async function fetchPathStarsInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/path/stars-invoices/${payloadToken}`);
  return data;
}

export async function raisePrestige(
  cardId: number, payload: { material_card_ids?: number[]; confirm_skill_loss?: boolean; idempotency_key: string },
): Promise<PathState & { granted?: Record<string, unknown>; new_balance?: number }> {
  const { data } = await api.post(`/path/cards/${cardId}/prestige`, payload);
  return data;
}

export async function reforgeTalent(cardId: number, talentCode: string, idempotencyKey: string): Promise<PathState> {
  const { data } = await api.post<PathState>(`/path/cards/${cardId}/reforge`, { talent_code: talentCode, idempotency_key: idempotencyKey });
  return data;
}

export async function fetchAcademyShowcase(userId: number): Promise<UserCard[]> {
  const { data } = await api.get<UserCard[]>(`/path/showcase/${userId}`);
  return data;
}
