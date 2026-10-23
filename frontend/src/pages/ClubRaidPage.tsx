import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { attackClubRaid, fetchClubRaid, type ClubRaid } from "@/api/events";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconClock, IconCoin } from "@/components/icons";
import { RewardBundleChips } from "@/components/rewards/RewardBundleView";
import { formatGameError } from "@/lib/errors";
import { formatCountdown } from "@/lib/format";
import { hapticNotify } from "@/lib/telegram";

function goalsWord(n: number): string {
  const d = n % 10;
  if (n % 100 >= 11 && n % 100 <= 14) return "голов";
  return d === 1 ? "гол" : d >= 2 && d <= 4 ? "гола" : "голов";
}

/** «Клубный рейд»: the club's boss of the week; every member's attacks add up. */
export default function ClubRaidPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<ClubRaid["last"]>(null);
  const { data, isLoading } = useQuery({ queryKey: ["clubs", "raid"], queryFn: fetchClubRaid, refetchInterval: 30_000 });
  const attack = useMutation({
    mutationFn: attackClubRaid,
    onSuccess: (view) => {
      queryClient.setQueryData(["clubs", "raid"], view);
      setLast(view.last);
      setError(null);
      hapticNotify(view.last?.defeated_now ? "success" : "warning");
      if (view.last?.defeated_now) queryClient.invalidateQueries({ queryKey: ["clubs"] });
    },
    onError: (err) => setError(formatGameError(err, "Атака не удалась")),
  });
  if (isLoading || !data) return <ListSkeleton />;
  const secondsLeft = Math.max(0, Math.floor((new Date(data.ends_at).getTime() - Date.now()) / 1000));
  const hpLeft = Math.max(0, data.hp - data.damage);
  const pct = Math.round((hpLeft / data.hp) * 100);
  const top = Math.max(1, ...data.members.map((m) => m.damage));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95" aria-label="Назад">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Клубный рейд</h1>
        <span className="ml-auto flex shrink-0 items-center gap-1 text-caption text-ink-mist-dim">
          <IconClock size={12} /> {secondsLeft >= 86400 ? `${Math.floor(secondsLeft / 86400)} д ${Math.floor((secondsLeft % 86400) / 3600)} ч` : formatCountdown(secondsLeft)}
        </span>
      </div>

      {!data.enabled && <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">Рейды сейчас выключены.</p>}

      <section className="flex flex-col items-center gap-3 rounded-2xl bg-gradient-to-b from-red-900/40 via-bg-surface to-bg-surface p-4 text-center">
        <motion.span
          key={data.damage}
          initial={{ scale: 1 }}
          animate={last ? { scale: [1, 0.85, 1.05, 1], rotate: [0, -6, 6, 0] } : {}}
          transition={{ duration: 0.5 }}
          className={`text-6xl ${data.defeated ? "grayscale" : ""}`}
        >
          {data.boss.emoji}
        </motion.span>
        <div>
          <p className="font-display text-lg font-bold text-ink-chalk">{data.boss.name}</p>
          <p className="text-caption text-ink-mist">{data.defeated ? "Повержен! Новый босс придёт в понедельник" : data.boss.line}</p>
        </div>
        <div className="w-full">
          <div className="h-3 overflow-hidden rounded-full bg-black/40">
            <motion.div
              className={`h-full rounded-full ${data.defeated ? "bg-accent-green" : "bg-gradient-to-r from-red-500 to-orange-400"}`}
              initial={false}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.6 }}
            />
          </div>
          <p className="mt-1 font-mono text-caption text-ink-mist">
            {hpLeft.toLocaleString("ru-RU")} / {data.hp.toLocaleString("ru-RU")} HP
          </p>
        </div>

        {last && (
          <div className="flex flex-col items-center gap-1.5">
            <div className="flex gap-1.5">
              {last.shots.map((goal, i) => (
                <motion.span
                  key={`${data.damage}-${i}`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.15 }}
                  className={`flex h-7 w-7 items-center justify-center rounded-full text-sm ${goal ? "bg-accent-lime text-bg-base" : "bg-white/10 text-ink-mist"}`}
                >
                  {goal ? "⚽" : "✕"}
                </motion.span>
              ))}
            </div>
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: last.shots.length * 0.15 }}
              className="font-display text-sm font-bold text-accent-lime"
            >
              {last.defeated_now ? "Босс повержен! 🎉" : `${last.goals} ${goalsWord(last.goals)} · −${last.damage} HP`}
            </motion.p>
          </div>
        )}

        {!data.defeated && (
          <button
            onClick={() => attack.mutate()}
            disabled={attack.isPending || data.attacks_left === 0 || !data.enabled}
            className="w-full rounded-xl bg-floodlight py-3 font-display text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            {data.attacks_left > 0 ? `Атаковать · осталось ${data.attacks_left}/${data.attacks_per_day}` : "Атаки на сегодня закончились"}
          </button>
        )}
        <p className="text-caption text-ink-mist-dim">
          {data.shots} ударов за атаку · сила твоего состава {data.strength} · шанс гола {data.chance_pct}%
        </p>
      </section>
      {error && <p className="text-xs text-red-400">{error}</p>}

      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3">
        <p className="font-display text-sm font-bold text-ink-chalk">Награда за победу</p>
        <div className="flex flex-wrap items-center gap-2 text-caption text-ink-mist">
          {data.reward_budget > 0 && (
            <span className="flex items-center gap-1 rounded-full bg-black/20 px-2 py-0.5">
              в казну +{data.reward_budget} <IconCoin size={11} className="text-accent-lime" />
            </span>
          )}
          <span>каждому:</span>
          <RewardBundleChips bundle={data.reward} />
        </div>
        {data.defeated && (
          <button onClick={() => navigate("/clubs/shop")} className="rounded-xl bg-floodlight py-2.5 text-xs font-bold text-bg-base active:scale-95">
            Забрать награду
          </button>
        )}
      </section>

      <section className="flex flex-col gap-1.5">
        <p className="font-display text-sm font-bold text-ink-chalk">Урон участников</p>
        {data.members.map((m) => (
          <div key={m.user_id} className={`relative overflow-hidden rounded-lg px-3 py-2 text-xs ${m.is_me ? "ring-1 ring-accent-lime/40" : ""} bg-bg-surface`}>
            <div className="absolute inset-y-0 left-0 bg-red-500/15" style={{ width: `${(m.damage / top) * 100}%` }} aria-hidden />
            <div className="relative flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-ink-chalk">{m.name}</span>
              <span className="text-ink-mist">⚽ {m.goals}</span>
              <span className="text-ink-mist">{m.attacks} атак</span>
              <span className="w-14 text-right font-mono font-bold text-ink-chalk">{m.damage}</span>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
