/** Reveal-stage sequences and timings, kept out of the stage components so
 * those files export only components (React fast refresh). */
export type Stage = "position" | "rarity" | "country" | "club" | "silhouette" | "reveal";
export const STAGES: Stage[] = ["position", "rarity", "country", "club", "silhouette", "reveal"];
export const STAGE_DURATION_MS = 900;

export type CoachStage = "rarity" | "silhouette" | "reveal";
export const COACH_STAGES: CoachStage[] = ["rarity", "silhouette", "reveal"];
export const COACH_STAGE_DURATION_MS = 900;

export type TokenStage = "glow" | "reveal";
export const TOKEN_STAGES: TokenStage[] = ["glow", "reveal"];
export const TOKEN_STAGE_DURATION_MS = 800;

export type StadiumStage = "rarity" | "silhouette" | "reveal";
export const STADIUM_STAGES: StadiumStage[] = ["rarity", "silhouette", "reveal"];
export const STADIUM_STAGE_DURATION_MS = 900;

/** «Выход» for the big pulls: a legendary or diamond card (not «Академия»)
 * comes out like a walkout — dark screen, a beam in its colour, the flag,
 * the position, the rating counting up — so each stage stays on screen a
 * bit longer than a regular card's. */
export const WALKOUT_STAGE_DURATION_MS = 1400;

export function isWalkout(player: { rarity: string; path_talent_code?: string | null }): boolean {
  return (player.rarity === "legendary" || player.rarity === "diamond") && !player.path_talent_code;
}

export function playerStageDuration(player: { rarity: string; path_talent_code?: string | null }): number {
  return isWalkout(player) ? WALKOUT_STAGE_DURATION_MS : STAGE_DURATION_MS;
}
