import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchMyPlayerHallOfFame, type MyPlayerHallMetric } from "@/api/myPlayer";
import { ListSkeleton } from "@/components/common/Skeleton";

import PlayerAvatar from "./PlayerAvatar";

const METRICS: [MyPlayerHallMetric, string][] = [
  ["goals", "⚽ Голы"], ["assists", "🎯 Передачи"], ["titles", "🏆 Титулы"], ["golden_ball", "🥇 Золотой мяч"],
  ["trophies", "🏅 Трофеи"], ["matches", "📅 Матчи"],
];
const MEDAL = ["🥇", "🥈", "🥉"];

/** «Зал славы»: the best «Мои игроки» of all time — league career totals
 * over every club, «Золотые мячи» and trophies. */
export default function MyPlayerHallOfFame() {
  const navigate = useNavigate();
  const [metric, setMetric] = useState<MyPlayerHallMetric>("goals");
  const { data, isLoading } = useQuery({ queryKey: ["my-player", "hall", metric], queryFn: () => fetchMyPlayerHallOfFame(metric) });
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-gradient-to-b from-amber-400/10 to-bg-surface p-4" data-testid="hall-of-fame">
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {METRICS.map(([id, label]) => (
          <button key={id} onClick={() => setMetric(id)}
            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${metric === id ? "bg-amber-400 text-bg-base" : "bg-bg-raised text-ink-mist"}`}>
            {label}
          </button>
        ))}
      </div>
      {isLoading || !data ? <ListSkeleton /> : data.entries.length === 0 ? (
        <p className="py-4 text-center text-sm text-ink-mist">Зал славы пока пуст — стань первым!</p>
      ) : (
        <div className="flex flex-col divide-y divide-white/5">
          {data.entries.map((e) => (
            <button key={e.user_id} onClick={() => navigate(`/users/${e.user_id}`)} className="flex items-center gap-3 py-2 text-left">
              <span className="w-7 text-center font-mono text-sm font-bold text-ink-mist">{MEDAL[e.place - 1] ?? e.place}</span>
              <span className="h-10 w-10 shrink-0 overflow-hidden rounded-lg">
                <PlayerAvatar appearance={e.player.appearance} accessory={e.player.accessory} backdrop={e.player.background} className="h-full w-full" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-ink-chalk">{e.player.name} <span className="text-ink-mist">#{e.player.number}</span></span>
                <span className="block truncate text-micro text-ink-mist">{e.user_name} · {e.player.position} · {e.player.rating}</span>
              </span>
              <span className="font-display text-lg font-black text-amber-300">{e.value}</span>
            </button>
          ))}
        </div>
      )}
      {data?.me && (
        <p className="rounded-xl bg-accent-lime/10 px-3 py-2 text-center text-xs text-ink-chalk">
          Ты: <b>{data.me.place}</b> место · <b>{data.me.value}</b>
        </p>
      )}
      <p className="text-micro text-ink-mist-dim">Голы, передачи, матчи и титулы — в лигах «Карьеры игрока» за всю карьеру.</p>
    </section>
  );
}
