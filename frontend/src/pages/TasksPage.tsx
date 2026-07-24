import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { claimTask, fetchTasks } from "@/api/tasks";
import EmptyState from "@/components/common/EmptyState";
import { ApiRequestError } from "@/lib/api";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Task } from "@/types";

export default function TasksPage() {
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();
  const [claimError, setClaimError] = useState<string | null>(null);
  const [tab, setTab] = useState<"regular" | "premium">("regular");

  const { data: taskList, isLoading } = useQuery({ queryKey: ["tasks"], queryFn: fetchTasks });
  const premiumUnclaimed = (taskList?.premium ?? []).filter((t) => t.is_completed && !t.is_claimed).length;

  const claimMutation = useMutation({
    mutationFn: claimTask,
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimError(null);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
    },
    onError: (err) => setClaimError(err instanceof ApiRequestError ? err.message : "Не удалось забрать награду"),
  });

  if (isLoading) return null;

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-2xl font-bold text-slate-100">🎯 Задания</h1>

      {claimError && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{claimError}</p>}

      <div className="flex gap-2">
        <TabButton active={tab === "regular"} label="Обычные" onClick={() => setTab("regular")} />
        <TabButton
          active={tab === "premium"}
          label="Премиум"
          badge={premiumUnclaimed || undefined}
          onClick={() => setTab("premium")}
        />
      </div>

      {tab === "regular" ? (
        <section className="flex flex-col gap-3">
          {!taskList?.regular.length ? (
            <EmptyState icon="🎯" title="Заданий пока нет" description="Загляните позже" />
          ) : (
            taskList.regular.map((task) => (
              <TaskCard
                key={task.user_task_id}
                task={task}
                isPending={claimMutation.isPending && claimMutation.variables === task.user_task_id}
                onClaim={() => claimMutation.mutate(task.user_task_id)}
              />
            ))
          )}
        </section>
      ) : (
        <section className="flex flex-col gap-3">
          {!taskList?.premium.length ? (
            <EmptyState icon="⭐" title="Премиум заданий пока нет" description="Загляните позже" />
          ) : (
            taskList.premium.map((task) => (
              <TaskCard
                key={task.user_task_id}
                task={task}
                isPending={claimMutation.isPending && claimMutation.variables === task.user_task_id}
                onClaim={() => claimMutation.mutate(task.user_task_id)}
                premium
              />
            ))
          )}
        </section>
      )}
    </div>
  );
}

function TabButton({
  active,
  label,
  badge,
  onClick,
}: {
  active: boolean;
  label: string;
  badge?: number;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative rounded-full px-4 py-1.5 text-xs font-semibold ${
        active ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"
      }`}
    >
      {label}
      {!!badge && (
        <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">
          {badge}
        </span>
      )}
    </button>
  );
}

function TaskCard({
  task,
  isPending,
  onClaim,
  premium = false,
}: {
  task: Task;
  isPending: boolean;
  onClaim: () => void;
  premium?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border p-4 ${
        premium ? "border-amber-500/30 bg-amber-500/5" : "border-white/5 bg-bg-surface"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-display text-sm font-bold text-slate-100">{task.name}</p>
          <p className="mt-0.5 text-xs text-slate-400">{task.description}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="font-display text-sm font-bold text-amber-300">
            {task.reward_pack_name ? `📦 ${task.reward_pack_name}` : `+${task.reward_coins} 🪙`}
          </p>
        </div>
      </div>

      {!premium && (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/5">
          <div
            className="h-full bg-accent"
            style={{ width: `${Math.min(100, (task.progress / Math.max(1, task.target_value)) * 100)}%` }}
          />
        </div>
      )}

      {premium && (task.invite_link || task.channel_username) && !task.is_claimed && (
        <a
          href={task.invite_link || `https://t.me/${task.channel_username!.replace("@", "")}`}
          target="_blank"
          rel="noreferrer"
          className="mt-3 block rounded-xl bg-white/5 py-2 text-center text-xs font-semibold text-slate-200"
        >
          Подписаться на {task.channel_username ?? "канал"}
        </a>
      )}

      {task.is_claimed ? (
        <p className="mt-3 text-center text-xs font-bold text-emerald-400">✓ Награда получена</p>
      ) : (
        <button
          onClick={onClaim}
          disabled={!task.is_completed || isPending}
          className="mt-3 w-full rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {isPending ? "Начисление..." : task.is_completed ? "Забрать награду" : "В процессе"}
        </button>
      )}
    </div>
  );
}
