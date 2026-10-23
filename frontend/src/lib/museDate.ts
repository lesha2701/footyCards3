import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import type { MuseAlbum } from "@/api/muses";

/** «Свидание с музой»: a mini-game page opened with ?muse=1 starts its
 * session as today's date (an extra attempt, backend muse_service). `done`
 * drops the flag after the claim, so «играть снова» is an ordinary game. */
export function useMuseDate(): { active: boolean; done: () => void } {
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  return {
    active: params.get("muse") === "1",
    done: () => {
      queryClient.invalidateQueries({ queryKey: ["muses"] });
      queryClient.invalidateQueries({ queryKey: ["my-player"] });
      setParams({}, { replace: true });
    },
  };
}

export type MuseHeartState = "date" | "inspired" | "bored";

/** The heart on her portrait: today's date waiting > inspired > misses you. */
export function museHeartState(album: Pick<MuseAlbum, "date">): MuseHeartState {
  if (!album.date.today?.completed) return "date";
  return album.date.inspired_until ? "inspired" : "bored";
}
