import { useQuery, type QueryClient } from "@tanstack/react-query";

import { fetchSkillCatalog, fetchSkillTokens } from "@/api/cardSkills";
import { useAuthStore } from "@/store/authStore";
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

/** Why a skill does nothing in a given lineup — null when it's active.
 * Mirrors the server's own rule (card_skill_effects.effect_for_card): the
 * mechanic must be on, the skill must act in that match engine, and the
 * card's position must be in the skill's server-side position list. */
export function skillInactiveReason(
  skill: SkillCatalogItem | undefined,
  engine: "arena" | "tournament",
  position: string | undefined,
  mechanicEnabled: boolean,
): string | null {
  if (!skill) return null;
  if (!mechanicEnabled) return "Навыки сейчас отключены";
  if (!skill.engines.includes(engine)) {
    return engine === "arena" ? "Не действует в Card Arena" : "Не действует в турнирах";
  }
  if (position && !skill.max_positions.includes(position)) return "Не подходит позиции карточки";
  return null;
}

/** (code, level) -> true when this skill could be upgraded right now with
 * the player's own tokens and coins (used for the little ▲ on card badges).
 * Display only — the server re-checks everything on the actual request. */
export function useSkillUpgradeCheck() {
  const { data: catalog } = useSkillCatalog();
  const { data: tokens } = useQuery({ queryKey: ["card-skills", "tokens"], queryFn: fetchSkillTokens });
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  return (code: string | null | undefined, level: number | null | undefined): boolean => {
    if (!catalog || !code || !level || level >= catalog.rules.max_level || !catalog.rules.enabled) return false;
    const skill = skillByCode(catalog.skills, code);
    if (!skill?.is_available) return false;
    const cost = level === 1 ? catalog.rules.costs.upgrade_to_2 : catalog.rules.costs.upgrade_to_3;
    const owned = tokens?.find((t) => t.skill_code === code)?.quantity ?? 0;
    return owned >= cost.token_cost && balance >= cost.coin_cost;
  };
}
