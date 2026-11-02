import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState } from "react";

import { fetchHalloween } from "@/api/halloween";
import type { HalloweenState } from "@/types";

/** «🎃 Ночь тыкв» art: drop files into src/assets/halloween/ with these names
 *  (banner, pack, door-1…3, frame-zombie, frame-vampire, badge — .webp/.png)
 *  and they replace the drawn placeholders without code changes. */
const ART = import.meta.glob<string>("@/assets/halloween/*.{webp,png}", { eager: true, import: "default" });

export function halloweenArt(name: string): string | undefined {
  return ART[`/src/assets/halloween/${name}.webp`] ?? ART[`/src/assets/halloween/${name}.png`];
}

export const HALLOWEEN_QUERY_KEY = ["halloween"] as const;

/** The event state; `live` is true only while it runs (switch on + dates). */
export function useHalloween() {
  const query = useQuery({
    queryKey: HALLOWEEN_QUERY_KEY,
    queryFn: fetchHalloween,
    staleTime: 60_000,
    retry: false,
  });
  return { ...query, live: !!query.data?.active };
}

/** Re-renders every 30 s so a countdown stays honest. */
export function useMinuteTick(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

/** «1 д 5 ч», «3 ч 10 мин», «12 мин». */
export function timeLeft(until: string | null | undefined, now = Date.now()): string {
  if (!until) return "";
  const ms = new Date(until).getTime() - now;
  if (ms <= 0) return "меньше минуты";
  const days = Math.floor(ms / 86_400_000);
  const hours = Math.floor((ms % 86_400_000) / 3_600_000);
  const minutes = Math.floor((ms % 3_600_000) / 60_000);
  if (days > 0) return `${days} д ${hours} ч`;
  return hours > 0 ? `${hours} ч ${minutes} мин` : `${minutes} мин`;
}

/** «тыква / тыквы / тыкв». */
export function pumpkinsWord(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "тыква";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "тыквы";
  return "тыкв";
}

/** Frame of a card: the collection's own skin, or the door trick's zombie
 *  frame on one footballer for a day (purely visual). */
export type HalloweenSkin = "zombie" | "vampire";

export const HalloweenZombieContext = createContext<number | null>(null);

export function useZombiePlayerId(): number | null {
  return useContext(HalloweenZombieContext);
}

export function cardHalloweenSkin(
  player: { id: number; collection_skin?: string | null },
  zombiePlayerId: number | null,
): HalloweenSkin | null {
  if (player.collection_skin === "zombie" || player.collection_skin === "vampire") return player.collection_skin;
  return zombiePlayerId !== null && player.id === zombiePlayerId ? "zombie" : null;
}

export type { HalloweenState };
