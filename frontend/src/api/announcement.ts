import { api } from "@/lib/api";
import type { Announcement } from "@/types";

export async function fetchAnnouncement(): Promise<Announcement> {
  const { data } = await api.get<Announcement>("/announcement");
  return data;
}
