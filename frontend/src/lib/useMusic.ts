import { useSyncExternalStore } from "react";

import { musicState, subscribeMusic } from "@/lib/music";

/** The soundtrack's current track and play state, for the UI. */
export function useMusic() {
  return useSyncExternalStore(subscribeMusic, musicState);
}
