import type { CardStarState, UserCard } from "@/types";

export interface StarFeedPreview {
  consumed: number;
  starsGained: number;
  coinsSpent: number;
  stars: number;
  progress: number;
  /** Banked duplicates already cover the next star, only coins are missing. */
  waitingForCoins: boolean;
}

/** What "Вложить N дублей" will do — mirrors backend
 * card_star_service.feed/_claim_ready_stars on the numbers the server
 * returned (thresholds, costs, progress), only for the confirmation text.
 * The server recomputes everything under a row lock. */
export function previewStarFeed(state: CardStarState, available: number, balance: number): StarFeedPreview {
  const consumed = Math.max(0, Math.min(available, state.dupes_to_max));
  let stars = state.stars;
  let progress = state.progress + consumed;
  let coins = balance;
  let coinsSpent = 0;
  while (stars < state.thresholds.length && progress >= state.thresholds[stars]) {
    const cost = state.coin_costs[stars] ?? 0;
    if (coins < cost) break;
    coins -= cost;
    coinsSpent += cost;
    progress -= state.thresholds[stars];
    stars += 1;
  }
  return {
    consumed, starsGained: stars - state.stars, coinsSpent, stars, progress,
    waitingForCoins: stars < state.thresholds.length && progress >= state.thresholds[stars],
  };
}

export function starString(stars: number, max: number): string {
  return "★".repeat(Math.max(0, stars)) + "☆".repeat(Math.max(0, max - stars));
}

/** Selling/burning this copy would lose its skill, its stars/«копилка» or
 * its «Начало пути» progress. */
export function losesProgress(
  card: Pick<UserCard, "skill_code" | "stars" | "star_progress"> & Partial<Pick<UserCard, "path_level" | "path_stage">>,
): boolean {
  return !!card.skill_code || !!card.stars || !!card.star_progress || !!card.path_level || !!card.path_stage;
}
