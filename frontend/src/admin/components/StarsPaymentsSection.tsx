import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useAdminToastStore } from "@/admin/adminToastStore";
import { fetchStarsReceipts, refundStarsReceipt, retryStarsReceipt } from "@/admin/api";
import type { StarsPaymentReceipt, StarsReceiptFilter, StarsReceiptStatus } from "@/admin/types";
import { ApiRequestError } from "@/lib/api";

const FILTERS: { value: StarsReceiptFilter; label: string }[] = [
  { value: "problems", label: "Требуют внимания" },
  { value: "all", label: "Все" },
  { value: "delivered", label: "Начислены" },
  { value: "refunded", label: "Возвращены" },
];

const STATUS: Record<StarsReceiptStatus, { label: string; className: string }> = {
  pending: { label: "Начисляется", className: "bg-sky-400/10 text-sky-300" },
  failed: { label: "Ошибка начисления", className: "bg-red-500/10 text-red-400" },
  delivered: { label: "Начислено", className: "bg-emerald-400/10 text-emerald-300" },
  refunded: { label: "Звёзды возвращены", className: "bg-white/5 text-slate-400" },
};

const fmt = (iso: string) => new Date(iso).toLocaleString("ru-RU");

/** Every Stars payment the bot received and how its delivery went. A paid
 *  order that failed to deliver is retried by the bot on its own; once the
 *  automatic attempts run out (or right away, if needed) an admin delivers
 *  it again or returns the Stars here. */
export default function StarsPaymentsSection() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<StarsReceiptFilter>("problems");
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({
    queryKey: ["admin-stars-receipts", filter, page],
    queryFn: () => fetchStarsReceipts(filter, page),
  });

  const toast = useAdminToastStore.getState().push;
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-stars-receipts"] });
    queryClient.invalidateQueries({ queryKey: ["admin-stars-receipt-problems"] });
  };
  const onDone = (text: string) => {
    toast(text, "success");
    refresh();
  };
  // A failed attempt is recorded on the receipt too (attempts, error) — refresh either way.
  const onError = (err: unknown) => {
    toast(err instanceof ApiRequestError ? err.message : "Не получилось — попробуй ещё раз", "error");
    refresh();
  };

  const retry = useMutation({ mutationFn: retryStarsReceipt, onSuccess: () => onDone("Покупка начислена"), onError });
  const refund = useMutation({ mutationFn: refundStarsReceipt, onSuccess: () => onDone("Звёзды возвращены"), onError });
  const busy = retry.isPending || refund.isPending;

  const confirmRefund = (r: StarsPaymentReceipt) => {
    if (confirm(`Вернуть ${r.stars_amount} ⭐ игроку? Покупка после этого начислена не будет.`)) refund.mutate(r.id);
  };

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <div className="mb-3">
        <p className="font-display text-base font-bold">Платежи Stars</p>
        <p className="text-xs text-slate-500">
          Каждая оплата звёздами. Если покупку не удалось начислить, бот повторяет сам; здесь можно начислить её
          вручную или вернуть звёзды.
        </p>
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => { setFilter(f.value); setPage(1); }}
            className={`rounded-lg px-3 py-1.5 text-xs ${filter === f.value ? "bg-accent font-bold text-bg-base" : "bg-white/5"}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="flex flex-col gap-2">
        {data?.items.map((r) => {
          const status = STATUS[r.status];
          const open = r.status === "pending" || r.status === "failed";
          return (
            <div key={r.id} className="rounded-xl bg-bg-base px-3 py-2.5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold">
                    {r.product} · <span className="text-amber-300">{r.stars_amount} ⭐</span>
                  </p>
                  <p className="text-caption text-slate-500">
                    {r.user_display_name ?? "Игрок не найден"}
                    {r.user_username && <> @{r.user_username}</>} · id {r.telegram_user_id} · {fmt(r.created_at)}
                  </p>
                </div>
                <span className={`shrink-0 rounded-md px-2 py-0.5 text-caption font-semibold ${status.className}`}>
                  {status.label}
                </span>
              </div>

              {open && (
                <div className="mt-2 flex flex-col gap-2">
                  {r.last_error && (
                    <p className="rounded-lg bg-red-500/5 px-2 py-1 text-caption text-red-300">Ошибка: {r.last_error}</p>
                  )}
                  <p className="text-caption text-slate-500">
                    Попыток: {r.attempts}
                    {r.auto_retry
                      ? r.next_attempt_at ? ` · бот повторит ${fmt(r.next_attempt_at)}` : " · бот повторит скоро"
                      : " · автоповторы закончились — нужно решение"}
                  </p>
                  <div className="flex gap-2">
                    <button
                      disabled={busy}
                      onClick={() => retry.mutate(r.id)}
                      className="flex-1 rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
                    >
                      Начислить
                    </button>
                    <button
                      disabled={busy}
                      onClick={() => confirmRefund(r)}
                      className="flex-1 rounded-lg bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-400 disabled:opacity-40"
                    >
                      Вернуть звёзды
                    </button>
                  </div>
                </div>
              )}
              {r.status === "delivered" && r.delivered_at && (
                <p className="mt-1 text-caption text-slate-500">
                  Начислено {fmt(r.delivered_at)}{r.attempts > 1 ? ` (с ${r.attempts}-й попытки)` : ""}
                </p>
              )}
              {r.status === "refunded" && r.refunded_at && (
                <p className="mt-1 text-caption text-slate-500">Возвращено {fmt(r.refunded_at)}</p>
              )}
            </div>
          );
        })}
        {data?.items.length === 0 && (
          <p className="rounded-xl bg-bg-base px-3 py-4 text-center text-xs text-slate-500">
            {filter === "problems" ? "Все оплаты начислены 👍" : "Платежей нет."}
          </p>
        )}
      </div>

      {data && data.pages > 1 && (
        <div className="mt-3 flex gap-2">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">←</button>
          <span className="text-sm text-slate-400">{page} / {data.pages}</span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">→</button>
        </div>
      )}
    </section>
  );
}
