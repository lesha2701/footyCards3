import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { fetchPlayerTournamentMatch } from "@/api/personalTournament";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { TournamentMatchReplay } from "@/components/clubs/TournamentMatchReplay";

export default function PlayerTournamentMatchPage() {
  const { matchId } = useParams<{ id: string; matchId: string }>();
  const matchIdNum = Number(matchId);

  const { data: match, isLoading, isError } = useQuery({
    queryKey: ["player-tournament", "matches", matchIdNum],
    queryFn: () => fetchPlayerTournamentMatch(matchIdNum),
    enabled: Number.isFinite(matchIdNum),
  });

  if (isError) return <EmptyState title="Не удалось загрузить матч" description="Попробуй обновить страницу" />;
  if (isLoading || !match) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Тур {match.round_number}</h1>
      <TournamentMatchReplay
        events={match.event_log}
        clubAName={match.user_a_name}
        clubBName={match.user_b_name}
        scoreA={match.score_a}
        scoreB={match.score_b}
      />
    </div>
  );
}
