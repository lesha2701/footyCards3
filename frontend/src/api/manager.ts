import type { CareerTableRow } from "@/api/career";
import type { MyPlayerAppearance } from "@/api/myPlayer";
import { api } from "@/lib/api";

/** Four styles in a circle: Атака > Оборона > Владение > Контратака > Атака. */
export type ManagerStyle = "attacking" | "possession" | "defensive" | "counter";
export type ManagerLine = "GK" | "DEF" | "MID" | "FWD";

/** Club money is euros (`€`), only inside «Менеджер»; wages of users' players are coins. */
export interface ManagerSquadPlayer {
  slot?: string;
  key?: string;
  /** own = my «Мой игрок», academy = my academy card (both always start),
   * live = another user's «Мой игрок», npc = a catalog footballer, kid = an academy kid in an empty slot. */
  kind: "own" | "academy" | "live" | "npc" | "kid";
  name: string;
  position: string;
  rating: number;
  value?: number;
  user_id?: number;
  owner_name?: string;
  player_id?: number;
  loan?: boolean;
  auto?: boolean;
  /** A «Мой игрок» on the pitch. */
  appearance?: MyPlayerAppearance;
  number?: number;
  /** A card's picture (static path). */
  photo?: string | null;
}

export interface ManagerContract {
  id: number;
  user_id: number;
  kind: "sign" | "transfer" | "loan";
  status: "offered" | "active" | "on_loan" | "ended" | "declined" | "cancelled";
  /** Transfer / loan fee, € to the selling club. */
  fee: number;
  /** Coins per season to the player's wallet. */
  wage: number;
  /** What the wage costs the club, €. */
  wage_eur: number;
  seasons_total: number;
  seasons_left: number;
  club_agreed: boolean;
  player_agreed: boolean;
  matches_played: number;
  goals: number;
  assists: number;
  earned: number;
  player_name: string;
  owner_name: string;
  position: string | null;
  rating: number | null;
  value: number | null;
  club_name: string | null;
  club_owner: string | null;
}

export interface ManagerNpc {
  id: number;
  player_id: number;
  name: string;
  position: string;
  rating: number;
  kind: "buy" | "loan";
  auto: boolean;
  seasons_left: number;
  /** € per season this club pays (division and «Бухгалтерия» applied). */
  wage: number;
  goals: number;
  value: number;
  sell_back: number;
}

export interface ManagerLook {
  shape: string;
  symbol: string;
  color: string;
  color2: string;
  kit: string;
  kit_color: string;
  kit_color2: string;
  frame: string;
  theme: string;
  /** Emblem outline and effect from «Стиль» ("none" = without). */
  rim?: string;
  fx?: string;
}

export interface ManagerBase {
  level: number;
  stadium: number;
  marketing: number;
  shop: number;
  matchday_pct: number;
  discount_pct: number;
  capacity: number;
}

export interface ManagerClub {
  id: number;
  name: string;
  formation: string;
  style: ManagerStyle;
  budget: number;
  division: number;
  division_name: string;
  /** Its league is running — no transfers. */
  playing: boolean;
  seasons_played: number;
  titles: number;
  best_division: number | null;
  base: ManagerBase;
  next_grant: { grant: number; bonus: number; bonus_raw: number; total: number };
  ticket_per_home_match: number;
  squad: { xi: ManagerSquadPlayer[]; bench: ManagerSquadPlayer[]; rating: number; kids: number; formation: string };
  contracts: ManagerContract[];
  offers_sent: ManagerContract[];
  /** Other clubs asking for my players. */
  incoming: ManagerContract[];
  npcs: ManagerNpc[];
  /** Wages the next season start takes for the squad already signed — set aside. */
  wages_per_season: number;
  /** The budget above those wages: what the window's deals may spend. */
  free_budget: number;
  squad_value: number;
  /** The next league match (during a season). */
  next_match: ManagerNextMatch | null;
  live_count: number;
  academy_card_id: number | null;
  academy_options: { card_id: number; name: string; position: string; rating: number }[];
  look: ManagerLook;
  owned_cosmetics: string[];
  stadium_name: string | null;
  pro: boolean;
  pro_until: string | null;
  merch: { sold: number; eur_season: number; cap_eur: number };
}

export interface ManagerNextMatch {
  opponent: string;
  owner_name: string | null;
  rating: number | null;
  home: boolean;
  at: string | null;
  style: ManagerStyle;
  formation: string;
  /** Does my style beat theirs? */
  edge: "win" | "lose" | "even";
  /** % on my lines' ratings in that match (style + formation + edge). */
  mods: Record<ManagerLine, number>;
}

export interface ManagerTacticsRules {
  styles: { value: ManagerStyle; label: string; about: string; beats: ManagerStyle; beats_label: string; reason: string }[];
  formations: { value: string; label: string; attack: number; defense: number }[];
  edge_pct: number;
}

export interface ManagerLeagueMatch {
  home: string;
  away: string;
  mine: boolean;
  /** Both teams are manager clubs. */
  live: boolean;
  hs?: number;
  away_score?: number;
  goals?: { team: "a" | "b"; minute: number | null; name: string; home: boolean }[];
  /** [home, away] styles / formations of a played match. */
  styles?: [ManagerStyle, ManagerStyle] | null;
  formations?: [string, string] | null;
}

export interface ManagerLeague {
  id: number;
  season_key: string;
  division: number;
  division_name: string;
  status: "active" | "finished";
  rounds_played: number;
  total_rounds: number;
  next_round_at: string | null;
  table: (CareerTableRow & {
    name: string; owner_name: string | null; club_id: number | null; is_mine: boolean; is_live: boolean; zone: "up" | "down" | null;
  })[];
  rounds: { index: number; at: string | null; matches: ManagerLeagueMatch[] }[];
  players: { name: string; team: string; matches: number; goals: number; assists: number; avg_rating: number | null }[];
  champion: string | null;
}

export interface ManagerRules {
  found_cost: number;
  min_level: number;
  max_live: number;
  squad_max: number;
  live_wage_max: number;
  wage_eur_per_coin: number;
  contract_seasons: number[];
  league_size: number;
  promote: number;
  place_rewards: number[];
  place_budget: number[];
  rounds: number;
  divisions: number;
  promotion_bonus_pct: number;
  parachute_pct: number;
  tactics: ManagerTacticsRules;
}

export interface ManagerCosmetic {
  code: string;
  kind: "shape" | "symbol" | "rim" | "fx" | "kit" | "frame" | "theme" | "stadium_name";
  name: string;
  value: string;
  coins: number;
  stars: number;
  owned: boolean;
  usable: boolean;
}

export interface ManagerMerchItem {
  code: string;
  name: string;
  emoji: string;
  coins: number;
  eur: number;
}

export interface ManagerShop {
  cosmetics: ManagerCosmetic[];
  palette: string[];
  merch_items: ManagerMerchItem[];
  my_merch: { club_name: string; code: string; emoji: string; name: string }[];
  pro_stars: number;
  pro_days: number;
}

export interface ManagerView {
  enabled: boolean;
  has_player: boolean;
  balance: number;
  level: number;
  market_open: boolean;
  /** My «Мой игрок»'s transfer value (€), rating and change since the last season start (%). */
  my_value: number | null;
  my_rating: number | null;
  my_trend_pct: number | null;
  season: {
    key: string; phase: "preseason" | "season"; preseason_ends_at: string; first_round_at: string; slots: string[]; rounds: number;
  };
  pyramid: { division: number; name: string; clubs: number; capacity: number | null; grant: number; rating: number }[];
  rules: ManagerRules;
  club: ManagerClub | null;
  /** My own «Мой игрок» at another club. */
  contract: ManagerContract | null;
  offers: ManagerContract[];
  league: ManagerLeague | null;
  shop: ManagerShop;
}

export interface ManagerMarketPlayer {
  user_id: number;
  player_name: string;
  owner_name: string;
  position: string;
  rating: number;
  level: number;
  value: number;
  trend_pct: number | null;
  is_friend: boolean;
  looking: boolean;
  offered: boolean;
  club: { name: string; seasons_left: number; on_loan: boolean; division: number } | null;
}

export interface ManagerCatalogPlayer {
  player_id: number;
  name: string;
  position: string;
  rating: number;
  club: string;
  country: string;
  value: number;
  /** Base wage per season, €. */
  wage: number;
  /** What my club would pay per season (division, «Бухгалтерия»). */
  wage_now: number;
  loan_fee: number;
  sell_back: number;
  taken_by: string | null;
  mine: boolean;
}

export interface ManagerClubCard {
  id: number;
  name: string;
  owner_name: string;
  division: number;
  division_name: string;
  titles: number;
  seasons_played: number;
  look: ManagerLook;
  stadium_name: string | null;
  pro: boolean;
  rating: number;
  fans: number;
  is_mine: boolean;
  xi: Pick<ManagerSquadPlayer, "slot" | "kind" | "name" | "position" | "rating">[];
  merch: (ManagerMerchItem & { bought: boolean })[];
}

export async function fetchManager(): Promise<ManagerView> {
  const { data } = await api.get<ManagerView>("/manager");
  return data;
}

export async function fetchManagerMarket(): Promise<{ players: ManagerMarketPlayer[] }> {
  const { data } = await api.get<{ players: ManagerMarketPlayer[] }>("/manager/market");
  return data;
}

export type ManagerMoveKind =
  | "sign" | "transfer" | "loan" | "buy" | "auto" | "loan_back"
  | "sold" | "loaned_out" | "release" | "expired" | "unpaid";

export interface ManagerMove {
  id: number;
  season_key: string;
  direction: "in" | "out";
  kind: ManagerMoveKind;
  who: string;
  position: string | null;
  rating: number | null;
  fee: number;
  other_club: string | null;
  at: string;
}

export interface ManagerMoves {
  /** The season of the open window (or the running one). */
  season_key: string;
  spent: number;
  earned: number;
  came: number;
  left: number;
  moves: ManagerMove[];
}

export async function fetchManagerMoves(): Promise<ManagerMoves> {
  const { data } = await api.get<ManagerMoves>("/manager/moves");
  return data;
}

export async function fetchManagerScout(): Promise<{ players: ManagerMarketPlayer[] }> {
  const { data } = await api.get<{ players: ManagerMarketPlayer[] }>("/manager/scout");
  return data;
}

export interface ManagerCatalogFilter {
  line: ManagerLine | null;
  q: string;
  /** Only those my budget pays for (the fee + a season's wage). */
  afford: "loan" | "buy" | null;
  sort: "rating" | "cheap";
  freeOnly: boolean;
}

export interface ManagerCatalogPage {
  players: ManagerCatalogPlayer[];
  /** With `afford`: the highest rating the budget pays for (0 = nobody). */
  max_rating: number | null;
  more: boolean;
}

export async function fetchManagerCatalog(filter: ManagerCatalogFilter, offset = 0): Promise<ManagerCatalogPage> {
  const { line, q, afford, sort, freeOnly } = filter;
  const { data } = await api.get<ManagerCatalogPage>("/manager/npc", {
    params: {
      ...(line ? { line } : {}), ...(q.trim() ? { q: q.trim() } : {}), ...(afford ? { afford } : {}),
      sort, ...(freeOnly ? { free_only: true } : {}), offset,
    },
  });
  return data;
}

export async function fetchManagerClubCard(clubId: number): Promise<ManagerClubCard> {
  const { data } = await api.get<ManagerClubCard>(`/manager/clubs/${clubId}`);
  return data;
}

export async function fetchManagerPopular(): Promise<{ clubs: { id: number; name: string; division: number; fans: number; look: ManagerLook }[] }> {
  const { data } = await api.get("/manager/popular");
  return data;
}

export async function foundManagerClub(name: string): Promise<ManagerView> {
  const { data } = await api.post<ManagerView>("/manager/club", { name });
  return data;
}

export async function updateManagerClub(patch: {
  name?: string; formation?: string; style?: ManagerStyle; academy_card_id?: number; clear_academy?: boolean;
}): Promise<ManagerView> {
  const { data } = await api.patch<ManagerView>("/manager/club", patch);
  return data;
}

export async function offerManagerContract(offer: {
  user_id: number; wage: number; seasons: number; fee?: number; kind?: "sign" | "transfer" | "loan";
}): Promise<ManagerView> {
  const { data } = await api.post<ManagerView>("/manager/offers", offer);
  return data;
}

export async function cancelManagerOffer(contractId: number): Promise<ManagerView> {
  const { data } = await api.post<ManagerView>(`/manager/offers/${contractId}/cancel`);
  return data;
}

export async function respondManagerOffer(contractId: number, accept: boolean): Promise<ManagerView> {
  const { data } = await api.post<ManagerView>(`/manager/offers/${contractId}/respond`, { accept });
  return data;
}

export async function endManagerContract(contractId: number): Promise<ManagerView> {
  const { data } = await api.post<ManagerView>(`/manager/contracts/${contractId}/end`);
  return data;
}

export async function setManagerMarket(open: boolean): Promise<ManagerView> {
  const { data } = await api.post<ManagerView>("/manager/market", { open });
  return data;
}

export async function signManagerNpc(playerId: number, kind: "buy" | "loan", seasons = 1): Promise<ManagerView> {
  const { data } = await api.post<ManagerView>("/manager/npc", { player_id: playerId, kind, seasons });
  return data;
}

export async function releaseManagerNpc(npcId: number): Promise<ManagerView> {
  const { data } = await api.post<ManagerView>(`/manager/npc/${npcId}/release`);
  return data;
}

export async function buyManagerCosmetic(code: string): Promise<ManagerView> {
  const { data } = await api.post<ManagerView>(`/manager/shop/${code}`);
  return data;
}

export async function setManagerLook(look: Partial<ManagerLook>): Promise<ManagerView> {
  const { data } = await api.patch<ManagerView>("/manager/look", look);
  return data;
}

export async function setManagerStadiumName(name: string): Promise<ManagerView> {
  const { data } = await api.post<ManagerView>("/manager/stadium-name", { name });
  return data;
}

export async function buyManagerMerch(clubId: number, code: string): Promise<ManagerClubCard> {
  const { data } = await api.post<ManagerClubCard>(`/manager/clubs/${clubId}/merch/${code}`);
  return data;
}

// --- «Кабинет президента» (manager_finance) -----------------------------------------------------

export type ManagerDealKind = "sponsor" | "naming" | "tour" | "tv" | "deposit" | "venture" | "farm";

export interface ManagerReportLine {
  kind: string;
  label: string;
  group: "income" | "expense" | "finance";
  amount: number;
}

/** One season of the club's money (key = ISO week, "2026-W45"). */
export interface ManagerReportSeason {
  key: string;
  income: number;
  /** Negative. */
  expense: number;
  /** Loans, deposits, the venture fund — money in and out, not profit. */
  finance: number;
  profit: number;
  lines: ManagerReportLine[];
}

export interface ManagerSponsorOffer {
  code: string;
  name: string;
  emoji: string;
  brand: string;
  upfront: number;
  per_win: number;
  /** By place, index 0 = champion. */
  places: number[];
  rest: number;
  relegated: number;
}

export interface ManagerTourOption {
  code: string;
  name: string;
  emoji: string;
  revenue: number;
  cost: number;
  fans: number;
  fatigue_pct: number;
  fatigue_rounds: number;
}

export interface ManagerDeal {
  id: number;
  kind: ManagerDealKind;
  season_key: string;
  seasons: number;
  option: string | null;
  amount: number;
  result: number;
  status: "active" | "done" | "lost";
  data: Record<string, unknown>;
}

export interface ManagerOffice {
  enabled: boolean;
  club_id: number;
  name: string;
  division: number;
  budget: number;
  grant: number;
  /** Deals are signed while the club does not play (for `season_key`). */
  window_open: boolean;
  season_key: string;
  current_key: string;
  value: { total: number; parts: Record<"squad" | "budget" | "invested" | "base" | "fans" | "titles" | "debt", number> };
  fans: number;
  levels: Record<"stadium" | "hotel" | "media" | "marketing" | "accounting" | "training" | "shop", number>;
  report: ManagerReportSeason[];
  sponsors: { taken: boolean; offers: ManagerSponsorOffer[]; marketing_pct: number };
  loan: {
    open: { id: number; principal: number; debt: number; rate_pct: number; seasons_total: number; seasons_left: number; status: "active" | "overdue" } | null;
    limit: number;
    min: number;
    rate_pct: number;
    base_rate_pct: number;
    seasons_max: number;
    penalty_pct: number;
  };
  offers: {
    naming: { taken: boolean; stadium: number; brands: string[]; prices: number[] };
    tour: { taken: boolean; options: ManagerTourOption[]; hotel_cut_pct: number; media_fans_pct: number };
    tv: { taken: boolean; estimate: number; discount_pct: number; advance: number };
    deposit: { taken: boolean; rate_pct: number; min: number; max: number; blocked: boolean };
    venture: { taken: boolean; win_pct: number; multiplier: number; min: number; max: number; max_pct: number };
    farm: { taken: boolean; fee: number; loan_cut_pct: number; kid_bonus: number };
  };
  deals: ManagerDeal[];
}

export async function fetchManagerOffice(): Promise<ManagerOffice> {
  const { data } = await api.get<ManagerOffice>("/manager/office");
  return data;
}

export async function signManagerDeal(kind: ManagerDealKind, body: { option?: string; seasons?: number; amount?: number } = {}): Promise<ManagerOffice> {
  const { data } = await api.post<ManagerOffice>(`/manager/office/deals/${kind}`, body);
  return data;
}

export async function takeManagerLoan(amount: number, seasons: number): Promise<ManagerOffice> {
  const { data } = await api.post<ManagerOffice>("/manager/office/loan", { amount, seasons });
  return data;
}

export async function repayManagerLoan(amount?: number): Promise<ManagerOffice> {
  const { data } = await api.post<ManagerOffice>("/manager/office/loan/repay", amount == null ? {} : { amount });
  return data;
}
