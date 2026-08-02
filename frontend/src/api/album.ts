import { api } from "@/lib/api";
import type { AlbumCollectionDetail, AlbumOverview } from "@/types";

export async function fetchAlbumOverview(search?: string): Promise<AlbumOverview> {
  const { data } = await api.get<AlbumOverview>("/collection/album", { params: { search: search || undefined } });
  return data;
}

export async function fetchAlbumCollectionDetail(collectionId: number, search?: string): Promise<AlbumCollectionDetail> {
  const { data } = await api.get<AlbumCollectionDetail>(`/collection/album/${collectionId}`, {
    params: { search: search || undefined },
  });
  return data;
}
