import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchPlayerTournamentRating } from "@/api/personalTournament";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconTrophy } from "@/components/icons";
import { useAuthStore } from "@/store/authStore";

export default function PlayerTournamentRatingPage() {
  const navigate = useNavigate();
  const myUserId = useAuthStore((s) => s.user?.id);
  const { data: rows, isLoading } = useQuery({ queryKey: ["player-tournament", "rating"], queryFn: fetchPlayerTournamentRating });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/player-tournament")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconTrophy size={20} className="text-accent-lime" />
          Рейтинг турнира
        </h1>
      </div>

      {isLoading && <ListSkeleton />}

      {!isLoading && !rows?.length && (
        <EmptyState icon={IconTrophy} title="Рейтинг ещё пуст" description="Сыграй турнир, чтобы попасть в список" />
      )}

      <div className="flex flex-col gap-2">
        {rows?.map((entry, index) => (
          <div
            key={entry.user_id}
            className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm ${
              entry.user_id === myUserId ? "bg-accent-lime/10" : "bg-bg-surface"
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">{index + 1}</span>
              <span className={entry.user_id === myUserId ? "font-semibold text-accent-lime" : "text-ink-chalk"}>
                {entry.display_name}
              </span>
            </div>
            <span className="font-mono font-bold text-accent-cyan">{entry.tournament_rating}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
