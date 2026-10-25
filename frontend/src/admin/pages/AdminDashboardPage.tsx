import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Link } from "react-router-dom";

import {
  clearMaintenanceBanner,
  fetchAnnouncementAdmin,
  fetchDashboard,
  fetchStarsReceiptProblemCount,
  setAnnouncement,
  startMaintenanceBanner,
} from "@/admin/api";
import { fetchMaintenanceStatus } from "@/api/maintenance";
import { fillDailySeries, type ChartPoint } from "@/admin/chartSeries";

export default function AdminDashboardPage() {
  const { data, isLoading } = useQuery({ queryKey: ["admin-dashboard"], queryFn: fetchDashboard, refetchInterval: 60_000 });
  const { data: paymentProblems = 0 } = useQuery({
    queryKey: ["admin-stars-receipt-problems"], queryFn: fetchStarsReceiptProblemCount, refetchInterval: 60_000,
  });

  if (isLoading || !data) return <p className="text-slate-400">Загрузка...</p>;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold">Дашборд</h1>

      {/* «За сутки»: what happened in the last 24 hours, and anything that needs attention. */}
      <section className="flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">За сутки</p>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
          <StatCard label="Новых игроков" value={data.new_users_24h} />
          <StatCard label="Заходили" value={data.active_users_24h} />
          <StatCard label="Звёзд получено" value={data.stars_24h} hint={`${data.stars_purchases_24h} покупок`} />
          <StatCard
            label="Ошибок сервера" value={data.server_errors_24h} tone={data.server_errors_24h ? "bad" : "good"}
            to="/admin/log?tab=errors" hint={data.server_errors_24h ? "Открыть список" : "Всё спокойно"}
          />
          <StatCard
            label="Неначисленные Stars" value={paymentProblems} tone={paymentProblems ? "bad" : "good"}
            to="/admin/shop" hint={paymentProblems ? "Разобрать в Магазине" : "Все начислены"}
          />
        </div>
      </section>

      <MaintenanceBannerSection />
      <AnnouncementBannerSection />

      <p className="-mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">За всё время</p>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Пользователей" value={data.total_users} />
        <StatCard label="Активны за 7 дней" value={data.active_users_7d} />
        <StatCard label="Паков открыто" value={data.total_packs_opened} />
        <StatCard label="Карточек выдано" value={data.total_cards_issued} />
        <StatCard label="Обменов" value={data.total_trades} />
        <StatCard label="Монет в обороте" value={data.coins_in_circulation} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Регистрации (14 дней)" points={data.registrations_by_day} />
        <ChartCard title="Открытия паков (14 дней)" points={data.pack_openings_by_day} />
      </div>

      <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Последние действия администраторов</p>
        <div className="flex flex-col gap-2 text-sm">
          {data.recent_actions.map((a) => (
            <div key={a.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 border-b border-white/5 pb-2 text-xs">
              <span className="min-w-0 break-words text-slate-300">
                #{a.admin_id} {a.action} → {a.entity_type} {a.entity_id ?? ""}
              </span>
              <span className="text-slate-500">{new Date(a.created_at).toLocaleString("ru-RU")}</span>
            </div>
          ))}
          {!data.recent_actions.length && <p className="text-slate-500">Пока нет действий</p>}
        </div>
      </div>
    </div>
  );
}

function MaintenanceBannerSection() {
  const queryClient = useQueryClient();
  const { data: status } = useQuery({
    queryKey: ["maintenance-status"],
    queryFn: fetchMaintenanceStatus,
    refetchInterval: 15000,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["maintenance-status"] });
  const startMutation = useMutation({ mutationFn: startMaintenanceBanner, onSuccess: invalidate });
  const clearMutation = useMutation({ mutationFn: clearMaintenanceBanner, onSuccess: invalidate });

  const minutesLeft = status?.until ? Math.max(1, Math.ceil((new Date(status.until).getTime() - Date.now()) / 60000)) : null;

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="mb-1 font-display text-base font-bold">🔧 Баннер техработ</p>
      <p className="mb-3 text-xs text-slate-500">
        Показывает игрокам в мини-аппе предупреждение на 5 минут — нажимай перед выкладкой обновления.
      </p>

      {status?.active ? (
        <div className="flex items-center justify-between rounded-xl bg-amber-500/10 px-3 py-2">
          <span className="text-sm text-amber-300">Баннер активен ещё ~{minutesLeft} мин</span>
          <button
            onClick={() => clearMutation.mutate()}
            disabled={clearMutation.isPending}
            className="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-bold disabled:opacity-50"
          >
            Убрать сейчас
          </button>
        </div>
      ) : (
        <button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
          className="rounded-lg bg-amber-500 px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-50"
        >
          {startMutation.isPending ? "Включаю..." : "Готовлю обновление (баннер на 5 мин)"}
        </button>
      )}
    </section>
  );
}

function AnnouncementBannerSection() {
  const queryClient = useQueryClient();
  const { data: announcement } = useQuery({
    queryKey: ["announcement-admin"],
    queryFn: fetchAnnouncementAdmin,
  });
  const [text, setText] = useState("");

  useEffect(() => {
    setText(announcement?.text ?? "");
  }, [announcement?.text]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["announcement-admin"] });
  const saveMutation = useMutation({ mutationFn: () => setAnnouncement(text.trim()), onSuccess: invalidate });
  const clearMutation = useMutation({ mutationFn: () => setAnnouncement(""), onSuccess: invalidate });

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="mb-1 font-display text-base font-bold">📣 Баннер-объявление</p>
      <p className="mb-3 text-xs text-slate-500">
        Показывает всем игрокам в мини-аппе баннер с этим текстом, пока он не закроет его крестиком. Новый текст
        снова покажется всем, даже тем, кто закрыл предыдущий.
      </p>

      {announcement?.text && (
        <div className="mb-3 rounded-xl bg-accent-cyan/10 px-3 py-2 text-xs text-accent-cyan">
          Сейчас активен: «{announcement.text}»
        </div>
      )}

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        maxLength={500}
        placeholder="Текст баннера для игроков, например: «31 августа турнир будет недоступен несколько часов из-за техработ»"
        className="w-full rounded-lg bg-bg-base px-3 py-2 text-sm outline-none"
      />

      <div className="mt-3 flex gap-2">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={!text.trim() || saveMutation.isPending}
          className="rounded-lg bg-accent px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
        >
          {saveMutation.isPending ? "Сохраняю..." : "Показать баннер"}
        </button>
        {announcement?.text && (
          <button
            onClick={() => clearMutation.mutate()}
            disabled={clearMutation.isPending}
            className="rounded-lg bg-white/10 px-3 py-2 text-xs font-bold disabled:opacity-50"
          >
            Убрать баннер
          </button>
        )}
      </div>
    </section>
  );
}

function StatCard({ label, value, hint, tone, to }: {
  label: string; value: number; hint?: string; tone?: "good" | "bad"; to?: string;
}) {
  const color = tone === "bad" ? "text-red-400" : tone === "good" ? "text-accent-lime" : "text-slate-100";
  const body = (
    <>
      <p className="truncate text-xs text-slate-400">{label}</p>
      <p className={`mt-1 truncate font-display text-2xl font-bold ${color}`}>{value.toLocaleString("ru-RU")}</p>
      {hint && <p className="mt-0.5 truncate text-micro text-slate-500">{hint}</p>}
    </>
  );
  const cls = `min-w-0 rounded-2xl border bg-bg-surface p-4 ${tone === "bad" ? "border-red-500/30" : "border-white/5"}`;
  return to ? <Link to={to} className={`${cls} block active:scale-[0.98]`}>{body}</Link> : <div className={cls}>{body}</div>;
}

function ChartCard({ title, points }: { title: string; points: ChartPoint[] }) {
  const series = fillDailySeries(points);
  const max = Math.max(1, ...series.map((p) => p.count));
  const total = series.reduce((sum, p) => sum + p.count, 0);

  return (
    <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <p className="font-display text-sm font-bold">{title}</p>
        <span className="text-xs text-slate-400">всего {total}</span>
      </div>
      {/* Every column must stretch to the container's full height (h-full):
          the bar's height is a percentage of its column, and an auto-height
          column collapses to 0px, which made every bar invisible. */}
      <div className="flex h-32 items-end gap-1 pt-4">
        {series.map((p) => (
          <div key={p.date} className="flex h-full flex-1 flex-col items-center justify-end" title={`${p.date}: ${p.count}`}>
            {p.count > 0 && <span className="mb-0.5 text-micro leading-none text-slate-400">{p.count}</span>}
            <div
              className={`w-full rounded-t ${p.count > 0 ? "bg-accent/70" : "bg-white/5"}`}
              style={{ height: p.count > 0 ? `${Math.max(4, (p.count / max) * 100)}%` : "2px" }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-1">
        {series.map((p, i) => (
          <span key={p.date} className="flex-1 text-center text-micro text-slate-500">
            {i % 2 === series.length % 2 ? "" : p.date.slice(8, 10)}
          </span>
        ))}
      </div>
    </div>
  );
}
