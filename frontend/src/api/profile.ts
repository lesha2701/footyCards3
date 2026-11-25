import { api } from "@/lib/api";
import type {
  CoinTransaction,
  GiftShelfItem,
  OwnedBadge,
  Page,
  ProfilePrivate,
  ProfilePublic,
  ProfileSettingsUpdate,
  UserPublic,
  UserCard,
  UserTrophy,
} from "@/types";

export async function fetchMyProfile(): Promise<ProfilePrivate> {
  const { data } = await api.get<ProfilePrivate>("/profile/me");
  return data;
}

export async function updateMySettings(payload: ProfileSettingsUpdate): Promise<ProfilePrivate> {
  const { data } = await api.patch<ProfilePrivate>("/profile/settings", payload);
  return data;
}

export async function fetchMyBadges(): Promise<OwnedBadge[]> {
  const { data } = await api.get<OwnedBadge[]>("/profile/badges");
  return data;
}

export async function fetchMyTrophies(): Promise<UserTrophy[]> {
  const { data } = await api.get<UserTrophy[]>("/profile/trophies");
  return data;
}

export async function fetchMyTransactions(page = 1): Promise<Page<CoinTransaction>> {
  const { data } = await api.get<Page<CoinTransaction>>("/profile/transactions", { params: { page } });
  return data;
}

export async function fetchPublicProfile(userId: number): Promise<ProfilePublic> {
  const { data } = await api.get<ProfilePublic>(`/users/${userId}`);
  return data;
}

export async function searchUsers(query: string): Promise<UserPublic[]> {
  const { data } = await api.get<UserPublic[]>("/users/search", { params: { q: query } });
  return data;
}

export interface Attention {
  incoming_trades: number;
  match_challenges: number;
  active_friend_matches: number;
  league_unseen_rewards: number;
  friend_requests: number;
  career_invites: number;
}

/** Badge counts for the bottom navigation (one cheap request). */
export async function fetchMyAttention(): Promise<Attention> {
  const { data } = await api.get<Attention>("/profile/me/attention");
  return data;
}

export interface ProfileFeedEvent {
  kind: "finish" | "trophy" | "collection";
  at: string;
  icon: string;
  text: string;
  image_path: string | null;
}

export interface ProfileSocial {
  respects: number;
  respected_today: boolean;
  can_respect: boolean;
  /** Only on your own profile: who gave a respect today. */
  today_givers: { id: number; first_name: string | null; avatar_url: string | null }[];
  feed: ProfileFeedEvent[];
}

export async function fetchProfileSocial(userId: number): Promise<ProfileSocial> {
  const { data } = await api.get<ProfileSocial>(`/users/${userId}/social`);
  return data;
}

export async function giveRespect(userId: number): Promise<ProfileSocial> {
  const { data } = await api.post<ProfileSocial>(`/users/${userId}/respect`);
  return data;
}

export interface HallCabinetItem {
  kind: "trophy" | "collection";
  code: string | null;
  name: string;
  description: string;
  icon: string;
  image_path: string | null;
  at: string;
}

/** A place of the hall the owner changed: the item standing there. */
export interface HallDecorItem {
  id: number;
  style_key: string;
  image_path: string | null;
}

/** Hall places: two skins (the niche, all pedestals) and four decor places. */
export type HallSlot = "cabinet" | "pedestal" | "corner" | "wall" | "front_left" | "front_right";
/** Missing place = the default look, null = emptied. */
export type HallDecor = Partial<Record<HallSlot, HallDecorItem | null>>;

export interface Hall {
  frames: UserCard[];
  cabinet: HallCabinetItem[];
  pedestals: GiftShelfItem[];
  decor: HallDecor;
  totals: { trophies: number; collections: number; gifts: number; rare_prints: number; respects: number };
}

/** «Зал славы» of a profile. */
export async function fetchHall(userId: number): Promise<Hall> {
  const { data } = await api.get<Hall>(`/users/${userId}/hall`);
  return data;
}

/** «Обустроить зал»: `cosmeticId` null = the default look, 0 = empty. */
export async function setHallDecor(slot: HallSlot, cosmeticId: number | null): Promise<HallDecor> {
  const { data } = await api.put<HallDecor>("/users/me/hall/decor", { slot, cosmetic_id: cosmeticId });
  return data;
}
