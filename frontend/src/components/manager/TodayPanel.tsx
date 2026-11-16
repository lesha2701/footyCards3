import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { claimManagerOnboarding, fetchManagerSummary, type ManagerSummary } from "@/api/manager";
import { goTo } from "@/lib/managerFocus";
import { eur } from "@/lib/managerMoney";
import { hapticNotify } from "@/lib/telegram";

/** The season as a line: the window, the rounds as dots, the results. */
export function Timeline({ view }: { view: ManagerSummary }) {
  const { rounds } = view.season;
  const league = view.league;
  const played = league?.status === "active" ? league.rounds_played : league?.status === "finished" ? league.total_rounds : 0;
  const total = league?.total_rounds || rounds;
  const window = view.season.transfers_open && league?.status !== "active";
  const done = league?.status === "finished";
  return (
    <div className="flex items-center gap-1.5" data-testid="season-timeline" aria-label={`Тур ${played} из ${total}`}>
      <span className={`shrink-0 rounded-full px-2 py-0.5 text-micro font-bold ${window ? "bg-accent-lime text-bg-base" : "bg-white/10 text-ink-mist"}`}>Окно</span>
      <span className="flex min-w-0 flex-1 items-center gap-[3px]">
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={`h-1.5 flex-1 rounded-full ${i < played ? "bg-amber-300" : i === played && league?.status === "active" ? "animate-pulse bg-amber-300/60" : "bg-white/10"}`}
          />
        ))}
      </span>
      <span className={`shrink-0 rounded-full px-2 py-0.5 text-micro font-bold ${done ? "bg-amber-300 text-bg-base" : "bg-white/10 text-ink-mist"}`}>Итоги</span>
    </div>
  );
}

/** «Сегодня в клубе» at the top of the mode: the one thing to do now as a
 * big card (the rest folded under «ещё N»), and the first-season checklist as
 * one line with its next step. The window's countdown is the hero's light. */
export default function TodayPanel({ onTab, onError }: { onTab: (tab: string) => void; onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "summary"], queryFn: fetchManagerSummary, refetchInterval: 60_000 });
  const [more, setMore] = useState(false);
  const [steps, setSteps] = useState(false);
  const claim = useMutation({
    mutationFn: claimManagerOnboarding,
    onSuccess: (v) => {
      hapticNotify("success");
      queryClient.setQueryData(["manager", "summary"], v);
      queryClient.invalidateQueries({ queryKey: ["manager"] });
    },
    onError,
  });
  if (!data?.club) return null;
  const list = data.club.checklist;
  const items = data.today.filter((i) => i.code !== "window");
  if (items.length === 0 && !list) return null;
  const open = (tab: string, target?: string) => { onTab(tab); goTo(target); };
  const [top, ...rest] = items;
  const done = list ? list.steps.filter((x) => x.done).length : 0;
  const next = list?.steps.find((x) => !x.done);
  return (
    <section className="flex flex-col gap-2" data-testid="today-panel">
      {top && (
        <button
          onClick={() => open(top.tab, top.target)}
          data-testid="today-top"
          className={`flex items-center gap-3 rounded-2xl p-3 text-left active:scale-[0.98] ${top.urgent ? "bg-accent-lime/15 ring-1 ring-accent-lime/50" : "bg-bg-surface ring-1 ring-white/5"}`}
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-bg-base/50 text-xl">{top.icon}</span>
          <span className="min-w-0 flex-1">
            <span className="block text-micro font-bold uppercase tracking-[0.18em] text-ink-mist">Сейчас главное</span>
            <span className="block text-sm font-semibold leading-snug text-ink-chalk">{top.text}</span>
          </span>
          <span className="shrink-0 rounded-xl bg-floodlight px-3 py-2 text-xs font-bold text-bg-base">Сделать</span>
        </button>
      )}
      {rest.length > 0 && (
        <>
          <button onClick={() => setMore(!more)} className="self-start rounded-full bg-bg-surface px-3 py-1 text-micro font-semibold text-ink-mist" data-testid="today-more">
            {more ? "Свернуть" : `Ещё ${rest.length} ${rest.length === 1 ? "дело" : rest.length < 5 ? "дела" : "дел"}`} {more ? "▴" : "▾"}
          </button>
          {more && rest.map((item) => (
            <button
              key={`${item.code}-${item.text}`}
              onClick={() => open(item.tab, item.target)}
              className={`flex items-center gap-2 rounded-xl px-2.5 py-2 text-left text-xs active:scale-[0.98] ${item.urgent ? "bg-accent-lime/10 font-semibold text-ink-chalk" : "bg-bg-surface text-ink-chalk"}`}
            >
              <span className="text-base leading-none">{item.icon}</span>
              <span className="min-w-0 flex-1">{item.text}</span>
              <span className="text-ink-mist">›</span>
            </button>
          ))}
        </>
      )}
      {list && (
        <div className="flex flex-col gap-1.5 rounded-2xl bg-gradient-to-br from-amber-400/15 to-transparent p-3 ring-1 ring-amber-300/30" data-testid="onboarding">
          <button onClick={() => setSteps(!steps)} className="flex items-center gap-2 text-left">
            <span className="text-base">🎯</span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center justify-between text-xs font-bold text-amber-100">
                <span>Первый сезон · {done}/{list.steps.length}</span>
                <span className="text-micro font-semibold text-amber-200">бонус {eur(list.bonus)}</span>
              </span>
              <span className="mt-1 flex h-1.5 overflow-hidden rounded-full bg-white/10">
                <span className="bg-amber-300" style={{ width: `${(done / Math.max(1, list.steps.length)) * 100}%` }} />
              </span>
            </span>
            <span className={`text-ink-mist transition ${steps ? "rotate-90" : ""}`}>›</span>
          </button>
          {!steps && next && (
            <button onClick={() => open(next.tab, next.target)} className="flex items-center gap-2 rounded-xl bg-bg-base/40 px-2.5 py-2 text-left text-xs text-ink-chalk">
              <span className="text-micro font-bold uppercase text-amber-200">Дальше:</span>
              <span className="min-w-0 flex-1">{next.title}</span>
              <span className="text-ink-mist">›</span>
            </button>
          )}
          {steps && list.steps.map((x) => (
            <button key={x.code} disabled={x.done} onClick={() => open(x.tab, x.target)}
              className={`flex items-center gap-2 text-left text-xs ${x.done ? "text-ink-mist line-through" : "text-ink-chalk"}`}>
              <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] ${x.done ? "bg-accent-lime text-bg-base" : "ring-1 ring-white/30"}`}>{x.done ? "✓" : ""}</span>
              {x.title}
            </button>
          ))}
          {list.ready && (
            <button onClick={() => claim.mutate()} disabled={claim.isPending}
              className="mt-1 rounded-xl bg-gradient-to-r from-amber-300 to-yellow-300 py-2 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50">
              Забрать {eur(list.bonus)} в бюджет
            </button>
          )}
        </div>
      )}
    </section>
  );
}
