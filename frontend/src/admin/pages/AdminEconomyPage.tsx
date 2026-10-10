import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchEconomyReport } from "@/admin/api";
import { TX_TYPE_LABELS } from "@/lib/transactionLabels";

const PERIODS = [1, 7, 30];

export default function AdminEconomyPage() {
  const [days, setDays] = useState(7);
  const { data, isLoading } = useQuery({ queryKey: ["admin-economy", days], queryFn: () => fetchEconomyReport(days) });

  const maxDay = Math.max(1, ...(data?.daily ?? []).flatMap((d) => [d.inflow, d.outflow]));
  const maxType = Math.max(1, ...(data?.by_type ?? []).flatMap((r) => [r.inflow, r.outflow]));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-2xl font-bold">Экономика</h1>
        <div className="flex gap-1 rounded-xl bg-white/5 p-1">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setDays(p)}
              className={`rounded-lg px-3 py-1.5 text-sm ${days === p ? "bg-accent text-bg-base" : "text-slate-300"}`}
            >
              {p === 1 ? "Сутки" : `${p} дней`}
            </button>
          ))}
        </div>
      </div>

      {isLoading || !data ? (
        <p className="text-slate-400">Загрузка...</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Выдано монет" value={data.total_inflow} tone="text-emerald-400" />
            <Stat label="Списано монет" value={data.total_outflow} tone="text-rose-400" />
            <Stat
              label="Баланс потока"
              value={(data.net > 0 ? "+" : "") + data.net}
              tone={data.net > 0 ? "text-amber-300" : "text-emerald-400"}
              hint={data.net > 0 ? "монет становится больше — инфляция" : "монеты выводятся из игры"}
            />
            <Stat label="Паков открыто" value={data.packs_opened} />
            <Stat label="Жетонов навыков выдано" value={data.skill_tokens_granted} />
            <Stat label="Жетонов потрачено" value={data.skill_tokens_spent} />
            <Stat label="Монет на навыки" value={data.skill_coins_spent} />
          </div>

          <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
            <p className="mb-1 font-display text-base font-bold">По дням</p>
            <p className="mb-3 text-xs text-slate-400">Зелёный — выдано, красный — списано.</p>
            {data.daily.length === 0 ? (
              <p className="text-sm text-slate-400">Нет транзакций за период</p>
            ) : (
              <div className="flex h-40 items-end gap-1 overflow-x-auto">
                {data.daily.map((d) => (
                  <div
                    key={d.date}
                    className="flex min-w-[18px] flex-1 flex-col items-center gap-1"
                    title={`${d.date}: +${d.inflow} / −${d.outflow}`}
                  >
                    <div className="flex h-32 w-full items-end gap-px">
                      <div className="flex-1 rounded-t bg-emerald-400/70" style={{ height: `${(d.inflow / maxDay) * 100}%` }} />
                      <div className="flex-1 rounded-t bg-rose-400/70" style={{ height: `${(d.outflow / maxDay) * 100}%` }} />
                    </div>
                    <span className="text-[9px] text-slate-500">{d.date.slice(5)}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
            <p className="mb-3 font-display text-base font-bold">Источники и стоки</p>
            <div className="flex flex-col gap-2">
              {data.by_type.map((r) => (
                <div key={r.type} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 text-sm">
                  <span className="truncate text-slate-300">
                    {TX_TYPE_LABELS[r.type] ?? r.type} <span className="text-xs text-slate-500">· {r.count}</span>
                  </span>
                  <span className="text-right font-mono text-xs">
                    {r.inflow > 0 && <span className="text-emerald-400">+{r.inflow}</span>}
                    {r.inflow > 0 && r.outflow > 0 && " / "}
                    {r.outflow > 0 && <span className="text-rose-400">−{r.outflow}</span>}
                  </span>
                  <div className="col-span-2 flex h-1.5 gap-px overflow-hidden rounded-full bg-white/5">
                    <div className="bg-emerald-400/70" style={{ width: `${(r.inflow / maxType) * 50}%` }} />
                    <div className="bg-rose-400/70" style={{ width: `${(r.outflow / maxType) * 50}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, tone, hint }: { label: string; value: string | number; tone?: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className={`font-display text-2xl font-bold ${tone ?? ""}`}>{value}</p>
      <p className="mt-1 text-xs text-slate-400">{label}</p>
      {hint && <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p>}
    </div>
  );
}
