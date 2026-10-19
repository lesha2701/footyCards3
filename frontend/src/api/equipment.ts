import { api } from "@/lib/api";
import type { Rarity, StarsInvoiceCreate } from "@/types";

/** «Экипировка» (backend services/equipment_service.py). */
export interface EquipmentItem {
  id: number;
  name: string;
  description: string | null;
  image_path: string | null;
  icon: string;
  slot: string;
  slot_label: string;
  rarity: Rarity;
  collection_id: number | null;
  collection_name: string | null;
  effect: string;
  effect_value: number;
  effect_label: string;
  cond_club: string | null;
  cond_country: string | null;
  coins_price: number;
  stars_price: number;
  owned?: number;
}

export interface EquipmentCollection {
  id: number;
  name: string;
  description: string | null;
  image_path: string | null;
  set_size: number;
  set_bonus_rating: number;
  items: EquipmentItem[];
}

export interface EquipmentShop {
  enabled: boolean;
  slots: { code: string; label: string }[];
  caps: { rating: number; pp: number; chemistry: number };
  collections: EquipmentCollection[];
  singles: EquipmentItem[];
}

export interface EquipmentInventory {
  enabled: boolean;
  items: { copy_id: number; item: EquipmentItem; user_card_id: number | null; card_name: string | null }[];
}

export interface CardEquipmentSlot {
  code: string;
  label: string;
  available: boolean;
  worn: { copy_id: number; item: EquipmentItem; applies: boolean } | null;
  options: { copy_id: number; item: EquipmentItem; applies: boolean }[];
}

export interface CardEquipment {
  enabled: boolean;
  card_id: number;
  rating_bonus: number;
  chemistry: number;
  boosts: { shot_pp?: number; dribble_pp?: number };
  slots: CardEquipmentSlot[];
}

export async function fetchEquipmentShop(): Promise<EquipmentShop> {
  const { data } = await api.get<EquipmentShop>("/equipment/shop");
  return data;
}

export async function fetchEquipmentInventory(): Promise<EquipmentInventory> {
  const { data } = await api.get<EquipmentInventory>("/equipment/inventory");
  return data;
}

export async function fetchCardEquipment(cardId: number): Promise<CardEquipment> {
  const { data } = await api.get<CardEquipment>(`/equipment/cards/${cardId}`);
  return data;
}

export async function buyEquipment(itemId: number, idempotencyKey: string): Promise<{ copy_id: number; new_balance: number }> {
  const { data } = await api.post(`/equipment/items/${itemId}/buy`, { idempotency_key: idempotencyKey });
  return data;
}

export async function createEquipmentStarsInvoice(itemId: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/equipment/items/${itemId}/stars-invoice`);
  return data;
}

export async function equipItem(copyId: number, userCardId: number): Promise<CardEquipment> {
  const { data } = await api.post<CardEquipment>("/equipment/equip", { copy_id: copyId, user_card_id: userCardId });
  return data;
}

export async function unequipItem(copyId: number): Promise<EquipmentInventory> {
  const { data } = await api.post<EquipmentInventory>("/equipment/unequip", { copy_id: copyId });
  return data;
}
