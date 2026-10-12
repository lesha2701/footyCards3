import type { ChemistryLink, ChemistryLinkLevel, ChemistryOut, ChemistryRules, PlayerChemistry } from "@/types";

/**
 * Client-side mirror of backend services/chemistry_service.compute_chemistry,
 * used ONLY for instant "what if" numbers (picker badges, swap hints) while
 * the player is still choosing — what is saved and what matches use always
 * comes from the server's `chemistry` object. Rules and adjacency are taken
 * from that server object, never hardcoded here; parity with the Python
 * implementation is pinned by src/test/chemistryCases.json, which both
 * src/test/chemistry.test.ts and backend tests/test_chemistry.py assert.
 */

export interface ChemistryPlayerInput {
  slot: string;
  club: string;
  country: string;
  position: string;
  idealPosition: string;
}

export interface ChemistryResult {
  links: ChemistryLink[];
  players: Record<string, PlayerChemistry>;
  team: number;
  teamMax: number;
}

function groupKey(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value.split(/\s+/).filter(Boolean).join(" ");
  return cleaned || null;
}

export function linkLevel(a: { club: string; country: string }, b: { club: string; country: string }): ChemistryLinkLevel {
  const clubA = groupKey(a.club), clubB = groupKey(b.club);
  const countryA = groupKey(a.country), countryB = groupKey(b.country);
  const sameClub = clubA !== null && clubA === clubB;
  const sameCountry = countryA !== null && countryA === countryB;
  if (sameClub && sameCountry) return "strong";
  if (sameClub || sameCountry) return "medium";
  return "none";
}

function linkPoints(level: ChemistryLinkLevel, rules: ChemistryRules): number {
  if (level === "strong") return rules.link_strong;
  if (level === "medium") return rules.link_medium;
  return 0;
}

export function playerPoints(linkSum: number, onPosition: boolean, rules: ChemistryRules): number {
  if (!onPosition) return 0;
  const cap = Math.max(0, rules.player_max);
  const reached = rules.thresholds.filter((t) => linkSum >= t).length;
  return Math.min(cap, Math.max(Math.min(rules.player_floor, cap), reached));
}

export function computeChemistry(
  players: ChemistryPlayerInput[],
  adjacency: [string, string][],
  rules: ChemistryRules,
  slotCount?: number,
): ChemistryResult {
  const bySlot = new Map(players.map((p) => [p.slot, p]));
  const linkSums = new Map(players.map((p) => [p.slot, 0]));
  const links: ChemistryLink[] = [];
  for (const [a, b] of adjacency) {
    const pa = bySlot.get(a), pb = bySlot.get(b);
    if (!pa || !pb) continue;
    const level = linkLevel(pa, pb);
    const points = linkPoints(level, rules);
    links.push({ a, b, level, points });
    linkSums.set(a, (linkSums.get(a) ?? 0) + points);
    linkSums.set(b, (linkSums.get(b) ?? 0) + points);
  }
  const result: Record<string, PlayerChemistry> = {};
  for (const p of players) {
    const onPosition = p.position === p.idealPosition;
    const linkSum = linkSums.get(p.slot) ?? 0;
    const points = playerPoints(linkSum, onPosition, rules);
    result[p.slot] = {
      slot_code: p.slot, points, link_sum: linkSum, on_position: onPosition,
      rating_bonus: points * rules.rating_per_point - (onPosition ? 0 : rules.off_position_penalty),
    };
  }
  const team = Object.values(result).reduce((sum, p) => sum + p.points, 0);
  return { links, players: result, team, teamMax: Math.max(0, rules.player_max) * (slotCount ?? players.length) };
}

interface SlotLike {
  slot_code: string;
  ideal_position: string;
  player: { id: number; display_name: string; club: string; country: string; position: string } | null;
}

export interface ChemistryCandidate {
  cardId: number;
  playerId: number;
  name: string;
  club: string;
  country: string;
  position: string;
}

export interface ChemistrySwapHint {
  slotCode: string;
  cardId: number;
  name: string;
  currentName: string | null;
  gain: number;
}

function inputsOf(slots: SlotLike[]): ChemistryPlayerInput[] {
  return slots
    .filter((s) => s.player)
    .map((s) => ({ slot: s.slot_code, club: s.player!.club, country: s.player!.country, position: s.player!.position, idealPosition: s.ideal_position }));
}

/** Team-chemistry change if `candidate` is put into `slotCode` (replacing
 * whoever is there). null when the server has chemistry switched off. */
export function chemistryGain(
  chemistry: ChemistryOut | undefined, slots: SlotLike[], slotCode: string, candidate: Omit<ChemistryCandidate, "cardId" | "playerId" | "name">,
): number | null {
  if (!chemistry?.enabled || !chemistry.rules) return null;
  const target = slots.find((s) => s.slot_code === slotCode);
  if (!target) return null;
  const before = computeChemistry(inputsOf(slots), chemistry.adjacency, chemistry.rules, slots.length).team;
  const after = computeChemistry(
    [
      ...inputsOf(slots.filter((s) => s.slot_code !== slotCode)),
      { slot: slotCode, club: candidate.club, country: candidate.country, position: candidate.position, idealPosition: target.ideal_position },
    ],
    chemistry.adjacency, chemistry.rules, slots.length,
  ).team;
  return after - before;
}

/** "Поставь сюда игрока X — +N к химии": the best single swaps from the
 * given candidates (already fitting each slot's category), biggest gain first. */
export function chemistrySwapHints(
  chemistry: ChemistryOut | undefined,
  slots: SlotLike[],
  candidatesForSlot: (slot: SlotLike) => ChemistryCandidate[],
  limit = 3,
): ChemistrySwapHint[] {
  if (!chemistry?.enabled || !chemistry.rules) return [];
  const used = new Set(slots.filter((s) => s.player).map((s) => s.player!.id));
  const best = new Map<string, ChemistrySwapHint>();
  for (const slot of slots) {
    for (const c of candidatesForSlot(slot)) {
      if (used.has(c.playerId)) continue;
      const gain = chemistryGain(chemistry, slots, slot.slot_code, c) ?? 0;
      const current = best.get(slot.slot_code);
      if (gain > 0 && (!current || gain > current.gain)) {
        best.set(slot.slot_code, { slotCode: slot.slot_code, cardId: c.cardId, name: c.name, currentName: slot.player?.display_name ?? null, gain });
      }
    }
  }
  return [...best.values()].sort((a, b) => b.gain - a.gain || a.slotCode.localeCompare(b.slotCode)).slice(0, limit);
}

/** Notice for an editor whose tournament is already running with frozen rules
 * (backend ChemistryOut.frozen); null when there is nothing to say. */
export function chemistryFrozenText(chemistry: ChemistryOut | undefined): string | null {
  if (!chemistry?.frozen) return null;
  if (chemistry.enabled) {
    return "Идущий турнир играет по правилам химии, зафиксированным на его старте. Новые настройки начнут действовать со следующего турнира.";
  }
  if (chemistry.live_enabled) {
    return "В идущем турнире химия связей не действует — он начался до её включения. Она заработает со следующего турнира.";
  }
  return null;
}
