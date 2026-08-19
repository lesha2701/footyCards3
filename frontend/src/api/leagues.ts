import { api } from "@/lib/api";
import type { LeagueStatus, LeagueTierPublic } from "@/types";

export async function fetchLeagues(): Promise<LeagueTierPublic[]> {
  const { data } = await api.get<LeagueTierPublic[]>("/leagues");
  return data;
}

export async function fetchLeagueStatus(): Promise<LeagueStatus> {
  const { data } = await api.get<LeagueStatus>("/leagues/status");
  return data;
}
