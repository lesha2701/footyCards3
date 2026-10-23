import { api } from "@/lib/api";
import type { Rarity, StarsInvoiceCreate } from "@/types";

/** «Музы» (backend services/muse_service.py). */
export interface Muse {
  id: number;
  name: string;
  title: string | null;
  description: string | null;
  icon: string;
  image_path: string | null;
  rarity: Rarity;
  collection_id: number | null;
  effect: string;
  effect_value: number;
  /** The bonus as it works now (gifts included, ceilings applied). */
  effect_label: string;
  base_effect_label: string;
  boosted_value: number;
  boost_pct: number;
  owned: boolean;
  user_muse_id: number | null;
  copies: number;
  is_active: boolean;
  accessory_ids: number[];
  spare_coins: number;
}

export interface MuseAccessory {
  id: number;
  name: string;
  description: string | null;
  icon: string;
  image_path: string | null;
  kind: string;
  kind_label: string;
  rarity: Rarity;
  boost_pct: number;
  coins_price: number;
  stars_price: number;
}

export interface MuseCollectionView {
  id: number | null;
  name: string;
  description: string | null;
  image_path: string | null;
  muses: Muse[];
}

export interface MuseDateToday {
  game: string;
  game_title: string;
  /** The game page, with ?muse=1. */
  path: string;
  completed: boolean;
  coins: number;
}

export interface MuseAlbum {
  enabled: boolean;
  collections: MuseCollectionView[];
  active: Muse | null;
  owned_count: number;
  total_count: number;
  daily: { coins: number; claimed_today: boolean; claimed_coins: number };
  /** «Свидание»: today's random mini-game with the Muse (once a day). */
  date: {
    today: MuseDateToday | null;
    coins: number;
    /** On: her bonus works only while inspired by a date. */
    required: boolean;
    inspiration_hours: number;
    inspired_until: string | null;
  };
  accessories: MuseAccessory[];
  caps: { stat: number; pp: number; xp_pct: number; daily_coins: number; accessory_pct: number };
  claimed?: number;
  sold_coins?: number;
  new_balance?: number;
}

export async function fetchMuses(): Promise<MuseAlbum> {
  const { data } = await api.get<MuseAlbum>("/muses");
  return data;
}

export async function setActiveMuse(museId: number | null): Promise<MuseAlbum> {
  const { data } = await api.post<MuseAlbum>("/muses/active", { muse_id: museId });
  return data;
}

export async function claimMuseDaily(): Promise<MuseAlbum> {
  const { data } = await api.post<MuseAlbum>("/muses/daily/claim");
  return data;
}

export async function startMuseDate(): Promise<MuseDateToday> {
  const { data } = await api.post<MuseDateToday>("/muses/date/start");
  return data;
}

export async function sellSpareMuse(museId: number, count = 1): Promise<MuseAlbum> {
  const { data } = await api.post<MuseAlbum>(`/muses/${museId}/sell-spare`, { count });
  return data;
}

export async function buyMuseGift(museId: number, accessoryId: number, idempotencyKey: string): Promise<MuseAlbum> {
  const { data } = await api.post<MuseAlbum>(`/muses/${museId}/gifts`, {
    accessory_id: accessoryId, idempotency_key: idempotencyKey,
  });
  return data;
}

export async function createMuseGiftStarsInvoice(museId: number, accessoryId: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/muses/${museId}/gifts/stars-invoice`, { accessory_id: accessoryId });
  return data;
}
