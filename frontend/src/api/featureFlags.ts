import { api } from "@/lib/api";
import type { FeatureFlags } from "@/types";

export async function fetchFeatureFlags(): Promise<FeatureFlags> {
  const { data } = await api.get<FeatureFlags>("/feature-flags");
  return data;
}
