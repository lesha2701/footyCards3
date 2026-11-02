import type { ReactNode } from "react";

import { HalloweenZombieContext, useHalloween } from "@/lib/halloween";

/** The door trick's zombie frame: one footballer of the player wears it for
 *  a day, wherever his card shows (purely visual, own state only). */
export function HalloweenZombieProvider({ children }: { children: ReactNode }) {
  const { data, live } = useHalloween();
  const until = data?.zombie_until ? new Date(data.zombie_until).getTime() : 0;
  const id = live && data?.zombie_player_id && until > Date.now() ? data.zombie_player_id : null;
  return <HalloweenZombieContext.Provider value={id}>{children}</HalloweenZombieContext.Provider>;
}
