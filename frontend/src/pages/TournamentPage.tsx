import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchTournamentDetail, fetchMyClub } from "@/api/clubs";
import { ClubPreviewPopup } from "@/components/clubs/ClubPreviewPopup";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";

function resultsGateKey(tournamentId: number) {
  return `tournament_results_seen_${tournamentId}`;
}

export default function TournamentPage() {
  const { id } = useParams<{ id: string }>();
  const tournamentId = Number(id);
  const navigate = useNavigate();
  const [previewClubId, setPreviewClubId] = useState<number | null>(null);
  const [resultsRevealed, setResultsRevealed] = useState(() => localStorage.getItem(resultsGateKey(tournamentId)) === "1");

  const { data: tournament, isLoading, isError } = useQuery({
    queryKey: ["clubs", "tournament", tournamentId],
    queryFn: () => fetchTournamentDetail(tournamentId),
    enabled: Number.isFinite(tournamentId),
  });
  const { data: myClub } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub, retry: false });

  if (isLoading) return <ListSkeleton />;
  if (isError || !tournament) return <EmptyState title="Не удалось загрузить турнир" description="Попробуй обновить страницу" />;

  const revealResults = () => {
    localStorage.setItem(resultsGateKey(tournamentId), "1");
    setResultsRevealed(true);
  };

  const matchesByRound = new Map<number, typeof tournament.matches>();
  for (const m of tournament.matches) {
    matchesByRound.set(m.round_number, [...(matchesByRound.get(m.round_number) ?? []), m]);
  }
  const rounds = [...matchesByRound.keys()].sort((a, b) => b - a);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Турнир #{tournament.id}</h1>
        <p className="text-xs text-ink-mist-dim">
          {tournament.status === "completed" ? "Завершён" : `Тур ${tournament.rounds_simulated}/14`}
        </p>
      </div>

      {tournament.status === "completed" && !resultsRevealed && (
        <button
          onClick={revealResults}
          className="rounded-2xl bg-floodlight p-3 text-sm font-bold text-bg-base active:scale-95"
        >
          🏆 Турнир завершён — смотреть итоги
        </button>
      )}

      <div className="flex flex-col gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">Турнирная таблица</p>
        {tournament.standings.map((s) => (
          <button
            key={s.club_id}
            onClick={() => setPreviewClubId(s.club_id)}
            className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm ${
              s.club_id === myClub?.id ? "bg-accent-lime/12" : "bg-bg-surface"
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">{s.final_rank}</span>
              <span className={s.club_id === myClub?.id ? "font-semibold text-accent-lime" : "text-ink-chalk"}>{s.club_name}</span>
            </div>
            <div className="flex items-center gap-3 font-mono text-xs text-ink-mist">
              <span>{s.goals_for}:{s.goals_against}</span>
              <span className="font-bold text-ink-chalk">{s.points} очк.</span>
            </div>
          </button>
        ))}
      </div>

      {tournament.status === "completed" && resultsRevealed && (
        <div className="flex flex-col gap-2">
          <p className="font-display text-sm font-bold text-ink-chalk">Итоги турнира</p>
          {tournament.standings.map((s) => (
            <div key={s.club_id} className="flex items-center justify-between rounded-xl bg-bg-surface p-3 text-sm">
              <span className="text-ink-chalk">#{s.final_rank} {s.club_name}</span>
              <div className="flex items-center gap-2 font-mono text-xs">
                {s.cup_awarded && <span>🏆</span>}
                {s.stars_delta !== null && (
                  <span className={s.stars_delta > 0 ? "text-accent-lime" : "text-ink-mist"}>
                    ⭐ {s.stars_delta > 0 ? `+${s.stars_delta}` : s.stars_delta}
                  </span>
                )}
                {s.budget_awarded !== null && <span className="text-accent-cyan">🪙 +{s.budget_awarded}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">Матчи</p>
        {rounds.map((round) => (
          <div key={round} className="flex flex-col gap-1.5">
            <p className="text-xs text-ink-mist-dim">Тур {round}</p>
            {matchesByRound.get(round)!.map((m) => {
              const clubA = tournament.standings.find((s) => s.club_id === m.club_a_id);
              const clubB = tournament.standings.find((s) => s.club_id === m.club_b_id);
              return (
                <button
                  key={m.id}
                  onClick={() => navigate(`/clubs/tournament/${tournament.id}/matches/${m.id}`)}
                  className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-left text-xs text-ink-chalk active:scale-[0.99]"
                >
                  <span>{clubA?.club_name ?? m.club_a_id}</span>
                  <span className="font-mono font-bold">{m.score_a} : {m.score_b}</span>
                  <span>{clubB?.club_name ?? m.club_b_id}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>

      <ClubPreviewPopup clubId={previewClubId} onClose={() => setPreviewClubId(null)} />
    </div>
  );
}
