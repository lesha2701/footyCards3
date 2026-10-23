import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { useAdminToastStore } from "@/admin/adminToastStore";
import { banAntifraudUsers, fetchAntifraudScan } from "@/admin/api";
import type { AntifraudAccount, AntifraudFarm, AntifraudHub } from "@/admin/types";
import { ApiRequestError } from "@/lib/api";

const fmt = (n: number) => n.toLocaleString("ru-RU");
const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("ru-RU") : "—");

/** «Антифрод»: coin-farming networks built from multi-accounts — hubs that
 *  take coins from many accounts, the accounts that fed them, and
 *  registration bursts — with bulk ban. Payers of Telegram Stars are
 *  flagged and never pre-selected. */
export default function AdminAntifraudPage() {
  const queryClient = useQueryClient();
  const toast = useAdminToastStore.getState().push;
  const [minSenders, setMinSenders] = useState(20);
  const [days, setDays] = useState(120);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [showAllFarms, setShowAllFarms] = useState(false);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["admin-antifraud", minSenders, days],
    queryFn: () => fetchAntifraudScan({ min_senders: minSenders, days }),
  });

  const banMutation = useMutation({
    mutationFn: (ids: number[]) => banAntifraudUsers(ids),
    onSuccess: (res) => {
      toast(`Забанено аккаунтов: ${res.banned}`, "success");
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["admin-antifraud"] });
    },
    onError: (err) => toast(err instanceof ApiRequestError ? err.message : "Не удалось забанить", "error"),
  });

  const openHubs = useMemo(() => (data?.hubs ?? []).filter((h) => !h.is_banned), [data]);
  const openFarms = useMemo(() => (data?.farms ?? []).filter((f) => !f.is_banned && !f.stars_paid), [data]);

  const ban = (ids: number[], what: string) => {
    if (!ids.length) return;
    if (confirm(`Забанить ${ids.length} ${what}? Они потеряют доступ к игре и исчезнут из рейтингов. Разбанить можно в «Пользователях».`)) {
      banMutation.mutate(ids);
    }
  };
  const toggle = (id: number) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const farmsShown = showAllFarms ? data?.farms ?? [] : (data?.farms ?? []).slice(0, 100);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="font-display text-2xl font-bold">Антифрод</h1>
        <p className="text-xs text-slate-500">
          Ищет сети мультиаккаунтов: «сборщиков», которые получают монеты от многих аккаунтов, и сами фарм-аккаунты,
          которые им отдавали монеты. Платившие Stars помечены и сами не выбираются.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-caption text-slate-400">
          Сборщик — отправителей от
          <input type="number" min={2} value={minSenders} onChange={(e) => setMinSenders(Math.max(2, Number(e.target.value) || 2))}
            className="w-28 rounded-lg bg-bg-surface px-3 py-2 text-sm text-slate-100 outline-none" />
        </label>
        <label className="flex flex-col gap-1 text-caption text-slate-400">
          За последние дней
          <input type="number" min={1} value={days} onChange={(e) => setDays(Math.max(1, Number(e.target.value) || 1))}
            className="w-28 rounded-lg bg-bg-surface px-3 py-2 text-sm text-slate-100 outline-none" />
        </label>
        <button onClick={() => refetch()} className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold text-slate-300">
          {isFetching ? "Ищу…" : "Обновить"}
        </button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Анализирую обмены…</p>}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Сборщиков" value={data.hubs_summary.total} hint={`не забанено: ${data.hubs_summary.not_banned}`} />
            <Stat label="Монет собрали" value={data.hubs_summary.coins} />
            <Stat label="Фарм-аккаунтов" value={data.farms_summary.total} hint={`не забанено: ${data.farms_summary.not_banned}`} />
            <Stat label="Монет отдали сборщикам" value={data.farms_summary.coins} />
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              disabled={!openHubs.length || banMutation.isPending}
              onClick={() => ban(openHubs.map((h) => h.id), "сборщиков")}
              className="rounded-lg bg-red-500 px-4 py-2 text-xs font-bold text-white disabled:opacity-40"
            >
              Забанить сборщиков ({openHubs.length})
            </button>
            <button
              disabled={!openFarms.length || banMutation.isPending}
              onClick={() => ban(openFarms.map((f) => f.id), "фарм-аккаунтов (без плативших Stars)")}
              className="rounded-lg bg-red-500/80 px-4 py-2 text-xs font-bold text-white disabled:opacity-40"
            >
              Забанить фарм-аккаунты ({openFarms.length})
            </button>
            {selected.size > 0 && (
              <button
                disabled={banMutation.isPending}
                onClick={() => ban([...selected], "выбранных аккаунтов")}
                className="rounded-lg bg-amber-400 px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
              >
                Забанить выбранных ({selected.size})
              </button>
            )}
          </div>

          <Section title={`Сборщики (${data.hubs.length})`} hint="Получили монеты от многих разных аккаунтов">
            <Table
              head={["", "Аккаунт", "Отправителей", "Получил", "Отдал", "Баланс", "Stars", "Рег."]}
              rows={data.hubs.map((h: AntifraudHub) => [
                <Pick key="p" account={h} selected={selected} toggle={toggle} />,
                <Who key="w" a={h} />, fmt(h.senders), fmt(h.coins_in), fmt(h.coins_out), fmt(h.balance),
                h.stars_paid ? `⭐ ${h.stars_paid}` : "—", day(h.registered),
              ])}
            />
          </Section>

          <Section
            title={`Фарм-аккаунты (${data.farms.length})`}
            hint="Отдавали монеты сборщикам. Жёлтые платили Stars — проверь их вручную."
          >
            <Table
              head={["", "Аккаунт", "Отдал", "Сборщиков", "Баланс", "Stars", "Рег.", "Был"]}
              rows={farmsShown.map((f: AntifraudFarm) => [
                <Pick key="p" account={f} selected={selected} toggle={toggle} />,
                <Who key="w" a={f} />, fmt(f.coins_sent), String(f.hubs), fmt(f.balance),
                f.stars_paid ? `⭐ ${f.stars_paid}` : "—", day(f.registered), day(f.last_seen),
              ])}
            />
            {(data.farms.length > 100) && (
              <button onClick={() => setShowAllFarms((v) => !v)} className="mt-2 text-xs font-semibold text-accent">
                {showAllFarms ? "Показать первые 100" : `Показать все ${data.farms.length}`}
              </button>
            )}
          </Section>

          <Section title="Всплески регистраций" hint="Часы, когда регистрировалось подозрительно много аккаунтов">
            <Table
              head={["Час", "Регистраций", "Из них фарм"]}
              rows={data.bursts.map((b) => [
                new Date(b.hour).toLocaleString("ru-RU"), fmt(b.registered),
                b.farm_accounts ? <b key="f" className="text-red-400">{fmt(b.farm_accounts)}</b> : "0",
              ])}
            />
          </Section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-xl bg-bg-surface p-3">
      <p className="font-display text-lg font-bold">{fmt(value)}</p>
      <p className="text-caption text-slate-400">{label}</p>
      {hint && <p className="text-micro text-slate-500">{hint}</p>}
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-3">
      <p className="font-display text-base font-bold">{title}</p>
      <p className="mb-2 text-xs text-slate-500">{hint}</p>
      {children}
    </section>
  );
}

function Who({ a }: { a: AntifraudAccount }) {
  return (
    <span className={a.is_banned ? "text-slate-500 line-through" : a.stars_paid ? "text-amber-300" : ""}>
      {a.username ? `@${a.username}` : "—"} <span className="text-micro text-slate-500">#{a.id}</span>
    </span>
  );
}

function Pick({ account, selected, toggle }: { account: AntifraudAccount; selected: Set<number>; toggle: (id: number) => void }) {
  if (account.is_banned) return <span className="text-micro text-slate-500">бан</span>;
  return (
    <input type="checkbox" checked={selected.has(account.id)} onChange={() => toggle(account.id)}
      aria-label={`Выбрать ${account.username ?? account.id}`} />
  );
}

function Table({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) {
  if (!rows.length) return <p className="text-xs text-slate-500">Ничего не найдено 👍</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-white/5">
      <table className="w-full min-w-[560px] text-xs">
        <thead className="bg-bg-base text-left text-slate-400">
          <tr>{head.map((h) => <th key={h} className="px-2 py-1.5 font-semibold">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((cells, i) => (
            <tr key={i} className="border-t border-white/5">
              {cells.map((c, j) => <td key={j} className="px-2 py-1.5">{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
