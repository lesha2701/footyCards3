import { api } from "@/lib/api";
import type {
  ClubPackOpenResult,
  ClubEmblem,
  ClubEmblemState,
  ClubLogoShape,
  ClubQuests,
  ClubShop,
  ClubSurplus,
  ClubTreasury,
  ClubTrophies,
  ClubWall,
  ClubWar,
  GrantedRewards,
  StarsInvoiceCreate,
} from "@/types";

export async function fetchClubEmblem(): Promise<ClubEmblemState> {
  const { data } = await api.get<ClubEmblemState>("/clubs/me/emblem");
  return data;
}

export async function saveClubEmblem(
  payload: { logo_shape: ClubLogoShape; logo_color: string } & Omit<ClubEmblem, never>,
): Promise<ClubEmblemState> {
  const { data } = await api.put<ClubEmblemState>("/clubs/me/emblem", payload);
  return data;
}

export async function buyClubEmblemItem(itemId: number): Promise<ClubEmblemState> {
  const { data } = await api.post<ClubEmblemState>(`/clubs/me/emblem/items/${itemId}/buy`);
  return data;
}

export async function createClubEmblemInvoice(itemId: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/clubs/me/emblem/items/${itemId}/stars-invoice`);
  return data;
}

export async function fetchClubTreasury(): Promise<ClubTreasury> {
  const { data } = await api.get<ClubTreasury>("/clubs/me/treasury");
  return data;
}

export async function createClubDonationInvoice(stars: number, target: "stars" | "coins"): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/clubs/me/treasury/stars-invoice", { stars, target });
  return data;
}

export async function buyClubEmblemItemWithClubStars(itemId: number): Promise<ClubEmblemState> {
  const { data } = await api.post<ClubEmblemState>(`/clubs/me/emblem/items/${itemId}/buy-club-stars`);
  return data;
}

export async function fetchClubSurplus(): Promise<ClubSurplus> {
  const { data } = await api.get<ClubSurplus>("/clubs/me/surplus");
  return data;
}

export async function sellClubCards(cardIds: number[]): Promise<{ sold: number; coins: number; budget: number }> {
  const { data } = await api.post<{ sold: number; coins: number; budget: number }>("/clubs/me/surplus/sell", { card_ids: cardIds });
  return data;
}

export async function exchangeClubCards(cardIds: number[]): Promise<ClubPackOpenResult> {
  const { data } = await api.post<ClubPackOpenResult>("/clubs/me/surplus/exchange", { card_ids: cardIds });
  return data;
}

export async function fetchClubWall(): Promise<ClubWall> {
  const { data } = await api.get<ClubWall>("/clubs/me/wall");
  return data;
}

export async function createClubPost(text: string, announce: boolean): Promise<ClubWall> {
  const { data } = await api.post<ClubWall>("/clubs/me/wall", { text, announce });
  return data;
}

export async function deleteClubPost(postId: number): Promise<ClubWall> {
  const { data } = await api.delete<ClubWall>(`/clubs/me/wall/${postId}`);
  return data;
}

export async function pinClubPost(postId: number): Promise<ClubWall> {
  const { data } = await api.post<ClubWall>(`/clubs/me/wall/${postId}/pin`);
  return data;
}

export async function fetchClubShop(): Promise<ClubShop> {
  const { data } = await api.get<ClubShop>("/clubs/me/shop");
  return data;
}

export async function buyClubShopItem(itemId: number): Promise<ClubShop> {
  const { data } = await api.post<ClubShop>(`/clubs/me/shop/${itemId}/buy`);
  return data;
}

export async function claimClubReward(grantId: number): Promise<GrantedRewards> {
  const { data } = await api.post<GrantedRewards>(`/clubs/me/rewards/${grantId}/claim`);
  return data;
}

export async function fetchClubQuests(): Promise<ClubQuests> {
  const { data } = await api.get<ClubQuests>("/clubs/me/quests");
  return data;
}

export async function fetchClubTrophies(clubId: number): Promise<ClubTrophies> {
  const { data } = await api.get<ClubTrophies>(`/clubs/${clubId}/trophies`);
  return data;
}

export async function fetchClubWar(): Promise<ClubWar> {
  const { data } = await api.get<ClubWar>("/clubs/me/war");
  return data;
}
