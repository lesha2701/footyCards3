import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { applyToPlayerTournament, fetchPlayerTournamentCurrent } from "@/api/personalTournament";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronRight, IconClock, IconFlagCheckered, IconTrophy, IconUsers } from "@/components/icons";
import { formatGameError } from "@/lib/errors";

export default function PlayerTournamentPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [applyError, setApplyError] = useState<string | null>(null);

  const { data: current, isLoading } = useQuery({
    queryKey: ["player-tournament", "current"],
    queryFn: fetchPlayerTournamentCurrent,
  });

  const applyMutation = useMutation({
    mutationFn: applyToPlayerTournament,
    onSuccess: () => {
      setApplyError(null);
      queryClient.invalidateQueries({ queryKey: ["player-tournament", "current"] });
    },
    onError: (err) => setApplyError(formatGameError(err, "Не удалось подать заявку")),
  });

  if (isLoading) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconFlagCheckered size={20} className="text-accent-lime" />
        Личный турнир
      </h1>
      <p className="text-xs text-ink-mist">
        16 игроков, 30 туров (2 круга) — свой состав, своя тактика. Тур симулируется 3 раза в день.
      </p>

      <button
        onClick={() => navigate("/player-tournament/squad")}
        className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
      >
        <IconUsers size={16} className="text-accent-lime" />
        Состав для турнира
        <IconChevronRight size={16} className="ml-auto text-ink-mist-dim" />
      </button>

      <button
        onClick={() => navigate("/player-tournament/rating")}
        className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
      >
        <IconTrophy size={16} className="text-accent-lime" />
        Рейтинг турнира
        <IconChevronRight size={16} className="ml-auto text-ink-mist-dim" />
      </button>

      {(current?.status === "active" || current?.status === "completed") && current.tournament_id != null && (
        <button
          onClick={() => navigate(`/player-tournament/${current.tournament_id}`)}
          className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
        >
          <IconFlagCheckered size={16} className="text-accent-lime" />
          Мой турнир
          {current.status === "active" && (
            <span className="ml-auto flex items-center gap-1.5 rounded-full bg-accent-lime/10 px-2 py-1 text-[10px] font-bold text-accent-lime">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-lime" />
              Идёт
            </span>
          )}
        </button>
      )}

      {current?.status === "queued" && (
        <div className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-sm text-ink-mist">
          <IconClock size={16} className="text-accent-lime" />
          В очереди на турнир — место {current.queue_position} из {current.queue_size}
        </div>
      )}

      {current?.can_apply && (
        <button
          onClick={() => applyMutation.mutate()}
          disabled={applyMutation.isPending}
          className="relative flex items-center gap-4 overflow-hidden rounded-3xl bg-gradient-to-br from-accent-lime/25 via-accent-cyan/10 to-bg-surface p-5 text-left active:scale-[0.98] disabled:opacity-40"
        >
          <div className="pointer-events-none absolute -right-6 -top-8 h-28 w-28 rounded-full bg-accent-lime/25 blur-2xl" />
          <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-accent-lime/20 text-accent-lime">
            <IconTrophy size={22} />
          </div>
          <div className="relative min-w-0 flex-1">
            <p className="font-display text-base font-bold text-ink-chalk">Состав готов!</p>
            <p className="mt-0.5 text-xs leading-snug text-ink-mist">
              Подай заявку и жди, пока наберётся 16 игроков — турнир начнётся сам
            </p>
          </div>
          <IconChevronRight size={18} className="relative shrink-0 text-ink-mist-dim" />
        </button>
      )}

      {current && !current.can_apply && current.status === "not_queued" && (
        <button
          onClick={() => navigate("/player-tournament/squad")}
          className="flex items-center gap-2 rounded-2xl bg-white/5 p-3 text-left text-xs text-ink-mist-dim active:scale-[0.99]"
        >
          <IconUsers size={14} />
          Заполни все 11 позиций в составе, чтобы подать заявку на турнир
        </button>
      )}

      {applyError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{applyError}</p>}
    </div>
  );
}
