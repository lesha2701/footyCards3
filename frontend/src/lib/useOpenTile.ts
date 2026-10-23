import { useState } from "react";

/** Which shop item has its details sheet open: one at a time. */
export function useOpenTile<K extends string | number>() {
  const [openKey, setOpenKey] = useState<K | null>(null);
  return {
    openKey,
    toggle: (key: K) => setOpenKey((cur) => (cur === key ? null : key)),
    close: () => setOpenKey(null),
  };
}
