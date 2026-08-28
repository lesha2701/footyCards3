import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchClubLeaderboard } from "@/api/leaderboard";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import EmptyState from "@/components/common/EmptyState";
import { IconStar, IconTrophy, type IconProps } from "@/components/icons";
import type { ClubRankingEntry, ClubRankingMetric } from "@/types";

const METRICS: { value: ClubRankingMetric; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { value: "cups", label: "Кубки", Icon: IconTrophy },
  { value: "stars", label: "Звёзды", Icon: IconStar },
];

export default function ClubLeaderboardPage() {
  const [metric, setMetric] = useState<ClubRankingMetric>("cups");
  const { data, isLoading } = useQuery({ queryKey: ["clubs", "leaderboard", metric], queryFn: () => fetchClubLeaderboard(metric) });

  const meInTop = !!data?.me && data.top.some((e) => e.club_id === data.me!.club_id);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconTrophy size={20} className="text-accent-lime" />
        Рейтинг клубов
      </h1>

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
        <EmptyState icon={IconTrophy} title="Пока никто не набрал очков" description="Стань первым клубом в рейтинге!" />
      ) : (
        <div className="flex flex-col gap-2">
          {data?.top.map((entry) => (
            <ClubRankingRow key={entry.club_id} entry={entry} highlight={entry.club_id === data?.me?.club_id} />
          ))}
        </div>
      )}

      {data?.me && !meInTop && (
        <>
          <p className="mt-1 text-center text-xs text-ink-mist-dim">⋯</p>
          <ClubRankingRow entry={data.me} highlight />
        </>
      )}
    </div>
  );
}

function ClubRankingRow({ entry, highlight = false }: { entry: ClubRankingEntry; highlight?: boolean }) {
  return (
    <div
      className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm ${
        highlight ? "bg-accent-lime/12" : "bg-bg-surface"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">{entry.rank}</span>
        <ClubLogo shape={entry.logo_shape} color={entry.logo_color} size={24} />
        <span className={highlight ? "font-semibold text-accent-lime" : "text-ink-chalk"}>{entry.name}</span>
      </div>
      <span className="font-mono font-bold text-accent-cyan">{entry.value}</span>
    </div>
  );
}
