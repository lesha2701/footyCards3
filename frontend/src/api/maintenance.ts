import { api } from "@/lib/api";
import type { MaintenanceStatus } from "@/types";

export async function fetchMaintenanceStatus(): Promise<MaintenanceStatus> {
  const { data } = await api.get<MaintenanceStatus>("/maintenance");
  return data;
}
