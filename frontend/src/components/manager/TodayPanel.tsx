import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { claimManagerOnboarding, fetchManagerSummary, type ManagerSummary, type ManagerTodayTab } from "@/api/manager";
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

/** «Сегодня в клубе» at the top of the mode: the season line, what to do now
 * (a tap opens its tab) and the first-season checklist with its bonus. */
export default function TodayPanel({ onTab, onError }: { onTab: (tab: ManagerTodayTab) => void; onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "summary"], queryFn: fetchManagerSummary, refetchInterval: 60_000 });
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
  if (data.today.length === 0 && !list) return null;
  return (
    <section className="flex flex-col gap-2.5 rounded-2xl bg-bg-surface p-3" data-testid="today-panel">
      {data.today.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-micro font-bold uppercase tracking-[0.18em] text-ink-mist">Сегодня в клубе</p>
          {data.today.slice(0, 4).map((item) => (
            <button
              key={`${item.code}-${item.text}`}
              onClick={() => onTab(item.tab)}
              className={`flex items-center gap-2 rounded-xl px-2.5 py-2 text-left text-xs active:scale-[0.98] ${item.urgent ? "bg-accent-lime/15 font-semibold text-ink-chalk ring-1 ring-accent-lime/40" : "bg-bg-raised text-ink-chalk"}`}
            >
              <span className="text-base leading-none">{item.icon}</span>
              <span className="min-w-0 flex-1">{item.text}</span>
              <span className="text-ink-mist">›</span>
            </button>
          ))}
        </div>
      )}
      {list && (
        <div className="flex flex-col gap-1.5 rounded-xl bg-gradient-to-br from-amber-400/15 to-transparent p-2.5 ring-1 ring-amber-300/30" data-testid="onboarding">
          <p className="flex items-center justify-between text-xs font-bold text-amber-100">
            <span>🎯 Первый сезон</span>
            <span className="text-micro font-semibold text-amber-200">бонус {eur(list.bonus)}</span>
          </p>
          {list.steps.map((s) => (
            <button key={s.code} disabled={s.done} onClick={() => onTab(s.tab)}
              className={`flex items-center gap-2 text-left text-xs ${s.done ? "text-ink-mist line-through" : "text-ink-chalk"}`}>
              <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] ${s.done ? "bg-accent-lime text-bg-base" : "ring-1 ring-white/30"}`}>{s.done ? "✓" : ""}</span>
              {s.title}
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
