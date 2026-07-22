import { api } from "@/lib/api";
import type { Page, Pack, Player, TradeOffer, TradeStatus } from "@/types";
import type {
  AdminActionLog,
  AdminUser,
  Dashboard,
  GameConfig,
  PackPreview,
  SuspiciousMatch,
  SuspiciousMemorySession,
} from "@/admin/types";

export async function fetchDashboard(): Promise<Dashboard> {
  const { data } = await api.get<Dashboard>("/admin/dashboard");
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

export async function fetchAdminUserCollection(id: number, page = 1) {
  const { data } = await api.get(`/admin/users/${id}/collection`, { params: { page } });
  return data;
}

export async function fetchAdminUserTransactions(id: number, page = 1) {
  const { data } = await api.get(`/admin/users/${id}/transactions`, { params: { page } });
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

export async function togglePackActive(id: number): Promise<Pack> {
  const { data } = await api.post<Pack>(`/admin/packs/${id}/toggle-active`);
  return data;
}

export async function previewPack(id: number, simulations = 1000): Promise<PackPreview> {
  const { data } = await api.get<PackPreview>(`/admin/packs/${id}/preview`, { params: { simulations } });
  return data;
}

// --- Trades ---
export async function fetchAdminTrades(status?: TradeStatus): Promise<TradeOffer[]> {
  const { data } = await api.get<TradeOffer[]>("/admin/trades", { params: { status } });
  return data;
}

export async function forceCancelTrade(id: number): Promise<TradeOffer> {
  const { data } = await api.post<TradeOffer>(`/admin/trades/${id}/force-cancel`);
  return data;
}

// --- Games ---
export async function fetchGameConfig(): Promise<GameConfig> {
  const { data } = await api.get<GameConfig>("/admin/games/config");
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

// --- Log ---
export async function fetchAdminLog(page: number): Promise<Page<AdminActionLog>> {
  const { data } = await api.get<Page<AdminActionLog>>("/admin/log", { params: { page } });
  return data;
}
