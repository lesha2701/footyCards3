import { api } from "@/lib/api";
import type { AlbumCollectionDetail, AlbumOverview } from "@/types";

/** `ownerId` = another player's album, read-only (a friend leafing through it). */
export async function fetchAlbumOverview(search?: string, ownerId?: number): Promise<AlbumOverview> {
  const url = ownerId ? `/users/${ownerId}/album` : "/collection/album";
  const { data } = await api.get<AlbumOverview>(url, { params: { search: search || undefined } });
  return data;
}

export async function fetchAlbumCollectionDetail(collectionId: number, search?: string, ownerId?: number): Promise<AlbumCollectionDetail> {
  const url = ownerId ? `/users/${ownerId}/album/${collectionId}` : `/collection/album/${collectionId}`;
  const { data } = await api.get<AlbumCollectionDetail>(url, { params: { search: search || undefined } });
  return data;
}
