import { api } from "@/lib/api";
import type { Achievement } from "@/types";

export async function fetchAchievements(): Promise<Achievement[]> {
  const { data } = await api.get<Achievement[]>("/achievements");
  return data;
}
