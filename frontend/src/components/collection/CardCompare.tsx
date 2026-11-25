import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchCollection } from "@/api/collection";
import PlayerCard from "@/components/cards/PlayerCard";
import { compareRows } from "@/lib/cardCompare";
import type { UserCard } from "@/types";

/** «⚖️ Сравнить»: this copy against another of the player's cards, side by side. */
export function CardCompareButton({ card }: { card: UserCard }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="min-h-[44px] rounded-xl bg-black/20 px-3 py-2 text-left text-xs font-semibold text-ink-chalk"
        data-testid="card-compare-open"
      >
        ⚖️ Сравнить с другой карточкой
      </button>
      {open && <CardCompareSheet base={card} onClose={() => setOpen(false)} />}
    </>
  );
}

function CardCompareSheet({ base, onClose }: { base: UserCard; onClose: () => void }) {
  const [search, setSearch] = useState("");
  const [other, setOther] = useState<UserCard | null>(null);
  const { data } = useQuery({
    queryKey: ["compare-candidates", base.player.position, search],
    queryFn: () => fetchCollection({
      search: search || undefined, position: search ? undefined : base.player.position, sort_by: "rating", sort_dir: "desc", page_size: 30,
    }),
  });
  const candidates = (data?.items ?? []).filter((c) => c.id !== base.id);
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/75 sm:items-center" onClick={onClose}>
      <div
        className="flex max-h-[88vh] w-full max-w-sm flex-col gap-3 overflow-y-auto rounded-t-3xl bg-bg-surface p-4 sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="card-compare"
      >
        <p className="font-display text-base font-bold text-ink-chalk">⚖️ Сравнение</p>
        <div className="grid grid-cols-2 gap-3">
          <PlayerCard player={base.player} size="sm" stars={base.stars} serial={base.serial_number} finish={base.finish} />
          {other ? (
            <button onClick={() => setOther(null)} className="text-left">
              <PlayerCard player={other.player} size="sm" stars={other.stars} serial={other.serial_number} finish={other.finish} />
            </button>
          ) : (
            <div className="flex aspect-[3/4] items-center justify-center rounded-xl border border-dashed border-white/15 p-2 text-center text-xs text-ink-mist">
              Выбери карточку ниже
            </div>
          )}
        </div>
        {other ? (
          <div className="flex flex-col gap-1" data-testid="card-compare-table">
            {compareRows(base, other).map((r) => (
              <div key={r.label} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-lg bg-black/20 px-3 py-1.5 text-sm">
                <span className={`text-right font-mono font-bold ${r.win === "a" ? "text-accent-lime" : "text-ink-chalk"}`}>{r.a}</span>
                <span className="text-micro text-ink-mist">{r.label}</span>
                <span className={`font-mono font-bold ${r.win === "b" ? "text-accent-lime" : "text-ink-chalk"}`}>{r.b}</span>
              </div>
            ))}
            <button onClick={() => setOther(null)} className="mt-1 text-xs text-ink-mist">Выбрать другую</button>
          </div>
        ) : (
          <>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по имени (по умолчанию — та же позиция)"
              className="rounded-xl bg-black/25 px-3 py-2 text-sm text-ink-chalk outline-none placeholder:text-ink-mist-dim"
            />
            <div className="grid grid-cols-3 gap-2">
              {candidates.map((c) => (
                <PlayerCard key={c.id} player={c.player} size="sm" stars={c.stars} finish={c.finish} onClick={() => setOther(c)} />
              ))}
            </div>
          </>
        )}
        <button onClick={onClose} className="rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
          Закрыть
        </button>
      </div>
    </div>
  );
}
