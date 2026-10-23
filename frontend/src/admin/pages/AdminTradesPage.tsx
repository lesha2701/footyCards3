import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchAdminTrades, fetchGameConfig, forceCancelTrade, updateGameConfig } from "@/admin/api";
import { staticUrl } from "@/lib/api";
import type { TradeOffer, TradeStatus, UserCard } from "@/types";

const STATUSES: (TradeStatus | "all")[] = ["all", "pending", "accepted", "rejected", "cancelled", "expired"];
const STATUS_LABELS: Record<string, string> = {
  all: "Все", pending: "Ожидает", accepted: "Принят", rejected: "Отклонён", cancelled: "Отменён", expired: "Истёк",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
}

const PAGE_SIZE = 50;

export default function AdminTradesPage() {
  const [status, setStatus] = useState<TradeStatus | "all">("all");
  const [usernameInput, setUsernameInput] = useState("");
  const [username, setUsername] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [coinsMin, setCoinsMin] = useState("");
  const [coinsMax, setCoinsMax] = useState("");
  const [coinsOnly, setCoinsOnly] = useState(false);
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();
  // Any filter change starts again from the first page.
  useEffect(() => setPage(1), [status, username, dateFrom, dateTo, coinsMin, coinsMax, coinsOnly]);
  const toNumber = (v: string) => (v.trim() === "" ? undefined : Math.max(0, Number(v)));
  const { data, isLoading } = useQuery({
    queryKey: ["admin-trades", status, username, dateFrom, dateTo, coinsMin, coinsMax, coinsOnly, page],
    queryFn: () => fetchAdminTrades({
      status: status === "all" ? undefined : status, username, date_from: dateFrom, date_to: dateTo,
      coins_min: toNumber(coinsMin), coins_max: toNumber(coinsMax), coins_only: coinsOnly,
      page, page_size: PAGE_SIZE,
    }),
    placeholderData: keepPreviousData,
  });
  const trades = data?.items;

  // Global switch for player-to-player trades (GameConfig.trades_enabled).
  const { data: config } = useQuery({ queryKey: ["admin-game-config"], queryFn: fetchGameConfig });
  const switchMutation = useMutation({
    mutationFn: (enabled: boolean) => updateGameConfig({ trades_enabled: enabled }),
    onSuccess: (updated) => queryClient.setQueryData(["admin-game-config"], updated),
  });
  const tradesOn = config?.trades_enabled !== false;
  const flipTrades = () => {
    const question = tradesOn
      ? "Выключить обмены для всех игроков? Новые предложения создавать и принимать будет нельзя."
      : "Включить обмены обратно?";
    if (confirm(question)) switchMutation.mutate(!tradesOn);
  };
  const cancelMutation = useMutation({
    mutationFn: forceCancelTrade,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-trades"] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Обмены</h1>

      {config && (
        <div
          className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-3 ${
            tradesOn ? "border-emerald-400/20 bg-emerald-400/5" : "border-red-500/30 bg-red-500/10"
          }`}
        >
          <div>
            <p className="text-sm font-bold">{tradesOn ? "Обмены включены" : "Обмены выключены"}</p>
            <p className="text-caption text-slate-400">
              {tradesOn
                ? "Игроки могут создавать и принимать предложения."
                : "Новые предложения создать и принять нельзя; ждущие можно только отменить или отклонить."}
            </p>
          </div>
          <button
            onClick={flipTrades}
            disabled={switchMutation.isPending}
            className={`rounded-lg px-4 py-2 text-xs font-bold disabled:opacity-50 ${
              tradesOn ? "bg-red-500 text-white" : "bg-accent text-bg-base"
            }`}
          >
            {tradesOn ? "Выключить обмены" : "Включить обмены"}
          </button>
        </div>
      )}

      <form
        onSubmit={(e) => { e.preventDefault(); setUsername(usernameInput.trim()); }}
        className="flex gap-2"
      >
        <input
          value={usernameInput}
          onChange={(e) => setUsernameInput(e.target.value)}
          placeholder="Юзернейм игрока (отправитель или получатель)..."
          className="flex-1 rounded-lg bg-bg-surface px-3 py-2 text-sm outline-none"
        />
        <button type="submit" className="rounded-lg bg-accent px-4 py-2 text-xs font-bold text-bg-base">Найти</button>
        {username && (
          <button
            type="button"
            onClick={() => { setUsernameInput(""); setUsername(""); }}
            className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold text-slate-300"
          >
            Сбросить
          </button>
        )}
      </form>

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

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-caption text-slate-400">
          С даты
          <input
            type="date"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(e) => setDateFrom(e.target.value)}
            className="rounded-lg bg-bg-surface px-3 py-2 text-sm text-slate-100 outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-caption text-slate-400">
          По дату
          <input
            type="date"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(e) => setDateTo(e.target.value)}
            className="rounded-lg bg-bg-surface px-3 py-2 text-sm text-slate-100 outline-none"
          />
        </label>
        {[["Сегодня", 0], ["7 дней", 6], ["30 дней", 29]].map(([label, back]) => (
          <button
            key={label}
            type="button"
            onClick={() => { setDateFrom(daysAgo(back as number)); setDateTo(daysAgo(0)); }}
            className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold text-slate-300"
          >
            {label}
          </button>
        ))}
        {(dateFrom || dateTo) && (
          <button
            type="button"
            onClick={() => { setDateFrom(""); setDateTo(""); }}
            className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold text-slate-300"
          >
            Все даты
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-caption text-slate-400">
          Монет от
          <input
            type="number" min={0} inputMode="numeric" value={coinsMin} placeholder="0"
            onChange={(e) => setCoinsMin(e.target.value)}
            className="w-32 rounded-lg bg-bg-surface px-3 py-2 text-sm text-slate-100 outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-caption text-slate-400">
          Монет до
          <input
            type="number" min={0} inputMode="numeric" value={coinsMax} placeholder="∞"
            onChange={(e) => setCoinsMax(e.target.value)}
            className="w-32 rounded-lg bg-bg-surface px-3 py-2 text-sm text-slate-100 outline-none"
          />
        </label>
        {[["≥ 100 000", "100000"], ["≥ 1 000 000", "1000000"]].map(([label, value]) => (
          <button
            key={value}
            type="button"
            onClick={() => { setCoinsMin(value); setCoinsMax(""); }}
            className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold text-slate-300"
          >
            {label}
          </button>
        ))}
        <label className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold text-slate-300">
          <input type="checkbox" checked={coinsOnly} onChange={(e) => setCoinsOnly(e.target.checked)} />
          Только монеты (без карт)
        </label>
        {(coinsMin || coinsMax || coinsOnly) && (
          <button
            type="button"
            onClick={() => { setCoinsMin(""); setCoinsMax(""); setCoinsOnly(false); }}
            className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold text-slate-300"
          >
            Любая сумма
          </button>
        )}
      </div>

      {data && <p className="text-xs text-slate-400">Найдено: {data.total}</p>}
      <Pager page={page} pages={data?.pages ?? 1} onChange={setPage} />

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="flex flex-col gap-2">
        {trades?.map((t) => (
          <TradeRow key={t.id} trade={t} onForceCancel={() => cancelMutation.mutate(t.id)} />
        ))}
        {!trades?.length && !isLoading && <p className="text-sm text-slate-500">Обменов нет</p>}
      </div>

      <Pager page={page} pages={data?.pages ?? 1} onChange={setPage} />
    </div>
  );
}

/** Local YYYY-MM-DD for `days` days ago (what <input type="date"> uses). */
function daysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function Pager({ page, pages, onChange }: { page: number; pages: number; onChange: (p: number) => void }) {
  if (pages <= 1) return null;
  return (
    <div className="flex items-center gap-2">
      <button
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30"
      >
        Назад
      </button>
      <span className="text-sm text-slate-400">{page} / {pages}</span>
      <button
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
        className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30"
      >
        Вперёд
      </button>
    </div>
  );
}

function CardChip({ card }: { card: UserCard }) {
  return (
    <div className="flex items-center gap-1.5 rounded-lg bg-black/20 px-2 py-1">
      <img decoding="async" loading="lazy"
        src={staticUrl(card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
        alt={card.player.display_name}
        className="h-8 w-8 rounded object-cover"
      />
      <div className="leading-tight">
        <p className="text-caption font-semibold text-slate-200">{card.player.display_name}</p>
        <p className="text-micro text-slate-500">Рейтинг {card.player.rating} · #{card.serial_number}</p>
      </div>
    </div>
  );
}

function TradeSide({ label, cards, coins }: { label: string; cards: UserCard[]; coins: number }) {
  return (
    <div className="flex-1">
      <p className="mb-1 text-micro font-semibold text-slate-500">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {cards.map((c) => <CardChip key={c.id} card={c} />)}
        {coins > 0 && (
          <div className="flex items-center rounded-lg bg-black/20 px-2 py-1 text-caption font-semibold text-accent-lime">
            🪙 {coins}
          </div>
        )}
        {cards.length === 0 && coins === 0 && <span className="text-caption text-slate-500">—</span>}
      </div>
    </div>
  );
}

function TradeRow({ trade: t, onForceCancel }: { trade: TradeOffer; onForceCancel: () => void }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-bg-surface p-3 text-sm">
      <div className="flex items-center justify-between">
        <span>
          #{t.id}: {t.sender.username ?? t.sender.id} → {t.receiver.username ?? t.receiver.id}
        </span>
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-caption">{STATUS_LABELS[t.status]}</span>
      </div>
      <p className="mt-1 text-caption text-slate-500">{formatDateTime(t.created_at)}</p>

      <div className="mt-2 flex flex-col gap-2 sm:flex-row">
        <TradeSide label="Отдаёт" cards={t.offered_cards} coins={t.sender_coins} />
        <TradeSide label="Просит" cards={t.requested_cards} coins={t.receiver_coins} />
      </div>

      {t.message && <p className="mt-2 text-xs italic text-slate-400">«{t.message}»</p>}

      {t.status === "pending" && (
        <button onClick={onForceCancel} className="mt-2 rounded-lg bg-red-500/70 px-3 py-1.5 text-xs font-bold">
          Принудительно отменить
        </button>
      )}
    </div>
  );
}
