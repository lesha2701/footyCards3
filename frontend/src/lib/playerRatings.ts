/** Match ratings of a career match (cosmetic, 3.0-10.0) and the man of the
 * match, from the event log and the line-ups of the 2D replay. Nothing in
 * the economy reads them: they only show who made the difference. Pure. */
import type { CareerReplay } from "@/api/career";
import type { MatchEventLite } from "@/lib/matchReplay";

export interface PlayerRating {
  /** Index in replay.players. */
  index: number;
  side: "a" | "b";
  name: string;
  n: number;
  rating: number;
  goals: number;
  assists: number;
}

const BASE = 6.0;
const R = {
  goal: 1.4, assist: 0.7, tackle: 0.3, foul: -0.1, yellow: -0.5, red: -1.5, shotOnTarget: 0.1,
  save: 0.4, conceded: -0.35, cleanKeeper: 0.6, cleanDefender: 0.3, win: 0.3, loss: -0.2,
};

const payloadOf = (e: MatchEventLite) => (e.payload ?? {}) as Record<string, unknown>;

/** Ratings of everyone who played (starters and substitutes who came on),
 * best first. */
export function matchRatings(replay: CareerReplay, events: MatchEventLite[], score: [number, number]): PlayerRating[] {
  const played = new Set<number>([...replay.roster, ...replay.swaps.map(([, , p]) => p)]);
  const keeperOf = { a: replay.roster[0], b: replay.roster[11] };
  const rows = new Map<number, PlayerRating>();
  for (const index of played) {
    const p = replay.players[index];
    if (!p) continue;
    rows.set(index, { index, side: p.s, name: p.name ?? `№${p.n}`, n: p.n, rating: BASE, goals: 0, assists: 0 });
  }
  // A name within a side → its player (names are unique enough per team).
  const find = (side: string | undefined, name: unknown): PlayerRating | undefined => {
    if ((side !== "a" && side !== "b") || typeof name !== "string") return undefined;
    for (const r of rows.values()) if (r.side === side && r.name === name) return r;
    return undefined;
  };
  const other = (side: "a" | "b") => (side === "a" ? "b" : "a");
  for (const e of events) {
    const side = e.team;
    if (side !== "a" && side !== "b") continue;
    const p = payloadOf(e);
    if (e.event_type === "goal") {
      const scorer = find(side, p.shooter);
      if (scorer) { scorer.rating += R.goal; scorer.goals += 1; }
      const assist = find(side, p.assist);
      if (assist) { assist.rating += R.assist; assist.assists += 1; }
      const keeper = rows.get(keeperOf[other(side)]);
      if (keeper && p.shot_type !== "empty_net") keeper.rating += R.conceded;
    } else if (e.event_type === "save") {
      const shooter = find(side, p.shooter);
      if (shooter) shooter.rating += R.shotOnTarget;
      const keeper = rows.get(keeperOf[other(side)]);
      if (keeper) keeper.rating += R.save;
    } else if (e.event_type === "tackle_won") {
      const d = find(side, p.defender);
      if (d) d.rating += R.tackle;
    } else if (e.event_type === "foul_stopped") {
      const d = find(side, p.defender);
      if (d) d.rating += R.foul + (p.card === "red" ? R.red : p.card === "yellow" ? R.yellow : 0);
    }
  }
  // Clean sheets and the result.
  for (const r of rows.values()) {
    const [own, opp] = r.side === "a" ? score : [score[1], score[0]];
    const pos = replay.players[r.index]?.slot ?? "";
    if (opp === 0) {
      if (r.index === keeperOf[r.side]) r.rating += R.cleanKeeper;
      else if (pos.startsWith("DEF")) r.rating += R.cleanDefender;
    }
    r.rating += own > opp ? R.win : own < opp ? R.loss : 0;
    r.rating = Math.round(Math.max(3, Math.min(10, r.rating)) * 10) / 10;
  }
  return [...rows.values()].sort((x, y) => y.rating - x.rating || y.goals - x.goals || x.index - y.index);
}

/** The man of the match: the best rating (goals break a tie). */
export function manOfTheMatch(ratings: PlayerRating[]): PlayerRating | null {
  return ratings[0] ?? null;
}

/** Colour band of a rating for the UI. */
export function ratingTone(rating: number): "great" | "good" | "poor" {
  return rating >= 7.5 ? "great" : rating >= 6.0 ? "good" : "poor";
}
