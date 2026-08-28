import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAdminTournamentDetail, fetchAdminTournamentStats, fetchAdminTournaments } from "@/admin/api";

const STATUS_TABS = [
  { value: undefined, label: "Все" },
  { value: "active" as const, label: "Идут" },
  { value: "completed" as const, label: "Завершены" },
];

export default function AdminTournamentsPage() {
  const [status, setStatus] = useState<"active" | "completed" | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data: stats } = useQuery({ queryKey: ["admin-tournament-stats"], queryFn: fetchAdminTournamentStats });
  const { data, isLoading } = useQuery({
    queryKey: ["admin-tournaments", status, page],
    queryFn: () => fetchAdminTournaments(status, page),
  });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Турниры</h1>

      <div className="flex gap-3">
        <div className="rounded-xl bg-bg-surface px-4 py-2.5">
          <p className="text-[11px] text-slate-400">Идут сейчас</p>
          <p className="font-mono text-lg font-bold text-emerald-400">{stats?.active_count ?? "—"}</p>
        </div>
        <div className="rounded-xl bg-bg-surface px-4 py-2.5">
          <p className="text-[11px] text-slate-400">Завершено всего</p>
          <p className="font-mono text-lg font-bold text-slate-100">{stats?.completed_count ?? "—"}</p>
        </div>
      </div>

      <div className="flex gap-2">
        {STATUS_TABS.map((t) => (
          <button
            key={t.label}
            onClick={() => { setStatus(t.value); setPage(1); }}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${status === t.value ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-2xl border border-white/5">
        <table className="w-full min-w-[560px] text-sm">
          <thead className="bg-bg-surface text-left text-xs text-slate-400">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2">Тур</th>
              <th className="px-3 py-2">Клубов</th>
              <th className="px-3 py-2">Создан</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((t) => (
              <tr key={t.id} className="border-t border-white/5">
                <td className="px-3 py-2">#{t.id}</td>
                <td className="px-3 py-2">
                  {t.status === "active" ? (
                    <span className="flex items-center gap-1.5 text-emerald-400">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                      Идёт
                    </span>
                  ) : (
                    <span className="text-slate-400">Завершён</span>
                  )}
                </td>
                <td className="px-3 py-2 text-slate-300">{t.rounds_simulated}/14</td>
                <td className="px-3 py-2 text-slate-300">{t.club_count}</td>
                <td className="px-3 py-2 text-slate-400">{new Date(t.created_at).toLocaleString("ru-RU")}</td>
                <td className="px-3 py-2">
                  <button onClick={() => setSelectedId(t.id)} className="rounded-lg bg-accent px-3 py-1 text-xs font-bold text-bg-base">
                    Открыть
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <p className="p-4 text-sm text-slate-400">Загрузка...</p>}
        {data && data.items.length === 0 && <p className="p-4 text-sm text-slate-500">Турниров нет</p>}
      </div>

      {data && data.pages > 1 && (
        <div className="flex gap-2">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">←</button>
          <span className="text-sm text-slate-400">{page} / {data.pages}</span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">→</button>
        </div>
      )}

      {selectedId !== null && <TournamentDetailModal tournamentId={selectedId} onClose={() => setSelectedId(null)} />}
    </div>
  );
}

function TournamentDetailModal({ tournamentId, onClose }: { tournamentId: number; onClose: () => void }) {
  const { data: detail } = useQuery({
    queryKey: ["admin-tournament-detail", tournamentId],
    queryFn: () => fetchAdminTournamentDetail(tournamentId),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <p className="font-display text-lg font-bold">
            Турнир #{tournamentId} {detail?.status === "active" ? `· тур ${detail.rounds_simulated}/14` : "· завершён"}
          </p>
          <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm">Закрыть</button>
        </div>

        {!detail && <p className="text-sm text-slate-400">Загрузка...</p>}

        {detail && (
          <>
            <p className="mb-2 text-sm font-semibold text-slate-200">Турнирная таблица</p>
            <div className="overflow-x-auto rounded-xl border border-white/5">
              <table className="w-full min-w-[480px] text-xs">
                <thead className="bg-bg-surface text-left text-slate-400">
                  <tr>
                    <th className="px-2 py-1.5">#</th>
                    <th className="px-2 py-1.5">Клуб</th>
                    <th className="px-2 py-1.5">Очки</th>
                    <th className="px-2 py-1.5">Мячи</th>
                    {detail.status === "completed" && <th className="px-2 py-1.5">Итог</th>}
                  </tr>
                </thead>
                <tbody>
                  {detail.standings.map((s) => (
                    <tr key={s.club_id} className="border-t border-white/5">
                      <td className="px-2 py-1.5">{s.final_rank}</td>
                      <td className="px-2 py-1.5 text-slate-200">{s.club_name}</td>
                      <td className="px-2 py-1.5">{s.points}</td>
                      <td className="px-2 py-1.5 text-slate-400">{s.goals_for}:{s.goals_against}</td>
                      {detail.status === "completed" && (
                        <td className="px-2 py-1.5 text-slate-400">
                          {s.cup_awarded ? "🏆 " : ""}⭐{s.stars_delta} · 🪙+{s.budget_awarded}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="mb-2 mt-4 text-sm font-semibold text-slate-200">Матчи ({detail.matches.length})</p>
            <div className="flex flex-col gap-1.5">
              {detail.matches.map((m) => (
                <div key={m.id} className="flex items-center justify-between rounded-lg bg-bg-surface px-3 py-1.5 text-xs">
                  <span className="text-slate-500">Тур {m.round_number}</span>
                  <span className="text-slate-200">Клуб #{m.club_a_id} {m.score_a} : {m.score_b} Клуб #{m.club_b_id}</span>
                </div>
              ))}
              {detail.matches.length === 0 && <p className="text-sm text-slate-500">Матчей пока нет</p>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
