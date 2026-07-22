import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  adjustUserBalance,
  banUser,
  deleteUserCard,
  fetchAdminUserCollection,
  fetchAdminUserTransactions,
  fetchAdminUsers,
  grantCard,
  resetUserLimits,
  toggleRewardBlock,
  unbanUser,
} from "@/admin/api";
import type { AdminUser } from "@/admin/types";
import { staticUrl } from "@/lib/api";

export default function AdminUsersPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<AdminUser | null>(null);

  const { data, isLoading } = useQuery({ queryKey: ["admin-users", search, page], queryFn: () => fetchAdminUsers(search, page) });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Пользователи</h1>

      <input
        value={search}
        onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        placeholder="Поиск по username, имени, ID..."
        className="max-w-sm rounded-xl bg-bg-surface px-4 py-2.5 text-sm outline-none"
      />

      <div className="overflow-x-auto rounded-2xl border border-white/5">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-bg-surface text-left text-xs text-slate-400">
            <tr>
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Username</th>
              <th className="px-3 py-2">Баланс</th>
              <th className="px-3 py-2">Рейтинг</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((u) => (
              <tr key={u.id} className="border-t border-white/5">
                <td className="px-3 py-2 text-slate-400">{u.id}</td>
                <td className="px-3 py-2">{u.username ?? u.first_name ?? "—"}</td>
                <td className="px-3 py-2 text-amber-300">🪙{u.balance}</td>
                <td className="px-3 py-2">{u.arena_rating}</td>
                <td className="px-3 py-2">
                  {u.is_banned ? <span className="text-red-400">Забанен</span> : <span className="text-emerald-400">Активен</span>}
                </td>
                <td className="px-3 py-2">
                  <button onClick={() => setSelected(u)} className="rounded-lg bg-accent px-3 py-1 text-xs font-bold text-bg-base">
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

      {selected && <UserDetailModal user={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function UserDetailModal({ user, onClose }: { user: AdminUser; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"overview" | "collection" | "transactions">("overview");
  const [balanceAmount, setBalanceAmount] = useState(0);
  const [balanceReason, setBalanceReason] = useState("");
  const [playerId, setPlayerId] = useState("");

  const { data: collection } = useQuery({
    queryKey: ["admin-user-collection", user.id],
    queryFn: () => fetchAdminUserCollection(user.id),
    enabled: tab === "collection",
  });
  const { data: transactions } = useQuery({
    queryKey: ["admin-user-transactions", user.id],
    queryFn: () => fetchAdminUserTransactions(user.id),
    enabled: tab === "transactions",
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-users"] });

  const balanceMutation = useMutation({
    mutationFn: () => adjustUserBalance(user.id, balanceAmount, balanceReason || "Корректировка администратором"),
    onSuccess: invalidate,
  });
  const banMutation = useMutation({ mutationFn: () => (user.is_banned ? unbanUser(user.id) : banUser(user.id)), onSuccess: invalidate });
  const rewardBlockMutation = useMutation({ mutationFn: () => toggleRewardBlock(user.id), onSuccess: invalidate });
  const resetMutation = useMutation({ mutationFn: () => resetUserLimits(user.id) });
  const grantMutation = useMutation({
    mutationFn: () => grantCard(user.id, Number(playerId)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-user-collection", user.id] }),
  });
  const deleteCardMutation = useMutation({
    mutationFn: (cardId: number) => deleteUserCard(user.id, cardId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-user-collection", user.id] }),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <p className="font-display text-lg font-bold">{user.username ?? user.first_name} (#{user.id})</p>
          <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm">Закрыть</button>
        </div>

        <div className="mb-4 flex gap-2">
          {(["overview", "collection", "transactions"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${tab === t ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"}`}
            >
              {t === "overview" ? "Обзор" : t === "collection" ? "Коллекция" : "Транзакции"}
            </button>
          ))}
        </div>

        {tab === "overview" && (
          <div className="flex flex-col gap-4 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <Info label="Telegram ID" value={user.telegram_id} />
              <Info label="Баланс" value={`🪙${user.balance}`} />
              <Info label="Рейтинг Arena" value={user.arena_rating} />
              <Info label="Статус" value={user.is_banned ? "Забанен" : "Активен"} />
            </div>

            <div className="rounded-xl bg-bg-surface p-3">
              <p className="mb-2 text-xs font-semibold text-slate-400">Изменить баланс</p>
              <div className="flex gap-2">
                <input type="number" value={balanceAmount} onChange={(e) => setBalanceAmount(Number(e.target.value))} className="w-24 rounded-lg bg-black/30 px-2 py-1.5 text-sm outline-none" />
                <input value={balanceReason} onChange={(e) => setBalanceReason(e.target.value)} placeholder="Причина" className="flex-1 rounded-lg bg-black/30 px-2 py-1.5 text-sm outline-none" />
                <button onClick={() => balanceMutation.mutate()} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base">Применить</button>
              </div>
            </div>

            <div className="rounded-xl bg-bg-surface p-3">
              <p className="mb-2 text-xs font-semibold text-slate-400">Выдать карточку (по ID футболиста)</p>
              <div className="flex gap-2">
                <input value={playerId} onChange={(e) => setPlayerId(e.target.value)} placeholder="ID игрока" className="flex-1 rounded-lg bg-black/30 px-2 py-1.5 text-sm outline-none" />
                <button onClick={() => grantMutation.mutate()} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base">Выдать</button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <button onClick={() => banMutation.mutate()} className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold">
                {user.is_banned ? "Разблокировать" : "Заблокировать"}
              </button>
              <button onClick={() => rewardBlockMutation.mutate()} className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold">
                {user.game_rewards_blocked ? "Разрешить награды за игры" : "Заблокировать награды за игры"}
              </button>
              <button onClick={() => resetMutation.mutate()} className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold">
                Сбросить дневные лимиты
              </button>
            </div>
          </div>
        )}

        {tab === "collection" && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {collection?.items?.map((c: any) => (
              <div key={c.id} className="rounded-xl bg-bg-surface p-2 text-center">
                <img src={staticUrl(c.player.image_path) ?? staticUrl("players/placeholder/player_placeholder.webp")} className="aspect-square w-full rounded-lg object-cover" />
                <p className="mt-1 truncate text-[11px]">{c.player.display_name}</p>
                <button onClick={() => deleteCardMutation.mutate(c.id)} className="mt-1 w-full rounded-lg bg-red-500/80 py-1 text-[10px] font-bold text-white">
                  Удалить
                </button>
              </div>
            ))}
            {!collection?.items?.length && <p className="text-sm text-slate-500">Нет карточек</p>}
          </div>
        )}

        {tab === "transactions" && (
          <div className="flex flex-col gap-2">
            {transactions?.items?.map((t: any) => (
              <div key={t.id} className="flex items-center justify-between rounded-lg bg-bg-surface px-3 py-2 text-xs">
                <span>{t.description || t.type}</span>
                <span className={t.amount >= 0 ? "text-emerald-400" : "text-red-400"}>{t.amount}</span>
              </div>
            ))}
            {!transactions?.items?.length && <p className="text-sm text-slate-500">Нет транзакций</p>}
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
