import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { hapticNotify } from "@/lib/telegram";

export type CareerCode = "pro" | "agent" | "refresh" | "heal" | "save_offer" | "fast";

/** Pays a career extra with Stars and refreshes the page data. */
export function useCareerStars(onError: (e: unknown) => void) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const buy = async (code: CareerCode, arg?: string) => {
    setBusy(code);
    try {
      if ((await payMyPlayerWithStars({ purchase: "career", code, arg })) === "paid") {
        hapticNotify("success");
        await queryClient.invalidateQueries({ queryKey: ["player-career"] });
        await queryClient.invalidateQueries({ queryKey: ["my-player"], exact: true });
      }
    } catch (err) {
      onError(err);
    } finally {
      setBusy(null);
    }
  };
  return { buy, busy };
}

