import { api } from "@/lib/api";
import type { Rarity, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export interface TownDistrictState {
  code: string;
  name: string;
  /** Coins a day one house of the district pays. */
  rent: number;
  /** What the next house of the district costs now (dearer with every house owned). */
  next_price: number;
  owned: number;
  total: number;
}

export interface TownHotel {
  owned: boolean;
  price: number;
  /** Cards the player holds now — the hotel's guests. */
  cards: number;
  /** Cards counted at most. */
  max_cards: number;
  rent_per_100_cards: number;
  /** Coins a day the hotel pays (or would pay) for the cards held now. */
  rent: number;
}

export interface TownResidentsState {
  enabled: boolean;
  /** Copies of resident cards held. */
  population: number;
  rent_per_resident: number;
  /** Coins a day the residents pay (population × rent). */
  rent: number;
  /** Bonuses of the residents (each resident counted once, capped). */
  rent_pct: number;
  hotel_pct: number;
  daily_coins: number;
}

export interface TownDecor {
  code: string;
  name: string;
  price: number;
  rent_pct: number;
  owned: boolean;
}

export interface TownState {
  enabled: boolean;
  /** Opened for coins (or open to everyone when unlock_coins is 0). */
  unlocked: boolean;
  unlock_coins: number;
  /** 0 — renaming is not sold. */
  rename_stars: number;
  /** The player's own name for the town; null — not named yet. */
  name: string | null;
  hotel: TownHotel;
  residents: TownResidentsState;
  /** Closed places on the map: bought once, each adds rent_pct % to the houses' rent. */
  decor: TownDecor[];
  /** +% to the houses' rent from the places bought. */
  decor_pct: number;
  houses: { district: string; code: string }[];
  owned_total: number;
  total_houses: number;
  price_growth_pct: number;
  districts: TownDistrictState[];
  income: { rate_per_day: number; pending: number; cap: number; max_hours: number };
  /** Present on a purchase / a claim. */
  new_balance?: number;
  claimed?: number;
}

export async function fetchTown(): Promise<TownState> {
  const { data } = await api.get<TownState>("/town");
  return data;
}

export async function buyTownHouse(district: string, code: string, idempotencyKey: string): Promise<TownState> {
  const { data } = await api.post<TownState>(`/town/houses/${district}/${code}/buy`, { idempotency_key: idempotencyKey });
  return data;
}

export async function claimTownIncome(idempotencyKey: string): Promise<TownState> {
  const { data } = await api.post<TownState>("/town/income/claim", { idempotency_key: idempotencyKey });
  return data;
}

export async function buyTownHotel(idempotencyKey: string): Promise<TownState> {
  const { data } = await api.post<TownState>("/town/hotel/buy", { idempotency_key: idempotencyKey });
  return data;
}

export async function buyTownDecor(code: string, idempotencyKey: string): Promise<TownState> {
  const { data } = await api.post<TownState>(`/town/decor/${code}/buy`, { idempotency_key: idempotencyKey });
  return data;
}

export async function unlockTown(idempotencyKey: string): Promise<TownState> {
  const { data } = await api.post<TownState>("/town/unlock", { idempotency_key: idempotencyKey });
  return data;
}

/** A «Житель города» card — the same card fields as a «Муза». */
export interface TownResident {
  id: number;
  name: string;
  title: string | null;
  description: string | null;
  icon: string;
  image_path: string | null;
  rarity: Rarity;
  bonus: string;
  bonus_value: number;
  bonus_label: string;
  effect_label: string;
  owned: boolean;
  copies: number;
  /** Coins one spare copy sells for. */
  spare_coins: number;
}

export interface TownResidentsAlbum {
  enabled: boolean;
  residents: TownResident[];
  owned_count: number;
  total_count: number;
  population: number;
  rent_per_resident: number;
  /** Each kind summed over the residents owned (capped); xp_pct, game_attempts
   * and build_pct work outside the town (Мой игрок, mini-games, the base). */
  bonuses: { rent_pct: number; hotel_pct: number; daily_coins: number; xp_pct?: number; game_attempts?: number; build_pct?: number };
  caps: { pct: number; daily_coins: number };
  /** Present on a sale. */
  sold_coins?: number;
  new_balance?: number;
}

export async function fetchTownResidents(): Promise<TownResidentsAlbum> {
  const { data } = await api.get<TownResidentsAlbum>("/town/residents");
  return data;
}

export async function sellTownResidentSpare(residentId: number, count = 1): Promise<TownResidentsAlbum> {
  const { data } = await api.post<TownResidentsAlbum>(`/town/residents/${residentId}/sell-spare`, { count });
  return data;
}

export async function createTownRenameInvoice(name: string): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/town/rename-invoice", { name });
  return data;
}

export async function fetchTownInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/town/stars-invoices/${payloadToken}`);
  return data;
}
