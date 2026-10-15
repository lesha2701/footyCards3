import { useQuery } from "@tanstack/react-query";

import { fetchPathCatalog } from "@/api/path";
import type { PathCatalog, PathState, Player, UserCard } from "@/types";

/** Stage marks on the path road, by stage index (Новичок … Легенда). The
 * names themselves come from the server (admin-editable). */
export const STAGE_ICONS = ["🌱", "🌿", "🌳", "⭐", "👑"];

export function stageIcon(index: number): string {
  return STAGE_ICONS[Math.max(0, Math.min(index, STAGE_ICONS.length - 1))];
}

export function isPathPlayer(player: Pick<Player, "path_talent_code"> | null | undefined): boolean {
  return !!player?.path_talent_code;
}

export function usePathCatalog(enabled = true) {
  return useQuery({ queryKey: ["path", "catalog"], queryFn: fetchPathCatalog, staleTime: 5 * 60_000, enabled });
}

export function talentByCode(catalog: PathCatalog | undefined, code: string | null | undefined) {
  if (!code) return undefined;
  return catalog?.talents.find((t) => t.code === code);
}

/** Talent level a stage index unlocks (highest unlocked so far). */
export function talentLevelAt(catalog: PathCatalog | undefined, stage: number): number {
  return Math.max(0, ...(catalog?.stages ?? []).filter((s) => s.index <= stage).map((s) => s.talent_level));
}

export function isLegendStage(catalog: PathCatalog | undefined, stage: number | undefined): boolean {
  if (!catalog?.stages.length || stage == null) return false;
  return stage >= catalog.stages[catalog.stages.length - 1].index;
}

/** 0..1 — how far along the whole path the card is (by rating). */
export function pathFraction(state: Pick<PathState, "base_rating" | "rating" | "ceiling">): number {
  const span = state.ceiling - state.base_rating;
  if (span <= 0) return 1;
  return Math.max(0, Math.min(1, (state.rating - state.base_rating) / span));
}

/** 0..1 — progress inside the current level. */
export function levelFraction(state: Pick<PathState, "xp_into_level" | "xp_for_next">): number {
  if (!state.xp_for_next) return 1;
  return Math.max(0, Math.min(1, state.xp_into_level / state.xp_for_next));
}

/** Experience shown toward the next level — never more than the level costs
 * (while the stage's tasks block the level, experience keeps piling up). */
export function shownLevelXp(state: Pick<PathState, "xp_into_level" | "xp_for_next">): number {
  return state.xp_for_next ? Math.min(state.xp_into_level, state.xp_for_next) : state.xp_into_level;
}

export function hasPathProgress(card: Pick<UserCard, "path_level" | "path_stage">): boolean {
  return !!card.path_level || !!card.path_stage;
}

const SEEN_KEY = "path-seen-stage-";

/** Highest stage of this copy the player has already seen celebrated.
 * Browser storage only (a per-viewer convenience); wrapped so a blocked
 * storage never breaks the screen. */
export function seenStage(cardId: number): number | null {
  try {
    const raw = window.localStorage.getItem(SEEN_KEY + cardId);
    return raw == null ? null : Number(raw);
  } catch {
    return null;
  }
}

export function markStageSeen(cardId: number, stage: number): void {
  try {
    window.localStorage.setItem(SEEN_KEY + cardId, String(stage));
  } catch {
    /* storage unavailable — the celebration may simply show again */
  }
}

/** «Росток» frame of a «Начало пути» card: a green-to-ice gradient in
 * place of the diamond one; gold once it reached «Легенда». The shimmer runs
 * only when the user allows motion (motion-safe). */
export const PATH_FRAME =
  "from-emerald-300 via-lime-200 to-cyan-300 shadow-[0_0_22px_rgba(110,231,183,0.45)] bg-[length:100%_400%] motion-safe:animate-diamond-shimmer";
export const PATH_LEGEND_FRAME =
  "from-amber-200 via-lime-200 to-amber-400 shadow-glow-legendary bg-[length:100%_400%] motion-safe:animate-diamond-shimmer";

export function pathFrameClass(stage: number | undefined, legendStage = 4): string {
  return stage != null && stage >= legendStage ? PATH_LEGEND_FRAME : PATH_FRAME;
}

export const SOURCE_LABELS: Record<string, string> = {
  arena: "Card Arena",
  ptour: "Турнир игроков",
  career: "Карьера",
};
