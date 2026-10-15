import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAnalyticsReport, type AnalyticsReport, type DayCount } from "@/admin/api";

const PERIODS = [7, 30, 90];

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 1000) / 10}%`);

/** Russian plural: forms for 1 / 2–4 / 5+ (игра / игры / игр). */
function plural(n: number, [one, few, many]: [string, string, string]): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}
const games = (n: number) => `${n} ${plural(n, ["игра", "игры", "игр"])}`;
const players = (n: number) => `${n} ${plural(n, ["игрок", "игрока", "игроков"])}`;
const ofPlayers = (n: number) => `из ${n} ${plural(n, ["игрока", "игроков", "игроков"])}`;

export default function AdminAnalyticsPage() {
  const [days, setDays] = useState(30);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-analytics", days],
    queryFn: () => fetchAnalyticsReport(days),
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-2xl font-bold">Аналитика</h1>
        <div className="flex gap-1 rounded-xl bg-white/5 p-1">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setDays(p)}
              className={`rounded-lg px-3 py-1.5 text-sm ${days === p ? "bg-accent text-bg-base" : "text-slate-300"}`}
            >
              {p} дней
            </button>
          ))}
        </div>
      </div>

      {isError ? (
        <p className="text-rose-400">Не удалось загрузить аналитику</p>
      ) : isLoading || !data ? (
        <p className="text-slate-400">Загрузка...</p>
      ) : (
        <>
          <ActivitySection data={data} />
          <RetentionSection data={data} />
          <FunnelSection data={data} />
          <ModesSection data={data} />
          <MonetizationSection data={data} />
          <p className="text-xs text-slate-500">
            Дни считаются по московскому времени. Активность до запуска аналитики восстановлена по действиям игроков
            (входы, покупки, игры), поэтому для прошлых дней это нижняя оценка.
          </p>
        </>
      )}
    </div>
  );
}

function ActivitySection({ data }: { data: AnalyticsReport }) {
  const a = data.activity;
  return (
    <section className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Stat label="Активны сегодня (DAU)" value={a.dau_today} />
        <Stat label="За 7 дней (WAU)" value={a.wau} />
        <Stat label="За 30 дней (MAU)" value={a.mau} />
        <Stat label="DAU / MAU" value={pct(a.stickiness)} hint="как часто возвращаются активные" />
        <Stat label={`Активны за ${data.days} дн.`} value={a.active_in_period} />
        <Stat label="Всего игроков" value={a.total_users} />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <BarChart title="Активные игроки по дням" points={a.dau_by_day} />
        <BarChart title="Регистрации по дням" points={a.registrations_by_day} />
      </div>
    </section>
  );
}

function RetentionSection({ data }: { data: AnalyticsReport }) {
  const { summary, cohorts } = data.retention;
  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="font-display text-base font-bold">Удержание</p>
      <p className="mb-3 text-xs text-slate-400">
        Доля новичков, которые зашли в игру ровно через 1, 7 и 30 дней после регистрации.
      </p>
      <div className="mb-4 grid grid-cols-3 gap-3">
        <Stat label="D1" value={pct(summary.d1)} hint={ofPlayers(summary.d1_eligible)} />
        <Stat label="D7" value={pct(summary.d7)} hint={ofPlayers(summary.d7_eligible)} />
        <Stat label="D30" value={pct(summary.d30)} hint={ofPlayers(summary.d30_eligible)} />
      </div>
      {cohorts.length === 0 ? (
        <p className="text-sm text-slate-400">Нет регистраций за период</p>
      ) : (
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-bg-surface text-xs text-slate-400">
              <tr>
                <th className="py-1 text-left font-normal">Регистрация</th>
                <th className="py-1 text-right font-normal">Игроков</th>
                <th className="py-1 text-right font-normal">D1</th>
                <th className="py-1 text-right font-normal">D7</th>
                <th className="py-1 text-right font-normal">D30</th>
              </tr>
            </thead>
            <tbody>
              {[...cohorts].reverse().map((c) => (
                <tr key={c.date} className="border-t border-white/5">
                  <td className="py-1 font-mono text-xs text-slate-300">{c.date}</td>
                  <td className="py-1 text-right font-mono text-xs">{c.size}</td>
                  {[c.d1, c.d7, c.d30].map((v, i) => (
                    <td key={i} className="py-1 text-right">
                      <RetentionCell value={v} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RetentionCell({ value }: { value: number | null }) {
  if (value == null) return <span className="text-xs text-slate-600">—</span>;
  // Opacity encodes the share so strong cohorts stand out at a glance.
  return (
    <span
      className="inline-block min-w-[3.25rem] rounded px-1.5 py-0.5 text-center font-mono text-xs text-slate-100"
      style={{ backgroundColor: `rgba(62, 209, 126, ${0.12 + value * 0.7})` }}
    >
      {pct(value)}
    </span>
  );
}

function FunnelSection({ data }: { data: AnalyticsReport }) {
  const { cohort_size, steps } = data.funnel;
  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="font-display text-base font-bold">Воронка новичков</p>
      <p className="mb-3 text-xs text-slate-400">
        Игроки, зарегистрированные за {data.days} дн. ({cohort_size}), и сколько из них дошли до каждого шага.
      </p>
      <div className="flex flex-col gap-2">
        {steps.map((s) => (
          <div key={s.key} className="text-sm">
            <div className="flex justify-between">
              <span className="text-slate-300">{s.label}</span>
              <span className="font-mono text-xs text-slate-400">
                {s.users} · {pct(s.share)}
              </span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/5">
              <div className="h-full rounded-full bg-accent/70" style={{ width: `${(s.share ?? 0) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ModesSection({ data }: { data: AnalyticsReport }) {
  const maxPlayers = Math.max(1, ...data.modes.map((m) => m.players));
  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="font-display text-base font-bold">Популярность режимов</p>
      <p className="mb-3 text-xs text-slate-400">
        Уникальные игроки и сыгранные игры за {data.days} дн. Боты игроками не считаются.
      </p>
      <div className="flex flex-col gap-2">
        {data.modes.map((m) => (
          <div key={m.key} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 text-sm">
            <span className="truncate text-slate-300">{m.label}</span>
            <span className="font-mono text-xs text-slate-400">
              {players(m.players)} · {games(m.games)}
            </span>
            <div className="col-span-2 h-1.5 overflow-hidden rounded-full bg-white/5">
              <div className="h-full rounded-full bg-accent/70" style={{ width: `${(m.players / maxPlayers) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function MonetizationSection({ data }: { data: AnalyticsReport }) {
  const m = data.monetization;
  const maxProduct = Math.max(1, ...m.by_product.map((p) => p.stars));
  return (
    <section className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Stars за период" value={`${m.stars_total} ⭐`} />
        <Stat label="Покупок" value={m.purchases} />
        <Stat label="Платящих игроков" value={m.payers} />
        <Stat label="Доля платящих" value={pct(m.paying_share)} hint="от активных за период" />
        <Stat label="ARPPU" value={m.arppu == null ? "—" : `${m.arppu} ⭐`} hint="Stars на платящего" />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <BarChart title="Stars по дням" points={m.stars_by_day} />
        <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
          <p className="mb-3 font-display text-sm font-bold">Stars по товарам</p>
          {m.by_product.length === 0 ? (
            <p className="text-sm text-slate-400">Покупок за период не было</p>
          ) : (
            <div className="flex flex-col gap-2">
              {m.by_product.map((p) => (
                <div key={p.product} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 text-sm">
                  <span className="truncate text-slate-300">
                    {p.product} <span className="text-xs text-slate-500">· {p.purchases}</span>
                  </span>
                  <span className="font-mono text-xs">{p.stars} ⭐</span>
                  <div className="col-span-2 h-1.5 overflow-hidden rounded-full bg-white/5">
                    <div className="h-full rounded-full bg-amber-300/70" style={{ width: `${(p.stars / maxProduct) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold text-slate-100">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p>}
    </div>
  );
}

/** Same bar style as the dashboard charts; the server already returns every
 * day of the window (gaps filled with 0), so no client-side filling. */
function BarChart({ title, points }: { title: string; points: DayCount[] }) {
  const max = Math.max(1, ...points.map((p) => p.count));
  const total = points.reduce((sum, p) => sum + p.count, 0);
  const labelEvery = Math.max(1, Math.ceil(points.length / 10));
  return (
    <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <p className="font-display text-sm font-bold">{title}</p>
        <span className="text-xs text-slate-400">всего {total}</span>
      </div>
      <div className="flex h-32 items-end gap-px pt-2">
        {points.map((p) => (
          <div key={p.date} className="flex h-full flex-1 flex-col justify-end" title={`${p.date}: ${p.count}`}>
            <div
              className={`w-full rounded-t ${p.count > 0 ? "bg-accent/70" : "bg-white/5"}`}
              style={{ height: p.count > 0 ? `${Math.max(4, (p.count / max) * 100)}%` : "2px" }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-px">
        {points.map((p, i) => (
          <span key={p.date} className="flex-1 text-center text-[10px] text-slate-500">
            {(points.length - 1 - i) % labelEvery === 0 ? p.date.slice(8, 10) : ""}
          </span>
        ))}
      </div>
    </div>
  );
}
