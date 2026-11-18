import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  claimManagerAchievement,
  fetchManagerDecisions,
  setManagerBudget,
  type ManagerBudgetView,
  type ManagerDecisions,
  type ManagerFinanceReview,
  type ManagerTodayTab,
} from "@/api/manager";
import { ListSkeleton } from "@/components/common/Skeleton";
import { eur } from "@/lib/managerMoney";
import { hapticNotify } from "@/lib/telegram";

const KEY = ["manager", "decisions"];
const BAR = ["bg-sky-400", "bg-violet-400", "bg-emerald-400", "bg-amber-300"];

function useDecisions(onError: (e: unknown) => void) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: KEY, queryFn: fetchManagerDecisions });
  const done = (v: ManagerDecisions) => {
    hapticNotify("success");
    queryClient.setQueryData(KEY, v);
    void queryClient.invalidateQueries({ queryKey: ["manager", "summary"] });
    void queryClient.invalidateQueries({ queryKey: ["manager", "office"] });
  };
  const plan = useMutation({ mutationFn: setManagerBudget, onSuccess: done, onError });
  const claim = useMutation({ mutationFn: claimManagerAchievement, onSuccess: done, onError });
  return { data, plan, claim };
}

/** «📒 Бюджет»: the season plan by articles (wages / transfers / the club,
 * the rest is the reserve), how much is spent, the hands-on meter and the
 * analyst's finance review. Numbers come from the server's config. */
export function BudgetPanel({ onError, onTab }: { onError: (e: unknown) => void; onTab: (t: ManagerTodayTab) => void }) {
  const { data, plan } = useDecisions(onError);
  const [draft, setDraft] = useState<Record<string, number> | null>(null);
  if (!data) return <ListSkeleton />;
  const b = data.budget;
  const editing = draft !== null;
  return (
    <div className="flex flex-col gap-3" data-testid="budget-panel">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-500/25 via-bg-surface to-bg-surface p-4 ring-1 ring-emerald-300/30">
        <div className="pointer-events-none absolute -right-6 -top-6 text-[96px] leading-none opacity-10">📒</div>
        <p className="text-micro font-bold uppercase tracking-[0.18em] text-emerald-200">Бюджет сезона</p>
        <p className="mt-1 font-display text-2xl font-black text-ink-chalk">{eur(b.pot)}</p>
        <p className="mt-1 text-caption text-ink-mist">
          Распредели деньги по статьям. Перерасход статьи больше чем на {b.tolerance_pct}% — минус {b.fans_penalty} болельщиков за каждую;
          уложился во все — бонус {b.bonus_pct}% от сэкономленного (до {eur(b.bonus_max)}).
        </p>
        {b.last && (
          <p className={`mt-2 rounded-xl px-2.5 py-1.5 text-caption ${b.last.ok ? "bg-emerald-400/15 text-emerald-100" : "bg-red-400/15 text-red-200"}`}>
            Прошлый сезон: {b.last.ok ? `в плане, бонус ${eur(b.last.bonus)}` : `перерасход (${b.last.fans} болельщиков)`}
          </p>
        )}
      </section>

      {editing ? (
        <PlanEditor b={b} draft={draft} setDraft={setDraft} busy={plan.isPending}
          onSave={() => plan.mutate(draft, { onSuccess: () => setDraft(null) })} onCancel={() => setDraft(null)} />
      ) : (
        <section className="flex flex-col gap-2.5 rounded-2xl bg-bg-surface p-4" data-focus="budget">
          {b.plan ? (
            <>
              {b.articles.map((a, i) => <ArticleBar key={a.code} a={a} color={BAR[i % BAR.length]} />)}
              <p className="flex justify-between text-caption text-ink-mist"><span>🛟 Резерв</span><b className="text-ink-chalk">{eur(b.reserve ?? 0)}</b></p>
            </>
          ) : (
            <p className="text-caption text-ink-mist">
              {b.window ? "План ещё не составлен — без плана нет ни бонуса, ни штрафа." : "План на этот сезон не составляли. Следующий — в трансферное окно."}
            </p>
          )}
          {b.result && (
            <p className={`text-caption font-semibold ${b.result.ok ? "text-emerald-300" : "text-red-300"}`}>
              Итог: {b.result.ok ? `уложился, бонус ${eur(b.result.bonus)}` : `перерасход, ${b.result.fans} болельщиков`}
            </p>
          )}
          {b.window && !b.result && (
            <button data-testid="budget-edit"
              onClick={() => setDraft({ ...(b.plan ?? b.suggest) })}
              className="rounded-xl bg-gradient-to-r from-emerald-300 to-lime-300 py-2.5 text-sm font-bold text-bg-base active:scale-95">
              {b.plan ? "Изменить план" : "Составить план"}
            </button>
          )}
        </section>
      )}

      <HandsOn b={b} onTab={onTab} />
      {data.review ? <FinanceReview review={data.review} /> : (
        <button onClick={() => onTab("staff")} className="rounded-2xl bg-sky-500/10 p-3 text-left text-caption text-sky-100 ring-1 ring-sky-300/30">
          📊 Разбор «куда ушли деньги и что окупилось» готовит Аналитик — найми его в «Штабе» ›
        </button>
      )}
    </div>
  );
}

function ArticleBar({ a, color }: { a: ManagerBudgetView["articles"][number]; color: string }) {
  const planned = a.plan ?? 0;
  const share = planned > 0 ? Math.min(100, (a.spent * 100) / planned) : a.spent > 0 ? 100 : 0;
  return (
    <div>
      <p className="flex justify-between text-caption">
        <span className="text-ink-chalk">{a.emoji} {a.name}</span>
        <span className={a.over ? "font-bold text-red-300" : "text-ink-mist"}>{eur(a.spent)} / {eur(planned)}</span>
      </p>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full ${a.over ? "bg-red-400" : color}`} style={{ width: `${share}%` }} />
      </div>
    </div>
  );
}

function PlanEditor({ b, draft, setDraft, busy, onSave, onCancel }: {
  b: ManagerBudgetView; draft: Record<string, number>; setDraft: (d: Record<string, number>) => void;
  busy: boolean; onSave: () => void; onCancel: () => void;
}) {
  const sum = Object.values(draft).reduce((s, v) => s + v, 0);
  const step = Math.max(1, Math.round(b.pot / 100));
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4 ring-1 ring-emerald-300/30" data-focus="budget" data-testid="budget-editor">
      {b.articles.map((a) => {
        const others = sum - (draft[a.code] ?? 0);
        return (
          <label key={a.code} className="flex flex-col gap-1">
            <span className="flex justify-between text-caption text-ink-chalk">
              <span>{a.emoji} {a.name}</span><b>{eur(draft[a.code] ?? 0)}</b>
            </span>
            <input type="range" min={0} max={b.pot} step={step} value={draft[a.code] ?? 0} aria-label={a.name}
              onChange={(e) => setDraft({ ...draft, [a.code]: Math.min(Number(e.target.value), b.pot - others) })}
              className="accent-emerald-300" />
          </label>
        );
      })}
      <p className="flex justify-between rounded-xl bg-bg-raised px-3 py-2 text-caption">
        <span className="text-ink-mist">🛟 Резерв</span><b className="text-ink-chalk">{eur(b.pot - sum)}</b>
      </p>
      <div className="grid grid-cols-3 gap-2">
        <button onClick={() => setDraft({ ...b.suggest })} className="rounded-xl bg-bg-raised py-2 text-xs font-bold text-ink-mist">Совет</button>
        <button onClick={onCancel} className="rounded-xl bg-bg-raised py-2 text-xs font-bold text-ink-mist">Отмена</button>
        <button onClick={onSave} disabled={busy || sum > b.pot} data-testid="budget-save"
          className="rounded-xl bg-emerald-300 py-2 text-xs font-bold text-bg-base disabled:opacity-50">Утвердить</button>
      </div>
    </section>
  );
}

/** «Ручное управление»: the share of decisions the president made himself. */
function HandsOn({ b, onTab }: { b: ManagerBudgetView; onTab: (t: ManagerTodayTab) => void }) {
  const { acts } = b;
  const ready = acts.total >= b.hands_on_min;
  return (
    <section className="rounded-2xl bg-bg-surface p-4" data-testid="hands-on">
      <p className="flex items-center justify-between text-sm font-bold text-ink-chalk">
        <span>🎛 Стиль управления</span>
        <span className="text-micro font-semibold text-ink-mist">сам {acts.me} · помощница {acts.assistant}</span>
      </p>
      <div className="mt-2 flex h-3 overflow-hidden rounded-full bg-white/10">
        <div className="h-full bg-gradient-to-r from-amber-300 to-orange-400" style={{ width: `${acts.total ? acts.share : 0}%` }} />
        <div className="h-full flex-1 bg-violet-400/50" />
      </div>
      <p className="mt-2 text-caption text-ink-mist">
        {ready
          ? <>Сам принял {acts.share}% решений — в конце сезона: +{b.hands_on.fans} болельщиков и {eur(b.hands_on.money)}.</>
          : <>Прими хотя бы {b.hands_on_min} решений за сезон — чем больше сам, тем больше бонус болельщиков и денег.</>}
        {" "}Делегируешь помощнице — удобно, но без бонуса.{" "}
        <button onClick={() => onTab("staff")} className="font-bold text-violet-200">Правила ›</button>
      </p>
    </section>
  );
}

/** The analyst's report: where the money went, what paid off, advice. */
export function FinanceReview({ review }: { review: ManagerFinanceReview }) {
  return (
    <section className="flex flex-col gap-2.5 rounded-2xl bg-gradient-to-br from-sky-500/15 to-bg-surface p-4 ring-1 ring-sky-300/25" data-testid="finance-review">
      <p className="text-sm font-bold text-ink-chalk">📊 Разбор финансов {review.finished ? "прошлого сезона" : "сезона"}</p>
      <div className="grid grid-cols-3 gap-2 text-center">
        <Num label="Доход" value={eur(review.income)} tone="text-emerald-300" />
        <Num label="Расход" value={eur(review.expense)} tone="text-red-300" />
        <Num label="Итог" value={eur(review.profit)} tone={review.profit >= 0 ? "text-emerald-200" : "text-red-200"} />
      </div>
      {review.costs.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-micro font-bold uppercase tracking-[0.14em] text-ink-mist">Куда ушли деньги</p>
          {review.costs.map((c) => (
            <p key={c.label} className="flex justify-between text-caption text-ink-chalk"><span>{c.label}</span><span className="text-ink-mist">{eur(c.amount)} · {c.share}%</span></p>
          ))}
        </div>
      )}
      {review.deals.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-micro font-bold uppercase tracking-[0.14em] text-ink-mist">Что окупилось</p>
          {review.deals.map((d) => (
            <p key={d.code} className="flex justify-between text-caption text-ink-chalk">
              <span>{d.net >= 0 ? "✅" : "❌"} {d.label}</span><b className={d.net >= 0 ? "text-emerald-300" : "text-red-300"}>{eur(d.net)}</b>
            </p>
          ))}
        </div>
      )}
      {review.advice.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-xl bg-black/20 p-2.5">
          {review.advice.map((a) => <li key={a} className="text-caption text-sky-100">💡 {a}</li>)}
        </ul>
      )}
    </section>
  );
}

function Num({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="rounded-xl bg-black/20 px-1 py-2">
      <p className="text-micro text-ink-mist">{label}</p>
      <p className={`text-xs font-black ${tone}`}>{value}</p>
    </div>
  );
}

/** «🏅 Достижения президента»: goals with a reward into the budget. */
export function AchievementsPanel({ onError }: { onError: (e: unknown) => void }) {
  const { data, claim } = useDecisions(onError);
  if (!data) return <ListSkeleton />;
  const list = [...data.achievements].sort((a, b) => Number(b.done && !b.claimed) - Number(a.done && !a.claimed) || Number(a.claimed) - Number(b.claimed));
  const got = data.achievements.filter((a) => a.claimed).length;
  return (
    <div className="flex flex-col gap-3" data-testid="achievements" data-focus="achievements">
      <p className="px-1 text-caption text-ink-mist">Получено {got} из {data.achievements.length}. Награда — в бюджет клуба.</p>
      <div className="grid grid-cols-2 gap-2">
        {list.map((a) => {
          const ready = a.done && !a.claimed;
          return (
            <section key={a.code}
              className={`flex flex-col gap-1.5 rounded-2xl p-3 ring-1 ${a.claimed ? "bg-amber-400/10 ring-amber-300/40" : ready ? "bg-accent-lime/10 ring-accent-lime/50" : "bg-bg-surface ring-white/5"}`}>
              <span className={`text-3xl leading-none ${a.done ? "" : "opacity-40 grayscale"}`}>{a.emoji}</span>
              <p className="text-xs font-bold text-ink-chalk">{a.name}</p>
              <p className="text-micro text-ink-mist">{a.about}</p>
              <div className="mt-auto h-1.5 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-amber-300" style={{ width: `${Math.min(100, (a.progress * 100) / Math.max(1, a.goal))}%` }} />
              </div>
              {ready ? (
                <button onClick={() => claim.mutate(a.code)} disabled={claim.isPending} data-testid={`claim-${a.code}`}
                  className="rounded-lg bg-accent-lime py-1.5 text-micro font-bold text-bg-base active:scale-95 disabled:opacity-50">
                  Забрать {eur(a.reward)}
                </button>
              ) : (
                <p className="text-micro font-semibold text-amber-200">{a.claimed ? "✓ получено" : `+${eur(a.reward)}`}</p>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
