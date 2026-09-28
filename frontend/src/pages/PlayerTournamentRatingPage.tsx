import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchPlayerTournamentLeaderboard } from "@/api/personalTournament";
import EmptyState from "@/components/common/EmptyState";
import { IconChevronLeft, IconStar, IconTrophy, type IconProps } from "@/components/icons";
import type { PlayerTournamentRankingEntry, PlayerTournamentRankingMetric } from "@/types";

const METRICS: { value: PlayerTournamentRankingMetric; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { value: "cups", label: "Кубки", Icon: IconTrophy },
  { value: "stars", label: "Звёзды", Icon: IconStar },
];

export default function PlayerTournamentRatingPage() {
  const navigate = useNavigate();
  const [metric, setMetric] = useState<PlayerTournamentRankingMetric>("cups");
  const { data, isLoading } = useQuery({
    queryKey: ["player-tournament", "leaderboard", metric],
    queryFn: () => fetchPlayerTournamentLeaderboard(metric),
  });

  const meInTop = !!data?.me && data.top.some((e) => e.user_id === data.me!.user_id);

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

      <div className="flex gap-2 overflow-x-auto pb-1">
        {METRICS.map((m) => (
          <button
            key={m.value}
            onClick={() => setMetric(m.value)}
            className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${
              metric === m.value ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
            }`}
          >
            <m.Icon size={13} />
            {m.label}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-ink-mist">Загрузка...</p>}

      {!isLoading && !data?.top.length ? (
        <EmptyState icon={IconTrophy} title="Пока никто не набрал очков" description="Сыграй турнир, чтобы попасть в рейтинг" />
      ) : (
        <div className="flex flex-col gap-2">
          {data?.top.map((entry) => (
            <RankingRow key={entry.user_id} entry={entry} highlight={entry.user_id === data?.me?.user_id} />
          ))}
        </div>
      )}

      {data?.me && !meInTop && (
        <>
          <p className="mt-1 text-center text-xs text-ink-mist-dim">⋯</p>
          <RankingRow entry={data.me} highlight />
        </>
      )}
    </div>
  );
}

function RankingRow({ entry, highlight = false }: { entry: PlayerTournamentRankingEntry; highlight?: boolean }) {
  return (
    <div className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm ${highlight ? "bg-accent-lime/10" : "bg-bg-surface"}`}>
      <div className="flex items-center gap-2">
        <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">{entry.rank}</span>
        <span className={highlight ? "font-semibold text-accent-lime" : "text-ink-chalk"}>{entry.display_name}</span>
      </div>
      <span className="font-mono font-bold text-accent-cyan">{entry.value}</span>
    </div>
  );
}
