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
