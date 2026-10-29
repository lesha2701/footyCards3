/** Half-time substitutions of a live career match: which bench player suits
 * a man going off, and a one-tap proposal for the tired ones. Only a
 * suggestion for the coach's form — the server validates every order. */
import type { CareerLivePlayer } from "@/api/career";

export interface Sub { out: number; in: number }

/** Fatigue from which a player is flagged as tired (and proposed off). */
export const TIRED_AT = 70;

const LINES: Record<string, "GK" | "DEF" | "MID" | "FWD"> = {
  GK: "GK",
  CB: "DEF", LB: "DEF", RB: "DEF", LWB: "DEF", RWB: "DEF",
  CDM: "MID", CM: "MID", CAM: "MID", LM: "MID", RM: "MID",
  ST: "FWD", CF: "FWD", LW: "FWD", RW: "FWD",
};

export function lineOf(position: string | null): string | null {
  return position ? LINES[position] ?? null : null;
}

/** Bench players still free for `out`, best fit first: the same position,
 * then the same line, then by rating and freshness. Keepers only for a
 * keeper, outfield players only for an outfield one. */
export function benchFor(out: CareerLivePlayer, bench: CareerLivePlayer[], subs: Sub[]): CareerLivePlayer[] {
  const used = new Set(subs.map((s) => s.in));
  const keeper = lineOf(out.position) === "GK";
  const fit = (p: CareerLivePlayer) =>
    (p.position && p.position === out.position ? 2 : 0) + (lineOf(p.position) && lineOf(p.position) === lineOf(out.position) ? 1 : 0);
  return bench
    .filter((p) => !used.has(p.card_id) && (lineOf(p.position) === "GK") === keeper)
    .sort((a, b) => fit(b) - fit(a) || (b.rating ?? 0) - (a.rating ?? 0) || a.fatigue - b.fatigue || a.card_id - b.card_id);
}

/** Players on the pitch, the most tired first (who to look at first). */
export function byFatigue(on: CareerLivePlayer[]): CareerLivePlayer[] {
  return [...on].sort((a, b) => b.fatigue - a.fatigue || a.card_id - b.card_id);
}

/** The orders with the tired players (fatigue >= TIRED_AT) taken off for
 * their best-fitting fresh bench player, the most tired first, up to the
 * substitutions left. Keepers only for keepers. */
export function suggestSubs(on: CareerLivePlayer[], bench: CareerLivePlayer[], subs: Sub[], left: number): Sub[] {
  const out = [...subs];
  for (const p of byFatigue(on)) {
    if (out.length >= left) break;
    if (p.fatigue < TIRED_AT || out.some((s) => s.out === p.card_id)) continue;
    const pick = benchFor(p, bench, out)[0];
    if (pick) out.push({ out: p.card_id, in: pick.card_id });
  }
  return out;
}
