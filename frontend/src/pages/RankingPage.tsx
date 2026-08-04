import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchRanking } from "@/api/leaderboard";
import EmptyState from "@/components/common/EmptyState";
import { UserBadge } from "@/components/common/UserBadge";
import { IconBall, IconCollection, IconFlagCheckered, IconHandshake, IconTrophy, IconUsers, type IconProps } from "@/components/icons";
import { useAuthStore } from "@/store/authStore";
import type { RankingEntry, RankingMetric } from "@/types";

const METRICS: { value: RankingMetric; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { value: "arena_rating", label: "Рейтинг Arena", Icon: IconBall },
  { value: "tactics_rating", label: "Рейтинг Тактико", Icon: IconFlagCheckered },
  { value: "matches_won", label: "Победы", Icon: IconTrophy },
  { value: "cards_count", label: "Карт в коллекции", Icon: IconCollection },
  { value: "unique_players", label: "Уникальных игроков", Icon: IconUsers },
  { value: "referral_count", label: "Рефералов", Icon: IconHandshake },
];

export default function RankingPage() {
  const [metric, setMetric] = useState<RankingMetric>("arena_rating");
  const user = useAuthStore((s) => s.user);
  const { data, isLoading } = useQuery({ queryKey: ["ranking", metric], queryFn: () => fetchRanking(metric) });

  const meInTop = !!data?.me && data.top.some((e) => e.user_id === data.me!.user_id);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconTrophy size={20} className="text-accent-lime" />
        Рейтинг
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
        <EmptyState icon={IconTrophy} title="Пока никто не набрал очков" description="Стань первым!" />
      ) : (
        <div className="flex flex-col gap-2">
          {data?.top.map((entry) => (
            <RankingRow key={entry.user_id} entry={entry} highlight={entry.user_id === user?.id} />
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

function RankingRow({ entry, highlight = false }: { entry: RankingEntry; highlight?: boolean }) {
  return (
    <div
      className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm ${
        highlight ? "bg-accent-lime/12" : "bg-bg-surface"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">{entry.rank}</span>
        <span className={highlight ? "font-semibold text-accent-lime" : "text-ink-chalk"}>{entry.display_name}</span>
        <UserBadge badge={entry.active_badge} />
      </div>
      <span className="font-mono font-bold text-accent-cyan">{entry.value}</span>
    </div>
  );
}
