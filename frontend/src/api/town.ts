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
  /** 0…100: care + houses + places + residents settled here. */
  mood: number;
  /** % of the houses' base rent the mood pays (70…120 by default). */
  pct: number;
  parts: { care: number; houses: number; decor: number; residents: number };
  /** Ids of the residents settled in the district. */
  residents: number[];
}

export interface TownMoodConfig {
  min_pct: number;
  max_pct: number;
  care: number;
  care_full_hours: number;
  care_zero_hours: number;
  houses: number;
  decor: number;
  resident: number;
  resident_legendary: number;
  resident_slots: number;
  cared_at: string | null;
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
  /** «Сезонный город»: the limited decorations the player holds (style only). */
  season_items?: TownSeasonOwned[];
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
  mood: TownMoodConfig;
  /** pending includes the guests' gifts (gifts), paid with the rent. */
  income: { rate_per_day: number; pending: number; cap: number; max_hours: number; gifts?: number };
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
  /** The district the resident lives in, if settled. */
  district?: string | null;
  /** The resident's bonus works now (settled, or settling not required). */
  bonus_active?: boolean;
  /** «Набор жителей» the resident belongs to. */
  set_name?: string | null;
}

export interface TownResidentSet {
  name: string;
  total: number;
  owned: number;
  complete: boolean;
  resident_ids: number[];
  rent_pct: number;
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
  /** Bonuses work only for residents settled in a district. */
  bonus_settled_only?: boolean;
  /** «Наборы жителей»: a whole set adds rent_pct % to the houses (all at most sets_max_pct). */
  sets?: TownResidentSet[];
  sets_pct?: number;
  sets_max_pct?: number;
  /** Present on a sale. */
  sold_coins?: number;
  new_balance?: number;
}

export async function fetchTownResidents(): Promise<TownResidentsAlbum> {
  const { data } = await api.get<TownResidentsAlbum>("/town/residents");
  return data;
}

export async function settleTownResident(residentId: number, district: string | null): Promise<TownState> {
  const { data } = await api.post<TownState>(`/town/residents/${residentId}/settle`, { district });
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

// --- residents' quests and guests (backend town_social_service) ---

export interface TownQuest {
  id: number;
  kind: string;
  label: string;
  target: number;
  progress: number;
  reward_coins: number;
  done: boolean;
  claimed: boolean;
  resident: { id: number; name: string; icon: string; image_path: string | null; rarity: Rarity } | null;
}

export interface TownQuests {
  day: string;
  quests: TownQuest[];
  paid?: number;
  new_balance?: number;
}

export async function fetchTownQuests(): Promise<TownQuests> {
  const { data } = await api.get<TownQuests>("/town/quests");
  return data;
}

export async function claimTownQuest(id: number): Promise<TownQuests> {
  const { data } = await api.post<TownQuests>(`/town/quests/${id}/claim`);
  return data;
}

export interface TownGuestTown {
  user_id: number;
  name: string;
  owner: string;
  friend: boolean;
  houses: number;
  likes: number;
  visited: boolean;
  liked: boolean;
  gifted: boolean;
}

export interface TownGuests {
  towns: TownGuestTown[];
  gift_price: number;
  gift_rent: number;
  gifts_left: number;
  likes_today: number;
  likes_total: number;
}

export async function fetchTownGuests(): Promise<TownGuests> {
  const { data } = await api.get<TownGuests>("/town/guests");
  return data;
}

export interface TownVisitView {
  user_id: number;
  name: string;
  owner: string;
  districts: { code: string; name: string; owned: number; total: number; mood: number }[];
  places: string[];
  season_items?: TownSeasonOwned[];
  hotel: boolean;
  population: number;
  likes_today: number;
  likes_total: number;
  liked: boolean;
  gifted: boolean;
  can_gift: boolean;
  gift_price: number;
  gift_rent: number;
  gifts_left: number;
  new_balance?: number;
}

export async function visitTown(ownerId: number): Promise<TownVisitView> {
  const { data } = await api.get<TownVisitView>(`/town/visit/${ownerId}`);
  return data;
}

export async function likeTown(ownerId: number): Promise<TownVisitView> {
  const { data } = await api.post<TownVisitView>(`/town/visit/${ownerId}/like`);
  return data;
}

export async function giftTown(ownerId: number): Promise<TownVisitView> {
  const { data } = await api.post<TownVisitView>(`/town/visit/${ownerId}/gift`);
  return data;
}

// --- «Город недели» (backend town_social_service.week_ranking) ---

export interface TownWeekRow {
  place: number;
  user_id: number;
  name: string;
  owner: string;
  score: number;
  likes: number;
  guests: number;
  houses: number;
  reward?: number;
}

export interface TownWeek {
  week: string;
  ends_on: string;
  points: { like: number; guest: number; house: number };
  rewards: { place: number; coins: number }[];
  top: TownWeekRow[];
  me: TownWeekRow | null;
  last_week: {
    week: string;
    winners: { place: number; user_id: number; owner: string; score: number; coins: number }[];
    mine: { place: number; coins: number } | null;
  };
}

export async function fetchTownWeek(): Promise<TownWeek> {
  const { data } = await api.get<TownWeek>("/town/week");
  return data;
}

// --- «Сезонный город» (backend town_season_service): Stars, style only ---

export type TownSeason = "winter" | "spring" | "summer" | "autumn";

export interface TownSeasonOwned {
  code: string;
  name: string;
  emoji: string;
  serial: number;
}

export interface TownSeasonItem {
  code: string;
  name: string;
  emoji: string;
  season: TownSeason;
  on_sale: boolean;
  owned: boolean;
  serial: number | null;
  sold: number;
  /** 0 = no limit. */
  supply: number;
}

export interface TownSeasonShop {
  season: TownSeason;
  season_name: string;
  stars: number;
  items: TownSeasonItem[];
}

export async function fetchTownSeason(): Promise<TownSeasonShop> {
  const { data } = await api.get<TownSeasonShop>("/town/season");
  return data;
}

export async function createTownSeasonInvoice(code: string): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/town/season/${code}/invoice`);
  return data;
}
