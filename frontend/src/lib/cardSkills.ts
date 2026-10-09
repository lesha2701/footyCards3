import { useQuery, type QueryClient } from "@tanstack/react-query";

import { fetchSkillCatalog } from "@/api/cardSkills";
import type { SkillCatalogItem, SkilledCopy } from "@/types";

export const SKILL_LEVEL_LABELS: Record<number, string> = { 1: "I", 2: "II", 3: "III" };

/** The server catalog (names, icons, exact effects, current bonus values).
 * Cards only carry `skill_code`/`skill_level`; this resolves them for display. */
export function useSkillCatalog() {
  return useQuery({ queryKey: ["card-skills", "catalog"], queryFn: fetchSkillCatalog, staleTime: 5 * 60_000 });
}

export function skillByCode(skills: SkillCatalogItem[] | undefined, code: string | null | undefined) {
  if (!code) return undefined;
  return skills?.find((s) => s.code === code);
}

/** Highest-level skilled copy — what the collapsed collection tile shows. */
export function bestSkilledCopy(copies: SkilledCopy[] | undefined): SkilledCopy | undefined {
  if (!copies?.length) return undefined;
  return [...copies].sort((a, b) => b.skill_level - a.skill_level)[0];
}

/** Everything a skill change can affect: the card itself, the collection
 * views that show its badge, squads that show it, trades, and the token
 * balances. Coins are refreshed from the server's own new_balance. */
export function invalidateAfterSkillChange(queryClient: QueryClient) {
  for (const key of [
    ["card-skills"],
    ["collection"],
    ["collection-stats"],
    ["album-overview"],
    ["album-detail"],
    ["lineup-templates"],
    ["player-tournament", "squads"],
    ["upgrade-cards"],
    ["trades"],
  ]) {
    queryClient.invalidateQueries({ queryKey: key });
  }
}
