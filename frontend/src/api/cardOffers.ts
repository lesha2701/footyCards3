import { api } from "@/lib/api";
import type { CardOffer, CardOfferAdmin, CardOfferAdminInput, StarsInvoiceCreate } from "@/types";

export async function fetchCardOffers(): Promise<CardOffer[]> {
  const { data } = await api.get<CardOffer[]>("/card-offers");
  return data;
}

export async function createCardOfferInvoice(offerId: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/card-offers/${offerId}/stars-invoice`);
  return data;
}

export async function fetchAdminCardOffers(): Promise<CardOfferAdmin[]> {
  const { data } = await api.get<CardOfferAdmin[]>("/admin/card-offers");
  return data;
}

export async function saveAdminCardOffer(body: CardOfferAdminInput, id?: number): Promise<CardOfferAdmin> {
  const { data } = id
    ? await api.put<CardOfferAdmin>(`/admin/card-offers/${id}`, body)
    : await api.post<CardOfferAdmin>("/admin/card-offers", body);
  return data;
}

export async function deleteAdminCardOffer(id: number): Promise<void> {
  await api.delete(`/admin/card-offers/${id}`);
}
