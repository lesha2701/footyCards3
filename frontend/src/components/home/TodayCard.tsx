import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimDailyReward } from "@/api/dailyRewards";
import { claimFreePack } from "@/api/freePack";
import { claimTask } from "@/api/tasks";
import { IconCheck, IconClock, IconGift, IconPack, IconTarget, type IconProps } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { formatClock, useTodayState } from "@/lib/today";
import { useAuthStore } from "@/store/authStore";
import type { Task, WheelStatus } from "@/types";

/** Everything the player can collect today in one place: daily reward,
 * finished tasks, free pack and wheel spins — with one "Забрать всё" button
 * instead of a profile trip plus a tasks trip plus a banner tap. */
export default function TodayCard({ wheel }: { wheel?: WheelStatus | null }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { calendar, taskList, freePack, claimableTasks, dailyReady, freePackReady } = useTodayState();
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A task that rewards a pack plays the pack-opening screen, so claim-all
  // only takes the instant ones and leaves the pack tasks one tap away.
  const instantTasks = claimableTasks.filter((t) => !t.reward_pack_name);
  const packTasks = claimableTasks.filter((t) => t.reward_pack_name);

  const refresh = () => {
    for (const key of [["daily-reward-calendar"], ["tasks"], ["collection"], ["card-skills"]]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };

  const claimAll = useMutation({
    mutationFn: async ({ daily, tasks }: { daily: boolean; tasks: Task[] }) => {
      let coins = 0;
      let balance: number | null = null;
      const extras: string[] = [];
      if (daily) {
        const r = await claimDailyReward();
        coins += r.coins_awarded;
        balance = r.new_balance;
        if (r.granted_card) extras.push(`карточка ${r.granted_card.player.display_name}`);
        if (r.granted_pack_name) extras.push(`пак «${r.granted_pack_name}»`);
      }
      for (const task of tasks) {
        const r = await claimTask(task.user_task_id);
        coins += r.reward_coins;
        balance = r.new_balance;
        if (r.granted_skill_tokens) extras.push(`жетоны ×${r.granted_skill_tokens.quantity}`);
      }
      return { coins, balance, extras };
    },
    onSuccess: ({ coins, balance, extras }) => {
      if (balance !== null) updateBalance(balance);
      hapticNotify("success");
      setError(null);
      setSummary(["Забрано", coins ? `+${coins} монет` : null, ...extras].filter(Boolean).join(" · "));
      refresh();
    },
    onError: (err) => {
      setError(formatGameError(err, "Не удалось забрать награды"));
      refresh();
    },
  });

  const freePackMutation = useMutation({
    mutationFn: claimFreePack,
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["free-pack-status"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      navigate(`/packs/${data.pack.id}/open`, { state: { result: data } });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось получить пак")),
  });

  if (!calendar && !taskList && !freePack) return null;

  const instantReady = dailyReady || instantTasks.length > 0;
  const tasksInProgress = [...(taskList?.regular ?? []), ...(taskList?.premium ?? [])].filter((t) => !t.is_completed).length;
  const busy = claimAll.isPending || freePackMutation.isPending;

  return (
    <section className="rounded-3xl bg-bg-surface p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">Сегодня</h2>
        {instantReady && (
          <button
            onClick={() => claimAll.mutate({ daily: dailyReady, tasks: instantTasks })}
            disabled={busy}
            className="rounded-full bg-accent-lime px-3 py-1.5 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-60"
          >
            {claimAll.isPending ? "Забираем..." : "Забрать всё"}
          </button>
        )}
      </div>

      <div className="flex flex-col divide-y divide-white/5">
        {calendar && (
          <TodayRow
            Icon={IconGift}
            title="Ежедневная награда"
            subtitle={dailyReady ? `День ${calendar.current_streak} серии` : "Уже забрано · завтра новая"}
            ready={dailyReady}
            done={!dailyReady}
            onClick={() => (dailyReady ? claimAll.mutate({ daily: true, tasks: [] }) : navigate("/profile"))}
            disabled={busy}
          />
        )}
        {taskList && (
          <TodayRow
            Icon={IconTarget}
            title="Задания"
            subtitle={
              claimableTasks.length
                ? `Готово к получению: ${claimableTasks.length}${packTasks.length ? ` (паки — в заданиях)` : ""}`
                : tasksInProgress
                  ? `В процессе: ${tasksInProgress}`
                  : "Все выполнены"
            }
            ready={instantTasks.length > 0}
            done={!claimableTasks.length && !tasksInProgress}
            onClick={() =>
              instantTasks.length ? claimAll.mutate({ daily: false, tasks: instantTasks }) : navigate("/tasks")
            }
            disabled={busy}
            badge={packTasks.length || undefined}
          />
        )}
        {freePack && (
          <TodayRow
            Icon={IconPack}
            title="Бесплатный пак"
            subtitle={
              freePackReady
                ? freePackMutation.isPending ? "Открываем..." : "Готов — открой сейчас"
                : `Снова в ${formatClock(freePack.available_at)}`
            }
            ready={freePackReady}
            waiting={!freePackReady}
            onClick={() => freePackReady && freePackMutation.mutate()}
            disabled={busy || !freePackReady}
            actionLabel="Открыть"
          />
        )}
        {wheel && (
          <TodayRow
            Icon={IconGift}
            title="Колесо фортуны"
            subtitle={
              wheel.free_spins_remaining > 0
                ? `Бесплатных прокруток: ${wheel.free_spins_remaining}`
                : `Бесплатные снова в ${formatClock(wheel.next_free_spin_reset_at)}`
            }
            ready={wheel.free_spins_remaining > 0}
            waiting={wheel.free_spins_remaining === 0}
            onClick={() => navigate("/wheel")}
            actionLabel="Крутить"
          />
        )}
      </div>

      {(summary || error) && (
        <p role="status" className={`mt-2 text-xs ${error ? "text-red-400" : "text-accent-lime"}`}>
          {error ?? summary}
        </p>
      )}
    </section>
  );
}

function TodayRow({
  Icon, title, subtitle, ready, done, waiting, onClick, disabled, actionLabel = "Забрать", badge,
}: {
  Icon: (props: IconProps) => JSX.Element;
  title: string;
  subtitle: string;
  ready?: boolean;
  done?: boolean;
  waiting?: boolean;
  onClick: () => void;
  disabled?: boolean;
  actionLabel?: string;
  badge?: number;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled && ready}
      className="flex items-center gap-3 py-2.5 text-left active:opacity-70"
    >
      <span
        className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
          ready ? "bg-accent-lime/15 text-accent-lime" : "bg-bg-raised text-ink-mist"
        }`}
      >
        <Icon size={17} />
        {!!badge && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-lime px-1 font-mono text-[9px] font-bold text-bg-base">
            {badge}
          </span>
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-bold text-ink-chalk">{title}</span>
        <span className="block text-xs text-ink-mist">{subtitle}</span>
      </span>
      {ready ? (
        <span className="rounded-full bg-accent-lime/15 px-2.5 py-1 text-[11px] font-semibold text-accent-lime">
          {actionLabel}
        </span>
      ) : done ? (
        <IconCheck size={16} className="text-ink-mist-dim" />
      ) : waiting ? (
        <IconClock size={16} className="text-ink-mist-dim" />
      ) : null}
    </button>
  );
}
