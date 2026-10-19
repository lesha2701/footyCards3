import { api } from "@/lib/api";
import type {
  Announcement,
  Badge,
  BingoGoalDefinition,
  BingoState,
  BingoStatsPreviewItem,
  CardUpgradeRule,
  CoinTransaction,
  Coach,
  ClubPack,
  CoinPackage,
  ClubEmblemItem,
  Cosmetic,
  DiamondUpgradeTier,
  Gift,
  GiftSet,
  LeagueTier,
  MaintenanceStatus,
  Page,
  Pack,
  Player,
  SkillCatalog,
  SkillTokenBalance,
  Stadium,
  TournamentDetail,
  TradeOffer,
  TradeStatus,
  TrophyDefinition,
  UserCard,
  UserTrophy,
} from "@/types";
import type {
  AdminPathOverview,
  AdminClubBaseArt,
  AdminClubBaseLedgerEntry,
  AdminPathTask,
  AdminLifestyleItem,
  AdminActionLog,
  AdminClub,
  AdminClubBudgetTransaction,
  AdminClubBudgetTransactionType,
  AdminClubDetail,
  AdminClubMember,
  AdminClubTournament,
  AdminTournamentStats,
  AdminTournamentSummary,
  AdminUser,
  AdminWheelPoolsSummary,
  AdminWheelPrize,
  AdminWheelPrizePool,
  CardCollection,
  AdminArtifact,
  AdminArtifactCatalog,
  AdminSeason,
  CalendarTemplateDay,
  MagnateBoardConfig,
  Dashboard,
  GameConfig,
  AdminSkillLedgerEntry,
  PackPreview,
  StarsDonationSummary,
  AntifraudScan,
  StarsPackPurchase,
  StarsPaymentReceipt,
  StarsReceiptFilter,
  TopSupporter,
  SuspiciousMatch,
  SuspiciousMemorySession,
  TaskDefinition,
  RewardBundleInput,
} from "@/admin/types";

export async function fetchDashboard(): Promise<Dashboard> {
  const { data } = await api.get<Dashboard>("/admin/dashboard");
  return data;
}

// --- Economy analytics ---
export interface EconomyReport {
  days: number;
  coins_in_circulation: number;
  inflow_outflow_ratio: number | null;
  positive_days: number;
  /** Set when coins are minted noticeably faster than they're spent. */
  warning: string | null;
  total_inflow: number;
  total_outflow: number;
  net: number;
  by_type: { type: string; inflow: number; outflow: number; count: number }[];
  daily: { date: string; inflow: number; outflow: number }[];
  packs_opened: number;
  skill_tokens_granted: number;
  skill_tokens_spent: number;
  skill_coins_spent: number;
}

export async function fetchEconomyReport(days: number): Promise<EconomyReport> {
  const { data } = await api.get<EconomyReport>("/admin/dashboard/economy", { params: { days } });
  return data;
}

// --- Product analytics (backend: admin_analytics_service.py) ---
export type DayCount = { date: string; count: number };

export interface AnalyticsReport {
  days: number;
  today: string;
  activity: {
    dau_today: number;
    wau: number;
    mau: number;
    stickiness: number | null;
    active_in_period: number;
    total_users: number;
    dau_by_day: DayCount[];
    registrations_by_day: DayCount[];
  };
  retention: {
    cohorts: { date: string; size: number; d1: number | null; d7: number | null; d30: number | null }[];
    summary: {
      d1: number | null; d7: number | null; d30: number | null;
      d1_eligible: number; d7_eligible: number; d30_eligible: number;
    };
  };
  modes: { key: string; label: string; games: number; players: number }[];
  funnel: { cohort_size: number; steps: { key: string; label: string; users: number; share: number | null }[] };
  monetization: {
    stars_total: number;
    purchases: number;
    payers: number;
    paying_share: number | null;
    arppu: number | null;
    stars_by_day: DayCount[];
    by_product: { product: string; stars: number; purchases: number }[];
  };
  suspicious_trades: {
    young_days: number;
    min_donors: number;
    rows: SuspiciousTradeRow[];
  };
}

export interface SuspiciousTradeRow {
  user_id: number;
  telegram_id: number | null;
  name: string;
  username: string | null;
  young_donors: number;
  coins_received: number;
  cards_received: number;
  trades: number;
  last_trade_at: string | null;
}

export async function fetchAnalyticsReport(days: number): Promise<AnalyticsReport> {
  const { data } = await api.get<AnalyticsReport>("/admin/dashboard/analytics", { params: { days } });
  return data;
}

export interface PackExpectedValue {
  pack_id: number;
  price: number;
  card_count: number;
  expected_quick_sell_value: number;
  value_to_price: number | null;
  rarities: { rarity: string; probability: number; avg_quick_sell: number; pool_size: number }[];
}

export async function fetchPackExpectedValue(packId: number): Promise<PackExpectedValue> {
  const { data } = await api.get<PackExpectedValue>(`/admin/dashboard/packs/${packId}/expected-value`);
  return data;
}

// --- Maintenance banner ---
export async function startMaintenanceBanner(): Promise<MaintenanceStatus> {
  const { data } = await api.post<MaintenanceStatus>("/admin/maintenance/start");
  return data;
}

export async function clearMaintenanceBanner(): Promise<MaintenanceStatus> {
  const { data } = await api.post<MaintenanceStatus>("/admin/maintenance/clear");
  return data;
}

// --- Announcement banner ---
export async function fetchAnnouncementAdmin(): Promise<Announcement> {
  const { data } = await api.get<Announcement>("/announcement");
  return data;
}

export async function setAnnouncement(text: string): Promise<Announcement> {
  const { data } = await api.post<Announcement>("/admin/announcement", { text });
  return data;
}

// --- Users ---
export async function fetchAdminUsers(search: string, page: number): Promise<Page<AdminUser>> {
  const { data } = await api.get<Page<AdminUser>>("/admin/users", { params: { search: search || undefined, page } });
  return data;
}

export async function fetchAdminUser(id: number): Promise<AdminUser> {
  const { data } = await api.get<AdminUser>(`/admin/users/${id}`);
  return data;
}

export async function fetchAdminUserCollection(id: number, page = 1): Promise<Page<UserCard>> {
  const { data } = await api.get<Page<UserCard>>(`/admin/users/${id}/collection`, { params: { page } });
  return data;
}

export async function fetchAdminUserTransactions(id: number, page = 1): Promise<Page<CoinTransaction>> {
  const { data } = await api.get<Page<CoinTransaction>>(`/admin/users/${id}/transactions`, { params: { page } });
  return data;
}

export async function adjustUserBalance(id: number, amount: number, description: string): Promise<AdminUser> {
  const { data } = await api.post<AdminUser>(`/admin/users/${id}/balance`, { amount, description });
  return data;
}

export async function banUser(id: number): Promise<AdminUser> {
  const { data } = await api.post<AdminUser>(`/admin/users/${id}/ban`);
  return data;
}

export async function unbanUser(id: number): Promise<AdminUser> {
  const { data } = await api.post<AdminUser>(`/admin/users/${id}/unban`);
  return data;
}

export async function grantCard(userId: number, playerId: number) {
  const { data } = await api.post(`/admin/users/${userId}/cards/grant`, { player_id: playerId });
  return data;
}

export async function deleteUserCard(userId: number, cardId: number) {
  await api.delete(`/admin/users/${userId}/cards/${cardId}`);
}

export async function resetUserLimits(userId: number) {
  await api.post(`/admin/users/${userId}/reset-limits`);
}

export async function toggleRewardBlock(userId: number): Promise<AdminUser> {
  const { data } = await api.post<AdminUser>(`/admin/users/${userId}/toggle-reward-block`);
  return data;
}

export async function toggleTradeBan(userId: number): Promise<AdminUser> {
  const { data } = await api.post<AdminUser>(`/admin/users/${userId}/toggle-trade-ban`);
  return data;
}

// --- Players ---
export async function fetchAdminPlayers(search: string, page: number): Promise<Page<Player>> {
  const { data } = await api.get<Page<Player>>("/admin/players", { params: { search: search || undefined, page, include_inactive: true } });
  return data;
}

export async function createPlayer(payload: Record<string, unknown>): Promise<Player> {
  const { data } = await api.post<Player>("/admin/players", payload);
  return data;
}

export async function updatePlayer(id: number, payload: Record<string, unknown>): Promise<Player> {
  const { data } = await api.put<Player>(`/admin/players/${id}`, payload);
  return data;
}

export async function togglePlayerActive(id: number): Promise<Player> {
  const { data } = await api.post<Player>(`/admin/players/${id}/toggle-active`);
  return data;
}

export async function togglePlayerPackDroppable(id: number): Promise<Player> {
  const { data } = await api.post<Player>(`/admin/players/${id}/toggle-pack-droppable`);
  return data;
}

export async function deletePlayer(id: number) {
  await api.delete(`/admin/players/${id}`);
}

export async function uploadPlayerImage(id: number, file: File): Promise<Player> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<Player>(`/admin/players/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deletePlayerImage(id: number): Promise<Player> {
  const { data } = await api.delete<Player>(`/admin/players/${id}/image`);
  return data;
}

export async function exportPlayersCsv(): Promise<string> {
  const { data } = await api.get<string>("/admin/players/export-csv", { responseType: "text" });
  return data;
}

export async function importPlayersCsv(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post("/admin/players/import-csv", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data as { created: number; updated: number; errors: { row: number; error: string }[] };
}

// --- Coaches ---
export async function fetchAdminCoaches(search: string, page: number): Promise<Page<Coach>> {
  const { data } = await api.get<Page<Coach>>("/admin/coaches", { params: { search: search || undefined, page, include_inactive: true } });
  return data;
}

export async function createCoach(payload: Record<string, unknown>): Promise<Coach> {
  const { data } = await api.post<Coach>("/admin/coaches", payload);
  return data;
}

export async function updateCoach(id: number, payload: Record<string, unknown>): Promise<Coach> {
  const { data } = await api.put<Coach>(`/admin/coaches/${id}`, payload);
  return data;
}

export async function toggleCoachActive(id: number): Promise<Coach> {
  const { data } = await api.post<Coach>(`/admin/coaches/${id}/toggle-active`);
  return data;
}

export async function toggleCoachPackDroppable(id: number): Promise<Coach> {
  const { data } = await api.post<Coach>(`/admin/coaches/${id}/toggle-pack-droppable`);
  return data;
}

export async function deleteCoach(id: number) {
  await api.delete(`/admin/coaches/${id}`);
}

export async function uploadCoachImage(id: number, file: File): Promise<Coach> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<Coach>(`/admin/coaches/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteCoachImage(id: number): Promise<Coach> {
  const { data } = await api.delete<Coach>(`/admin/coaches/${id}/image`);
  return data;
}

// --- Stadiums ---
export async function fetchAdminStadiums(search: string, page: number): Promise<Page<Stadium>> {
  const { data } = await api.get<Page<Stadium>>("/admin/stadiums", { params: { search: search || undefined, page, include_inactive: true } });
  return data;
}

export async function createStadium(payload: Record<string, unknown>): Promise<Stadium> {
  const { data } = await api.post<Stadium>("/admin/stadiums", payload);
  return data;
}

export async function updateStadium(id: number, payload: Record<string, unknown>): Promise<Stadium> {
  const { data } = await api.put<Stadium>(`/admin/stadiums/${id}`, payload);
  return data;
}

export async function toggleStadiumActive(id: number): Promise<Stadium> {
  const { data } = await api.post<Stadium>(`/admin/stadiums/${id}/toggle-active`);
  return data;
}

export async function toggleStadiumPackDroppable(id: number): Promise<Stadium> {
  const { data } = await api.post<Stadium>(`/admin/stadiums/${id}/toggle-pack-droppable`);
  return data;
}

export async function deleteStadium(id: number) {
  await api.delete(`/admin/stadiums/${id}`);
}

export async function uploadStadiumImage(id: number, file: File): Promise<Stadium> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<Stadium>(`/admin/stadiums/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteStadiumImage(id: number): Promise<Stadium> {
  const { data } = await api.delete<Stadium>(`/admin/stadiums/${id}/image`);
  return data;
}

// --- Packs ---
export async function fetchAdminPacks(): Promise<Pack[]> {
  const { data } = await api.get<Pack[]>("/admin/packs");
  return data;
}

export async function createPack(payload: Record<string, unknown>): Promise<Pack> {
  const { data } = await api.post<Pack>("/admin/packs", payload);
  return data;
}

export async function updatePack(id: number, payload: Record<string, unknown>): Promise<Pack> {
  const { data } = await api.put<Pack>(`/admin/packs/${id}`, payload);
  return data;
}

export async function uploadPackImage(id: number, file: File): Promise<Pack> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<Pack>(`/admin/packs/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function togglePackActive(id: number): Promise<Pack> {
  const { data } = await api.post<Pack>(`/admin/packs/${id}/toggle-active`);
  return data;
}

export async function previewPack(id: number, simulations = 1000): Promise<PackPreview> {
  const { data } = await api.get<PackPreview>(`/admin/packs/${id}/preview`, { params: { simulations } });
  return data;
}

export async function deletePack(id: number): Promise<void> {
  await api.delete(`/admin/packs/${id}`);
}

// --- Club Packs ---
export async function fetchAdminClubPacks(): Promise<ClubPack[]> {
  const { data } = await api.get<ClubPack[]>("/admin/club-packs");
  return data;
}

export async function createClubPack(payload: Record<string, unknown>): Promise<ClubPack> {
  const { data } = await api.post<ClubPack>("/admin/club-packs", payload);
  return data;
}

export async function updateClubPack(id: number, payload: Record<string, unknown>): Promise<ClubPack> {
  const { data } = await api.put<ClubPack>(`/admin/club-packs/${id}`, payload);
  return data;
}

export async function uploadClubPackImage(id: number, file: File): Promise<ClubPack> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<ClubPack>(`/admin/club-packs/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function toggleClubPackActive(id: number): Promise<ClubPack> {
  const { data } = await api.post<ClubPack>(`/admin/club-packs/${id}/toggle-active`);
  return data;
}

export async function deleteClubPack(id: number): Promise<void> {
  await api.delete(`/admin/club-packs/${id}`);
}


// --- Card Collections ---
export async function fetchAdminCardCollections(): Promise<CardCollection[]> {
  const { data } = await api.get<CardCollection[]>("/admin/card-collections");
  return data;
}

export async function createCardCollection(payload: Record<string, unknown>): Promise<CardCollection> {
  const { data } = await api.post<CardCollection>("/admin/card-collections", payload);
  return data;
}

export async function updateCardCollection(id: number, payload: Record<string, unknown>): Promise<CardCollection> {
  const { data } = await api.put<CardCollection>(`/admin/card-collections/${id}`, payload);
  return data;
}

export async function toggleCardCollectionActive(id: number): Promise<CardCollection> {
  const { data } = await api.post<CardCollection>(`/admin/card-collections/${id}/toggle-active`);
  return data;
}

export async function uploadCardCollectionImage(id: number, file: File): Promise<CardCollection> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<CardCollection>(`/admin/card-collections/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function fetchCardCollectionPlayers(id: number): Promise<Player[]> {
  const { data } = await api.get<Player[]>(`/admin/card-collections/${id}/players`);
  return data;
}

export async function setCardCollectionPlayers(id: number, playerIds: number[]): Promise<Player[]> {
  const { data } = await api.put<Player[]>(`/admin/card-collections/${id}/players`, { player_ids: playerIds });
  return data;
}

// --- Tasks ---
export async function fetchAdminTasks(): Promise<TaskDefinition[]> {
  const { data } = await api.get<TaskDefinition[]>("/admin/tasks");
  return data;
}

export async function createTask(payload: Record<string, unknown>): Promise<TaskDefinition> {
  const { data } = await api.post<TaskDefinition>("/admin/tasks", payload);
  return data;
}

export async function updateTask(id: number, payload: Record<string, unknown>): Promise<TaskDefinition> {
  const { data } = await api.put<TaskDefinition>(`/admin/tasks/${id}`, payload);
  return data;
}

export async function toggleTaskActive(id: number): Promise<TaskDefinition> {
  const { data } = await api.post<TaskDefinition>(`/admin/tasks/${id}/toggle-active`);
  return data;
}

export async function deleteTask(id: number): Promise<void> {
  await api.delete(`/admin/tasks/${id}`);
}

export async function sendPremiumTaskBroadcast(taskCount: number, message: string): Promise<{ recipients: number }> {
  const { data } = await api.post<{ recipients: number }>("/admin/tasks/broadcast-premium", {
    task_count: taskCount,
    message: message.trim() || undefined,
  });
  return data;
}

export async function backfillPremiumTaskCoins(): Promise<{ definitions_updated: number; users_credited: number }> {
  const { data } = await api.post<{ definitions_updated: number; users_credited: number }>(
    "/admin/tasks/backfill-premium-coins",
  );
  return data;
}

// --- Wheel of Fortune ---
export async function fetchAdminWheelPrizes(pool?: AdminWheelPrizePool): Promise<AdminWheelPrize[]> {
  const { data } = await api.get<AdminWheelPrize[]>("/admin/wheel/prizes", { params: pool ? { pool } : undefined });
  return data;
}
export async function createWheelPrize(payload: Record<string, unknown>): Promise<AdminWheelPrize> {
  const { data } = await api.post<AdminWheelPrize>("/admin/wheel/prizes", payload);
  return data;
}
export async function updateWheelPrize(id: number, payload: Record<string, unknown>): Promise<AdminWheelPrize> {
  const { data } = await api.put<AdminWheelPrize>(`/admin/wheel/prizes/${id}`, payload);
  return data;
}
export async function deleteWheelPrize(id: number): Promise<void> {
  await api.delete(`/admin/wheel/prizes/${id}`);
}
export async function fetchAdminWheelPoolsSummary(): Promise<AdminWheelPoolsSummary> {
  const { data } = await api.get<AdminWheelPoolsSummary>("/admin/wheel/pools-summary");
  return data;
}
export async function toggleWheelPrizeActive(id: number): Promise<AdminWheelPrize> {
  const { data } = await api.post<AdminWheelPrize>(`/admin/wheel/prizes/${id}/toggle-active`);
  return data;
}

// --- «Календарь наград» template ---
export async function fetchCalendarTemplate(): Promise<CalendarTemplateDay[]> {
  const { data } = await api.get<CalendarTemplateDay[]>("/admin/login-calendar");
  return data;
}
export async function updateCalendarTemplate(days: CalendarTemplateDay[]): Promise<CalendarTemplateDay[]> {
  const { data } = await api.put<CalendarTemplateDay[]>("/admin/login-calendar", { days });
  return data;
}

// --- Club emblem constructor catalog ---
export async function fetchAdminClubEmblemItems(): Promise<ClubEmblemItem[]> {
  const { data } = await api.get<ClubEmblemItem[]>("/admin/club-emblem-items");
  return data;
}
export async function saveAdminClubEmblemItem(item: ClubEmblemItem): Promise<ClubEmblemItem> {
  const { id, name, coins_price, stars_price, is_active, sort_order } = item;
  const { data } = await api.put<ClubEmblemItem>(`/admin/club-emblem-items/${id}`, {
    name, coins_price, stars_price, is_active, sort_order,
  });
  return data;
}

// --- «Клубный магазин» ---
export interface AdminClubShopItem {
  id?: number;
  name: string;
  description: string;
  price: number;
  weekly_limit: number;
  reward: RewardBundleInput;
  is_active: boolean;
  sort_order: number;
}
export async function fetchAdminClubShopItems(): Promise<AdminClubShopItem[]> {
  const { data } = await api.get<AdminClubShopItem[]>("/admin/club-shop-items");
  return data;
}
export async function saveAdminClubShopItem(item: AdminClubShopItem): Promise<AdminClubShopItem> {
  const { id, ...body } = item;
  const { data } = id
    ? await api.put<AdminClubShopItem>(`/admin/club-shop-items/${id}`, body)
    : await api.post<AdminClubShopItem>("/admin/club-shop-items", body);
  return data;
}

// --- «Задания недели» клуба ---
export interface AdminClubQuest {
  id?: number;
  title: string;
  metric: "games" | "packs" | "tasks";
  target_per_member: number;
  reward_budget: number;
  reward: RewardBundleInput;
  is_active: boolean;
  sort_order: number;
}
export async function fetchAdminClubQuests(): Promise<AdminClubQuest[]> {
  const { data } = await api.get<AdminClubQuest[]>("/admin/club-quests");
  return data;
}
export async function saveAdminClubQuest(item: AdminClubQuest): Promise<AdminClubQuest> {
  const { id, ...body } = item;
  const { data } = id
    ? await api.put<AdminClubQuest>(`/admin/club-quests/${id}`, body)
    : await api.post<AdminClubQuest>("/admin/club-quests", body);
  return data;
}

// --- Cosmetics & seasons ---
export async function fetchAdminCosmetics(): Promise<Cosmetic[]> {
  const { data } = await api.get<Cosmetic[]>("/admin/cosmetics");
  return data;
}
export async function saveAdminCosmetic(item: Omit<Cosmetic, "id"> & { id?: number }): Promise<Cosmetic> {
  const { id, ...body } = item;
  const { data } = id
    ? await api.put<Cosmetic>(`/admin/cosmetics/${id}`, body)
    : await api.post<Cosmetic>("/admin/cosmetics", body);
  return data;
}
export async function fetchAdminSeasons(): Promise<AdminSeason[]> {
  const { data } = await api.get<AdminSeason[]>("/admin/seasons");
  return data;
}
export async function saveAdminSeason(season: AdminSeason): Promise<AdminSeason> {
  const { id, players: _players, premium_players: _premium, ...body } = season;
  const { data } = id
    ? await api.put<AdminSeason>(`/admin/seasons/${id}`, body)
    : await api.post<AdminSeason>("/admin/seasons", body);
  return data;
}

// --- Trades ---
export interface AdminTradesQuery {
  status?: TradeStatus;
  username?: string;
  /** Inclusive local days, YYYY-MM-DD. */
  date_from?: string;
  date_to?: string;
  /** Coins in the offer, both sides summed. */
  coins_min?: number;
  coins_max?: number;
  /** Only offers without cards (pure coin transfers). */
  coins_only?: boolean;
  page: number;
  page_size?: number;
}

export async function fetchAdminTrades(q: AdminTradesQuery): Promise<Page<TradeOffer>> {
  const { data } = await api.get<Page<TradeOffer>>("/admin/trades", {
    params: {
      status: q.status, username: q.username || undefined, date_from: q.date_from || undefined,
      date_to: q.date_to || undefined, coins_min: q.coins_min, coins_max: q.coins_max,
      coins_only: q.coins_only || undefined, page: q.page, page_size: q.page_size ?? 50,
    },
  });
  return data;
}

export async function forceCancelTrade(id: number): Promise<TradeOffer> {
  const { data } = await api.post<TradeOffer>(`/admin/trades/${id}/force-cancel`);
  return data;
}

// --- Games ---
export interface CareerClubAdmin {
  id?: number;
  name: string;
  division: number;
  source?: string;
  pool_club?: string | null;
  pool_players?: number;
  rating_offset: number;
  formation?: string | null;
  preset?: string | null;
  is_active: boolean;
}

export async function fetchCareerClubs(): Promise<{ clubs: CareerClubAdmin[] }> {
  const { data } = await api.get<{ clubs: CareerClubAdmin[] }>("/admin/career/clubs");
  return data;
}

export async function buildCareerClubs(replace: boolean): Promise<{ clubs: CareerClubAdmin[] }> {
  const { data } = await api.post<{ clubs: CareerClubAdmin[] }>("/admin/career/clubs/build", { replace });
  return data;
}

export async function createCareerClub(club: CareerClubAdmin): Promise<{ clubs: CareerClubAdmin[] }> {
  const { data } = await api.post<{ clubs: CareerClubAdmin[] }>("/admin/career/clubs", club);
  return data;
}

export async function updateCareerClub(club: CareerClubAdmin): Promise<{ clubs: CareerClubAdmin[] }> {
  const { id, name, division, pool_club, rating_offset, formation, preset, is_active } = club;
  const { data } = await api.put<{ clubs: CareerClubAdmin[] }>(`/admin/career/clubs/${id}`,
    { name, division, pool_club, rating_offset, formation, preset, is_active });
  return data;
}

export async function fetchGameConfig(): Promise<GameConfig> {
  const { data } = await api.get<GameConfig>("/admin/games/config");
  return data;
}

export async function fetchMagnateDefaults(): Promise<{ board: MagnateBoardConfig; cards: Record<string, unknown> }> {
  const { data } = await api.get<{ board: MagnateBoardConfig; cards: Record<string, unknown> }>("/admin/games/magnate-defaults");
  return data;
}

export async function updateGameConfig(payload: Partial<GameConfig>): Promise<GameConfig> {
  const { data } = await api.put<GameConfig>("/admin/games/config", payload);
  return data;
}

export async function fetchSuspiciousMemorySessions(): Promise<SuspiciousMemorySession[]> {
  const { data } = await api.get<SuspiciousMemorySession[]>("/admin/games/suspicious-memory-sessions");
  return data;
}

export async function fetchSuspiciousMatches(): Promise<SuspiciousMatch[]> {
  const { data } = await api.get<SuspiciousMatch[]>("/admin/games/suspicious-matches");
  return data;
}

// --- Card upgrades ---
export async function fetchUpgradeRules(): Promise<CardUpgradeRule[]> {
  const { data } = await api.get<CardUpgradeRule[]>("/admin/card-upgrades");
  return data;
}

export async function updateUpgradeRule(
  id: number,
  payload: Partial<Pick<CardUpgradeRule, "success_chance" | "coin_cost" | "is_active">>,
): Promise<CardUpgradeRule> {
  const { data } = await api.put<CardUpgradeRule>(`/admin/card-upgrades/${id}`, payload);
  return data;
}

// --- Diamond upgrade tiers ---
type DiamondUpgradeTierFields = Omit<DiamondUpgradeTier, "id">;

export async function fetchDiamondUpgradeTiers(): Promise<DiamondUpgradeTier[]> {
  const { data } = await api.get<DiamondUpgradeTier[]>("/admin/diamond-upgrade-tiers");
  return data;
}

export async function createDiamondUpgradeTier(payload: DiamondUpgradeTierFields): Promise<DiamondUpgradeTier> {
  const { data } = await api.post<DiamondUpgradeTier>("/admin/diamond-upgrade-tiers", payload);
  return data;
}

export async function updateDiamondUpgradeTier(
  id: number,
  payload: Partial<DiamondUpgradeTierFields>,
): Promise<DiamondUpgradeTier> {
  const { data } = await api.put<DiamondUpgradeTier>(`/admin/diamond-upgrade-tiers/${id}`, payload);
  return data;
}

export async function deleteDiamondUpgradeTier(id: number): Promise<void> {
  await api.delete(`/admin/diamond-upgrade-tiers/${id}`);
}

// --- Bingo of the Week ---
export async function fetchBingoState(): Promise<BingoState> {
  const { data } = await api.get<BingoState>("/admin/bingo/state");
  return data;
}

export async function updateBingoState(isEnabled: boolean): Promise<BingoState> {
  const { data } = await api.put<BingoState>("/admin/bingo/state", { is_enabled: isEnabled });
  return data;
}

export async function fetchBingoGoals(): Promise<BingoGoalDefinition[]> {
  const { data } = await api.get<BingoGoalDefinition[]>("/admin/bingo/goals");
  return data;
}

export async function createBingoGoal(
  payload: Pick<BingoGoalDefinition, "goal_type" | "target_value" | "is_active">,
): Promise<BingoGoalDefinition> {
  const { data } = await api.post<BingoGoalDefinition>("/admin/bingo/goals", payload);
  return data;
}

export async function updateBingoGoal(
  id: number, payload: Partial<Pick<BingoGoalDefinition, "target_value" | "is_active">>,
): Promise<BingoGoalDefinition> {
  const { data } = await api.put<BingoGoalDefinition>(`/admin/bingo/goals/${id}`, payload);
  return data;
}

export async function deleteBingoGoal(id: number): Promise<void> {
  await api.delete(`/admin/bingo/goals/${id}`);
}

export async function fetchBingoStatsPreview(): Promise<BingoStatsPreviewItem[]> {
  const { data } = await api.get<BingoStatsPreviewItem[]>("/admin/bingo/stats-preview");
  return data;
}

// --- Broadcasts ---
export async function sendUpdateBroadcast(message: string): Promise<{ recipients: number; broadcast_at: string }> {
  const { data } = await api.post<{ recipients: number; broadcast_at: string }>("/admin/broadcasts", { message });
  return data;
}

// --- Badges ---
export async function fetchAdminBadges(): Promise<Badge[]> {
  const { data } = await api.get<Badge[]>("/admin/badges");
  return data;
}

export async function createBadge(payload: Record<string, unknown>): Promise<Badge> {
  const { data } = await api.post<Badge>("/admin/badges", payload);
  return data;
}

export async function updateBadge(id: number, payload: Record<string, unknown>): Promise<Badge> {
  const { data } = await api.put<Badge>(`/admin/badges/${id}`, payload);
  return data;
}

export async function deleteBadge(id: number): Promise<void> {
  await api.delete(`/admin/badges/${id}`);
}

export async function uploadBadgeImage(id: number, file: File): Promise<Badge> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<Badge>(`/admin/badges/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteBadgeImage(id: number): Promise<Badge> {
  const { data } = await api.delete<Badge>(`/admin/badges/${id}/image`);
  return data;
}

// --- Trophies ---
export async function fetchAdminTrophies(): Promise<TrophyDefinition[]> {
  const { data } = await api.get<TrophyDefinition[]>("/admin/trophies");
  return data;
}

export async function createTrophy(payload: Record<string, unknown>): Promise<TrophyDefinition> {
  const { data } = await api.post<TrophyDefinition>("/admin/trophies", payload);
  return data;
}

export async function updateTrophy(id: number, payload: Record<string, unknown>): Promise<TrophyDefinition> {
  const { data } = await api.put<TrophyDefinition>(`/admin/trophies/${id}`, payload);
  return data;
}

export async function deleteTrophy(id: number): Promise<void> {
  await api.delete(`/admin/trophies/${id}`);
}

export async function uploadTrophyImage(id: number, file: File): Promise<TrophyDefinition> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<TrophyDefinition>(`/admin/trophies/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteTrophyImage(id: number): Promise<TrophyDefinition> {
  const { data } = await api.delete<TrophyDefinition>(`/admin/trophies/${id}/image`);
  return data;
}

export async function fetchUserTrophies(userId: number): Promise<UserTrophy[]> {
  const { data } = await api.get<UserTrophy[]>(`/admin/users/${userId}/trophies`);
  return data;
}

export async function grantTrophy(userId: number, trophyDefinitionId: number, message?: string): Promise<UserTrophy> {
  const { data } = await api.post<UserTrophy>(`/admin/users/${userId}/trophies/grant`, {
    trophy_definition_id: trophyDefinitionId,
    message: message || undefined,
  });
  return data;
}

// --- Gifts ---
export async function fetchAdminGiftSets(): Promise<GiftSet[]> {
  const { data } = await api.get<GiftSet[]>("/admin/gifts/sets");
  return data;
}

export async function createGiftSet(payload: Record<string, unknown>): Promise<GiftSet> {
  const { data } = await api.post<GiftSet>("/admin/gifts/sets", payload);
  return data;
}

export async function updateGiftSet(id: number, payload: Record<string, unknown>): Promise<GiftSet> {
  const { data } = await api.put<GiftSet>(`/admin/gifts/sets/${id}`, payload);
  return data;
}

export async function deleteGiftSet(id: number): Promise<void> {
  await api.delete(`/admin/gifts/sets/${id}`);
}

export async function uploadGiftSetImage(id: number, file: File): Promise<GiftSet> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<GiftSet>(`/admin/gifts/sets/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteGiftSetImage(id: number): Promise<GiftSet> {
  const { data } = await api.delete<GiftSet>(`/admin/gifts/sets/${id}/image`);
  return data;
}

export async function adminSendGift(giftSetId: number, userId: number, message?: string): Promise<Gift> {
  const { data } = await api.post<Gift>("/admin/gifts/send", {
    gift_set_id: giftSetId, user_id: userId, message: message || undefined,
  });
  return data;
}

export async function adminBroadcastGift(giftSetId: number, message?: string): Promise<{ recipients: number }> {
  const { data } = await api.post<{ recipients: number }>("/admin/gifts/broadcast", {
    gift_set_id: giftSetId, message: message || undefined,
  });
  return data;
}

// --- Coin packages ---
export async function fetchAdminCoinPackages(): Promise<CoinPackage[]> {
  const { data } = await api.get<CoinPackage[]>("/admin/coin-packages");
  return data;
}

export async function createCoinPackage(payload: Record<string, unknown>): Promise<CoinPackage> {
  const { data } = await api.post<CoinPackage>("/admin/coin-packages", payload);
  return data;
}

export async function updateCoinPackage(id: number, payload: Record<string, unknown>): Promise<CoinPackage> {
  const { data } = await api.put<CoinPackage>(`/admin/coin-packages/${id}`, payload);
  return data;
}

export async function deleteCoinPackage(id: number): Promise<void> {
  await api.delete(`/admin/coin-packages/${id}`);
}

// --- Log ---
export async function fetchAdminLog(page: number): Promise<Page<AdminActionLog>> {
  const { data } = await api.get<Page<AdminActionLog>>("/admin/log", { params: { page } });
  return data;
}

export async function fetchStarsPackPurchases(page: number): Promise<Page<StarsPackPurchase>> {
  const { data } = await api.get<Page<StarsPackPurchase>>("/admin/stars-purchases", { params: { page } });
  return data;
}

export async function fetchStarsDonationSummary(): Promise<StarsDonationSummary> {
  const { data } = await api.get<StarsDonationSummary>("/admin/stars-purchases/summary");
  return data;
}

export async function fetchTopSupporters(): Promise<TopSupporter[]> {
  const { data } = await api.get<TopSupporter[]>("/admin/stars-purchases/top-supporters");
  return data;
}

export async function fetchStarsReceipts(status: StarsReceiptFilter, page: number): Promise<Page<StarsPaymentReceipt>> {
  const { data } = await api.get<Page<StarsPaymentReceipt>>("/admin/stars-purchases/receipts", { params: { status, page } });
  return data;
}

export async function fetchStarsReceiptProblemCount(): Promise<number> {
  const { data } = await api.get<{ count: number }>("/admin/stars-purchases/receipts/problem-count");
  return data.count;
}

export async function retryStarsReceipt(id: number): Promise<StarsPaymentReceipt> {
  const { data } = await api.post<StarsPaymentReceipt>(`/admin/stars-purchases/receipts/${id}/retry`);
  return data;
}

export async function refundStarsReceipt(id: number): Promise<StarsPaymentReceipt> {
  const { data } = await api.post<StarsPaymentReceipt>(`/admin/stars-purchases/receipts/${id}/refund`);
  return data;
}

// --- Leagues ---
export async function fetchAdminLeagues(): Promise<LeagueTier[]> {
  const { data } = await api.get<LeagueTier[]>("/admin/leagues");
  return data;
}

export async function createLeagueTier(payload: Record<string, unknown>): Promise<LeagueTier> {
  const { data } = await api.post<LeagueTier>("/admin/leagues", payload);
  return data;
}

export async function updateLeagueTier(id: number, payload: Record<string, unknown>): Promise<LeagueTier> {
  const { data } = await api.put<LeagueTier>(`/admin/leagues/${id}`, payload);
  return data;
}

export async function deleteLeagueTier(id: number): Promise<void> {
  await api.delete(`/admin/leagues/${id}`);
}

export async function uploadLeagueTierImage(id: number, file: File): Promise<LeagueTier> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<LeagueTier>(`/admin/leagues/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteLeagueTierImage(id: number): Promise<LeagueTier> {
  const { data } = await api.delete<LeagueTier>(`/admin/leagues/${id}/image`);
  return data;
}

export async function backfillLeagueRewards(): Promise<{ rewarded_count: number }> {
  const { data } = await api.post<{ rewarded_count: number }>("/admin/leagues/backfill-rewards");
  return data;
}

// --- Clubs ---
export async function fetchAdminClubs(search: string, page: number): Promise<Page<AdminClub>> {
  const { data } = await api.get<Page<AdminClub>>("/admin/clubs", { params: { search: search || undefined, page } });
  return data;
}

export async function fetchAdminClub(id: number): Promise<AdminClubDetail> {
  const { data } = await api.get<AdminClubDetail>(`/admin/clubs/${id}`);
  return data;
}

export async function adjustClubBudget(id: number, amount: number, description: string): Promise<AdminClubDetail> {
  const { data } = await api.post<AdminClubDetail>(`/admin/clubs/${id}/budget`, { amount, description });
  return data;
}

export async function fetchAdminClubMembers(id: number): Promise<AdminClubMember[]> {
  const { data } = await api.get<AdminClubMember[]>(`/admin/clubs/${id}/members`);
  return data;
}

export type AdminClubBudgetPage = Page<AdminClubBudgetTransaction> & { total_spent: number; total_income: number };

export async function fetchAdminClubBudgetTransactions(
  id: number,
  page = 1,
  filters: { direction?: "spend" | "income"; type?: AdminClubBudgetTransactionType } = {},
): Promise<AdminClubBudgetPage> {
  const { data } = await api.get<AdminClubBudgetPage>(`/admin/clubs/${id}/budget-transactions`, {
    params: { page, page_size: 20, ...filters },
  });
  return data;
}

export async function fetchAdminClubTournaments(id: number): Promise<AdminClubTournament[]> {
  const { data } = await api.get<AdminClubTournament[]>(`/admin/clubs/${id}/tournaments`);
  return data;
}

// --- Tournaments ---
export async function fetchAdminTournamentStats(): Promise<AdminTournamentStats> {
  const { data } = await api.get<AdminTournamentStats>("/admin/tournaments/stats");
  return data;
}

export async function fetchAdminTournaments(
  status: "active" | "completed" | undefined,
  page: number
): Promise<Page<AdminTournamentSummary>> {
  const { data } = await api.get<Page<AdminTournamentSummary>>("/admin/tournaments", { params: { status, page } });
  return data;
}

export async function fetchAdminTournamentDetail(id: number): Promise<TournamentDetail> {
  const { data } = await api.get<TournamentDetail>(`/admin/tournaments/${id}`);
  return data;
}

// --- Card skills (backend: routers/admin_card_skills.py; economy lives on GameConfig) ---

export async function fetchAdminSkillCatalog(): Promise<SkillCatalog> {
  const { data } = await api.get<SkillCatalog>("/admin/card-skills");
  return data;
}

export async function updateAdminSkill(
  code: string,
  payload: {
    is_enabled?: boolean;
    allowed_positions?: string[];
    reset_positions?: boolean;
    sort_order?: number;
    pack_drop_weight?: number;
    pack_drop_quantity?: number;
  },
): Promise<SkillCatalog> {
  const { data } = await api.patch<SkillCatalog>(`/admin/card-skills/${code}`, payload);
  return data;
}

export async function fetchAdminUserSkillTokens(userId: number): Promise<SkillTokenBalance[]> {
  const { data } = await api.get<{ tokens: SkillTokenBalance[] }>(`/admin/card-skills/tokens/${userId}`);
  return data.tokens;
}

export async function grantSkillTokens(payload: {
  user_id: number;
  skill_code: string;
  quantity: number;
  reason: string;
  idempotency_key: string;
}): Promise<SkillTokenBalance[]> {
  const { data } = await api.post<{ tokens: SkillTokenBalance[] }>("/admin/card-skills/tokens/grant", payload);
  return data.tokens;
}

export async function fetchSkillLedger(params: { user_id?: number; skill_code?: string; kind?: string; limit?: number }) {
  const { data } = await api.get<AdminSkillLedgerEntry[]>("/admin/card-skills/ledger", { params });
  return data;
}

export async function fetchAdminLifestyleItems(): Promise<AdminLifestyleItem[]> {
  const { data } = await api.get<AdminLifestyleItem[]>("/admin/lifestyle");
  return data;
}

export async function createLifestyleItem(payload: Omit<AdminLifestyleItem, "id" | "image_path" | "sold_count">): Promise<AdminLifestyleItem> {
  const { data } = await api.post<AdminLifestyleItem>("/admin/lifestyle", payload);
  return data;
}

export async function updateLifestyleItem(
  id: number, payload: Partial<Omit<AdminLifestyleItem, "id" | "image_path" | "sold_count">>,
): Promise<AdminLifestyleItem> {
  const { data } = await api.put<AdminLifestyleItem>(`/admin/lifestyle/${id}`, payload);
  return data;
}

export async function deleteLifestyleItem(id: number): Promise<void> {
  await api.delete(`/admin/lifestyle/${id}`);
}

export async function uploadLifestyleItemImage(id: number, file: File): Promise<AdminLifestyleItem> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<AdminLifestyleItem>(`/admin/lifestyle/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteLifestyleItemImage(id: number): Promise<AdminLifestyleItem> {
  const { data } = await api.delete<AdminLifestyleItem>(`/admin/lifestyle/${id}/image`);
  return data;
}


// --- «Академия» ---------------------------------------------------------

export async function fetchAdminPath(): Promise<AdminPathOverview> {
  const { data } = await api.get<AdminPathOverview>("/admin/path");
  return data;
}

export async function updateAdminPathTalent(
  code: string, payload: { is_enabled?: boolean; sort_order?: number; level_values?: Record<string, Record<string, number>> },
): Promise<AdminPathOverview> {
  const { data } = await api.put<AdminPathOverview>(`/admin/path/talents/${code}`, payload);
  return data;
}

export async function updateAdminPathStage(
  index: number, payload: { name?: string; max_rating?: number; talent_level?: number },
): Promise<AdminPathOverview> {
  const { data } = await api.put<AdminPathOverview>(`/admin/path/stages/${index}`, payload);
  return data;
}

export type AdminPathTaskIn = Omit<AdminPathTask, "id">;

export async function createAdminPathTask(payload: AdminPathTaskIn): Promise<AdminPathOverview> {
  const { data } = await api.post<AdminPathOverview>("/admin/path/tasks", payload);
  return data;
}

export async function updateAdminPathTask(id: number, payload: AdminPathTaskIn): Promise<AdminPathOverview> {
  const { data } = await api.put<AdminPathOverview>(`/admin/path/tasks/${id}`, payload);
  return data;
}

export async function deleteAdminPathTask(id: number): Promise<AdminPathOverview> {
  const { data } = await api.delete<AdminPathOverview>(`/admin/path/tasks/${id}`);
  return data;
}

// --- All users' coin transactions --------------------------------------------

export interface AdminTransactionFilters {
  search?: string;
  type?: string;
  direction?: "income" | "spend";
  date_from?: string;
  date_to?: string;
}

export interface AdminTransaction extends CoinTransaction {
  user_id: number;
  user_name: string;
  username: string | null;
  telegram_id: number | null;
}

export interface AdminTransactionsPage {
  items: AdminTransaction[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  income: number;
  spent: number;
}

export async function fetchAdminTransactions(
  params: AdminTransactionFilters & { user_id?: number; page: number; page_size: number },
): Promise<AdminTransactionsPage> {
  const { data } = await api.get<AdminTransactionsPage>("/admin/transactions", { params });
  return data;
}

// --- «Артефакты» ---
export async function fetchAdminArtifacts(): Promise<AdminArtifactCatalog> {
  const { data } = await api.get<AdminArtifactCatalog>("/admin/artifacts");
  return data;
}
export async function saveAdminArtifact(item: AdminArtifact): Promise<AdminArtifact> {
  const { id, sold_count: _sold, image_path: _image, ...body } = item;
  const { data } = id
    ? await api.put<AdminArtifact>(`/admin/artifacts/${id}`, body)
    : await api.post<AdminArtifact>("/admin/artifacts", body);
  return data;
}
export async function uploadArtifactImage(id: number, file: File): Promise<AdminArtifact> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<AdminArtifact>(`/admin/artifacts/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
export async function grantArtifact(id: number, userId: number): Promise<{ serial_number: number }> {
  const { data } = await api.post<{ serial_number: number }>(`/admin/artifacts/${id}/grant`, { user_id: userId });
  return data;
}
export async function giftArtifactToTopDonors(
  id: number, top: number, message: string | null,
): Promise<{ donors: number; granted: number; already_owned: number; sold_out: number }> {
  const { data } = await api.post(`/admin/artifacts/${id}/gift-top-donors`, { top, message });
  return data;
}

// --- Антифрод ---
export async function fetchAntifraudScan(params: { min_senders: number; days: number }): Promise<AntifraudScan> {
  const { data } = await api.get<AntifraudScan>("/admin/antifraud/scan", { params });
  return data;
}

export async function banAntifraudUsers(userIds: number[]): Promise<{ banned: number; user_ids: number[] }> {
  const { data } = await api.post<{ banned: number; user_ids: number[] }>("/admin/antifraud/ban", { user_ids: userIds });
  return data;
}

// --- «Клубная база» ---

export async function fetchClubBaseArt(): Promise<AdminClubBaseArt> {
  const { data } = await api.get<AdminClubBaseArt>("/admin/club-base/art");
  return data;
}

export async function uploadClubBaseArt(slot: string, file: File): Promise<AdminClubBaseArt> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<AdminClubBaseArt>(`/admin/club-base/art/${slot}`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteClubBaseArt(slot: string): Promise<AdminClubBaseArt> {
  const { data } = await api.delete<AdminClubBaseArt>(`/admin/club-base/art/${slot}`);
  return data;
}

export async function fetchClubBaseLedger(userId?: number): Promise<AdminClubBaseLedgerEntry[]> {
  const { data } = await api.get<AdminClubBaseLedgerEntry[]>("/admin/club-base/ledger", {
    params: { limit: 200, ...(userId ? { user_id: userId } : {}) },
  });
  return data;
}

// --- «Экипировка» ---
const ITEM_FIELDS = [
  "name", "description", "icon", "slot", "rarity", "collection_id", "effect", "effect_value", "cond_club",
  "cond_country", "coins_price", "stars_price", "is_active", "sort_order",
] as const;
const COLLECTION_FIELDS = ["name", "description", "set_size", "set_bonus_rating", "is_active", "sort_order"] as const;
const pick = <T extends object>(obj: T, keys: readonly string[]) =>
  Object.fromEntries(keys.map((k) => [k, (obj as Record<string, unknown>)[k]]));

export async function fetchAdminEquipment(): Promise<import("@/admin/types").AdminEquipmentCatalog> {
  const { data } = await api.get("/admin/equipment");
  return data;
}
export async function saveAdminEquipmentItem(
  item: import("@/admin/types").AdminEquipmentItem,
): Promise<import("@/admin/types").AdminEquipmentItem> {
  const body = pick(item, ITEM_FIELDS);
  const { data } = item.id ? await api.put(`/admin/equipment/items/${item.id}`, body) : await api.post("/admin/equipment/items", body);
  return data;
}
export async function saveAdminEquipmentCollection(
  collection: import("@/admin/types").AdminEquipmentCollection,
): Promise<import("@/admin/types").AdminEquipmentCollection> {
  const body = pick(collection, COLLECTION_FIELDS);
  const { data } = collection.id
    ? await api.put(`/admin/equipment/collections/${collection.id}`, body)
    : await api.post("/admin/equipment/collections", body);
  return data;
}
export async function uploadAdminEquipmentImage(kind: "items" | "collections", id: number, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post(`/admin/equipment/${kind}/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
export async function grantAdminEquipment(itemId: number, userId: number): Promise<{ copy_id: number }> {
  const { data } = await api.post(`/admin/equipment/items/${itemId}/grant`, { user_id: userId });
  return data;
}
