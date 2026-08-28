import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  fetchAdminClub,
  fetchAdminClubBudgetTransactions,
  fetchAdminClubMembers,
  fetchAdminClubs,
  fetchAdminClubTournaments,
} from "@/admin/api";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import type { AdminClub, AdminClubMember } from "@/admin/types";

const ROLE_LABELS: Record<AdminClubMember["role"], string> = { captain: "Капитан", assistant: "Ассистент", member: "Участник" };

export default function AdminClubsPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<AdminClub | null>(null);

  const { data, isLoading } = useQuery({ queryKey: ["admin-clubs", search, page], queryFn: () => fetchAdminClubs(search, page) });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Клубы</h1>

      <input
        value={search}
        onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        placeholder="Поиск по названию..."
        className="max-w-sm rounded-xl bg-bg-surface px-4 py-2.5 text-sm outline-none"
      />

      <div className="overflow-x-auto rounded-2xl border border-white/5">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-bg-surface text-left text-xs text-slate-400">
            <tr>
              <th className="px-3 py-2">Название</th>
              <th className="px-3 py-2">Тип</th>
              <th className="px-3 py-2">Участники</th>
              <th className="px-3 py-2">Бюджет</th>
              <th className="px-3 py-2">🏆 / ⭐</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id} className="border-t border-white/5">
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <ClubLogo shape={c.logo_shape} color={c.logo_color} size={24} />
                    {c.name}
                  </div>
                </td>
                <td className="px-3 py-2 text-slate-400">{c.club_type === "open" ? "Открытый" : "Закрытый"}</td>
                <td className="px-3 py-2">{c.member_count}/11</td>
                <td className="px-3 py-2 text-amber-300">🪙{c.budget}</td>
                <td className="px-3 py-2 text-slate-400">{c.cups_count} / {c.stars_count}</td>
                <td className="px-3 py-2">
                  {c.is_disbanded ? <span className="text-red-400">Расформирован</span> : <span className="text-emerald-400">Активен</span>}
                </td>
                <td className="px-3 py-2">
                  <button onClick={() => setSelected(c)} className="rounded-lg bg-accent px-3 py-1 text-xs font-bold text-bg-base">
                    Открыть
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <p className="p-4 text-sm text-slate-400">Загрузка...</p>}
      </div>

      {data && data.pages > 1 && (
        <div className="flex gap-2">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">←</button>
          <span className="text-sm text-slate-400">{page} / {data.pages}</span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">→</button>
        </div>
      )}

      {selected && <ClubDetailModal clubId={selected.id} onClose={() => setSelected(null)} />}
    </div>
  );
}

function ClubDetailModal({ clubId, onClose }: { clubId: number; onClose: () => void }) {
  const [tab, setTab] = useState<"overview" | "members" | "budget" | "tournaments">("overview");

  const { data: club } = useQuery({ queryKey: ["admin-club", clubId], queryFn: () => fetchAdminClub(clubId) });
  const { data: members } = useQuery({
    queryKey: ["admin-club-members", clubId],
    queryFn: () => fetchAdminClubMembers(clubId),
    enabled: tab === "members",
  });
  const { data: budgetTransactions } = useQuery({
    queryKey: ["admin-club-budget", clubId],
    queryFn: () => fetchAdminClubBudgetTransactions(clubId),
    enabled: tab === "budget",
  });
  const { data: tournaments } = useQuery({
    queryKey: ["admin-club-tournaments", clubId],
    queryFn: () => fetchAdminClubTournaments(clubId),
    enabled: tab === "tournaments",
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <p className="font-display text-lg font-bold">{club?.name ?? "..."} (#{clubId})</p>
          <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm">Закрыть</button>
        </div>

        <div className="mb-4 flex gap-2">
          {(["overview", "members", "budget", "tournaments"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${tab === t ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"}`}
            >
              {t === "overview" ? "Обзор" : t === "members" ? "Участники" : t === "budget" ? "Бюджет" : "Турниры"}
            </button>
          ))}
        </div>

        {tab === "overview" && club && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Info label="Тип" value={club.club_type === "open" ? "Открытый" : "Закрытый"} />
            <Info label="Капитан (ID)" value={club.captain_id} />
            <Info label="Основан" value={new Date(club.founded_at).toLocaleDateString("ru-RU")} />
            <Info label="Бюджет" value={`🪙${club.budget}`} />
            <Info label="Кубки / Звёзды" value={`🏆${club.cups_count} / ⭐${club.stars_count}`} />
            <Info label="Код приглашения" value={club.invite_code} />
            <Info label="Статус" value={club.is_disbanded ? "Расформирован" : "Активен"} />
            <Info
              label="Последняя заявка на турнир"
              value={club.last_tournament_applied_at ? new Date(club.last_tournament_applied_at).toLocaleDateString("ru-RU") : "—"}
            />
            {club.description && <div className="col-span-2"><Info label="Описание" value={club.description} /></div>}
          </div>
        )}

        {tab === "members" && (
          <div className="flex flex-col gap-2">
            {members?.map((m) => (
              <div key={m.user_id} className="flex items-center justify-between rounded-lg bg-bg-surface px-3 py-2 text-xs">
                <span>{m.username ?? m.first_name ?? `#${m.user_id}`}</span>
                <span className="text-slate-400">{ROLE_LABELS[m.role]}</span>
                <span className="text-slate-500">{new Date(m.joined_at).toLocaleDateString("ru-RU")}</span>
              </div>
            ))}
            {!members?.length && <p className="text-sm text-slate-500">Нет участников</p>}
          </div>
        )}

        {tab === "budget" && (
          <div className="flex flex-col gap-2">
            {budgetTransactions?.items.map((t) => (
              <div key={t.id} className="flex items-center justify-between rounded-lg bg-bg-surface px-3 py-2 text-xs">
                <div>
                  <p>{t.description || t.type}</p>
                  <p className="text-slate-500">{new Date(t.created_at).toLocaleString("ru-RU")} · {t.balance_before} → {t.balance_after}</p>
                </div>
                <span className={t.amount >= 0 ? "text-emerald-400" : "text-red-400"}>{t.amount}</span>
              </div>
            ))}
            {!budgetTransactions?.items.length && <p className="text-sm text-slate-500">Нет транзакций</p>}
          </div>
        )}

        {tab === "tournaments" && (
          <div className="flex flex-col gap-2">
            {tournaments?.map((t) => (
              <div key={t.tournament_id} className="flex items-center justify-between rounded-lg bg-bg-surface px-3 py-2 text-xs">
                <div>
                  <p>Турнир #{t.tournament_id} — {t.status === "completed" ? "завершён" : `тур ${t.rounds_simulated}/14`}{t.is_withdrawn && " · снялся"}</p>
                  <p className="text-slate-400">{t.points} очк. · {t.goals_for}:{t.goals_against}</p>
                </div>
                {t.status === "completed" && (
                  <div className="text-right">
                    <p>#{t.final_rank}{t.cup_awarded ? " 🏆" : ""}</p>
                    <p className="text-slate-400">⭐{t.stars_delta} · 🪙+{t.budget_awarded}</p>
                  </div>
                )}
              </div>
            ))}
            {!tournaments?.length && <p className="text-sm text-slate-500">Клуб не участвовал в турнирах</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-bg-surface px-3 py-2">
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className="font-semibold text-slate-100">{value}</p>
    </div>
  );
}
