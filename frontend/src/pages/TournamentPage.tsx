import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchTournamentDetail, fetchMyClub } from "@/api/clubs";
import { ClubPreviewPopup } from "@/components/clubs/ClubPreviewPopup";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconCoin, IconStar, IconTrophy } from "@/components/icons";
import { formatCountdown } from "@/lib/format";
import type { TournamentMatchSummary, TournamentStanding } from "@/types";

function resultsGateKey(tournamentId: number) {
  return `tournament_results_seen_${tournamentId}`;
}

interface StandingRow extends TournamentStanding {
  played: number;
  wins: number;
  draws: number;
  losses: number;
}

function buildStandingsRows(standings: TournamentStanding[], matches: TournamentMatchSummary[]): StandingRow[] {
  return standings.map((s) => {
    let played = 0;
    let wins = 0;
    let draws = 0;
    let losses = 0;
    for (const m of matches) {
      const isA = m.club_a_id === s.club_id;
      const isB = m.club_b_id === s.club_id;
      if (!isA && !isB) continue;
      played += 1;
      const my = isA ? m.score_a : m.score_b;
      const their = isA ? m.score_b : m.score_a;
      if (my > their) wins += 1;
      else if (my < their) losses += 1;
      else draws += 1;
    }
    return { ...s, played, wins, draws, losses };
  });
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

  const rows = buildStandingsRows(tournament.standings, tournament.matches);

  const matchesByRound = new Map<number, typeof tournament.matches>();
  for (const m of tournament.matches) {
    matchesByRound.set(m.round_number, [...(matchesByRound.get(m.round_number) ?? []), m]);
  }
  const rounds = [...matchesByRound.keys()].sort((a, b) => b - a);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <div>
          <h1 className="font-display text-xl font-bold text-ink-chalk">Турнир #{tournament.id}</h1>
          <p className="text-xs text-ink-mist-dim">
            {tournament.status === "completed" ? "Завершён" : `Тур ${tournament.rounds_simulated}/14`}
            {tournament.next_round_seconds_remaining != null &&
              ` · Новый тур через ${formatCountdown(tournament.next_round_seconds_remaining)}`}
          </p>
        </div>
      </div>

      {tournament.status === "completed" && !resultsRevealed && (
        <button
          onClick={revealResults}
          className="flex items-center justify-center gap-2 rounded-2xl bg-floodlight p-3 text-sm font-bold text-bg-base active:scale-95"
        >
          <IconTrophy size={16} />
          Турнир завершён — смотреть итоги
        </button>
      )}

      <div className="flex flex-col gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">Турнирная таблица</p>
        <div className="overflow-x-auto rounded-2xl bg-bg-surface">
          <table className="w-full min-w-[420px] text-xs">
            <thead>
              <tr className="border-b border-white/5 text-left text-[10px] uppercase text-ink-mist-dim">
                <th className="px-2 py-2 font-semibold">#</th>
                <th className="px-2 py-2 font-semibold">Клуб</th>
                <th className="px-2 py-2 text-center font-semibold">И</th>
                <th className="px-2 py-2 text-center font-semibold">В</th>
                <th className="px-2 py-2 text-center font-semibold">Н</th>
                <th className="px-2 py-2 text-center font-semibold">П</th>
                <th className="px-2 py-2 text-center font-semibold">Мячи</th>
                <th className="px-2 py-2 text-center font-semibold">РМ</th>
                <th className="px-2 py-2 text-right font-semibold">О</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr
                  key={s.club_id}
                  onClick={() => setPreviewClubId(s.club_id)}
                  className={`cursor-pointer border-b border-white/5 last:border-0 active:bg-white/5 ${
                    s.club_id === myClub?.id ? "bg-accent-lime/10" : ""
                  }`}
                >
                  <td className="px-2 py-2 font-mono font-bold text-ink-mist-dim">{s.final_rank}</td>
                  <td className={`px-2 py-2 font-semibold ${s.club_id === myClub?.id ? "text-accent-lime" : "text-ink-chalk"}`}>
                    {s.club_name}
                  </td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.played}</td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.wins}</td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.draws}</td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.losses}</td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.goals_for}:{s.goals_against}</td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.goals_for - s.goals_against}</td>
                  <td className="px-2 py-2 text-right font-mono font-bold text-ink-chalk">{s.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {tournament.status === "completed" && resultsRevealed && (
        <div className="flex flex-col gap-2">
          <p className="font-display text-sm font-bold text-ink-chalk">Итоги турнира</p>
          {tournament.standings.map((s) => (
            <div key={s.club_id} className="flex items-center justify-between rounded-xl bg-bg-surface p-3 text-sm">
              <span className="text-ink-chalk">#{s.final_rank} {s.club_name}</span>
              <div className="flex items-center gap-3 font-mono text-xs">
                {s.cup_awarded && <IconTrophy size={14} className="text-accent-lime" />}
                {s.stars_delta !== null && (
                  <span className={`flex items-center gap-1 ${s.stars_delta > 0 ? "text-accent-lime" : "text-ink-mist"}`}>
                    <IconStar size={12} />
                    {s.stars_delta > 0 ? `+${s.stars_delta}` : s.stars_delta}
                  </span>
                )}
                {s.budget_awarded !== null && (
                  <span className="flex items-center gap-1 text-accent-cyan">
                    <IconCoin size={12} />
                    +{s.budget_awarded}
                  </span>
                )}
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
                  className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-xl bg-bg-surface px-3 py-2 text-left text-xs text-ink-chalk active:scale-[0.99]"
                >
                  <span className="truncate text-right">{clubA?.club_name ?? m.club_a_id}</span>
                  <span className="flex items-center justify-center gap-1 font-mono font-bold">
                    <span className="w-4 text-right">{m.score_a}</span>
                    <span>:</span>
                    <span className="w-4 text-left">{m.score_b}</span>
                  </span>
                  <span className="truncate">{clubB?.club_name ?? m.club_b_id}</span>
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
