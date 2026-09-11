import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchClubStats } from "@/api/clubs";
import { IconChevronLeft, IconTarget } from "@/components/icons";

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl bg-bg-surface p-3">
      <p className="text-[11px] text-ink-mist-dim">{label}</p>
      <p className="font-mono text-lg font-bold text-ink-chalk">{value}</p>
    </div>
  );
}

export default function ClubStatsPage() {
  const navigate = useNavigate();
  const { data: stats, isLoading } = useQuery({ queryKey: ["clubs", "stats"], queryFn: fetchClubStats });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconTarget size={20} className="text-accent-lime" />
          Статистика клуба
        </h1>
      </div>

      {isLoading && <p className="text-sm text-ink-mist-dim">Загрузка...</p>}

      {stats && (
        <>
          <p className="text-xs text-ink-mist">Статистика за всё время выступлений клуба в турнире.</p>
          <div className="grid grid-cols-2 gap-3">
            <StatTile label="Матчей сыграно" value={stats.matches_played} />
            <StatTile label="Побед" value={stats.wins} />
            <StatTile label="Ничьих" value={stats.draws} />
            <StatTile label="Поражений" value={stats.losses} />
            <StatTile label="Голов забито" value={stats.goals_scored} />
            <StatTile label="Голов пропущено" value={stats.goals_conceded} />
            <StatTile label="% побед" value={`${stats.win_rate_pct}%`} />
            <StatTile label="% ничьих" value={`${stats.draw_rate_pct}%`} />
            <StatTile label="% поражений" value={`${stats.loss_rate_pct}%`} />
            <StatTile label="Голов за матч" value={stats.goals_scored_per_match} />
            <StatTile label="Пропущено за матч" value={stats.goals_conceded_per_match} />
          </div>
        </>
      )}
    </div>
  );
}
