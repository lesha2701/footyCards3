import type { UserCard } from "@/types";

type LockFields = Pick<UserCard, "is_in_lineup" | "is_in_tactico_squad" | "is_user_locked" | "in_personal_squad">;

/** Stands in any squad (Card Arena, Тактико or a player-tournament squad). */
export function inSquad(card: LockFields): boolean {
  return card.is_in_lineup || card.is_in_tactico_squad || !!card.in_personal_squad;
}

export function squadLabel(card: LockFields): string | null {
  if (card.is_in_lineup) return "в составе Card Arena";
  if (card.is_in_tactico_squad) return "в составе Тактико";
  if (card.in_personal_squad) return "в составе турнира игроков";
  return null;
}

/** Props for PlayerCard: the squad shade and the owner's lock mark. */
export function cardLockProps(card: LockFields): { inSquad: boolean; userLocked: boolean } {
  return { inSquad: inSquad(card), userLocked: !!card.is_user_locked };
}
