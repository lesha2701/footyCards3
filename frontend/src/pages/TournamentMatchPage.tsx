import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { fetchTournamentDetail, fetchTournamentMatch } from "@/api/clubs";
import { ListSkeleton } from "@/components/common/Skeleton";
import { TournamentMatchReplay } from "@/components/clubs/TournamentMatchReplay";

export default function TournamentMatchPage() {
  const { id, matchId } = useParams<{ id: string; matchId: string }>();
  const tournamentId = Number(id);
  const matchIdNum = Number(matchId);

  const { data: tournament } = useQuery({
    queryKey: ["clubs", "tournament", tournamentId],
    queryFn: () => fetchTournamentDetail(tournamentId),
  });
  const { data: match, isLoading } = useQuery({
    queryKey: ["clubs", "tournament", tournamentId, "matches", matchIdNum],
    queryFn: () => fetchTournamentMatch(tournamentId, matchIdNum),
  });

  if (isLoading || !match) return <ListSkeleton />;

  const clubAName = tournament?.standings.find((s) => s.club_id === match.club_a_id)?.club_name ?? "Клуб A";
  const clubBName = tournament?.standings.find((s) => s.club_id === match.club_b_id)?.club_name ?? "Клуб B";

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Тур {match.round_number}</h1>
      <TournamentMatchReplay
        events={match.event_log}
        clubAName={clubAName}
        clubBName={clubBName}
        scoreA={match.score_a}
        scoreB={match.score_b}
      />
    </div>
  );
}
