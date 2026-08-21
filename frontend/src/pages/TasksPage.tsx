import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimTask, fetchTasks } from "@/api/tasks";
import EmptyState from "@/components/common/EmptyState";
import { IconChat, IconCheck, IconCoin, IconPack, IconParty, IconTarget, IconTrophy } from "@/components/icons";
import { ApiRequestError } from "@/lib/api";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Task } from "@/types";

export default function TasksPage() {
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [claimError, setClaimError] = useState<string | null>(null);
  const [claimedCoins, setClaimedCoins] = useState<number | null>(null);
  const [tab, setTab] = useState<"regular" | "premium">("regular");
  const [premiumFilter, setPremiumFilter] = useState<"active" | "done">("active");

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
      if (data.granted_pack) {
        // Reuses the same full packshot + per-card reveal animation as a
        // real pack purchase, instead of a bespoke "reward received" popup.
        navigate(`/packs/${data.granted_pack.pack.id}/open`, { state: { result: data.granted_pack } });
      } else {
        setClaimedCoins(data.reward_coins);
      }
    },
    onError: (err) => setClaimError(err instanceof ApiRequestError ? err.message : "Не удалось забрать награду"),
  });

  if (isLoading) return null;

  const premiumTasks = (taskList?.premium ?? []).filter((t) =>
    premiumFilter === "active" ? !t.is_claimed : t.is_claimed
  );

  return (
    <div className="flex flex-col gap-5">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconTarget size={20} className="text-accent-lime" />
        Задания
      </h1>

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
            <EmptyState icon={IconTarget} title="Заданий пока нет" description="Загляните позже" />
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
          <div className="flex gap-2">
            <TabButton active={premiumFilter === "active"} label="Активные" onClick={() => setPremiumFilter("active")} />
            <TabButton active={premiumFilter === "done"} label="Выполненные" onClick={() => setPremiumFilter("done")} />
          </div>

          {!premiumTasks.length ? (
            <EmptyState
              icon={IconTrophy}
              title={premiumFilter === "active" ? "Активных заданий пока нет" : "Выполненных заданий пока нет"}
              description="Загляните позже"
            />
          ) : (
            premiumTasks.map((task) => (
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

      {claimedCoins !== null && (
        <RewardClaimedModal coins={claimedCoins} onClose={() => setClaimedCoins(null)} />
      )}
    </div>
  );
}

function RewardClaimedModal({ coins, onClose }: { coins: number; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-6">
      <div className="w-full max-w-xs rounded-2xl border border-white/10 bg-bg-surface p-6 text-center">
        <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-accent-lime/15 text-accent-lime">
          <IconParty size={32} />
        </span>
        <p className="mt-3 font-display text-lg font-bold text-ink-chalk">Награда получена!</p>
        <p className="mt-1 text-sm text-ink-mist">Задание выполнено, монеты начислены на баланс.</p>
        <p className="mt-3 flex items-center justify-center gap-1.5 font-display text-2xl font-bold text-amber-300">
          <IconCoin size={20} />+{coins}
        </p>
        <button
          onClick={onClose}
          className="mt-5 w-full rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base active:scale-95"
        >
          Ок
        </button>
      </div>
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
        active ? "bg-accent text-bg-base" : "bg-white/5 text-ink-mist"
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
  const isChannelTask = !!(task.invite_link || task.channel_username);

  return (
    <div
      className={`rounded-2xl border p-4 ${
        premium ? "border-amber-500/30 bg-amber-500/5" : "border-white/5 bg-bg-surface"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-display text-sm font-bold text-ink-chalk">{task.name}</p>
          <p className="mt-0.5 text-xs text-ink-mist">{task.description}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="flex items-center justify-end gap-1 font-display text-sm font-bold text-amber-300">
            {task.reward_pack_name ? (
              <>
                <IconPack size={14} />
                {task.reward_pack_name}
              </>
            ) : (
              <>
                <IconCoin size={14} />+{task.reward_coins}
              </>
            )}
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

      {premium && isChannelTask && !task.is_claimed && (
        <a
          href={task.invite_link || `https://t.me/${task.channel_username!.replace("@", "")}`}
          target="_blank"
          rel="noreferrer"
          className="mt-3 flex items-center justify-center gap-1.5 rounded-xl border-2 border-accent bg-accent/15 py-2.5 text-center text-sm font-bold text-accent active:scale-95"
        >
          <IconChat className="h-4 w-4" />
          Подписаться на канал
        </a>
      )}

      {task.is_claimed ? (
        <p className="mt-3 flex items-center justify-center gap-1 text-xs font-bold text-emerald-400">
          <IconCheck size={14} />
          Награда получена
        </p>
      ) : (
        <button
          onClick={onClaim}
          disabled={!task.is_completed || isPending}
          className="mt-3 w-full rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {isPending
            ? "Начисление..."
            : !task.is_completed
              ? "В процессе"
              : premium && isChannelTask
                ? "Проверить подписку"
                : "Забрать награду"}
        </button>
      )}
    </div>
  );
}
