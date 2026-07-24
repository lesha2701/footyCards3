import { api } from "@/lib/api";
import type { CardCollectionPublic } from "@/types";

export async function fetchCollections(): Promise<CardCollectionPublic[]> {
  const { data } = await api.get<CardCollectionPublic[]>("/collections");
  return data;
}
