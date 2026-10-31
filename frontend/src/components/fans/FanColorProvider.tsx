import type { ReactNode } from "react";

import { FanColorContext, sideByCode, useFanBattle } from "@/lib/fanBattle";

/** «Капитаны» cards wear the colours of the viewer's side (own state only). */
export function FanColorProvider({ children }: { children: ReactNode }) {
  const { data } = useFanBattle();
  const color = data?.enabled ? sideByCode(data.sides, data.my_side)?.color ?? null : null;
  return <FanColorContext.Provider value={color}>{children}</FanColorContext.Provider>;
}
