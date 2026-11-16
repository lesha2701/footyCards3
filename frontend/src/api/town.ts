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
  /** «Моя вилла»: its prestige and the +% it adds to the houses' rent; level and car once opened. */
  villa?: TownVillaSummary;
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
  /** null — the owner has no villa yet. */
  villa?: { villa_level: number; prestige: number; car: string | null } | null;
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

// --- «Моя вилла» -------------------------------------------------------------------------------

export interface TownVillaSummary {
  prestige: number;
  rent_pct: number;
  villa_level?: number;
  car?: string | null;
}

export type VillaKind = "villa" | "garage" | "car" | "yard" | "premium";

export interface VillaItem {
  id: number;
  code: string;
  name: string;
  emoji: string;
  kind: VillaKind;
  w: number;
  h: number;
  /** Both null — in storage. */
  x: number | null;
  y: number | null;
  /** 1 — turned: w and h swapped. */
  rot: number;
  serial: number | null;
  /** The villa's / the garage's level. */
  level: number | null;
}

export interface VillaStaff {
  post: string;
  name: string;
  emoji: string;
  /** Its workplace stands on the plot — only then the post adds prestige. */
  working: boolean;
  resident: { id: number; name: string; title: string | null; icon: string; image_path: string | null; rarity: string };
}

/** Two things standing side by side. */
export interface VillaCombo {
  a: string;
  b: string;
  name: string;
  emoji: string;
  ids: number[];
}

/** What anyone may see of a villa. */
export interface VillaPlotView {
  villa_level: number;
  garage_level: number;
  /** Cells a side open at this villa level (from the back corner). */
  grid: number;
  /** Cells a side of the whole lawn (the last level). */
  grid_max: number;
  combos: VillaCombo[];
  items: VillaItem[];
  car: { id: number; code: string; name: string; emoji: string } | null;
  staff: VillaStaff[];
  prestige: number;
  prestige_pct: number;
  user_id: number;
  likes_total: number;
}

export interface VillaShopItem {
  code: string;
  name: string;
  emoji: string;
  kind: VillaKind;
  w: number;
  h: number;
  coins: number;
  stars: number;
  prestige: number;
  owned: number;
  /** > 0 — limited, numbered copies. */
  supply: number;
  sold: number;
  can_buy: boolean;
  reason: string;
}

export interface VillaState extends VillaPlotView {
  next_villa: { level: number; price: number; grid: number } | null;
  next_garage: { level: number; price: number; slots: number } | null;
  garage_slots: number;
  cars: number;
  shop: VillaShopItem[];
  posts: { post: string; name: string; emoji: string; workplace: string[] }[];
  all_combos: { a: string; b: string; name: string; emoji: string; a_name: string; b_name: string }[];
  prestige_combo: number;
  prestige_staff: number;
  candidates: { id: number; name: string; title: string | null; icon: string; image_path: string | null; rarity: string; posts: string[] }[];
  prestige_per_pct: number;
  prestige_max_pct: number;
  max_items: number;
  new_balance?: number;
}

export interface VillaGuestView extends VillaPlotView {
  liked: boolean;
  likes_week: number;
}

export interface VillaWeek {
  ends_on: string;
  rewards: { place: number; coins: number }[];
  top: { user_id: number; owner: string; likes: number; villa_level: number; place: number; reward: number }[];
  me: { place: number; likes: number } | null;
  last_week: { place: number; user_id: number; owner: string; likes: number; coins: number }[];
}

export async function fetchVilla(): Promise<VillaState> {
  const { data } = await api.get<VillaState>("/town/villa");
  return data;
}

export async function upgradeVilla(target: "villa" | "garage", idempotencyKey: string): Promise<VillaState> {
  const { data } = await api.post<VillaState>("/town/villa/upgrade", { target, idempotency_key: idempotencyKey });
  return data;
}

export async function buyVillaItem(code: string, idempotencyKey: string): Promise<VillaState> {
  const { data } = await api.post<VillaState>(`/town/villa/items/${code}/buy`, { idempotency_key: idempotencyKey });
  return data;
}

export async function createVillaInvoice(code: string): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/town/villa/items/${code}/invoice`);
  return data;
}

export async function saveVillaLayout(items: { id: number; x: number | null; y: number | null; rot: number }[]): Promise<VillaState> {
  const { data } = await api.put<VillaState>("/town/villa/layout", { items });
  return data;
}

export async function chooseVillaCar(itemId: number | null): Promise<VillaState> {
  const { data } = await api.post<VillaState>("/town/villa/car", { item_id: itemId });
  return data;
}

export async function setVillaStaff(post: string, residentId: number | null): Promise<VillaState> {
  const { data } = await api.post<VillaState>("/town/villa/staff", { post, resident_id: residentId });
  return data;
}

export async function visitVilla(ownerId: number): Promise<VillaGuestView> {
  const { data } = await api.get<VillaGuestView>(`/town/visit/${ownerId}/villa`);
  return data;
}

export async function likeVilla(ownerId: number): Promise<VillaGuestView> {
  const { data } = await api.post<VillaGuestView>(`/town/visit/${ownerId}/villa/like`);
  return data;
}

export async function fetchVillaWeek(): Promise<VillaWeek> {
  const { data } = await api.get<VillaWeek>("/town/villa/week");
  return data;
}
