import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";

import { clearMaintenanceBanner, fetchDashboard, startMaintenanceBanner } from "@/admin/api";
import { fetchMaintenanceStatus } from "@/api/maintenance";

export default function AdminDashboardPage() {
  const { data, isLoading } = useQuery({ queryKey: ["admin-dashboard"], queryFn: fetchDashboard });

  if (isLoading || !data) return <p className="text-slate-400">Загрузка...</p>;

  const maxReg = Math.max(1, ...data.registrations_by_day.map((p) => p.count));
  const maxPacks = Math.max(1, ...data.pack_openings_by_day.map((p) => p.count));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold">Дашборд</h1>

      <MaintenanceBannerSection />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Пользователей" value={data.total_users} />
        <StatCard label="Активны за 7 дней" value={data.active_users_7d} />
        <StatCard label="Паков открыто" value={data.total_packs_opened} />
        <StatCard label="Карточек выдано" value={data.total_cards_issued} />
        <StatCard label="Обменов" value={data.total_trades} />
        <StatCard label="Монет в обороте" value={data.coins_in_circulation} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Регистрации (14 дней)" points={data.registrations_by_day} max={maxReg} />
        <ChartCard title="Открытия паков (14 дней)" points={data.pack_openings_by_day} max={maxPacks} />
      </div>

      <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Последние действия администраторов</p>
        <div className="flex flex-col gap-2 text-sm">
          {data.recent_actions.map((a) => (
            <div key={a.id} className="flex items-center justify-between border-b border-white/5 pb-2 text-xs">
              <span className="text-slate-300">
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

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold text-slate-100">{value}</p>
    </div>
  );
}

function ChartCard({ title, points, max }: { title: string; points: { date: string; count: number }[]; max: number }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="mb-3 font-display text-sm font-bold">{title}</p>
      <div className="flex h-32 items-end gap-1">
        {points.map((p) => (
          <div key={p.date} className="group relative flex-1">
            <div
              className="w-full rounded-t bg-accent/70 transition-all"
              style={{ height: `${Math.max(4, (p.count / max) * 100)}%` }}
            />
            <span className="pointer-events-none absolute -top-5 left-1/2 -translate-x-1/2 text-[9px] text-slate-500 opacity-0 group-hover:opacity-100">
              {p.count}
            </span>
          </div>
        ))}
        {!points.length && <p className="text-xs text-slate-500">Нет данных</p>}
      </div>
    </div>
  );
}
