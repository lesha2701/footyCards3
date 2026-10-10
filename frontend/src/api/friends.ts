import { api } from "@/lib/api";
import type { UserPublic } from "@/types";

export interface FriendsList {
  friends: { user: UserPublic; since: string }[];
  incoming: { request_id: number; user: UserPublic; created_at: string }[];
  outgoing: { request_id: number; user: UserPublic; created_at: string }[];
}

export type FriendRelation = "none" | "friends" | "outgoing" | "incoming";

export interface FriendFeedItem {
  kind: "pull" | "trophy" | "career";
  user: UserPublic;
  text: string;
  at: string;
}

export async function fetchFriends(): Promise<FriendsList> {
  const { data } = await api.get<FriendsList>("/friends");
  return data;
}

export async function fetchFriendsFeed(): Promise<FriendFeedItem[]> {
  const { data } = await api.get<FriendFeedItem[]>("/friends/feed");
  return data;
}

export async function fetchFriendRelation(userId: number): Promise<FriendRelation> {
  const { data } = await api.get<{ relation: FriendRelation }>(`/friends/relation/${userId}`);
  return data.relation;
}

/** "pending", or "accepted" when they had already asked you. */
export async function sendFriendRequest(userId: number): Promise<"pending" | "accepted"> {
  const { data } = await api.post<{ status: "pending" | "accepted" }>("/friends/requests", { user_id: userId });
  return data.status;
}

export async function acceptFriendRequest(requestId: number): Promise<void> {
  await api.post(`/friends/requests/${requestId}/accept`);
}

export async function declineFriendRequest(requestId: number): Promise<void> {
  await api.post(`/friends/requests/${requestId}/decline`);
}

export async function removeFriend(userId: number): Promise<void> {
  await api.delete(`/friends/${userId}`);
}
