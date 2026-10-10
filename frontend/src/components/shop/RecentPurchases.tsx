import { useQuery } from "@tanstack/react-query";

import { fetchPackHistory } from "@/api/packs";
import { staticUrl } from "@/lib/api";
import type { Pack } from "@/types";

/** "Недавние покупки": the packs the player actually opens, one tap to buy
 * the same again (coin packs open the quantity sheet, Stars packs switch to
 * the Stars tab). Packs no longer on sale are left out. */
export default function RecentPurchases({
  availablePacks,
  onRebuy,
}: {
  availablePacks: Pack[] | undefined;
  onRebuy: (pack: Pack) => void;
}) {
  const { data: history } = useQuery({ queryKey: ["packs", "history"], queryFn: fetchPackHistory });
  const onSale = new Map((availablePacks ?? []).map((p) => [p.id, p]));
  const items = (history ?? []).filter((h) => onSale.get(h.pack.id)?.is_available_now);
  if (!items.length) return null;

  return (
    <section>
      <p className="mb-2 font-mono text-[11px] uppercase tracking-wider text-ink-mist">Недавние покупки</p>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {items.map((h) => {
          const pack = onSale.get(h.pack.id)!;
          return (
            <button
              key={h.pack.id}
              onClick={() => onRebuy(pack)}
              className="flex w-28 shrink-0 flex-col items-center gap-1.5 rounded-2xl bg-bg-surface p-2.5 active:scale-95"
            >
              <img src={staticUrl(pack.image_path ?? undefined)} alt="" className="h-12 w-12 rounded-xl object-cover" />
              <span className="w-full truncate text-center text-[11px] font-semibold text-ink-chalk">{pack.name}</span>
              <span className="text-[10px] text-ink-mist">×{h.times_opened} · ещё раз</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
