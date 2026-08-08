import { api } from "@/lib/api";
import type { Gift, GiftClaimResult, GiftSet, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export async function fetchGiftSets(): Promise<GiftSet[]> {
  const { data } = await api.get<GiftSet[]>("/gifts/sets");
  return data;
}

export async function createGiftInvoice(
  giftSetId: number, recipientId: number, message?: string
): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/gifts/invoice", {
    gift_set_id: giftSetId, recipient_id: recipientId, message,
  });
  return data;
}

export async function fetchGiftInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/gifts/stars-invoices/${payloadToken}`);
  return data;
}

export async function fetchMyGifts(): Promise<Gift[]> {
  const { data } = await api.get<Gift[]>("/gifts/mine");
  return data;
}

export async function claimGift(giftId: number): Promise<GiftClaimResult> {
  const { data } = await api.post<GiftClaimResult>(`/gifts/${giftId}/claim`);
  return data;
}
