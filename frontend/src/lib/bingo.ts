import type { BingoCurrent } from "@/types";

/** The server's common reward can be taken: every goal done, not taken yet
 * and a closed line on the player's own card (an old backend has no card). */
export function communityReady(bingo?: BingoCurrent | null): boolean {
  if (!bingo?.all_goals_completed || bingo.has_claimed) return false;
  return bingo.card ? bingo.card.community_eligible : true;
}

/** Anything to take on the «Бинго недели» page right now. */
export function bingoReady(bingo?: BingoCurrent | null): boolean {
  return !!bingo?.is_enabled && (!!bingo.card?.can_claim || communityReady(bingo));
}
