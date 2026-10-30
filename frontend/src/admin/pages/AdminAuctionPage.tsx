import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  fetchAdminAgents,
  fetchAdminAuctionLots,
  fetchGameConfig,
  removeAdminAuctionLot,
  revokeAdminAgent,
  updateGameConfig,
} from "@/admin/api";
import { useAdminToastStore } from "@/admin/adminToastStore";
import type { GameConfig } from "@/admin/types";
import { LOT_STATUS_LABELS, type AuctionLot, type AuctionLotStatus } from "@/api/auction";
import { ApiRequestError, staticUrl } from "@/lib/api";

const input = "w-full rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none";
const toast = (msg: string) => useAdminToastStore.getState().push(msg, "success");
const errText = (err: unknown, fallback: string) => (err instanceof ApiRequestError ? err.message : fallback);
const STATUSES: (AuctionLotStatus | "all")[] = ["all", "active", "sold", "expired", "cancelled", "removed"];

function formatDateTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" }) : "—";
}

/** «Трансферный рынок»: settings (GameConfig) and every lot, with removal. */
export default function AdminAuctionPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Трансферный рынок</h1>
      <Settings />
      <Agents />
      <Lots />
    </div>
  );
}

type ConfigKey = keyof GameConfig;

function Settings() {
  const queryClient = useQueryClient();
  const { data: config } = useQuery({ queryKey: ["admin-game-config"], queryFn: fetchGameConfig });
  const [draft, setDraft] = useState<Partial<GameConfig>>({});
  const [durationsText, setDurationsText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const payload: Partial<GameConfig> = { ...draft };
      if (durationsText !== null) {
        payload.auction_durations_hours = durationsText.split(/[\s,;]+/).filter(Boolean).map(Number);
      }
      return updateGameConfig(payload);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["admin-game-config"], data);
      setDraft({});
      setDurationsText(null);
      setError(null);
      toast("Настройки рынка сохранены");
    },
    onError: (err) => setError(errText(err, "Не удалось сохранить")),
  });
  if (!config) return <p className="text-sm text-slate-400">Загрузка...</p>;

  const value = <K extends ConfigKey>(k: K): GameConfig[K] => (k in draft ? (draft[k] as GameConfig[K]) : config[k]);
  const set = (k: ConfigKey, v: unknown) => setDraft((d) => ({ ...d, [k]: v }));
  const num = (k: ConfigKey, label: string) => (
    <label className="flex flex-col gap-0.5">
      <span className="text-micro text-slate-500">{label}</span>
      <input type="number" min={0} value={value(k) as number} onChange={(e) => set(k, Number(e.target.value))} className={input} />
    </label>
  );
  const dirty = Object.keys(draft).length > 0 || durationsText !== null;

  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-white/5 bg-bg-surface p-4">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={value("auction_enabled") as boolean} onChange={(e) => set("auction_enabled", e.target.checked)} />
        Рынок открыт (новые лоты и ставки). Закрытие не мешает завершению уже идущих лотов.
      </label>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <label className="flex flex-col gap-0.5">
          <span className="text-micro text-slate-500">Сроки лота, часы (через запятую)</span>
          <input
            value={durationsText ?? (config.auction_durations_hours ?? []).join(", ")}
            onChange={(e) => setDurationsText(e.target.value)}
            className={input}
          />
        </label>
        {num("auction_fixed_duration_hours", "«Купить сразу»: лот висит, часов")}
        {num("auction_fee_pct", "Комиссия (сжигается), %")}
        {num("auction_min_increment_pct", "Мин. шаг ставки, %")}
        {num("auction_min_increment_coins", "Мин. шаг ставки, монет")}
        {num("auction_min_price", "Мин. стартовая цена, монет (иначе — ценность карточки)")}
        {num("auction_max_active_lots", "Активных лотов на игрока")}
        {num("auction_snipe_window_seconds", "Анти-снайпинг: окно, сек")}
        {num("auction_snipe_extend_seconds", "Анти-снайпинг: продление до, сек")}
        {num("auction_min_account_age_days", "Возраст аккаунта для ставок, дней (0 = все)")}
        {num("auction_max_wins_per_seller_daily", "Побед у одного продавца за сутки")}
      </div>
      <p className="font-display text-sm font-bold">Агентская лицензия (выставлять лоты могут только агенты)</p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={value("agent_license_enabled") as boolean} onChange={(e) => set("agent_license_enabled", e.target.checked)} />
        Продаётся
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={value("agent_license_requires_verified") as boolean}
          onChange={(e) => set("agent_license_requires_verified", e.target.checked)}
        />
        Только для «Проверенного аккаунта»
      </label>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {num("agent_license_stars", "Цена, ⭐")}
        {num("agent_license_days", "Срок, дней")}
        {num("agent_license_min_account_age_days", "Мин. возраст аккаунта, дней")}
      </div>
      {error && <p className="text-sm text-red-400">{error}</p>}
      <button
        disabled={!dirty || save.isPending}
        onClick={() => save.mutate()}
        className="self-start rounded-lg bg-accent px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
      >
        {save.isPending ? "Сохранение..." : "Сохранить"}
      </button>
    </section>
  );
}

function Lots() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuctionLotStatus | "all">("active");
  const [usernameInput, setUsernameInput] = useState("");
  const [username, setUsername] = useState("");
  const { data: lots, isLoading } = useQuery({
    queryKey: ["admin-auction-lots", status, username],
    queryFn: () => fetchAdminAuctionLots(status === "all" ? undefined : status, username || undefined),
  });
  const remove = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => removeAdminAuctionLot(id, reason),
    onSuccess: () => {
      toast("Лот снят, ставка возвращена");
      queryClient.invalidateQueries({ queryKey: ["admin-auction-lots"] });
    },
    onError: (err) => useAdminToastStore.getState().push(errText(err, "Не удалось снять лот"), "error"),
  });
  const askRemove = (lot: AuctionLot) => {
    const reason = window.prompt(`Снять лот #${lot.id} (${lot.card.player.display_name})? Причина (увидят продавец и лидер):`);
    if (reason && reason.trim().length >= 3) remove.mutate({ id: lot.id, reason: reason.trim() });
  };

  return (
    <section className="flex flex-col gap-3">
      <form onSubmit={(e) => { e.preventDefault(); setUsername(usernameInput.trim()); }} className="flex gap-2">
        <input
          value={usernameInput}
          onChange={(e) => setUsernameInput(e.target.value)}
          placeholder="Юзернейм (продавец, лидер или победитель)..."
          className="flex-1 rounded-lg bg-bg-surface px-3 py-2 text-sm outline-none"
        />
        <button type="submit" className="rounded-lg bg-accent px-4 py-2 text-xs font-bold text-bg-base">Найти</button>
      </form>
      <div className="flex flex-wrap gap-2">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${status === s ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"}`}
          >
            {s === "all" ? "Все" : LOT_STATUS_LABELS[s]}
          </button>
        ))}
      </div>
      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}
      {!isLoading && !lots?.length && <p className="text-sm text-slate-500">Лотов нет</p>}
      <div className="flex flex-col gap-2">
        {lots?.map((lot) => (
          <div key={lot.id} className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/5 bg-bg-surface p-3 text-sm">
            <img
              decoding="async"
              loading="lazy"
              src={staticUrl(lot.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
              alt={lot.card.player.display_name}
              className="h-10 w-10 rounded object-cover"
            />
            <div className="min-w-0 flex-1 leading-tight">
              <p className="font-semibold">#{lot.id} · {lot.card.player.display_name} (#{lot.card.serial_number}, {lot.card.player.rating})</p>
              <p className="text-caption text-slate-400">
                Продавец {lot.seller_name} · старт {lot.start_price}
                {lot.buy_now_price ? ` · сразу ${lot.buy_now_price}` : ""} · ставок {lot.bid_count}
                {lot.current_bid ? ` · лидер ${lot.leader_name ?? "—"} (${lot.current_bid})` : ""}
              </p>
              <p className="text-micro text-slate-500">
                {LOT_STATUS_LABELS[lot.status]} · создан {formatDateTime(lot.created_at)} · конец {formatDateTime(lot.closed_at ?? lot.ends_at)}
                {lot.final_price != null ? ` · продан за ${lot.final_price}, сожжено ${lot.fee_amount}` : ""}
                {lot.close_reason ? ` · причина: ${lot.close_reason}` : ""}
              </p>
            </div>
            {lot.status === "active" && (
              <button
                disabled={remove.isPending}
                onClick={() => askRemove(lot)}
                className="rounded-lg bg-red-500/80 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-40"
              >
                Снять
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function Agents() {
  const queryClient = useQueryClient();
  const [onlyActive, setOnlyActive] = useState(true);
  const { data: agents, isLoading } = useQuery({
    queryKey: ["admin-auction-agents", onlyActive],
    queryFn: () => fetchAdminAgents(onlyActive),
  });
  const revoke = useMutation({
    mutationFn: ({ userId, reason }: { userId: number; reason: string }) => revokeAdminAgent(userId, reason),
    onSuccess: () => {
      toast("Лицензия отозвана");
      queryClient.invalidateQueries({ queryKey: ["admin-auction-agents"] });
    },
    onError: (err) => useAdminToastStore.getState().push(errText(err, "Не удалось отозвать"), "error"),
  });
  const askRevoke = (userId: number, name: string) => {
    const reason = window.prompt(`Отозвать лицензию у ${name}? Причина:`);
    if (reason && reason.trim().length >= 3) revoke.mutate({ userId, reason: reason.trim() });
  };

  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-white/5 bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="font-display text-sm font-bold">Агенты{agents ? ` (${agents.length})` : ""}</p>
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <input type="checkbox" checked={onlyActive} onChange={(e) => setOnlyActive(e.target.checked)} /> только активные
        </label>
      </div>
      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}
      {!isLoading && !agents?.length && <p className="text-sm text-slate-500">Агентов нет</p>}
      {agents?.map((a) => (
        <div key={a.user_id} className="flex flex-wrap items-center gap-3 rounded-xl bg-black/20 px-3 py-2 text-sm">
          <div className="min-w-0 flex-1 leading-tight">
            <p className="font-semibold">
              {a.name} {a.username ? `@${a.username}` : ""} · id {a.user_id}
              {a.is_banned && <span className="ml-1 text-red-400">бан</span>}
              {a.is_trade_banned && <span className="ml-1 text-red-400">бан обменов</span>}
            </p>
            <p className="text-caption text-slate-400">
              {a.active ? `активна до ${formatDateTime(a.expires_at)}` : a.revoked_at ? `отозвана ${formatDateTime(a.revoked_at)}` : `истекла ${formatDateTime(a.expires_at)}`}
              {" · "}покупок {a.purchases} · {a.stars_total} ⭐ · с {formatDateTime(a.first_bought_at)}
              {a.revoke_reason ? ` · причина: ${a.revoke_reason}` : ""}
            </p>
          </div>
          {a.active && (
            <button
              disabled={revoke.isPending}
              onClick={() => askRevoke(a.user_id, a.name)}
              className="rounded-lg bg-red-500/80 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-40"
            >
              Отозвать
            </button>
          )}
        </div>
      ))}
    </section>
  );
}
