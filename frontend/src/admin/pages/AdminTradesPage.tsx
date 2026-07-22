import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAdminTrades, forceCancelTrade } from "@/admin/api";
import type { TradeStatus } from "@/types";

const STATUSES: (TradeStatus | "all")[] = ["all", "pending", "accepted", "rejected", "cancelled", "expired"];
const STATUS_LABELS: Record<string, string> = {
  all: "Все", pending: "Ожидает", accepted: "Принят", rejected: "Отклонён", cancelled: "Отменён", expired: "Истёк",
};

export default function AdminTradesPage() {
  const [status, setStatus] = useState<TradeStatus | "all">("all");
  const queryClient = useQueryClient();
  const { data: trades, isLoading } = useQuery({
    queryKey: ["admin-trades", status],
    queryFn: () => fetchAdminTrades(status === "all" ? undefined : status),
  });
  const cancelMutation = useMutation({
    mutationFn: forceCancelTrade,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-trades"] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Обмены</h1>

      <div className="flex flex-wrap gap-2">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${status === s ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"}`}
          >
            {STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="flex flex-col gap-2">
        {trades?.map((t) => (
          <div key={t.id} className="rounded-2xl border border-white/5 bg-bg-surface p-3 text-sm">
            <div className="flex items-center justify-between">
              <span>#{t.id}: {t.sender.username ?? t.sender.id} → {t.receiver.username ?? t.receiver.id}</span>
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-[11px]">{STATUS_LABELS[t.status]}</span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Отдаёт: {t.offered_cards.length} карт + 🪙{t.sender_coins} · Просит: {t.requested_cards.length} карт + 🪙{t.receiver_coins}
            </p>
            {t.status === "pending" && (
              <button onClick={() => cancelMutation.mutate(t.id)} className="mt-2 rounded-lg bg-red-500/70 px-3 py-1.5 text-xs font-bold">
                Принудительно отменить
              </button>
            )}
          </div>
        ))}
        {!trades?.length && !isLoading && <p className="text-sm text-slate-500">Обменов нет</p>}
      </div>
    </div>
  );
}
