import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimMatchDay, fetchMatchDay, predictMatchDay, type MatchDayFixture } from "@/api/events";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { formatCountdown } from "@/lib/format";
import { hapticNotify, hapticSelection } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const KIND_LABEL: Record<string, string> = {
  exact: "Точный счёт!", diff: "Угадана разница", outcome: "Угадан исход", miss: "Мимо",
};

function kickoffLabel(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
}

/** «Матч дня»: guess the score of a real match before kickoff, claim coins after the result. */
export default function MatchDayPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [error, setError] = useState<string | null>(null);
  const { data, isLoading } = useQuery({ queryKey: ["match-day"], queryFn: fetchMatchDay, refetchInterval: 60_000 });
  const claim = useMutation({
    mutationFn: claimMatchDay,
    onSuccess: (res) => {
      updateBalance(res.new_balance);
      hapticNotify("success");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["match-day"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось забрать награду")),
  });
  if (isLoading || !data) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/play")} className="rounded-full bg-bg-surface p-2 active:scale-95" aria-label="Назад">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Матч дня</h1>
      </div>

      {!data.enabled && <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">«Матч дня» сейчас выключен.</p>}

      {data.current ? (
        <CurrentMatch fixture={data.current} onError={setError} />
      ) : (
        <p className="rounded-2xl bg-bg-surface px-4 py-6 text-center text-sm text-ink-mist">Следующий матч скоро появится</p>
      )}
      {error && <p className="text-xs text-red-400">{error}</p>}

      <section className="grid grid-cols-3 gap-1.5 text-center">
        {([["exact", "Точный счёт"], ["diff", "Разница голов"], ["outcome", "Исход"]] as const).map(([key, label]) => (
          <div key={key} className="rounded-xl bg-bg-surface px-2 py-2">
            <p className="flex items-center justify-center gap-1 font-mono text-sm font-bold text-accent-lime">
              <IconCoin size={12} /> {data.rewards[key]}
            </p>
            <p className="text-micro text-ink-mist">{label}</p>
          </div>
        ))}
      </section>

      {data.recent.length > 0 && (
        <section className="flex flex-col gap-1.5">
          <p className="font-display text-sm font-bold text-ink-chalk">Прошедшие матчи</p>
          {data.recent.map((f) => (
            <div key={f.id} className="flex items-center gap-2 rounded-xl bg-bg-surface px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink-chalk">
                  {f.home} <span className="font-mono">{f.home_score}:{f.away_score}</span> {f.away}
                </p>
                <p className="text-caption text-ink-mist">
                  {f.prediction ? `Твой прогноз ${f.prediction.home}:${f.prediction.away} · ${KIND_LABEL[f.reward_kind ?? "miss"]}` : "Без прогноза"}
                </p>
              </div>
              {f.prediction && (f.reward ?? 0) > 0 && (
                f.claimed ? (
                  <span className="flex items-center gap-1 text-caption text-ink-mist-dim">
                    <IconCoin size={11} /> +{f.reward}
                  </span>
                ) : (
                  <button
                    onClick={() => claim.mutate(f.id)}
                    disabled={claim.isPending}
                    className="flex items-center gap-1 rounded-lg bg-floodlight px-3 py-1.5 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-50"
                  >
                    <IconCoin size={11} /> {f.reward}
                  </button>
                )
              )}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

function CurrentMatch({ fixture: f, onError }: { fixture: MatchDayFixture; onError: (e: string | null) => void }) {
  const queryClient = useQueryClient();
  const [home, setHome] = useState(f.prediction?.home ?? 1);
  const [away, setAway] = useState(f.prediction?.away ?? 1);
  useEffect(() => {
    setHome(f.prediction?.home ?? 1);
    setAway(f.prediction?.away ?? 1);
  }, [f.id, f.prediction?.home, f.prediction?.away]);
  const save = useMutation({
    mutationFn: () => predictMatchDay(f.id, home, away),
    onSuccess: (view) => {
      queryClient.setQueryData(["match-day"], view);
      hapticNotify("success");
      onError(null);
    },
    onError: (err) => onError(formatGameError(err, "Не удалось сохранить прогноз")),
  });
  const secondsLeft = Math.max(0, Math.floor((new Date(f.kickoff_at).getTime() - Date.now()) / 1000));
  const changed = !f.prediction || f.prediction.home !== home || f.prediction.away !== away;
  const split = f.split;

  return (
    <section className="flex flex-col gap-4 rounded-2xl bg-gradient-to-br from-emerald-600/25 via-bg-surface to-bg-surface p-4">
      <div className="flex items-center justify-between text-caption text-ink-mist">
        <span>{f.league ?? "Футбол"}</span>
        <span>{f.open ? `Начало через ${formatCountdown(secondsLeft)}` : "Матч идёт — ждём результат"}</span>
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
        <Side name={f.home} value={home} onChange={setHome} disabled={!f.open} />
        <span className="font-display text-2xl font-bold text-ink-mist">:</span>
        <Side name={f.away} value={away} onChange={setAway} disabled={!f.open} />
      </div>
      <p className="text-center text-caption text-ink-mist-dim">{kickoffLabel(f.kickoff_at)}</p>
      {f.open ? (
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending || !changed}
          className="rounded-xl bg-floodlight py-3 font-display text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {f.prediction ? (changed ? "Изменить прогноз" : `Прогноз принят: ${f.prediction.home}:${f.prediction.away}`) : "Сделать прогноз"}
        </button>
      ) : (
        <p className="rounded-xl bg-black/20 py-2.5 text-center text-xs text-ink-mist">
          {f.prediction ? `Твой прогноз: ${f.prediction.home}:${f.prediction.away}` : "Прогнозы закрыты"}
        </p>
      )}
      {split && split.total > 0 && (
        <div className="flex flex-col gap-1">
          <div className="flex h-2 overflow-hidden rounded-full bg-black/30">
            <div className="bg-emerald-400" style={{ width: `${(split.home / split.total) * 100}%` }} />
            <div className="bg-slate-400" style={{ width: `${(split.draw / split.total) * 100}%` }} />
            <div className="bg-sky-400" style={{ width: `${(split.away / split.total) * 100}%` }} />
          </div>
          <p className="flex justify-between text-micro text-ink-mist">
            <span>П1 {Math.round((split.home / split.total) * 100)}%</span>
            <span>Ничья {Math.round((split.draw / split.total) * 100)}%</span>
            <span>П2 {Math.round((split.away / split.total) * 100)}%</span>
          </p>
          <p className="text-center text-micro text-ink-mist-dim">Прогнозов: {split.total}</p>
        </div>
      )}
    </section>
  );
}

function Side({ name, value, onChange, disabled }: { name: string; value: number; onChange: (v: number) => void; disabled: boolean }) {
  const step = (d: number) => {
    hapticSelection();
    onChange(Math.max(0, Math.min(20, value + d)));
  };
  return (
    <div className="flex min-w-0 flex-col items-center gap-2">
      <p className="w-full truncate text-center font-display text-sm font-bold text-ink-chalk">{name}</p>
      <div className="flex items-center gap-2">
        <button
          onClick={() => step(-1)}
          disabled={disabled || value === 0}
          aria-label={`Меньше голов: ${name}`}
          className="h-9 w-9 rounded-xl bg-black/30 text-lg font-bold text-ink-chalk active:scale-95 disabled:opacity-30"
        >
          −
        </button>
        <span className="w-8 text-center font-mono text-3xl font-bold text-ink-chalk">{value}</span>
        <button
          onClick={() => step(1)}
          disabled={disabled}
          aria-label={`Больше голов: ${name}`}
          className="h-9 w-9 rounded-xl bg-black/30 text-lg font-bold text-ink-chalk active:scale-95 disabled:opacity-30"
        >
          +
        </button>
      </div>
    </div>
  );
}
