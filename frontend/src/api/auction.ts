import { api } from "@/lib/api";
import type { UserCard } from "@/types";

/** «Трансферный рынок» rules — every number comes from GameConfig. */
export interface AuctionInfo {
  enabled: boolean;
  durations_hours: number[];
  fee_pct: number;
  min_increment_pct: number;
  min_increment_coins: number;
  min_price: number;
  min_price_quick_sell_pct: number;
  max_active_lots: number;
  snipe_window_seconds: number;
  snipe_extend_seconds: number;
  min_account_age_days: number;
  premium_min_price: number;
  premium_rating: number;
  my_active_lots: number;
  restriction: string | null;
  server_now: string;
}

export interface AuctionBid {
  id: number;
  bidder_name: string;
  is_mine: boolean;
  amount: number;
  kind: "bid" | "buy_now";
  status: string;
  created_at: string;
}

export type AuctionLotStatus = "active" | "sold" | "expired" | "cancelled" | "removed";

export interface AuctionLot {
  id: number;
  card: UserCard;
  seller_id: number;
  seller_name: string;
  status: AuctionLotStatus;
  start_price: number;
  buy_now_price: number | null;
  current_bid: number | null;
  bid_count: number;
  min_next_bid: number;
  fee_pct: number;
  duration_hours: number;
  ends_at: string;
  created_at: string;
  closed_at: string | null;
  final_price: number | null;
  fee_amount: number | null;
  close_reason: string | null;
  is_mine: boolean;
  i_am_leading: boolean;
  i_won: boolean;
  my_max_bid: number | null;
  leader_name: string | null;
  server_now: string;
  bids: AuctionBid[] | null;
}

export interface AuctionLotFilters {
  search?: string;
  rarity?: string;
  position?: string;
  skill?: string;
  min_stars?: number;
  min_price?: number;
  max_price?: number;
  sort?: "ending" | "newest" | "price_asc" | "price_desc";
  limit?: number;
  offset?: number;
}

export interface AuctionActionResult {
  lot: AuctionLot;
  new_balance: number;
}

export async function fetchAuctionInfo(): Promise<AuctionInfo> {
  const { data } = await api.get<AuctionInfo>("/auction/info");
  return data;
}

export async function fetchAuctionLots(filters: AuctionLotFilters): Promise<{ items: AuctionLot[]; total: number }> {
  const { data } = await api.get<{ items: AuctionLot[]; total: number }>("/auction/lots", { params: filters });
  return data;
}

export async function fetchMyAuctionLots(): Promise<AuctionLot[]> {
  const { data } = await api.get<AuctionLot[]>("/auction/my-lots");
  return data;
}

export async function fetchMyAuctionBids(): Promise<AuctionLot[]> {
  const { data } = await api.get<AuctionLot[]>("/auction/my-bids");
  return data;
}

export async function fetchAuctionLot(id: number): Promise<AuctionLot> {
  const { data } = await api.get<AuctionLot>(`/auction/lots/${id}`);
  return data;
}

export async function fetchAuctionPriceFloor(userCardId: number): Promise<{ user_card_id: number; min_price: number; premium: boolean }> {
  const { data } = await api.get(`/auction/price-floor/${userCardId}`);
  return data as { user_card_id: number; min_price: number; premium: boolean };
}

export async function createAuctionLot(payload: {
  user_card_id: number;
  start_price: number;
  buy_now_price?: number | null;
  duration_hours: number;
  confirm_last_copy?: boolean;
}): Promise<AuctionLot> {
  const { data } = await api.post<AuctionLot>("/auction/lots", payload);
  return data;
}

export async function placeAuctionBid(id: number, amount: number, idempotencyKey: string): Promise<AuctionActionResult> {
  const { data } = await api.post<AuctionActionResult>(`/auction/lots/${id}/bid`, {
    amount,
    idempotency_key: idempotencyKey,
  });
  return data;
}

export async function buyAuctionLotNow(id: number, expectedPrice: number): Promise<AuctionActionResult> {
  const { data } = await api.post<AuctionActionResult>(`/auction/lots/${id}/buy-now`, { expected_price: expectedPrice });
  return data;
}

export async function cancelAuctionLot(id: number): Promise<AuctionLot> {
  const { data } = await api.post<AuctionLot>(`/auction/lots/${id}/cancel`);
  return data;
}

/** Client clock skew vs the server, so countdowns match the server's ends_at. */
export function serverOffsetMs(serverNow: string): number {
  return new Date(serverNow).getTime() - Date.now();
}

export function formatTimeLeft(ms: number): string {
  if (ms <= 0) return "Завершается…";
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h} ч ${m.toString().padStart(2, "0")} мин`;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export const LOT_STATUS_LABELS: Record<AuctionLotStatus, string> = {
  active: "Идут торги",
  sold: "Продан",
  expired: "Не продан",
  cancelled: "Снят продавцом",
  removed: "Снят администрацией",
};

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID().replace(/-/g, "");
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
}
