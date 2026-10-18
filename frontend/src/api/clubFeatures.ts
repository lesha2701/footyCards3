import { api } from "@/lib/api";
import type { ClubEmblem, ClubEmblemState, ClubLogoShape, ClubTreasury, StarsInvoiceCreate } from "@/types";

export async function fetchClubEmblem(): Promise<ClubEmblemState> {
  const { data } = await api.get<ClubEmblemState>("/clubs/me/emblem");
  return data;
}

export async function saveClubEmblem(
  payload: { logo_shape: ClubLogoShape; logo_color: string } & Omit<ClubEmblem, never>,
): Promise<ClubEmblemState> {
  const { data } = await api.put<ClubEmblemState>("/clubs/me/emblem", payload);
  return data;
}

export async function buyClubEmblemItem(itemId: number): Promise<ClubEmblemState> {
  const { data } = await api.post<ClubEmblemState>(`/clubs/me/emblem/items/${itemId}/buy`);
  return data;
}

export async function createClubEmblemInvoice(itemId: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/clubs/me/emblem/items/${itemId}/stars-invoice`);
  return data;
}

export async function fetchClubTreasury(): Promise<ClubTreasury> {
  const { data } = await api.get<ClubTreasury>("/clubs/me/treasury");
  return data;
}

export async function createClubDonationInvoice(stars: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/clubs/me/treasury/stars-invoice", { stars });
  return data;
}
