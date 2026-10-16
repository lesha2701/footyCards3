import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchMyPlayerLeaderboard, type MyPlayerLeaderboardEntry } from "@/api/myPlayer";
import { ListSkeleton } from "@/components/common/Skeleton";
import { TIER_TEXT } from "@/lib/myPlayer";

import PlayerAvatar from "./PlayerAvatar";

/** Rating of everyone's «Мой игрок» — all players or just friends. */
export default function MyPlayerLeaderboard() {
  const [scope, setScope] = useState<"all" | "friends">("all");
  const { data, isLoading } = useQuery({
    queryKey: ["my-player", "leaderboard", scope],
    queryFn: () => fetchMyPlayerLeaderboard(scope),
  });

  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
      <div className="grid grid-cols-2 gap-1 rounded-xl bg-bg-raised p-1">
        {([["all", "Все"], ["friends", "Друзья"]] as const).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setScope(id)}
            className={`rounded-lg py-1.5 text-xs font-semibold ${scope === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {isLoading || !data ? (
        <ListSkeleton />
      ) : (
        <div className="flex flex-col divide-y divide-white/5">
          {data.entries.map((e) => <Row key={e.user_id} entry={e} />)}
          {data.me && (
            <>
              <p className="py-1 text-center text-micro text-ink-mist-dim">…</p>
              <Row entry={data.me} />
            </>
          )}
          {!data.entries.length && <p className="py-4 text-center text-sm text-ink-mist">Пока никого — позови друзей!</p>}
        </div>
      )}
    </section>
  );
}

function Row({ entry }: { entry: MyPlayerLeaderboardEntry }) {
  const navigate = useNavigate();
  const p = entry.player;
  return (
    <button
      onClick={() => !entry.is_me && navigate(`/users/${entry.user_id}`)}
      className={`flex items-center gap-3 py-2 text-left ${entry.is_me ? "rounded-xl bg-accent-lime/10 px-2" : ""}`}
    >
      <span className="w-7 text-center font-mono text-sm font-bold text-ink-mist">{entry.rank}</span>
      <span className="h-10 w-10 shrink-0 overflow-hidden rounded-lg">
        <PlayerAvatar appearance={p.appearance} accessory={p.accessory} backdrop={p.background} className="h-full w-full" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-ink-chalk">{p.name} <span className="text-ink-mist">#{p.number}</span></span>
        <span className="block truncate text-micro text-ink-mist">
          {entry.user_name} · {p.position} · ур. {entry.level} · <span className={TIER_TEXT[p.tier]}>{p.tier_label}</span>
        </span>
      </span>
      <span className="font-display text-lg font-black text-ink-chalk">{p.rating}</span>
    </button>
  );
}
