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
  /** Limited edition: total copies (null = unlimited) and copies left. */
  max_supply?: number | null;
  left?: number | null;
  /** Seasonal: on sale until this moment (ISO, null = always). */
  available_until?: string | null;
}

export interface EquipmentCollection {
  id: number;
  name: string;
  description: string | null;
  image_path: string | null;
  set_size: number;
  set_bonus_rating: number;
  /** «Комплект сборной»: the full set gives +N chemistry to this country's players in the squad. */
  set_team_country?: string | null;
  set_team_chemistry?: number;
  items: EquipmentItem[];
}

export interface EquipmentShop {
  enabled: boolean;
  slots: { code: string; label: string }[];
  caps: { rating: number; pp: number; chemistry: number; talisman_pct?: number };
  collections: EquipmentCollection[];
  singles: EquipmentItem[];
}

export interface EquipmentInventory {
  enabled: boolean;
  items: {
    copy_id: number; item: EquipmentItem; serial_number?: number | null; user_card_id: number | null; card_name: string | null;
    /** Bought with coins: binds to the first card it's put on. */
    binds?: boolean;
    /** That card (only it may wear the thing again). */
    bound_card_id?: number | null;
    bound_card_name?: string | null;
  }[];
}

export interface CardEquipmentSlot {
  code: string;
  label: string;
  available: boolean;
  /** `bound`: a thing bought with coins — belongs to this card for good. */
  worn: { copy_id: number; item: EquipmentItem; applies: boolean; bound?: boolean } | null;
  /** `binds`: bought with coins, not bound yet — putting it on binds it to this card;
   * `bound`: already this card's own. */
  options: { copy_id: number; item: EquipmentItem; applies: boolean; binds?: boolean; bound?: boolean }[];
}

export interface CardEquipment {
  enabled: boolean;
  card_id: number;
  rating_bonus: number;
  chemistry: number;
  boosts: {
    shot_pp?: number; dribble_pp?: number; save_pp?: number; tackle_pp?: number; pass_pp?: number;
    xp_pct?: number; coins_pct?: number; team_country?: string; team_chemistry?: number;
  };
  slots: CardEquipmentSlot[];
  /** Sets this card wears things of: progress toward each set bonus. */
  sets?: {
    name: string; have: number; needed: number; complete: boolean; bonus_rating: number;
    team_country: string | null; team_chemistry: number;
  }[];
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
