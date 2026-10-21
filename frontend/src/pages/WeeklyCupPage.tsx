import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimWeeklyCup, fetchWeeklyCup } from "@/api/events";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconClock, IconCoin, IconTrophy } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { formatCountdown } from "@/lib/format";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const MEDALS = ["🥇", "🥈", "🥉"];

/** «Неделя мини-игры»: one game a week, the sum of the best N games, prizes for the top places. */
export default function WeeklyCupPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [error, setError] = useState<string | null>(null);
  const { data, isLoading } = useQuery({ queryKey: ["weekly-cup"], queryFn: fetchWeeklyCup, refetchInterval: 60_000 });
  const claim = useMutation({
    mutationFn: claimWeeklyCup,
    onSuccess: (res) => {
      updateBalance(res.new_balance);
      hapticNotify("success");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["weekly-cup"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось забрать приз")),
  });
  if (isLoading || !data) return <ListSkeleton />;
  const secondsLeft = Math.max(0, Math.floor((new Date(data.ends_at).getTime() - Date.now()) / 1000));
  const meInTop = data.top.some((r) => r.is_me);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/play")} className="rounded-full bg-bg-surface p-2 active:scale-95" aria-label="Назад">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="min-w-0 truncate font-display text-xl font-bold text-ink-chalk">Неделя: {data.title}</h1>
        <span className="ml-auto flex shrink-0 items-center gap-1 text-caption text-ink-mist-dim">
          <IconClock size={12} /> {secondsLeft >= 86400 ? `${Math.floor(secondsLeft / 86400)} д ${Math.floor((secondsLeft % 86400) / 3600)} ч` : formatCountdown(secondsLeft)}
        </span>
      </div>

      {!data.enabled && <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">Недельный турнир сейчас выключен.</p>}

      {data.unclaimed_coins > 0 && (
        <div className="flex items-center gap-3 rounded-2xl bg-gradient-to-r from-amber-400/25 to-bg-surface p-3 ring-1 ring-amber-400/40">
          <span className="text-2xl">🏆</span>
          <span className="min-w-0 flex-1">
            <span className="block font-display text-sm font-bold text-ink-chalk">
              {data.last_week ? `Прошлая неделя: ${data.last_week.place} место` : "Твой приз ждёт"}
            </span>
            <span className="flex items-center gap-1 text-caption text-amber-200">
              <IconCoin size={11} /> {data.unclaimed_coins.toLocaleString("ru-RU")}
            </span>
          </span>
          <button
            onClick={() => claim.mutate()}
            disabled={claim.isPending}
            className="rounded-xl bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-50"
          >
            Забрать
          </button>
        </div>
      )}
      {error && <p className="text-xs text-red-400">{error}</p>}

      <section className="flex flex-col gap-3 rounded-2xl bg-gradient-to-br from-orange-500/20 via-bg-surface to-bg-surface p-4">
        <div className="flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-orange-500 text-white">
            <IconTrophy size={22} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-base font-bold text-ink-chalk">{data.me ? `${data.me.place} место` : "Ты ещё не в таблице"}</p>
            <p className="text-caption text-ink-mist">
              {data.me
                ? `${data.me.points} очк. · засчитано игр ${data.me.games} из ${data.best_of}`
                : `Сыграй — в зачёт идут ${data.best_of} лучших игр недели`}
            </p>
          </div>
        </div>
        <p className="text-caption text-ink-mist-dim">
          Очки: {data.unit}. Участников: {data.participants}. Итоги — в ночь на понедельник.
        </p>
        <button
          onClick={() => navigate(data.path)}
          className="rounded-xl bg-floodlight py-3 font-display text-sm font-bold text-bg-base active:scale-95"
        >
          Играть в «{data.title}»
        </button>
      </section>

      {data.prizes.length > 0 && (
        <section className="flex flex-col gap-1.5">
          <p className="font-display text-sm font-bold text-ink-chalk">Призы</p>
          <div className="flex flex-wrap gap-1.5">
            {data.prizes.map((coins, i) => (
              <span key={i} className="flex items-center gap-1 rounded-full bg-bg-surface px-2.5 py-1 text-caption text-ink-chalk">
                {MEDALS[i] ?? `${i + 1}.`} <IconCoin size={11} className="text-accent-lime" /> {coins.toLocaleString("ru-RU")}
              </span>
            ))}
          </div>
        </section>
      )}

      <section className="flex flex-col gap-1.5">
        <p className="font-display text-sm font-bold text-ink-chalk">Таблица</p>
        {data.top.length === 0 && (
          <p className="rounded-xl bg-bg-surface px-3 py-4 text-center text-xs text-ink-mist">Пока никто не сыграл — будь первым</p>
        )}
        {data.top.map((r) => (
          <div
            key={r.user_id}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs ${r.is_me ? "bg-accent-lime/15 ring-1 ring-accent-lime/40" : "bg-bg-surface"}`}
          >
            <span className="w-6 text-center font-mono font-bold text-ink-mist">{MEDALS[r.place - 1] ?? r.place}</span>
            <span className="min-w-0 flex-1 truncate text-ink-chalk">{r.name}</span>
            <span className="text-ink-mist-dim">{r.games} игр</span>
            <span className="w-14 text-right font-mono font-bold text-ink-chalk">{r.points}</span>
          </div>
        ))}
        {data.me && !meInTop && (
          <div className="flex items-center gap-2 rounded-lg bg-accent-lime/15 px-3 py-2 text-xs ring-1 ring-accent-lime/40">
            <span className="w-6 text-center font-mono font-bold text-ink-mist">{data.me.place}</span>
            <span className="min-w-0 flex-1 truncate text-ink-chalk">Ты</span>
            <span className="text-ink-mist-dim">{data.me.games} игр</span>
            <span className="w-14 text-right font-mono font-bold text-ink-chalk">{data.me.points}</span>
          </div>
        )}
      </section>
    </div>
  );
}
