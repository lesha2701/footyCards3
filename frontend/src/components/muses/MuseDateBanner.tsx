import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { fetchMuses } from "@/api/muses";
import MuseArt from "@/components/muses/MuseArt";

/** Top of a mini-game opened as «Свидание с музой» (?muse=1): who you play
 * with and what it gives. Renders nothing otherwise. */
export default function MuseDateBanner() {
  const [params] = useSearchParams();
  const on = params.get("muse") === "1";
  const { data } = useQuery({ queryKey: ["muses"], queryFn: fetchMuses, enabled: on });
  if (!on || !data?.active) return null;
  return (
    <div className="flex w-full items-center gap-3 rounded-2xl bg-gradient-to-r from-pink-500/20 to-bg-surface p-3">
      <MuseArt muse={data.active} className="h-14 w-11 shrink-0 rounded-xl" iconClass="text-2xl" />
      <div className="min-w-0 text-left">
        <p className="truncate font-display text-sm font-bold text-ink-chalk">Свидание · {data.active.name}</p>
        <p className="text-caption text-pink-200">
          Отдельная попытка, результат не важен: +{data.date.coins} монет и вдохновение на {data.date.inspiration_hours} ч
        </p>
      </div>
    </div>
  );
}
