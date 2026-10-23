import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { fetchMyProfile } from "@/api/profile";
import { CardSkinContext } from "@/lib/cardSkin";

export function MyCardSkinProvider({ children }: { children: ReactNode }) {
  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  return <CardSkinContext.Provider value={profile?.cosmetics?.card_skin ?? null}>{children}</CardSkinContext.Provider>;
}
