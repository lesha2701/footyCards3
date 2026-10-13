import { api } from "@/lib/api";
import type {
  MagnateAction,
  MagnateInfo,
  MagnateMatch,
  MagnateMatchBrief,
  MagnateRoomPreview,
} from "@/types";

export async function fetchMagnateInfo(): Promise<MagnateInfo> {
  const { data } = await api.get<MagnateInfo>("/magnate/info");
  return data;
}

export async function fetchMagnateMatches(): Promise<MagnateMatchBrief[]> {
  const { data } = await api.get<MagnateMatchBrief[]>("/magnate/matches");
  return data;
}

export async function fetchMagnateMatch(id: number): Promise<MagnateMatch> {
  const { data } = await api.get<MagnateMatch>(`/magnate/matches/${id}`);
  return data;
}

export async function createMagnateBotMatch(): Promise<MagnateMatch> {
  const { data } = await api.post<MagnateMatch>("/magnate/matches/bot");
  return data;
}

export async function joinMagnateLobby(): Promise<MagnateMatch> {
  const { data } = await api.post<MagnateMatch>("/magnate/lobby/join");
  return data;
}

export async function createMagnateRoom(): Promise<MagnateMatch> {
  const { data } = await api.post<MagnateMatch>("/magnate/rooms");
  return data;
}

export async function fetchMagnateRoom(code: string): Promise<MagnateRoomPreview> {
  const { data } = await api.get<MagnateRoomPreview>(`/magnate/rooms/${code}`);
  return data;
}

export async function joinMagnateRoom(code: string): Promise<MagnateMatch> {
  const { data } = await api.post<MagnateMatch>(`/magnate/rooms/${code}/join`);
  return data;
}

export async function startMagnateRoom(id: number): Promise<MagnateMatch> {
  const { data } = await api.post<MagnateMatch>(`/magnate/matches/${id}/start`);
  return data;
}

/** null = left a lobby (no longer at the table). */
export async function leaveMagnateMatch(id: number): Promise<MagnateMatch | null> {
  const { data } = await api.post<MagnateMatch | null>(`/magnate/matches/${id}/leave`);
  return data;
}

export async function sendMagnateAction(
  id: number, action: MagnateAction, version: number, cell?: number,
): Promise<MagnateMatch> {
  const { data } = await api.post<MagnateMatch>(`/magnate/matches/${id}/action`, { action, cell, version });
  return data;
}
