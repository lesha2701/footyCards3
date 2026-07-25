import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchRanking } from "@/api/leaderboard";
import EmptyState from "@/components/common/EmptyState";
import { useAuthStore } from "@/store/authStore";
import type { RankingEntry, RankingMetric } from "@/types";

const METRICS: { value: RankingMetric; label: string; icon: string }[] = [
  { value: "arena_rating", label: "Рейтинг Arena", icon: "⚽" },
  { value: "matches_won", label: "Победы", icon: "🏆" },
  { value: "cards_count", label: "Карт в коллекции", icon: "🗂️" },
  { value: "unique_players", label: "Уникальных игроков", icon: "⭐" },
  { value: "referral_count", label: "Рефералов", icon: "🤝" },
];

export default function RankingPage() {
  const [metric, setMetric] = useState<RankingMetric>("arena_rating");
  const user = useAuthStore((s) => s.user);
  const { data, isLoading } = useQuery({ queryKey: ["ranking", metric], queryFn: () => fetchRanking(metric) });

  const meInTop = !!data?.me && data.top.some((e) => e.user_id === data.me!.user_id);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold text-slate-100">🏆 Рейтинг</h1>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {METRICS.map((m) => (
          <button
            key={m.value}
            onClick={() => setMetric(m.value)}
            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${
              metric === m.value ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"
            }`}
          >
            {m.icon} {m.label}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      {!isLoading && !data?.top.length ? (
        <EmptyState icon="🏆" title="Пока никто не набрал очков" description="Стань первым!" />
      ) : (
        <div className="flex flex-col gap-2">
          {data?.top.map((entry) => (
            <RankingRow key={entry.user_id} entry={entry} highlight={entry.user_id === user?.id} />
          ))}
        </div>
      )}

      {data?.me && !meInTop && (
        <>
          <p className="mt-1 text-center text-xs text-slate-500">⋯</p>
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
        highlight ? "border border-accent/40 bg-accent/15" : "bg-bg-surface"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="w-6 text-center font-display text-sm font-bold text-slate-400">{entry.rank}</span>
        <span className={highlight ? "font-semibold text-accent" : "text-slate-200"}>{entry.display_name}</span>
      </div>
      <span className="font-bold text-cyan-300">{entry.value}</span>
    </div>
  );
}
