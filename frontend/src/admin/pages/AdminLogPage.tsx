import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchAdminLog, fetchServerErrors } from "@/admin/api";

type LogTab = "actions" | "errors";

/** «Журнал»: what the admins did, and what broke on the server (the 500s the
 * bot also reports in its daily digest). */
export default function AdminLogPage() {
  const [params, setParams] = useSearchParams();
  const tab: LogTab = params.get("tab") === "errors" ? "errors" : "actions";

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Журнал</h1>
      <div className="grid grid-cols-2 gap-1 rounded-xl bg-bg-surface p-1">
        {([["actions", "Действия админов"], ["errors", "Ошибки сервера"]] as [LogTab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setParams(id === "actions" ? {} : { tab: id }, { replace: true })}
            className={`min-w-0 truncate rounded-lg px-2 py-2 text-xs font-semibold ${tab === id ? "bg-accent text-bg-base" : "text-slate-400"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "actions" ? <ActionsLog /> : <ServerErrorsLog />}
    </div>
  );
}

function ActionsLog() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({ queryKey: ["admin-log", page], queryFn: () => fetchAdminLog(page) });

  return (
    <>
      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      {/* Phone: one card per action; wider screens: the table. */}
      <div className="flex flex-col gap-2 md:hidden">
        {data?.items.map((log) => (
          <div key={log.id} className="rounded-xl border border-white/5 bg-bg-surface px-3 py-2 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-x-3 text-slate-500">
              <span>{new Date(log.created_at).toLocaleString("ru-RU")}</span>
              <span>{log.admin_username ?? `#${log.admin_id}`}</span>
            </div>
            <p className="mt-1 break-words font-semibold text-slate-200">{log.action}</p>
            <p className="break-words text-slate-400">{log.entity_type} {log.entity_id ?? ""}</p>
          </div>
        ))}
      </div>

      <div className="hidden overflow-x-auto rounded-2xl border border-white/5 md:block">
        <table className="w-full text-sm">
          <thead className="bg-bg-surface text-left text-xs text-slate-400">
            <tr>
              <th className="px-3 py-2">Дата</th>
              <th className="px-3 py-2">Администратор</th>
              <th className="px-3 py-2">Действие</th>
              <th className="px-3 py-2">Сущность</th>
              <th className="px-3 py-2">IP</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((log) => (
              <tr key={log.id} className="border-t border-white/5 align-top">
                <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-400">{new Date(log.created_at).toLocaleString("ru-RU")}</td>
                <td className="px-3 py-2 text-xs">{log.admin_username ?? log.admin_id}</td>
                <td className="px-3 py-2 text-xs">{log.action}</td>
                <td className="px-3 py-2 text-xs">{log.entity_type} {log.entity_id ?? ""}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{log.ip_address ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center gap-2">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">←</button>
          <span className="text-sm text-slate-400">{page} / {data.pages}</span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">→</button>
        </div>
      )}
    </>
  );
}

function ServerErrorsLog() {
  const { data, isLoading } = useQuery({ queryKey: ["admin-server-errors"], queryFn: fetchServerErrors, refetchInterval: 60_000 });
  const [open, setOpen] = useState<number | null>(null);

  if (isLoading) return <p className="text-sm text-slate-400">Загрузка...</p>;
  if (!data?.groups.length) {
    return (
      <p className="rounded-xl bg-accent-lime/10 px-3 py-3 text-sm text-accent-lime">
        ✓ За неделю сервер не падал ни разу
      </p>
    );
  }
  return (
    <>
      <p className="text-xs text-slate-500">
        Ошибки за 7 дней, сгруппированные по запросу. Каждое утро в 10:00 бот присылает такую сводку за сутки.
      </p>
      <div className="flex flex-col gap-1.5">
        {data.groups.map((g) => (
          <div key={`${g.method} ${g.path}`} className="rounded-xl border border-red-500/20 bg-bg-surface px-3 py-2 text-xs">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <code className="min-w-0 break-all font-semibold text-slate-200">{g.method} {g.path}</code>
              <span className="shrink-0 font-bold text-red-400">{g.count}×</span>
            </div>
            <p className="mt-0.5 break-words text-slate-400">{g.last_error}</p>
            <p className="text-micro text-slate-600">последняя: {new Date(g.last_at).toLocaleString("ru-RU")}</p>
          </div>
        ))}
      </div>

      <p className="mt-2 font-display text-sm font-bold">Последние ошибки</p>
      <div className="flex flex-col gap-1.5">
        {data.recent.map((e) => (
          <div key={e.id} className="rounded-xl bg-bg-surface px-3 py-2 text-xs">
            <button onClick={() => setOpen(open === e.id ? null : e.id)} className="flex w-full flex-col gap-0.5 text-left">
              <span className="text-slate-500">{new Date(e.created_at).toLocaleString("ru-RU")} · {e.method}</span>
              <code className="break-all text-slate-300">{e.path}</code>
              <span className="break-words text-red-300">{e.error}</span>
              <span className="text-micro text-accent-cyan">{open === e.id ? "Скрыть подробности" : "Подробности (traceback)"}</span>
            </button>
            {open === e.id && (
              <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-black/40 p-2 text-micro text-slate-400">
                {e.traceback}
              </pre>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
