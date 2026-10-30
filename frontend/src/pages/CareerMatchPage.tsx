import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { fetchCareer, fetchCareerCupMatch, fetchCareerFriendly, fetchCareerMatch } from "@/api/career";
import CareerMatchAnalysis from "@/components/career/CareerMatchAnalysis";
import { CareerMatchViewer } from "@/components/career/MatchViewer";
import { TournamentMatchReplay } from "@/components/clubs/TournamentMatchReplay";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconFlagCheckered } from "@/components/icons";

export default function CareerMatchPage() {
  const { seasonId, round, match, cupRound, tie } = useParams<{
    seasonId: string; round: string; match: string; cupRound: string; tie: string;
  }>();
  const isCup = cupRound !== undefined;
  const isFriendly = !isCup && round === undefined;
  const { data, isLoading, isError } = useQuery({
    queryKey: ["career", "match", seasonId, round, match, cupRound, tie],
    queryFn: () => isFriendly
      ? fetchCareerFriendly(Number(seasonId))
      : isCup
        ? fetchCareerCupMatch(Number(seasonId), Number(cupRound), Number(tie))
        : fetchCareerMatch(Number(seasonId), Number(round), Number(match)),
  });

  // The tactics catalog (axis labels) comes with the career view.
  const { data: view } = useQuery({ queryKey: ["career"], queryFn: fetchCareer, staleTime: 60_000 });

  // The second half of this match is on air: no spoilers below the pitch.
  const sh = view?.season?.second_half;
  const onAir = !isCup && !isFriendly && !!sh && sh.round === Number(round) && sh.match_index === Number(match);

  if (isLoading) return <ListSkeleton count={4} />;
  if (isError || !data) return <EmptyState icon={IconFlagCheckered} title="Матч не найден" description="Он ещё не сыгран или недоступен" />;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">
        {isFriendly ? "Товарищеский матч" : isCup ? `Кубок · ${["1/8 финала", "1/4 финала", "1/2 финала", "Финал"][Number(cupRound)] ?? ""}` : `Карьера · тур ${Number(round) + 1}`}
      </h1>
      {(() => {
        const text = (
          <TournamentMatchReplay
            events={data.events}
            clubAName={data.home_name}
            clubBName={data.away_name}
            scoreA={data.home_score}
            scoreB={data.away_score}
          />
        );
        // Every career match has a 2D replay; the text one stays as the fallback
        // (a match played before replays were stored, or no network).
        return isFriendly ? <CareerMatchViewer seasonId={Number(seasonId)} kind="friendly" fallback={text} />
          : isCup ? <CareerMatchViewer seasonId={Number(seasonId)} kind="cup" round={Number(cupRound)} match={Number(tie)} fallback={text} />
            : <CareerMatchViewer seasonId={Number(seasonId)} round={Number(round)} match={Number(match)} fallback={text} />;
      })()}
      {data.pens && (
        <section className="rounded-3xl bg-bg-surface p-4">
          <p className="font-display text-base font-bold text-ink-chalk">Серия пенальти {data.pens[0]}:{data.pens[1]}</p>
          <div className="mt-2 grid grid-cols-2 gap-2 text-caption">
            {(["a", "b"] as const).map((side) => (
              <div key={side} className="flex flex-col gap-1">
                <p className="truncate font-semibold text-ink-mist">{side === "a" ? data.home_name : data.away_name}</p>
                {(data.kicks ?? []).filter((k) => k.team === side).map((k, i) => (
                  <p key={i} className={k.scored ? "text-accent-lime" : "text-red-400"}>{k.scored ? "●" : "○"} {k.shooter}</p>
                ))}
              </div>
            ))}
          </div>
        </section>
      )}
      {data.analysis && (onAir
        ? <p className="rounded-3xl bg-bg-surface p-4 text-caption text-ink-mist">Тактический разбор — после финального свистка.</p>
        : <CareerMatchAnalysis analysis={data.analysis} catalog={view?.tactics_catalog ?? null} />)}
    </div>
  );
}
