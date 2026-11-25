import { api } from "@/lib/api";
import type {
  Gift, GiftClaimResult, GiftHistory, GiftLeaderboard, GiftPurchaseResult, GiftSet, GiftShelf, StarsInvoiceCreate,
  StarsInvoiceStatus,
} from "@/types";

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

export async function buyCollectibleWithCoins(
  giftSetId: number, recipientId: number, message?: string
): Promise<GiftPurchaseResult> {
  const { data } = await api.post<GiftPurchaseResult>(`/gifts/collectibles/${giftSetId}/buy-with-coins`, {
    recipient_id: recipientId, message,
  });
  return data;
}

export async function pinGift(giftId: number, pinned: boolean): Promise<Gift> {
  const { data } = await api.patch<Gift>(`/gifts/${giftId}/pin`, { pinned });
  return data;
}

export async function fetchGiftTransferPrice(): Promise<{ stars: number }> {
  const { data } = await api.get<{ stars: number }>("/gifts/transfer-price");
  return data;
}

/** Numbered copies the user owns, passed on to another player — Stars only. */
export async function createGiftTransferInvoice(
  giftIds: number[], recipientId: number, message?: string,
): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/gifts/transfer-invoice", {
    gift_ids: giftIds, recipient_id: recipientId, message: message || undefined,
  });
  return data;
}

export async function markGiftTransfersSeen(): Promise<void> {
  await api.post("/gifts/seen");
}

export async function fetchGiftHistory(giftId: number): Promise<GiftHistory> {
  const { data } = await api.get<GiftHistory>(`/gifts/${giftId}/history`);
  return data;
}

export async function fetchGiftLeaderboard(): Promise<GiftLeaderboard> {
  const { data } = await api.get<GiftLeaderboard>("/gifts/leaderboard");
  return data;
}

export async function fetchGiftShelf(userId: number): Promise<GiftShelf> {
  const { data } = await api.get<GiftShelf>(`/users/${userId}/gift-shelf`);
  return data;
}
