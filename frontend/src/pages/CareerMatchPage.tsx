import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { fetchCareerMatch } from "@/api/career";
import { TournamentMatchReplay } from "@/components/clubs/TournamentMatchReplay";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconFlagCheckered } from "@/components/icons";

export default function CareerMatchPage() {
  const { seasonId, round, match } = useParams<{ seasonId: string; round: string; match: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["career", "match", seasonId, round, match],
    queryFn: () => fetchCareerMatch(Number(seasonId), Number(round), Number(match)),
  });

  if (isLoading) return <ListSkeleton count={4} />;
  if (isError || !data) return <EmptyState icon={IconFlagCheckered} title="Матч не найден" description="Он ещё не сыгран или недоступен" />;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Карьера · тур {Number(round) + 1}</h1>
      <TournamentMatchReplay
        events={data.events}
        clubAName={data.home_name}
        clubBName={data.away_name}
        scoreA={data.home_score}
        scoreB={data.away_score}
      />
    </div>
  );
}
