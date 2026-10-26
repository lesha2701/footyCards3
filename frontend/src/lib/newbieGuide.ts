import type { Rarity } from "@/types";

/** Where the newbie is in the Card Arena part of the «Путь дебютанта» (per
 * device): "card" — the first-match card was just revealed, "test" — it was
 * put in the squad for a test match, "done" — sent back to the tasks. */
export type ArenaStage = { step: "" | "card" | "test" | "done"; cardName?: string; rarity?: Rarity };

const key = (userId: number) => `fc_newbie_arena_${userId}`;

export function arenaStage(userId: number): ArenaStage {
  try {
    const raw = localStorage.getItem(key(userId));
    return raw ? (JSON.parse(raw) as ArenaStage) : { step: "" };
  } catch {
    return { step: "" };
  }
}

export function setArenaStage(userId: number, stage: ArenaStage): void {
  try {
    localStorage.setItem(key(userId), JSON.stringify(stage));
  } catch {
    // Storage unavailable — the guide just won't resume after a reload.
  }
}
