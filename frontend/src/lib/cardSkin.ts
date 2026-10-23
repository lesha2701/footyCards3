import { createContext, useContext } from "react";

/** The equipped card frame skin (a cosmetic style key). Only provided
 * around the player's OWN cards («Мои карточки»), so other players' cards
 * and pack reveals keep their plain rarity frame. Visual only. */
export const CardSkinContext = createContext<string | null>(null);

export function useCardSkin(): string | null {
  return useContext(CardSkinContext);
}
