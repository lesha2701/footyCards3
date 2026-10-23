import { CATEGORY_POSITIONS, onIdealPosition } from "@/lib/formation";
import type { Lineup, LineupSlot, UserCard } from "@/types";

export type Placement =
  | { ok: true; slots: { slot_code: string; user_card_id: number }[]; slotCode: string; replaced: UserCard | null }
  | { ok: false; reason: string };

const isPath = (card: UserCard) => !!card.player.path_talent_code;
const isPlainDiamond = (card: UserCard) => card.player.rarity === "diamond" && !isPath(card);

/** Where to put `card` into the active Card Arena lineup, straight from the
 * card: the slot of another copy of the same player, else the slot that has
 * to give way for the diamond / «Академия» limit, else an empty slot of its
 * line (its ideal position first), else the weakest card of its line
 * (ideal position first). The server re-checks every rule. */
export function planArenaPlacement(lineup: Lineup, card: UserCard): Placement {
  const fits = (slot: LineupSlot) => CATEGORY_POSITIONS[slot.category as keyof typeof CATEGORY_POSITIONS]
    ?.includes(card.player.position) ?? false;
  const candidates = lineup.slots.filter(fits);
  if (!candidates.length) return { ok: false, reason: "В схеме нет места для этой позиции" };

  let target: LineupSlot | undefined = lineup.slots.find((s) => s.card?.player.id === card.player.id);
  if (target && !fits(target)) return { ok: false, reason: "Другая копия этого игрока стоит на другой позиции" };

  if (!target) {
    const limited = isPath(card)
      ? { max: lineup.max_path ?? 1, same: isPath, label: "«Академии»" }
      : isPlainDiamond(card)
        ? { max: lineup.max_diamond, same: isPlainDiamond, label: "бриллиантовых" }
        : null;
    if (limited) {
      const taken = lineup.slots.filter((s) => s.card && limited.same(s.card));
      if (taken.length >= limited.max) {
        target = taken.find(fits);
        if (!target) {
          return { ok: false, reason: `В составе уже максимум карт ${limited.label} — замени одну из них вручную` };
        }
      }
    }
  }

  if (!target) {
    const byStrength = (a: LineupSlot, b: LineupSlot) => (a.card?.player.rating ?? 0) - (b.card?.player.rating ?? 0);
    const ideal = candidates.filter((s) => onIdealPosition(card.player.position, s.ideal_position));
    target = ideal.find((s) => !s.card)
      ?? candidates.find((s) => !s.card)
      ?? [...ideal].sort(byStrength)[0]
      ?? [...candidates].sort(byStrength)[0];
  }

  const replaced = target.card && target.card.id !== card.id ? target.card : null;
  const slots = lineup.slots
    .map((s) => ({ slot_code: s.slot_code, user_card_id: s.slot_code === target!.slot_code ? card.id : s.card?.id }))
    .filter((s): s is { slot_code: string; user_card_id: number } => typeof s.user_card_id === "number");
  return { ok: true, slots, slotCode: target.slot_code, replaced };
}
