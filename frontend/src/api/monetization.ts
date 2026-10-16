import { api } from "@/lib/api";
import type {
  ClubPass,
  CosmeticCatalog,
  CosmeticKind,
  GrantedRewards,
  SeasonPass,
  StarsInvoiceCreate,
  StarterOffer,
} from "@/types";

// --- cosmetics ---
export async function fetchCosmetics(): Promise<CosmeticCatalog> {
  const { data } = await api.get<CosmeticCatalog>("/cosmetics");
  return data;
}

export async function buyCosmeticWithCoins(id: number): Promise<CosmeticCatalog> {
  const { data } = await api.post<CosmeticCatalog>(`/cosmetics/${id}/buy`);
  return data;
}

export async function createCosmeticStarsInvoice(id: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/cosmetics/${id}/stars-invoice`);
  return data;
}

export async function equipCosmetic(kind: CosmeticKind, cosmeticId: number | null): Promise<CosmeticCatalog> {
  const { data } = await api.post<CosmeticCatalog>("/cosmetics/equip", { kind, cosmetic_id: cosmeticId });
  return data;
}

// --- «Клубный абонемент» ---
export async function fetchClubPass(): Promise<ClubPass> {
  const { data } = await api.get<ClubPass>("/club-pass");
  return data;
}

export async function createClubPassInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/club-pass/stars-invoice");
  return data;
}

export async function claimClubPassDaily(): Promise<GrantedRewards> {
  const { data } = await api.post<GrantedRewards>("/club-pass/daily");
  return data;
}

export async function setClubPassAutoRenew(autoRenew: boolean): Promise<ClubPass> {
  const { data } = await api.post<ClubPass>("/club-pass/auto-renew", { auto_renew: autoRenew });
  return data;
}

// --- «Сезонный пропуск» ---
export async function fetchSeasonPass(): Promise<SeasonPass> {
  const { data } = await api.get<SeasonPass>("/season-pass");
  return data;
}

export async function claimSeasonReward(level: number, track: "free" | "premium"): Promise<GrantedRewards> {
  const { data } = await api.post<GrantedRewards>("/season-pass/claim", { level, track });
  return data;
}

export async function createSeasonPassInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/season-pass/stars-invoice");
  return data;
}

// --- starter offer ---
export async function fetchStarterOffer(): Promise<StarterOffer> {
  const { data } = await api.get<StarterOffer>("/starter-offer");
  return data;
}

export async function markStarterOfferSeen(): Promise<StarterOffer> {
  const { data } = await api.post<StarterOffer>("/starter-offer/seen");
  return data;
}

export async function createStarterOfferInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/starter-offer/stars-invoice");
  return data;
}

export async function fetchShopInvoiceStatus(token: string): Promise<{ status: "pending" | "completed" }> {
  const { data } = await api.get<{ status: "pending" | "completed" }>(`/shop/stars-invoices/${token}`);
  return data;
}
