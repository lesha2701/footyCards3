import { useNavigate } from "react-router-dom";

import { Skeleton } from "@/components/common/Skeleton";
import { IconGift, IconPack, IconTarget, type IconProps } from "@/components/icons";
import { useTodayClaims } from "@/components/home/useTodayClaims";
import { formatClock, useTodayState } from "@/lib/today";
import type { WheelStatus } from "@/types";

/** «Сегодня» in one compact card: a summary line with «Забрать всё» and
 * four small items (calendar, tasks, free pack, wheel). A ready item
 * claims on tap; the rest open their page. */
export default function TodayCard({ wheel }: { wheel?: WheelStatus | null }) {
  const navigate = useNavigate();
  const { calendar, taskList, freePack, claimableTasks, dailyReady, freePackReady } = useTodayState();
  const { claimAll, freePack: freePackMutation, summary, error, busy } = useTodayClaims();

  if (!calendar && !taskList && !freePack) {
    return <Skeleton className="h-[116px] rounded-3xl" />;
  }

  const tasksInProgress = [...(taskList?.regular ?? []), ...(taskList?.premium ?? [])].filter((t) => !t.is_completed).length;
  const wheelReady = !!wheel && wheel.free_spins_remaining > 0;
  const instant = (dailyReady ? 1 : 0) + claimableTasks.length;
  const readyCount = instant + (freePackReady ? 1 : 0) + (wheelReady ? 1 : 0);

  return (
    <section className="rounded-3xl bg-bg-surface p-3">
      <div className="mb-2.5 flex items-center justify-between gap-2 px-1">
        <div>
          <h2 className="font-display text-base font-bold text-ink-chalk">Сегодня</h2>
          <p className="text-xs text-ink-mist">
            {readyCount ? `Готово к получению: ${readyCount}` : "Всё забрано — загляни позже"}
          </p>
        </div>
        {instant > 0 && (
          <button
            onClick={() => claimAll.mutate({ daily: dailyReady, tasks: claimableTasks })}
            disabled={busy}
            className="animate-claim-glow shrink-0 rounded-full bg-floodlight px-3.5 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-60"
          >
            {claimAll.isPending ? "Забираем..." : "Забрать всё"}
          </button>
        )}
      </div>

      <div className="grid auto-cols-fr grid-flow-col gap-1.5">
        {calendar && (
          <TodayItem
            Icon={IconGift}
            label="Вход"
            status={dailyReady ? "Забрать" : `${calendar.claimed_count}/${calendar.days_in_month}`}
            ready={dailyReady}
            onClick={() => (dailyReady ? claimAll.mutate({ daily: true, tasks: [] }) : navigate("/profile"))}
            disabled={busy}
          />
        )}
        {taskList && (
          <TodayItem
            Icon={IconTarget}
            label="Задания"
            status={claimableTasks.length ? `${claimableTasks.length} готово` : tasksInProgress ? `${tasksInProgress} в работе` : "Все"}
            ready={claimableTasks.length > 0}
            onClick={() =>
              claimableTasks.length ? claimAll.mutate({ daily: false, tasks: claimableTasks }) : navigate("/tasks")
            }
            disabled={busy}
          />
        )}
        {freePack && (
          <TodayItem
            Icon={IconPack}
            label="Пак"
            status={freePackReady ? (freePackMutation.isPending ? "..." : "Открыть") : formatClock(freePack.available_at)}
            ready={freePackReady}
            onClick={() => freePackReady && freePackMutation.mutate()}
            disabled={busy || !freePackReady}
          />
        )}
        {wheel && (
          <TodayItem
            Icon={IconGift}
            label="Колесо"
            status={wheelReady ? `×${wheel.free_spins_remaining}` : formatClock(wheel.next_free_spin_reset_at)}
            ready={wheelReady}
            onClick={() => navigate("/wheel")}
          />
        )}
      </div>

      {(summary || error) && (
        <p role="status" className={`mt-2 px-1 text-xs ${error ? "text-red-400" : "text-accent-lime"}`}>
          {error ?? summary}
        </p>
      )}
    </section>
  );
}

function TodayItem({
  Icon, label, status, ready, onClick, disabled,
}: {
  Icon: (props: IconProps) => JSX.Element;
  label: string;
  status: string;
  ready?: boolean;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled && ready}
      className={`flex min-w-0 flex-col items-center gap-1 rounded-2xl px-1 py-2 active:scale-95 ${
        ready ? "bg-accent-lime/10 ring-1 ring-accent-lime/30" : "bg-bg-raised/60"
      }`}
    >
      <span className={ready ? "text-accent-lime" : "text-ink-mist"}>
        <Icon size={18} />
      </span>
      <span className="w-full truncate text-center text-caption font-semibold text-ink-chalk">{label}</span>
      <span className={`w-full truncate text-center text-micro ${ready ? "font-bold text-accent-lime" : "text-ink-mist"}`}>
        {status}
      </span>
    </button>
  );
}
