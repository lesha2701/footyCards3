import type { QueryClient, QueryKey } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** `GET /home`: the first screen's data in one request instead of ~25.
 * Each part is exactly what its own endpoint returns, so it goes straight
 * into that query's cache; the components then find it fresh and don't ask
 * (default staleTime). A part the server left out («не в клубе», an error)
 * is simply not seeded — its component fetches it itself, as before. */
export const HOME_PARTS: Record<string, QueryKey> = {
  "/profile/me": ["profile", "me"],
  "/feature-flags": ["feature-flags"],
  "/announcement": ["announcement"],
  "/maintenance": ["maintenance-status"],
  "/updates/status": ["update-status"],
  "/my-player": ["my-player"],
  "/leagues/status": ["league-status"],
  "/wheel/status": ["wheel-status"],
  "/newbie": ["newbie"],
  "/starter-offer": ["starter-offer"],
  "/presence": ["presence"],
  "/academy": ["academy"],
  "/matches/stats": ["arena-stats"],
  "/career": ["career"],
  "/club-base": ["club-base"],
  "/clubs/me": ["clubs", "me"],
  "/player-tournaments/current": ["player-tournament", "current"],
  "/town": ["town"],
  "/artifacts": ["artifacts"],
  "/cosmetics": ["cosmetics"],
  "/packs/daily-offer": ["packs", "daily-offer"],
  "/packs": ["packs"],
  "/streak-rewards/unseen": ["streak-rewards"],
  "/loyalty/unseen": ["loyalty-rewards"],
  "/comeback-gifts/unseen": ["comeback-gifts"],
  "/stars-patron/letters": ["stars-patron-letters"],
  "/muses": ["muses"],
  "/halloween": ["halloween"],
  "/fans": ["fan-battle"],
  "/anniversary": ["anniversary"],
  "/loyalty/status": ["loyalty-status"],
  "/daily-rewards/calendar": ["daily-reward-calendar"],
  "/tasks": ["tasks"],
  "/free-pack/status": ["free-pack-status"],
  "/manager/summary": ["manager", "summary"],
  "/prospect": ["prospect"],
  "/profile/me/attention": ["attention"],
  "/weekly-top/awards": ["weekly-top-awards"],
};

export interface HomeBundle {
  data: Record<string, unknown>;
  errors: Record<string, number>;
}

export function seedHome(queryClient: QueryClient, bundle: HomeBundle): number {
  let seeded = 0;
  for (const [path, key] of Object.entries(HOME_PARTS)) {
    if (!(path in bundle.data)) continue;
    queryClient.setQueryData(key, bundle.data[path]);
    seeded += 1;
  }
  return seeded;
}

/** Fetches and seeds the first screen; never fails — on a slow or broken
 * answer the components just load their own data as they always did. */
export async function prefetchHome(queryClient: QueryClient, timeoutMs = 6000): Promise<void> {
  try {
    const { data } = await api.get<HomeBundle>("/home", { timeout: timeoutMs });
    if (data && typeof data === "object" && data.data) seedHome(queryClient, data);
  } catch {
    // the screen loads its parts one by one
  }
}
