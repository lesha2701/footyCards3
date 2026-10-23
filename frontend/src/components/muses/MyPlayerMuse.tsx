import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchMuses } from "@/api/muses";
import { IconChevronRight } from "@/components/icons";
import MuseArt from "@/components/muses/MuseArt";

/** «Мой игрок» → Имущество: the active «Муза» and her bonus, with a way to
 * the album. Hidden while Muses are off. */
export default function MyPlayerMuse() {
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["muses"], queryFn: fetchMuses });
  if (!data?.enabled) return null;
  const active = data.active;
  return (
    <button onClick={() => navigate("/muses")} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.99]">
      {active ? (
        <MuseArt muse={active} className="h-14 w-14 shrink-0 rounded-2xl" iconClass="text-2xl" />
      ) : (
        <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-dashed border-white/15 text-2xl">💖</span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-bold text-ink-chalk">
          Муза{active ? ` · ${active.name}` : ""}
        </span>
        <span className="block text-xs text-pink-300">
          {active
            ? active.effect_label
            : `В альбоме ${data.owned_count} из ${data.total_count} — выбей музу в паке «Музы»`}
        </span>
        {active && data.daily.coins > 0 && !data.daily.claimed_today && (
          <span className="block text-caption text-accent-lime">Монеты дня ждут →</span>
        )}
      </span>
      <IconChevronRight size={16} className="shrink-0 text-ink-mist-dim" />
    </button>
  );
}
