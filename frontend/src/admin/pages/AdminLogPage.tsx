import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAdminLog } from "@/admin/api";

export default function AdminLogPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({ queryKey: ["admin-log", page], queryFn: () => fetchAdminLog(page) });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Журнал администратора</h1>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="overflow-x-auto rounded-2xl border border-white/5">
        <table className="w-full min-w-[720px] text-sm">
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
                <td className="px-3 py-2 text-xs text-slate-400">{new Date(log.created_at).toLocaleString("ru-RU")}</td>
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
        <div className="flex gap-2">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">←</button>
          <span className="text-sm text-slate-400">{page} / {data.pages}</span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">→</button>
        </div>
      )}
    </div>
  );
}
