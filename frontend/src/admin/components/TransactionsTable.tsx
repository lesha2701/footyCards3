import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAdminTransactions, type AdminTransactionFilters } from "@/admin/api";
import { TX_TYPE_LABELS } from "@/lib/transactionLabels";


/** Every coin transaction (optionally of one user), newest first, by pages,
 * with filters and the totals of the filtered set. Used by «Транзакции»
 * and the user card's «Транзакции» tab. */
export default function TransactionsTable({ userId, pageSize = 50 }: { userId?: number; pageSize?: number }) {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<AdminTransactionFilters>({});
  const set = (patch: Partial<AdminTransactionFilters>) => {
    setPage(1);
    setFilters((f) => ({ ...f, ...patch }));
  };
  const { data, isFetching } = useQuery({
    queryKey: ["admin-transactions", userId ?? null, filters, page],
    queryFn: () => fetchAdminTransactions({ ...filters, user_id: userId, page, page_size: pageSize }),
    placeholderData: keepPreviousData,
  });

  // The page switcher sits both above and below the table, so it is reachable
  // without scrolling through a whole page of rows.
  const pager = data && data.pages > 1 ? (
        <div className="flex flex-wrap items-center justify-center gap-2 text-xs">
          <button disabled={page <= 1} onClick={() => setPage(1)} className="rounded-lg bg-white/5 px-3 py-1.5 disabled:opacity-30">«</button>
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-white/5 px-3 py-1.5 disabled:opacity-30">Назад</button>
          <span className="text-slate-400">
            Стр.{" "}
            <input
              type="number"
              min={1}
              max={data.pages}
              value={page}
              onChange={(e) => setPage(Math.max(1, Math.min(data.pages, Number(e.target.value) || 1)))}
              className="w-14 rounded bg-bg-surface px-1 py-0.5 text-center"
              aria-label="Номер страницы"
            />{" "}
            из {data.pages}
          </span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-white/5 px-3 py-1.5 disabled:opacity-30">Вперёд</button>
          <button disabled={page >= data.pages} onClick={() => setPage(data.pages)} className="rounded-lg bg-white/5 px-3 py-1.5 disabled:opacity-30">»</button>
        </div>
  ) : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-5">
        {userId == null && (
          <input
            placeholder="Игрок: имя, @username, Telegram ID"
            value={filters.search ?? ""}
            onChange={(e) => set({ search: e.target.value || undefined })}
            className="col-span-2 rounded-lg bg-bg-surface px-3 py-2 outline-none"
          />
        )}
        <select
          value={filters.type ?? ""}
          onChange={(e) => set({ type: e.target.value || undefined })}
          className="rounded-lg bg-bg-surface px-2 py-2"
          aria-label="Тип"
        >
          <option value="">Все типы</option>
          {Object.entries(TX_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <select
          value={filters.direction ?? ""}
          onChange={(e) => set({ direction: (e.target.value || undefined) as AdminTransactionFilters["direction"] })}
          className="rounded-lg bg-bg-surface px-2 py-2"
          aria-label="Направление"
        >
          <option value="">Приход и расход</option>
          <option value="income">Только приход</option>
          <option value="spend">Только расход</option>
        </select>
        <input
          type="date"
          value={filters.date_from?.slice(0, 10) ?? ""}
          onChange={(e) => set({ date_from: e.target.value ? `${e.target.value}T00:00:00` : undefined })}
          className="rounded-lg bg-bg-surface px-2 py-2"
          aria-label="С даты"
        />
        <input
          type="date"
          value={filters.date_to?.slice(0, 10) ?? ""}
          onChange={(e) => set({ date_to: e.target.value ? `${e.target.value}T23:59:59` : undefined })}
          className="rounded-lg bg-bg-surface px-2 py-2"
          aria-label="По дату"
        />
      </div>

      {data && (
        <p className="text-xs text-slate-400">
          Найдено: <b className="text-slate-100">{data.total.toLocaleString("ru-RU")}</b> · приход{" "}
          <b className="text-emerald-400">+{data.income.toLocaleString("ru-RU")}</b> · расход{" "}
          <b className="text-red-400">−{data.spent.toLocaleString("ru-RU")}</b>
        </p>
      )}

      {pager}

      <div className={`overflow-x-auto rounded-xl border border-white/5 ${isFetching ? "opacity-60" : ""}`}>
        <table className="w-full text-left text-xs">
          <thead className="bg-bg-surface text-slate-400">
            <tr>
              <th className="px-3 py-2">Дата</th>
              {userId == null && <th className="px-3 py-2">Игрок</th>}
              <th className="px-3 py-2">Тип</th>
              <th className="px-3 py-2">Описание</th>
              <th className="px-3 py-2 text-right">Сумма</th>
              <th className="px-3 py-2 text-right">Баланс после</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {data?.items.map((t) => (
              <tr key={t.id}>
                <td className="whitespace-nowrap px-3 py-2 text-slate-400">{new Date(t.created_at).toLocaleString("ru-RU")}</td>
                {userId == null && (
                  <td className="px-3 py-2">
                    {t.user_name}
                    <span className="block text-micro text-slate-500">
                      #{t.user_id}{t.username ? ` · @${t.username}` : ""}{t.telegram_id ? ` · ${t.telegram_id}` : ""}
                    </span>
                  </td>
                )}
                <td className="px-3 py-2">{TX_TYPE_LABELS[t.type] ?? t.type}</td>
                <td className="px-3 py-2 text-slate-300">{t.description}</td>
                <td className={`whitespace-nowrap px-3 py-2 text-right font-mono ${t.amount >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {t.amount > 0 ? "+" : ""}{t.amount}
                </td>
                <td className="px-3 py-2 text-right font-mono text-slate-400">{t.balance_after}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !data.items.length && <p className="px-3 py-4 text-sm text-slate-500">Нет транзакций</p>}
      </div>

      {pager}
    </div>
  );
}
