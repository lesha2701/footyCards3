import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

import {
  claimClubBaseIncome,
  createClubBaseSpeedupInvoice,
  fetchClubBase,
  fetchClubBaseInvoiceStatus,
  setStadiumLook,
  upgradeClubBaseBuilding,
} from "@/api/clubBase";
import BaseMap from "@/components/base/BaseMap";
import FirstVisitHint from "@/components/common/FirstVisitHint";
import { IconClose, IconCoin } from "@/components/icons";
import { SEAT_COLOR_NAMES, SEAT_COLORS, formatBuildTime, hoursLabel, upgradeBlocker } from "@/lib/clubBase";
import { formatGameError } from "@/lib/errors";
import { useMarkSeen } from "@/lib/seenSections";
import { hapticNotify, openTelegramInvoice } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { ClubBaseBuilding, ClubBaseCode, ClubBaseLook, ClubBaseState } from "@/types";

function useCountdown(endsAt: string | null | undefined): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!endsAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [endsAt]);
  return endsAt ? Math.max(0, Math.round((new Date(endsAt).getTime() - now) / 1000)) : 0;
}

function LookEditor({ state, onSave, pending }: { state: ClubBaseState; onSave: (look: Partial<ClubBaseLook>) => void; pending: boolean }) {
  const { look, level, unlocks } = state.stadium;
  const roofs: { value: ClubBaseLook["roof"]; label: string; need: number }[] = [
    { value: "none", label: "Без крыши", need: 0 },
    { value: "canopy", label: "Козырьки", need: unlocks.roof_canopy },
    { value: "full", label: "Крыша по кругу", need: unlocks.roof_full },
  ];
  const chip = (active: boolean, locked: boolean) =>
    `min-h-[36px] rounded-xl px-3 text-xs font-semibold ${active ? "bg-path text-bg-base" : "bg-white/5 text-ink-chalk"} ${locked ? "opacity-40" : ""}`;
  return (
    <div className="mt-3 flex flex-col gap-2.5 rounded-2xl bg-white/5 p-3">
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Внешний вид</p>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Цвет кресел">
        {state.stadium.seat_colors.map((c) => (
          <button
            key={c} type="button" role="radio" aria-checked={look.seats === c} aria-label={SEAT_COLOR_NAMES[c] ?? c}
            disabled={pending} onClick={() => onSave({ seats: c })}
            className={`h-9 w-9 rounded-full border-2 ${look.seats === c ? "border-path" : "border-white/15"}`}
            style={{ background: SEAT_COLORS[c] }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {roofs.map((r) => (
          <button key={r.value} type="button" disabled={pending || level < r.need} onClick={() => onSave({ roof: r.value })}
                  className={chip(look.roof === r.value, level < r.need)}>
            {r.label}{level < r.need ? ` · ур. ${r.need}` : ""}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={pending || level < unlocks.lights} onClick={() => onSave({ lights: !look.lights })}
                className={chip(look.lights, level < unlocks.lights)}>
          💡 Подсветка{level < unlocks.lights ? ` · ур. ${unlocks.lights}` : ""}
        </button>
        <button type="button" disabled={pending || level < unlocks.screen} onClick={() => onSave({ screen: !look.screen })}
                className={chip(look.screen, level < unlocks.screen)}>
          📺 Табло{level < unlocks.screen ? ` · ур. ${unlocks.screen}` : ""}
        </button>
      </div>
    </div>
  );
}

function BuildingSheet({
  state, building, balance, onClose, onUpgrade, upgrading, onLook, lookPending,
}: {
  state: ClubBaseState; building: ClubBaseBuilding | null; balance: number; onClose: () => void;
  onUpgrade: (code: ClubBaseCode) => void; upgrading: boolean; onLook: (look: Partial<ClubBaseLook>) => void; lookPending: boolean;
}) {
  return createPortal(
    <AnimatePresence>
      {building && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}
        >
          <motion.div
            role="dialog" aria-label={building.name}
            className="safe-bottom max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-t-3xl border border-white/10 bg-bg-surface p-4 sm:rounded-3xl"
            initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }} onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-path/10 text-2xl" aria-hidden>{building.emoji}</span>
              <div className="min-w-0 flex-1">
                <p className="font-display text-lg font-bold text-ink-chalk">{building.name}</p>
                <p className="text-xs text-ink-mist">{building.about}</p>
              </div>
              <button type="button" onClick={onClose} aria-label="Закрыть" className="grid h-9 w-9 place-items-center rounded-full bg-white/5">
                <IconClose size={16} />
              </button>
            </div>
            <div className="mt-3 flex items-center gap-1" aria-label={`Уровень ${building.level} из ${building.max_level}`}>
              {Array.from({ length: building.max_level }).map((_, i) => (
                <span key={i} className={`h-2 flex-1 rounded-full ${i < building.level ? "bg-path" : "bg-white/10"}`} />
              ))}
              <span className="ml-2 font-mono text-xs text-ink-mist">{building.level}/{building.max_level}</span>
            </div>
            {building.effects.length > 0 && (
              <div className="mt-3">
                <p className="text-micro uppercase tracking-wider text-ink-mist-dim">Сейчас</p>
                {building.effects.map((e) => <p key={e} className="text-sm text-path">{e}</p>)}
              </div>
            )}
            {building.next_effects.length > 0 && (
              <div className="mt-2">
                <p className="text-micro uppercase tracking-wider text-ink-mist-dim">Уровень {building.level + 1}</p>
                {building.next_effects.map((e) => <p key={e} className="text-sm text-ink-chalk">{e}</p>)}
              </div>
            )}
            {building.code === "stadium" && building.level > 0 && (
              <p className="mt-2 text-xs text-ink-mist">
                Сейчас с домашнего матча: <b className="text-legend">+{state.stadium.matchday_income}</b> монет
                (с отелем и ценами на билеты)
              </p>
            )}
            {building.next_cost != null ? (() => {
              const blocker = upgradeBlocker(state, building, balance);
              return (
                <>
                  <button
                    type="button" disabled={!!blocker || upgrading} onClick={() => onUpgrade(building.code)}
                    className="mt-4 flex min-h-[48px] w-full items-center justify-center gap-1.5 rounded-2xl bg-floodlight text-sm font-bold text-bg-base disabled:opacity-40"
                  >
                    {building.level ? "Улучшить" : "Построить"} · <IconCoin size={14} /> {building.next_cost.toLocaleString("ru-RU")}
                    {building.next_hours ? ` · ${hoursLabel(building.next_hours)}` : ""}
                  </button>
                  {building.next_cost_full != null && building.next_cost_full > building.next_cost && (
                    <p className="mt-1 text-center text-caption text-ink-mist">
                      Бухгалтерия сэкономила {(building.next_cost_full - building.next_cost).toLocaleString("ru-RU")} монет
                    </p>
                  )}
                  {blocker && <p className="mt-1 text-center text-xs text-legend">{blocker}</p>}
                </>
              );
            })() : (
              <p className="mt-4 text-center text-sm font-semibold text-legend">Максимальный уровень</p>
            )}
            {building.code === "stadium" && building.level > 0 && (
              <LookEditor state={state} onSave={onLook} pending={lookPending} />
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

export default function ClubBasePage() {
  useMarkSeen("club-base");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [picked, setPicked] = useState<ClubBaseCode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { data: state, isLoading } = useQuery({ queryKey: ["club-base"], queryFn: fetchClubBase, refetchInterval: 30_000 });
  const remaining = useCountdown(state?.construction?.ends_at);

  // A construction that just finished: pull the new level.
  useEffect(() => {
    if (state?.construction && remaining === 0) queryClient.invalidateQueries({ queryKey: ["club-base"] });
  }, [remaining, state?.construction, queryClient]);

  const apply = (next: ClubBaseState) => {
    hapticNotify("success");
    setError(null);
    if (next.new_balance != null) updateBalance(next.new_balance);
    queryClient.setQueryData(["club-base"], next);
    queryClient.invalidateQueries({ queryKey: ["academy"] });
  };
  const fail = (err: unknown) => {
    hapticNotify("error");
    setError(formatGameError(err, "Не получилось"));
  };
  const upgrade = useMutation({
    mutationFn: (code: string) => upgradeClubBaseBuilding(code, crypto.randomUUID()),
    onSuccess: (data) => { apply(data); setPicked(null); },
    onError: (err) => { fail(err); setPicked(null); },
  });
  const income = useMutation({
    mutationFn: () => claimClubBaseIncome(crypto.randomUUID()),
    onSuccess: (data) => { apply(data); setNotice(`Финансовый департамент принёс +${data.claimed ?? 0} монет 💼`); },
    onError: fail,
  });
  const look = useMutation({ mutationFn: setStadiumLook, onSuccess: apply, onError: fail });
  const speedup = useMutation({
    mutationFn: async () => {
      const invoice = await createClubBaseSpeedupInvoice();
      const status = await openTelegramInvoice(invoice.invoice_link);
      if (status === "cancelled") return null;
      if (status === "failed") throw new Error("Платёж не прошёл");
      for (let i = 0; i < 20; i++) {
        if ((await fetchClubBaseInvoiceStatus(invoice.payload_token)).status === "completed") return fetchClubBase();
        await new Promise((r) => setTimeout(r, 1000));
      }
      throw new Error("Оплата ещё обрабатывается — загляни через минуту");
    },
    onSuccess: (data) => data && apply(data),
    onError: fail,
  });

  if (isLoading || !state) {
    return <div className="h-72 animate-pulse rounded-3xl bg-bg-surface" aria-busy />;
  }
  const building = picked ? state.buildings.find((b) => b.code === picked) ?? null : null;
  const finance = state.buildings.filter((b) => b.group === "finance");
  const core = state.buildings.filter((b) => b.group === "core");

  const row = (b: ClubBaseBuilding) => (
    <button
      key={b.code} type="button" onClick={() => setPicked(b.code)}
      className={`flex min-h-[56px] items-center gap-3 rounded-2xl bg-bg-surface p-2.5 text-left active:scale-[0.99] ${b.building ? "ring-1 ring-legend/60" : ""}`}
    >
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-path/10 text-xl" aria-hidden>{b.emoji}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate font-display text-sm font-bold text-ink-chalk">{b.name}</span>
          <span className="shrink-0 font-mono text-xs text-ink-mist">{b.level}/{b.max_level}</span>
        </span>
        <span className="block truncate text-caption text-ink-mist">
          {b.building ? "🏗️ Строится…" : b.effects[0] ?? (b.locked && b.code !== "hq" ? "🔒 Нужна штаб-квартира" : b.next_effects[0] ?? "")}
        </span>
      </span>
    </button>
  );

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-ink-chalk">🏟️ Клубная база</h1>
          <p className="text-xs text-ink-mist">Твой тренировочный городок: стадион, корпуса и Академия</p>
        </div>
        <div className="text-right">
          <p className="font-display text-2xl font-bold text-path">{state.total_level}</p>
          <p className="text-micro uppercase tracking-wider text-ink-mist">уровень из {state.max_level + state.academy_max_level}</p>
        </div>
      </header>

      <FirstVisitHint
        id="club-base"
        title="Как растёт база"
        lines={[
          "Начни со штаб-квартиры: корпуса не бывают выше её уровня.",
          "У базы одна бригада — за раз строится один корпус (Академия тоже).",
          "Стадион, отель и маркетинг приносят монеты с домашних матчей «Карьеры тренера», магазин и спонсоры — каждый день.",
        ]}
      />

      <section className="rounded-3xl border border-path/25 bg-bg-surface p-2">
        <BaseMap state={state} onPick={setPicked} onAcademy={() => navigate("/academy")} />
        {state.construction ? (
          <div className="mt-2 flex items-center gap-2 rounded-2xl bg-legend/10 p-2.5">
            <span className="text-xl" aria-hidden>🏗️</span>
            <div className="min-w-0 flex-1 text-xs">
              <p className="truncate font-semibold text-ink-chalk">{state.construction.name} → уровень {state.construction.to_level}</p>
              <p className="font-mono text-legend">осталось {formatBuildTime(remaining)}</p>
            </div>
            {state.construction.owner === "base" ? (
              <button
                type="button" disabled={speedup.isPending || remaining === 0} onClick={() => speedup.mutate()}
                className="min-h-[40px] shrink-0 rounded-xl bg-amber-400 px-3 text-xs font-bold text-black disabled:opacity-40"
              >
                Ускорить ⭐ {state.construction.speedup_stars}
              </button>
            ) : (
              <button type="button" onClick={() => navigate("/academy")}
                      className="min-h-[40px] shrink-0 rounded-xl bg-white/10 px-3 text-xs font-semibold text-ink-chalk">
                В Академию →
              </button>
            )}
          </div>
        ) : (
          <p className="mt-2 text-center text-xs text-ink-mist">Бригада свободна — нажми на здание на карте</p>
        )}
      </section>

      {!state.enabled && <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-xs text-legend">Клубная база временно закрыта.</p>}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {notice && <p className="rounded-xl bg-path/10 px-3 py-2 text-xs text-path">{notice}</p>}

      <section className="flex items-center gap-3 rounded-2xl border border-legend/25 bg-legend/5 p-3" aria-label="Доход базы">
        <span className="text-2xl" aria-hidden>💼</span>
        <div className="min-w-0 flex-1 text-xs">
          <p className="font-semibold text-ink-chalk">Спонсоры и клубный магазин</p>
          {state.income.daily > 0 ? (
            <p className="text-ink-mist">
              +{state.income.daily} в день · накоплено <b className="text-legend">{state.income.pending}</b> из {state.income.cap}
            </p>
          ) : (
            <p className="text-ink-mist">Построй отдел маркетинга или клубный магазин — и монеты пойдут каждый день</p>
          )}
          {state.stadium.matchday_income > 0 && (
            <p className="text-ink-mist">🏟️ Домашний матч карьеры: +{state.stadium.matchday_income}</p>
          )}
        </div>
        <button
          type="button" disabled={!state.enabled || state.income.pending <= 0 || income.isPending} onClick={() => income.mutate()}
          className="min-h-[40px] shrink-0 rounded-xl bg-floodlight px-3 text-xs font-bold text-bg-base disabled:opacity-40"
        >
          Забрать
        </button>
      </section>

      <section className="flex flex-col gap-2" aria-label="Корпуса">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Корпуса</h2>
        {core.map(row)}
        <h2 className="mt-2 text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">🌱 Академия</h2>
        <button type="button" onClick={() => navigate("/academy")}
                className="flex min-h-[56px] items-center gap-3 rounded-2xl border border-path/25 bg-path/5 p-2.5 text-left">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-path/15 text-xl" aria-hidden>🌱</span>
          <span className="min-w-0 flex-1">
            <span className="flex items-baseline justify-between gap-2">
              <span className="font-display text-sm font-bold text-ink-chalk">Академия</span>
              <span className="font-mono text-xs text-ink-mist">{state.academy_level}/{state.academy_max_level}</span>
            </span>
            <span className="block text-caption text-ink-mist">Скауты, тренировки, интернат, штаб и зал славы →</span>
          </span>
        </button>
        <h2 className="mt-2 text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">💼 Финансовый департамент</h2>
        {finance.map(row)}
      </section>

      <button type="button" onClick={() => navigate("/ranking?metric=base_level")}
              className="min-h-[44px] rounded-2xl bg-white/5 text-xs font-semibold text-ink-mist">
        Рейтинг: уровень базы →
      </button>

      <BuildingSheet
        state={state} building={building} balance={balance} onClose={() => setPicked(null)}
        onUpgrade={(code) => upgrade.mutate(code)} upgrading={upgrade.isPending}
        onLook={(next) => look.mutate(next)} lookPending={look.isPending}
      />
    </div>
  );
}
