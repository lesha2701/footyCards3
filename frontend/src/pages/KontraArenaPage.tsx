import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchKontraArena, refreshKontraArena, startKontraArena } from "@/api/kontra";
import { IconChevronLeft, IconCoin, IconTrophy } from "@/components/icons";
import FighterCard from "@/components/kontra/FighterCard";
import { formatGameError } from "@/lib/errors";
import type { KontraBattle } from "@/types";

/** Arena: three defence squads to attack (players near your rating, bots
 *  when there aren't enough), auto or manual. */
export default function KontraArenaPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data: arena } = useQuery({ queryKey: ["kontra-arena"], queryFn: fetchKontraArena });
  const refresh = useMutation({
    mutationFn: refreshKontraArena,
    onSuccess: (a) => queryClient.setQueryData(["kontra-arena"], a),
  });
  const start = useMutation({
    mutationFn: ({ offer, manual }: { offer: number; manual: boolean }) => startKontraArena(offer, manual),
    onSuccess: (b: KontraBattle) => {
      queryClient.invalidateQueries({ queryKey: ["kontra-arena"] });
      queryClient.invalidateQueries({ queryKey: ["kontra-hub"] });
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      navigate(`/play/kontra/battles/${b.id}`);
    },
    onError: (err) => setError(formatGameError(err, "Не удалось начать бой")),
  });

  return (
    <div className="flex flex-col gap-3">
      <button onClick={() => navigate("/play/kontra")} className="flex items-center gap-1 self-start text-xs text-ink-mist">
        <IconChevronLeft size={16} /> Контратака
      </button>
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Арена</h1>
        <button onClick={() => navigate("/ranking?metric=kontra_rating")} className="flex items-center gap-1 rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-amber-300">
          <IconTrophy size={13} /> {arena?.rating ?? "—"}{arena?.rank ? ` · #${arena.rank}` : ""}
        </button>
      </div>
      {arena && (
        <p className="text-caption text-ink-mist-dim">
          Победа +{arena.rating_win} рейтинга и {arena.reward_win} <IconCoin size={10} className="inline" />, поражение −{arena.rating_loss}.
          Наградных боёв сегодня {arena.rewarded_today}/{arena.daily_limit}. Твой отряд — это и твоя защита.
        </p>
      )}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {arena?.offers.map((o) => (
        <section key={o.index} className="rounded-2xl bg-bg-surface p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="min-w-0 truncate font-display text-sm font-bold text-ink-chalk">{o.name}{o.is_bot ? " · бот" : ""}</span>
            <span className="shrink-0 font-mono text-xs text-ink-mist">⚡ {o.power.toLocaleString("ru-RU")} · ★ {o.rating}</span>
          </div>
          <div className="grid grid-cols-5 gap-1">
            {o.cards.map((c, i) => <FighterCard key={c.card_id} card={c} foe edge={i === 0 ? "left" : i === o.cards.length - 1 ? "right" : undefined} />)}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <button onClick={() => start.mutate({ offer: o.index, manual: false })} disabled={start.isPending} className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-chalk active:scale-95 disabled:opacity-50">
              Автобой
            </button>
            <button onClick={() => start.mutate({ offer: o.index, manual: true })} disabled={start.isPending} className="rounded-xl bg-amber-400 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-50">
              Вручную
            </button>
          </div>
        </section>
      ))}
      <button onClick={() => refresh.mutate()} disabled={refresh.isPending} className="rounded-2xl bg-white/5 py-2.5 text-xs font-semibold text-ink-mist active:scale-95">
        Других соперников
      </button>
    </div>
  );
}
