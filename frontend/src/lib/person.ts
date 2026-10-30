import type { Player, UserCard } from "@/types";

/** The footballer behind a card — the backend's player_identity.person_key:
 * copies and other versions of one player (base, TOTY…) share it, so a squad
 * holds each person once («нельзя две карточки Несты»). */
export function personKey(player: Pick<Player, "display_name"> & { person_key?: string | null }): string {
  return (player.person_key || player.display_name || "").trim().replace(/\s+/g, " ").toLowerCase().replace(/ё/g, "е");
}

/** Copies that look and play the same: same player, stars, «Академия» stage and skill. */
function copyKey(card: UserCard): string {
  return [
    card.player.id, card.stars ?? 0, card.path_stage ?? "", card.prestige ?? "", card.talent_override ?? "",
    card.skill_code ?? "", card.skill_level ?? "",
  ].join("|");
}

/** Identical copies collapsed into one tile (`count` = how many), keeping the
 * first one of each group — a `preferIds` copy (e.g. already in the squad)
 * stands for its group when there is one. */
export function collapseCopies(cards: UserCard[], preferIds: Iterable<number> = []): { card: UserCard; count: number }[] {
  const prefer = new Set(preferIds);
  const groups = new Map<string, { card: UserCard; count: number }>();
  for (const card of cards) {
    const key = copyKey(card);
    const group = groups.get(key);
    if (!group) groups.set(key, { card, count: 1 });
    else {
      group.count += 1;
      if (prefer.has(card.id) && !prefer.has(group.card.id)) group.card = card;
    }
  }
  return [...groups.values()];
}
