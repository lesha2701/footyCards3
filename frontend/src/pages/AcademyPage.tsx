import FirstVisitHint from "@/components/common/FirstVisitHint";
import { useMarkSeen } from "@/lib/seenSections";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  claimScoutReport,
  createAcademySpeedupInvoice,
  fetchAcademy,
  fetchAcademyInvoiceStatus,
  upgradeAcademyWing,
} from "@/api/academy";
import PlayerCard from "@/components/cards/PlayerCard";
import CardDetailModal from "@/components/collection/CardDetailModal";
import { useCardActions } from "@/components/collection/useCardActions";
import { cardLockProps } from "@/lib/cardLocks";
import { IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { hapticNotify, openTelegramInvoice } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { AcademyState, AcademyWing } from "@/types";

function useCountdown(endsAt: string | null | undefined): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!endsAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [endsAt]);
  return endsAt ? Math.max(0, Math.round((new Date(endsAt).getTime() - now) / 1000)) : 0;
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return h > 0 ? `${h} ч ${String(m).padStart(2, "0")} мин` : `${m}:${String(s).padStart(2, "0")}`;
}

// Campus layout: x position and base width of each wing's building.
const CAMPUS: Record<AcademyWing["code"], { x: number; w: number; label: string }> = {
  scout: { x: 8, w: 46, label: "Скауты" },
  dorm: { x: 60, w: 58, label: "Интернат" },
  hall: { x: 124, w: 72, label: "Зал славы" },
  training: { x: 202, w: 58, label: "База" },
  staff: { x: 266, w: 46, label: "Штаб" },
};

/** The academy as a little campus: one building per wing, a floor per
 * level (lit windows), scaffolding on the one under construction. Purely
 * illustrative — every number is in the wing cards below. */
function Campus({ state, onPick }: { state: AcademyState; onPick: (code: string) => void }) {
  const ground = 132;
  return (
    <svg viewBox="0 0 320 150" className="w-full" role="img" aria-label={`Здание Академии, уровень ${state.level}`}>
      <defs>
        <linearGradient id="campus-sky" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="rgb(var(--c-path))" stopOpacity="0.18" />
          <stop offset="1" stopColor="rgb(var(--c-path))" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="320" height="150" rx="16" fill="url(#campus-sky)" />
      <rect x="0" y={ground} width="320" height="18" fill="rgb(var(--c-path))" opacity="0.25" />
      {state.wings.map((wing) => {
        const spot = CAMPUS[wing.code];
        const floors = Math.max(1, wing.level);
        const height = 22 + floors * 16;
        const y = ground - height;
        return (
          <g key={wing.code} onClick={() => onPick(wing.code)} className="cursor-pointer" role="button" aria-label={wing.name}>
            <rect
              x={spot.x} y={y} width={spot.w} height={height} rx="4"
              fill={wing.level ? "rgb(var(--c-bg-raised))" : "rgb(var(--c-bg-surface))"}
              stroke="rgb(var(--c-path))" strokeOpacity={wing.level ? 0.8 : 0.3} strokeDasharray={wing.level ? undefined : "3 3"}
            />
            {Array.from({ length: floors }).map((_, f) =>
              [0, 1, 2].map((col) => (
                <rect
                  key={`${f}-${col}`}
                  x={spot.x + 6 + col * ((spot.w - 12) / 3)} y={ground - 14 - f * 16} width={(spot.w - 12) / 3 - 4} height="8" rx="1.5"
                  fill={wing.level > f ? "rgb(var(--c-legend))" : "rgb(var(--c-ink-mist-dim))"}
                  opacity={wing.level > f ? 0.9 : 0.25}
                />
              )),
            )}
            {wing.building && (
              <g stroke="rgb(var(--c-legend))" strokeWidth="1.5" opacity="0.9">
                <line x1={spot.x - 3} y1={ground} x2={spot.x - 3} y2={y - 10} />
                <line x1={spot.x + spot.w + 3} y1={ground} x2={spot.x + spot.w + 3} y2={y - 10} />
                <line x1={spot.x - 3} y1={y - 10} x2={spot.x + spot.w + 3} y2={y - 10} />
              </g>
            )}
            <text x={spot.x + spot.w / 2} y={y - (wing.building ? 14 : 4)} textAnchor="middle" fontSize="13">{wing.emoji}</text>
            <text x={spot.x + spot.w / 2} y={ground + 12} textAnchor="middle" fontSize="7.5" fill="rgb(var(--c-ink-mist))">
              {spot.label} {wing.level}/{wing.max_level}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function AcademyPage() {
  useMarkSeen("academy");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // The card sheet works here like in the collection: lock, hide, «В состав».
  const { detailCard: detail, setDetailCard: setDetail, hideMutation } = useCardActions([["academy"], ["collection"]]);
  const { data: state, isLoading } = useQuery({ queryKey: ["academy"], queryFn: fetchAcademy, refetchInterval: 30_000 });
  const remaining = useCountdown(state?.construction?.ends_at);

  // A construction that just finished: pull the new level.
  useEffect(() => {
    if (state?.construction && remaining === 0) queryClient.invalidateQueries({ queryKey: ["academy"] });
  }, [remaining, state?.construction, queryClient]);

  const apply = (next: AcademyState) => {
    hapticNotify("success");
    setError(null);
    if (next.new_balance != null) updateBalance(next.new_balance);
    queryClient.setQueryData(["academy"], next);
    queryClient.invalidateQueries({ queryKey: ["path"] });
  };
  const fail = (err: unknown) => {
    hapticNotify("error");
    setError(formatGameError(err, "Не получилось"));
  };
  const upgrade = useMutation({ mutationFn: (code: string) => upgradeAcademyWing(code, crypto.randomUUID()), onSuccess: apply, onError: fail });
  const report = useMutation({
    mutationFn: () => claimScoutReport(crypto.randomUUID()),
    onSuccess: (data) => {
      apply(data);
      setNotice(data.report?.player_name ? `Скауты нашли игрока: ${data.report.player_name}! 🌱` : `Таланта не нашли — +${data.report?.coins ?? 0} монет`);
      queryClient.invalidateQueries({ queryKey: ["collection"] });
    },
    onError: fail,
  });
  const speedup = useMutation({
    mutationFn: async () => {
      const invoice = await createAcademySpeedupInvoice();
      const status = await openTelegramInvoice(invoice.invoice_link);
      if (status === "cancelled") return null;
      if (status === "failed") throw new Error("Платёж не прошёл");
      for (let i = 0; i < 20; i++) {
        if ((await fetchAcademyInvoiceStatus(invoice.payload_token)).status === "completed") return fetchAcademy();
        await new Promise((r) => setTimeout(r, 1000));
      }
      throw new Error("Оплата ещё обрабатывается — загляни через минуту");
    },
    onSuccess: (data) => data && apply(data),
    onError: fail,
  });

  if (isLoading || !state) {
    return <div className="h-64 animate-pulse rounded-3xl bg-bg-surface" aria-busy />;
  }
  const building = state.construction ? state.wings.find((w) => w.code === state.construction!.building_code) : null;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-ink-chalk">🌱 Академия</h1>
          <p className="text-xs text-ink-mist">Растим молодых игроков и развиваем базу</p>
        </div>
        <div className="text-right">
          <p className="font-display text-2xl font-bold text-path">{state.level}</p>
          <p className="text-micro uppercase tracking-wider text-ink-mist">уровень из {state.max_level}</p>
        </div>
      </header>

      <FirstVisitHint
        id="academy"
        title="Как растёт Академия"
        lines={[
          "Карты Академии растут сами — за матчи, в которых стоят в составе.",
          "Корпуса за монеты дают бонусы всем картам Академии: опыт, попытки, задания.",
          "Открой карту → вкладка «Путь»: этапы, задания и покупка попыток.",
        ]}
      />

      <section className="rounded-3xl border border-path/25 bg-bg-surface p-3">
        <Campus state={state} onPick={(code) => document.getElementById(`wing-${code}`)?.scrollIntoView({ behavior: "smooth", block: "center" })} />
        {state.construction && building ? (
          <div className="mt-2 flex items-center gap-2 rounded-2xl bg-legend/10 p-2.5">
            <span className="text-xl" aria-hidden>🏗️</span>
            <div className="min-w-0 flex-1 text-xs">
              <p className="font-semibold text-ink-chalk">{building.name} → уровень {state.construction.to_level}</p>
              <p className="font-mono text-legend">осталось {formatDuration(remaining)}</p>
            </div>
            <button
              type="button"
              disabled={speedup.isPending || remaining === 0}
              onClick={() => speedup.mutate()}
              className="min-h-[40px] shrink-0 rounded-xl bg-amber-400 px-3 text-xs font-bold text-black disabled:opacity-40"
            >
              Ускорить ⭐ {state.construction.speedup_stars}
            </button>
          </div>
        ) : (
          <p className="mt-2 text-center text-xs text-ink-mist">Стройка свободна — выбери корпус для улучшения</p>
        )}
      </section>

      {!state.enabled && <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-xs text-legend">Академия временно закрыта.</p>}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {notice && <p className="rounded-xl bg-path/10 px-3 py-2 text-xs text-path">{notice}</p>}

      {state.scout_report && (
        <section className="flex items-center gap-3 rounded-2xl border border-path/25 bg-path/5 p-3" aria-label="Скаутский отчёт">
          <span className="text-2xl" aria-hidden>🔭</span>
          <div className="min-w-0 flex-1 text-xs">
            <p className="font-semibold text-ink-chalk">Скаутский отчёт</p>
            <p className="text-ink-mist">
              {state.scout_report.chance_pct}% — молодой игрок «Академии», иначе {state.scout_report.consolation_coins} монет
            </p>
            {state.scout_report.next_at && (
              <p className="text-ink-mist-dim">Следующий: {new Date(state.scout_report.next_at).toLocaleString("ru-RU")}</p>
            )}
          </div>
          <button
            type="button"
            disabled={!state.scout_report.available || report.isPending}
            onClick={() => report.mutate()}
            className="min-h-[40px] shrink-0 rounded-xl bg-floodlight px-3 text-xs font-bold text-bg-base disabled:opacity-40"
          >
            Получить
          </button>
        </section>
      )}

      <section className="flex flex-col gap-2" aria-label="Корпуса">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Корпуса</h2>
        {state.wings.map((wing) => (
          <article key={wing.code} id={`wing-${wing.code}`} className={`rounded-2xl bg-bg-surface p-3 ${wing.building ? "ring-1 ring-legend/60" : ""}`}>
            <div className="flex items-start gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-path/10 text-2xl" aria-hidden>{wing.emoji}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="font-display text-sm font-bold text-ink-chalk">{wing.name}</p>
                  <p className="font-mono text-xs text-ink-mist">{wing.level}/{wing.max_level}</p>
                </div>
                <div className="mt-1 flex gap-1" aria-hidden>
                  {Array.from({ length: wing.max_level }).map((_, i) => (
                    <span key={i} className={`h-1.5 flex-1 rounded-full ${i < wing.level ? "bg-path" : "bg-white/10"}`} />
                  ))}
                </div>
                <p className="mt-1.5 text-caption text-ink-mist">{wing.about}</p>
                {wing.effect && <p className="mt-1 text-xs text-path">Сейчас: {wing.effect}</p>}
                {wing.next_effect && <p className="text-xs text-ink-chalk">Дальше: {wing.next_effect}</p>}
              </div>
            </div>
            {wing.next_cost != null ? (
              <button
                type="button"
                disabled={!state.enabled || !!state.construction || upgrade.isPending || balance < wing.next_cost}
                onClick={() => upgrade.mutate(wing.code)}
                className="mt-2.5 flex min-h-[44px] w-full items-center justify-center gap-1.5 rounded-xl bg-bg-raised text-xs font-semibold text-ink-chalk disabled:opacity-40"
              >
                {wing.building ? "Строится…" : wing.level ? "Улучшить" : "Построить"} · <IconCoin size={12} /> {wing.next_cost.toLocaleString("ru-RU")}
                {wing.next_hours ? ` · ${wing.next_hours} ч` : ""}
              </button>
            ) : (
              <p className="mt-2 text-center text-xs font-semibold text-legend">Максимальный уровень</p>
            )}
          </article>
        ))}
      </section>

      <section className="rounded-2xl bg-bg-surface p-3" aria-label="Игроки Академии">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Мои игроки · {state.academy_cards}</h2>
          <button type="button" onClick={() => navigate("/packs")} className="text-xs font-semibold text-path">Пак «Академия» →</button>
        </div>
        {state.cards.length ? (
          <div className="grid grid-cols-3 gap-2">
            {state.cards.map((card) => (
              <PlayerCard
                key={card.id}
                player={card.player}
                size="sm"
                pathStage={card.path_stage}
                prestige={card.prestige}
                talentOverride={card.talent_override}
                {...cardLockProps(card)}
                onClick={() => setDetail(card)}
              />
            ))}
          </div>
        ) : (
          <p className="text-xs text-ink-mist">Пока нет игроков — открой пак «Академия» или получи скаутский отчёт.</p>
        )}
      </section>

      <button type="button" onClick={() => navigate("/base")} className="min-h-[44px] rounded-2xl border border-legend/25 bg-legend/5 text-xs font-semibold text-ink-chalk">
        🏟️ Академия — часть Клубной базы: стадион, медцентр, финансы →
      </button>

      <button type="button" onClick={() => navigate("/ranking")} className="min-h-[44px] rounded-2xl bg-white/5 text-xs font-semibold text-ink-mist">
        Рейтинг: уровень и престиж Академии →
      </button>

      {detail && (
        <CardDetailModal
          card={detail}
          onClose={() => setDetail(null)}
          onSell={() => navigate("/collection?tab=mine")}
          onToggleHidden={(hidden) => hideMutation.mutate({ id: detail.id, hidden })}
          hiddenPending={hideMutation.isPending}
        />
      )}
    </div>
  );
}
