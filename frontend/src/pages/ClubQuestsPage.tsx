import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchClubQuests } from "@/api/clubFeatures";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCheck, IconChevronLeft, IconClock, IconCoin, IconTarget } from "@/components/icons";
import { RewardBundleChips } from "@/components/rewards/RewardBundleView";
import { formatCountdown } from "@/lib/format";

const METRIC_LABELS: Record<string, string> = { games: "игр", packs: "паков", tasks: "заданий" };

/** «Задания недели» клуба: общий прогресс, вклад участников, награды (забрать — в клубном магазине). */
export default function ClubQuestsPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ["clubs", "quests"], queryFn: fetchClubQuests, refetchInterval: 30_000 });
  if (isLoading || !data) return <ListSkeleton />;
  const secondsLeft = Math.max(0, Math.floor((new Date(data.ends_at).getTime() - Date.now()) / 1000));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Задания недели</h1>
        <span className="ml-auto flex items-center gap-1 text-caption text-ink-mist-dim">
          <IconClock size={12} /> {formatCountdown(secondsLeft)}
        </span>
      </div>

      {!data.enabled && <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">Задания клубов сейчас выключены.</p>}

      {data.quests.map((q) => {
        const pct = Math.min(100, Math.round((q.progress / q.target) * 100));
        return (
          <div key={q.id} className={`flex flex-col gap-2 rounded-2xl p-3 ${q.completed ? "bg-accent-green/10" : "bg-bg-surface"}`}>
            <div className="flex items-center gap-2">
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${q.completed ? "bg-accent-green/20 text-accent-green" : "bg-accent-lime/10 text-accent-lime"}`}>
                {q.completed ? <IconCheck size={16} /> : <IconTarget size={16} />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-display text-sm font-bold text-ink-chalk">{q.title}</p>
                <p className="text-caption text-ink-mist">
                  Вместе: {Math.min(q.progress, q.target)} / {q.target} {METRIC_LABELS[q.metric]}
                </p>
              </div>
              {q.completed && <span className="text-caption font-bold text-accent-green">Выполнено</span>}
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-black/30">
              <div className={`h-full rounded-full ${q.completed ? "bg-accent-green" : "bg-accent-lime"}`} style={{ width: `${pct}%` }} />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-caption text-ink-mist">
              {q.reward_budget > 0 && (
                <span className="flex items-center gap-1 rounded-full bg-black/20 px-2 py-0.5">
                  в казну +{q.reward_budget} <IconCoin size={11} className="text-accent-lime" />
                </span>
              )}
              <span>каждому:</span>
              <RewardBundleChips bundle={q.reward} />
            </div>
          </div>
        );
      })}

      {data.quests.some((q) => q.completed) && (
        <button onClick={() => navigate("/clubs/shop")} className="rounded-xl bg-floodlight py-2.5 text-xs font-bold text-bg-base active:scale-95">
          Забрать награды
        </button>
      )}

      <section className="flex flex-col gap-1.5">
        <p className="font-display text-sm font-bold text-ink-chalk">Вклад участников</p>
        {data.members.map((m) => (
          <div key={m.user_id} className="flex items-center gap-2 rounded-lg bg-bg-surface px-3 py-2 text-xs">
            <span className="min-w-0 flex-1 truncate text-ink-chalk">{m.name}</span>
            <span className="text-ink-mist">🎮 {m.games}</span>
            <span className="text-ink-mist">📦 {m.packs}</span>
            <span className="text-ink-mist">✅ {m.tasks}</span>
          </div>
        ))}
      </section>
    </div>
  );
}
