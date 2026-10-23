import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { AdminFixture } from "@/api/events";
import { api } from "@/lib/api";
import { formatGameError } from "@/lib/errors";

async function fetchFixtures(): Promise<AdminFixture[]> {
  const { data } = await api.get<AdminFixture[]>("/admin/match-day");
  return data;
}

interface AutoStatus {
  enabled: boolean;
  has_key: boolean;
  status: string | null;
}

async function fetchAuto(): Promise<AutoStatus> {
  const { data } = await api.get<AutoStatus>("/admin/match-day/auto");
  return data;
}

/** A local `datetime-local` value → an ISO instant. */
function toIso(local: string): string {
  return new Date(local).toISOString();
}

/** «Матч дня»: real matches players guess. Enter the score after the final whistle — rewards follow. */
export default function AdminMatchDayPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ home: "", away: "", league: "", kickoff: "" });
  const [error, setError] = useState<string | null>(null);
  const { data: fixtures = [] } = useQuery({ queryKey: ["admin", "match-day"], queryFn: fetchFixtures });
  const { data: auto } = useQuery({ queryKey: ["admin", "match-day", "auto"], queryFn: fetchAuto });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin", "match-day"] });
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));

  const create = useMutation({
    mutationFn: () => api.post("/admin/match-day", {
      home: form.home, away: form.away, league: form.league || null, kickoff_at: toIso(form.kickoff),
    }),
    onSuccess: () => {
      setForm({ home: "", away: "", league: "", kickoff: "" });
      setError(null);
      refresh();
    },
    onError,
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api.patch(`/admin/match-day/${id}`, body),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError,
  });
  const sync = useMutation({
    mutationFn: () => api.post("/admin/match-day/sync"),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError,
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/admin/match-day/${id}`),
    onSuccess: refresh,
    onError,
  });

  const input = "rounded-lg bg-bg-surface px-3 py-2 text-sm outline-none";
  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold">Матч дня</h1>
      <p className="text-xs text-slate-400">
        Добавь реальный матч — игроки угадывают счёт до начала. После финального свистка впиши счёт: игроки получат
        уведомление и заберут монеты (точный счёт / разница голов / исход — суммы в «Игры» → «Матч дня»). Результат можно
        исправить, пока никто не забрал награду. На экране игрока — ближайший не начавшийся матч.
      </p>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <div className="flex flex-wrap items-center gap-3">
          <p className="font-display text-base font-bold">Автоматически (API-Football)</p>
          <span className={`rounded-full px-2 py-0.5 text-xs ${auto?.enabled ? "bg-accent-green/20 text-accent-green" : "bg-white/10 text-slate-400"}`}>
            {auto?.enabled ? "включено" : "выключено"}
          </span>
          <button
            onClick={() => sync.mutate()}
            disabled={sync.isPending || !auto?.has_key}
            className="ml-auto rounded-xl bg-white/10 px-3 py-1.5 text-xs font-semibold disabled:opacity-40"
          >
            {sync.isPending ? "Обновляю…" : "Обновить сейчас"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          {auto && !auto.has_key
            ? "На сервере нет ключа API_FOOTBALL_KEY — добавь его в .env и пересобери backend."
            : auto?.status ?? "Ещё не запускалось."}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Включается в «Игры» → «Матч дня» (там же лиги по приоритету). Бот проверяет раз в 30 минут: берёт лучший матч
          сегодня/завтра и сам записывает счёт основного времени. Ручные матчи он не трогает.
        </p>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Новый матч</p>
        <div className="grid grid-cols-2 gap-3">
          <input className={input} placeholder="Хозяева" value={form.home} onChange={(e) => setForm({ ...form, home: e.target.value })} />
          <input className={input} placeholder="Гости" value={form.away} onChange={(e) => setForm({ ...form, away: e.target.value })} />
          <input className={input} placeholder="Турнир (необязательно)" value={form.league} onChange={(e) => setForm({ ...form, league: e.target.value })} />
          <input className={input} type="datetime-local" value={form.kickoff} onChange={(e) => setForm({ ...form, kickoff: e.target.value })} />
        </div>
        <button
          onClick={() => create.mutate()}
          disabled={!form.home.trim() || !form.away.trim() || !form.kickoff || create.isPending}
          className="mt-3 rounded-xl bg-floodlight px-4 py-2 text-sm font-bold text-bg-base disabled:opacity-40"
        >
          Добавить
        </button>
      </section>
      {error && <p className="text-sm text-red-400">{error}</p>}

      <section className="flex flex-col gap-2">
        {fixtures.map((f) => (
          <FixtureRow
            key={f.id}
            fixture={f}
            onScore={(home_score, away_score) => update.mutate({ id: f.id, body: { home_score, away_score } })}
            onClear={() => update.mutate({ id: f.id, body: { clear_result: true } })}
            onDelete={() => {
              if (window.confirm(`Удалить «${f.home} — ${f.away}»?`)) remove.mutate(f.id);
            }}
          />
        ))}
        {!fixtures.length && <p className="text-sm text-slate-400">Матчей пока нет</p>}
      </section>
    </div>
  );
}

function FixtureRow({
  fixture: f, onScore, onClear, onDelete,
}: {
  fixture: AdminFixture;
  onScore: (home: number, away: number) => void;
  onClear: () => void;
  onDelete: () => void;
}) {
  const [home, setHome] = useState(f.home_score ?? 0);
  const [away, setAway] = useState(f.away_score ?? 0);
  const hasResult = f.home_score !== null && f.away_score !== null;
  const started = new Date(f.kickoff_at).getTime() <= Date.now();
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/5 bg-bg-surface p-3 text-sm">
      <div className="min-w-[200px] flex-1">
        <p className="font-semibold">
          {f.auto && <span className="mr-1 rounded bg-sky-500/20 px-1.5 py-0.5 text-xs text-sky-300">авто</span>}
          {f.home} — {f.away} {hasResult && <span className="font-mono text-accent-lime">{f.home_score}:{f.away_score}</span>}
        </p>
        <p className="text-xs text-slate-400">
          {f.league ? `${f.league} · ` : ""}
          {new Date(f.kickoff_at).toLocaleString("ru-RU")} · прогнозов {f.predictions} · забрали {f.claimed}
        </p>
      </div>
      {started && f.claimed === 0 && (
        <div className="flex items-center gap-1">
          <input type="number" min={0} max={20} value={home} onChange={(e) => setHome(Number(e.target.value))} className="w-14 rounded-lg bg-black/30 px-2 py-1" />
          <span>:</span>
          <input type="number" min={0} max={20} value={away} onChange={(e) => setAway(Number(e.target.value))} className="w-14 rounded-lg bg-black/30 px-2 py-1" />
          <button onClick={() => onScore(home, away)} className="rounded-lg bg-floodlight px-3 py-1 text-xs font-bold text-bg-base">
            {hasResult ? "Исправить" : "Записать счёт"}
          </button>
          {hasResult && (
            <button onClick={onClear} className="rounded-lg bg-white/10 px-3 py-1 text-xs">Сбросить</button>
          )}
        </div>
      )}
      {!started && <span className="text-xs text-slate-400">Счёт — после начала матча</span>}
      {f.claimed === 0 && (
        <button onClick={onDelete} className="rounded-lg bg-red-500/20 px-3 py-1 text-xs text-red-300">Удалить</button>
      )}
    </div>
  );
}
