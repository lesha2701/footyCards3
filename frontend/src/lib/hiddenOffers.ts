import { usePersistentState } from "@/lib/usePersistentState";

/** Offers the player hid from the home screen («Стартовый набор» and any
 * future ones — give each its own id). Remembered per device, like the
 * dismissed announcement banner; the shop keeps showing the offer so it
 * can still be bought. */
export function useHiddenOffer(id: string): [boolean, () => void] {
  const [hidden, setHidden] = usePersistentState(`hidden_offer.${id}`, false);
  return [hidden, () => setHidden(true)];
}
