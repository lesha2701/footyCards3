import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimMuseDaily, fetchMuses } from "@/api/muses";
import { IconCoin } from "@/components/icons";
import MuseArt from "@/components/muses/MuseArt";
import MuseDateButton, { MuseMoodLine } from "@/components/muses/MuseDateButton";
import MusePickerSheet from "@/components/muses/MusePickerSheet";
import { formatGameError } from "@/lib/errors";
import { RARITY_LABELS } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

/** Profile → «Муза»: a big portrait of the active Muse (only she gives her
 * bonus). Tapping it opens the picker of the player's own Muses — he picks
 * whichever he likes or whose bonus he needs. Below: her mood, the daily
 * date and her daily coins. Hidden while Muses are off. */
export default function ProfileMuse() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["muses"], queryFn: fetchMuses });
  const claim = useMutation({
    mutationFn: claimMuseDaily,
    onSuccess: (album) => {
      hapticNotify("success");
      queryClient.setQueryData(["muses"], album);
      if (album.new_balance != null) updateBalance(album.new_balance);
      setError(null);
    },
    onError: (err) => setError(formatGameError(err, "Не получилось забрать монеты")),
  });

  if (!data?.enabled) return null;
  const active = data.active;
  const ownedCount = data.owned_count;

  const portrait = (
    <button
      onClick={() => {
        haptic("light");
        if (ownedCount) setPicking(true);
        else navigate("/muses");
      }}
      className="mx-auto block w-48 active:scale-[0.98]"
      aria-label={active ? `Сменить музу: сейчас ${active.name}` : "Выбрать музу"}
    >
      {active ? (
        <MuseArt
          muse={active}
          className="aspect-[3/4] w-full rounded-3xl shadow-[0_0_50px_-12px] shadow-pink-400/60"
          iconClass="text-8xl"
        />
      ) : (
        <span className="flex aspect-[3/4] w-full items-center justify-center rounded-3xl border border-dashed border-pink-300/30 text-6xl">
          💖
        </span>
      )}
    </button>
  );

  const details = (
    <div className="mt-3 flex flex-col items-center gap-1 text-center">
      {active ? (
        <>
          <p className="font-display text-lg font-bold leading-tight text-ink-chalk">{active.name}</p>
          <p className="text-caption text-ink-mist">
            {active.title ? `${active.title} · ` : ""}{RARITY_LABELS[active.rarity]}
          </p>
          <p className="text-sm font-semibold text-accent-lime">{active.effect_label}</p>
          <MuseMoodLine album={data} />
          <p className="text-caption text-ink-mist-dim">
            {ownedCount > 1 ? "Нажми на портрет, чтобы сменить музу" : "Бонус даёт только активная муза"}
          </p>
        </>
      ) : (
        <p className="text-xs text-ink-mist">
          {ownedCount ? "Нажми на портрет и выбери музу" : "Муз пока нет — они выпадают из пака «Музы»"}
        </p>
      )}
      <MuseDateButton album={data} className="mt-2 w-full" />
      {active && data.daily.coins > 0 && (
        <button
          onClick={() => claim.mutate()}
          disabled={claim.isPending || data.daily.claimed_today}
          className="flex w-full items-center justify-center gap-1 rounded-full bg-floodlight py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {data.daily.claimed_today ? (
            <>Сегодня получено: {data.daily.claimed_coins} <IconCoin size={12} /></>
          ) : (
            <>Забрать {data.daily.coins} <IconCoin size={12} /></>
          )}
        </button>
      )}
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );

  return (
    <section className="rounded-2xl bg-gradient-to-b from-pink-500/10 to-bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="font-display text-base font-bold text-ink-chalk">Муза</p>
        <button onClick={() => navigate("/muses")} className="text-xs font-semibold text-pink-300">
          Альбом {data.owned_count}/{data.total_count} →
        </button>
      </div>
      {portrait}
      {details}
      <MusePickerSheet album={data} open={picking} onClose={() => setPicking(false)} />
    </section>
  );
}
