import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchClubActivity, fetchMyClub, remindMember } from "@/api/clubs";
import EmptyState from "@/components/common/EmptyState";
import { IconBrain, IconChevronLeft, IconGift, IconUsers } from "@/components/icons";
import { ApiRequestError } from "@/lib/api";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const ROLE_LABELS: Record<string, string> = { captain: "Капитан", assistant: "Ассистент", member: "Участник" };
const ACTIVITY_WINDOW_DAYS = 7;

export default function ClubActivityPage() {
  const navigate = useNavigate();
  const userId = useAuthStore((s) => s.user?.id);
  const queryClient = useQueryClient();
  const [remindedIds, setRemindedIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const { data: club } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub });
  const { data: activity, isLoading } = useQuery({ queryKey: ["clubs", "activity"], queryFn: fetchClubActivity });

  const remindMutation = useMutation({
    mutationFn: remindMember,
    onSuccess: (_data, targetUserId) => {
      hapticNotify("success");
      setError(null);
      setRemindedIds((prev) => new Set(prev).add(targetUserId));
    },
    onError: (err) => {
      setError(err instanceof ApiRequestError ? err.message : "Не удалось отправить напоминание");
      queryClient.invalidateQueries({ queryKey: ["clubs", "activity"] });
    },
  });

  const isManager = club?.my_role === "captain" || club?.my_role === "assistant";
  const sorted = [...(activity ?? [])].sort(
    (a, b) => a.games_played + a.daily_rewards_claimed - (b.games_played + b.daily_rewards_claimed)
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Активность клуба</h1>
      </div>

      <p className="text-xs text-ink-mist">
        Игры и ежедневные награды за последние {ACTIVITY_WINDOW_DAYS} дней. Список ниже отсортирован от самых
        неактивных к самым активным.
      </p>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {isLoading && <p className="text-sm text-ink-mist-dim">Загрузка...</p>}

      {!isLoading && !sorted.length && (
        <EmptyState icon={IconUsers} title="Нет данных" description="В клубе пока никого нет" />
      )}

      <div className="flex flex-col gap-2">
        {sorted.map((m) => {
          const inactive = m.games_played === 0 && m.daily_rewards_claimed === 0;
          const reminded = remindedIds.has(m.user_id);
          return (
            <div
              key={m.user_id}
              className={`flex items-center justify-between gap-2 rounded-2xl p-3 ${
                inactive ? "border border-red-500/20 bg-red-500/5" : "bg-bg-surface"
              }`}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink-chalk">
                  {m.username ?? m.first_name ?? `#${m.user_id}`}
                </p>
                <p className="text-[11px] text-ink-mist-dim">{ROLE_LABELS[m.role]}</p>
                <div className="mt-1.5 flex items-center gap-3 text-xs text-ink-mist">
                  <span className="flex items-center gap-1">
                    <IconBrain size={13} className="text-accent-lime" />
                    {m.games_played}
                  </span>
                  <span className="flex items-center gap-1">
                    <IconGift size={13} className="text-accent-lime" />
                    {m.daily_rewards_claimed}
                  </span>
                </div>
              </div>
              {isManager && m.user_id !== userId && (
                <button
                  onClick={() => remindMutation.mutate(m.user_id)}
                  disabled={remindMutation.isPending || reminded}
                  className="shrink-0 rounded-lg bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist active:scale-95 disabled:opacity-40"
                >
                  {reminded ? "Напомнили" : "Напомнить"}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
