import { ListSkeleton } from "@/components/common/Skeleton";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchRanking } from "@/api/leaderboard";
import { fetchWeeklyTopInfo } from "@/api/weeklyTop";
import EmptyState from "@/components/common/EmptyState";
import { UserBadge } from "@/components/common/UserBadge";
import { IconBall, IconBoxingGlove, IconCollection, IconCounter, IconFlag, IconFlagCheckered, IconGoal, IconHandshake, IconStadium, IconStar, IconTrophy, IconUsers, type IconProps } from "@/components/icons";
import { useAuthStore } from "@/store/authStore";
import { frameClass } from "@/lib/cosmetics";
import type { RankingEntry, RankingMetric, WeeklyTopInfo } from "@/types";

const METRICS: { value: RankingMetric; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { value: "arena_rating", label: "Рейтинг Arena", Icon: IconBall },
  { value: "tactics_rating", label: "Рейтинг Тактико", Icon: IconFlagCheckered },
  { value: "penalty_rating", label: "Рейтинг Пенальти", Icon: IconGoal },
  { value: "stratego_rating", label: "Рейтинг Стратего", Icon: IconFlag },
  { value: "stratego_puzzles", label: "Задачи Стратего", Icon: IconFlag },
  { value: "mordoboi_rating", label: "Рейтинг Мордобоя", Icon: IconBoxingGlove },
  { value: "kontra_rating", label: "Арена Контратаки", Icon: IconCounter },
  { value: "matches_won", label: "Победы", Icon: IconTrophy },
  { value: "cards_count", label: "Карт в коллекции", Icon: IconCollection },
  { value: "unique_players", label: "Уникальных игроков", Icon: IconUsers },
  { value: "referral_count", label: "Рефералов", Icon: IconHandshake },
  { value: "base_level", label: "Уровень базы", Icon: IconStadium },
  { value: "academy_level", label: "Уровень Академии", Icon: IconStar },
  { value: "academy_prestige", label: "Престиж Академии", Icon: IconStar },
  { value: "league_rating", label: "Рейтинг лиги", Icon: IconTrophy },
  { value: "games_week", label: "Игр за неделю", Icon: IconBall },
  { value: "stars_week", label: "Звёзд за неделю", Icon: IconStar },
  { value: "referrals_week", label: "Рефералов за неделю", Icon: IconHandshake },
];
const MEDALS = ["🥇", "🥈", "🥉"];

export default function RankingPage() {
  // ?metric=… opens a specific board (e.g. «Уровень базы» from the base screen).
  const [params] = useSearchParams();
  const [metric, setMetric] = useState<RankingMetric>(() => {
    const wanted = params.get("metric");
    return METRICS.find((m) => m.value === wanted)?.value ?? "arena_rating";
  });
  const user = useAuthStore((s) => s.user);
  const { data, isLoading } = useQuery({ queryKey: ["ranking", metric], queryFn: () => fetchRanking(metric) });
  const { data: weekly } = useQuery({ queryKey: ["weekly-top-info"], queryFn: fetchWeeklyTopInfo, staleTime: 60_000 });
  const pays = !!weekly?.enabled && weekly.metrics.includes(metric);

  const meInTop = !!data?.me && data.top.some((e) => e.user_id === data.me!.user_id);
  // How far the player is from the last paid place of this week's top.
  const lastPaid = pays && weekly ? data?.top[weekly.size - 1] : undefined;
  const me = data?.me;
  const toPrize = lastPaid && me && me.rank > weekly!.size ? lastPaid.value - me.value + 1 : null;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconTrophy size={20} className="text-accent-lime" />
        Рейтинг
      </h1>

      {weekly?.enabled && <WeeklyTopBanner info={weekly} pays={pays} />}

      {/* Wrapped, not a sideways-scrolling row: every board stays reachable. */}
      <div className="flex flex-wrap gap-1.5">
        {METRICS.map((m) => (
          <button
            key={m.value}
            onClick={() => setMetric(m.value)}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${
              metric === m.value ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
            }`}
          >
            <m.Icon size={13} />
            {m.label}
          </button>
        ))}
      </div>

      {isLoading && <ListSkeleton count={3} />}

      {!isLoading && !data?.top.length ? (
        <EmptyState icon={IconTrophy} title="Пока никто не набрал очков" description="Стань первым!" />
      ) : (
        <div className="flex flex-col gap-2">
          {data?.top.map((entry) => (
            <RankingRow key={entry.user_id} entry={entry} highlight={entry.user_id === user?.id}
              prized={pays && entry.rank <= (weekly?.size ?? 0) && entry.value > (weekly?.starting_values[metric] ?? 0)} />
          ))}
        </div>
      )}

      {data?.me && !meInTop && (
        <>
          <p className="mt-1 text-center text-xs text-ink-mist-dim">⋯</p>
          <RankingRow entry={data.me} highlight />
        </>
      )}
      {toPrize != null && toPrize > 0 && (
        <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-center text-xs text-amber-200">
          До топ-{weekly!.size} и награды недели не хватает <b className="font-mono">{toPrize.toLocaleString("ru-RU")}</b>
        </p>
      )}
    </div>
  );
}

function timeLeft(endsAt: string): string {
  const ms = Math.max(0, new Date(endsAt).getTime() - Date.now());
  const days = Math.floor(ms / 86_400_000);
  const hours = Math.floor((ms % 86_400_000) / 3_600_000);
  return days > 0 ? `${days} д ${hours} ч` : `${hours} ч ${Math.floor((ms % 3_600_000) / 60_000)} мин`;
}

/** «Топ недели»: what the places pay and when the week closes. */
function WeeklyTopBanner({ info, pays }: { info: WeeklyTopInfo; pays: boolean }) {
  const [open, setOpen] = useState(false);
  const shown = open ? info.places : info.places.slice(0, 3);
  return (
    <section className="rounded-2xl bg-gradient-to-br from-amber-400/20 via-bg-surface to-bg-surface p-3 ring-1 ring-amber-300/20">
      <div className="flex items-center justify-between gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">🏆 Топ недели — награды топ-{info.size}</p>
        <span className="shrink-0 rounded-full bg-black/30 px-2 py-0.5 font-mono text-micro text-amber-200">
          ещё {timeLeft(info.ends_at)}
        </span>
      </div>
      <p className="mt-0.5 text-micro text-ink-mist">
        {pays
          ? "Эта номинация награждается: в понедельник лучшие получат награду своего места."
          : "Эта таблица в недельных наградах не участвует."}
      </p>
      <div className="mt-2 flex flex-col gap-1">
        {shown.map((p) => (
          <div key={p.rank} className="flex items-center gap-2 rounded-lg bg-black/20 px-2 py-1 text-xs">
            <span className="w-7 text-center">{MEDALS[p.rank - 1] ?? `#${p.rank}`}</span>
            <span className="font-mono font-bold text-accent-lime">+{p.coins.toLocaleString("ru-RU")}</span>
            {p.pack_name && <span className="truncate text-accent-cyan">· {p.pack_name}</span>}
            {p.cosmetic_name && (
              <span className="ml-auto flex shrink-0 items-center gap-1 text-ink-mist">
                <span className={`h-3.5 w-3.5 rounded-full p-[2px] ${frameClass(p.cosmetic_style) ?? "bg-white/20"}`}>
                  <span className="block h-full w-full rounded-full bg-bg-surface" />
                </span>
                {p.cosmetic_name}
              </span>
            )}
          </div>
        ))}
      </div>
      {info.places.length > 3 && (
        <button onClick={() => setOpen(!open)} className="mt-1.5 w-full text-center text-micro text-ink-mist underline">
          {open ? "Свернуть" : `Все ${info.places.length} мест`}
        </button>
      )}
    </section>
  );
}

function RankingRow({ entry, highlight = false, prized = false }: { entry: RankingEntry; highlight?: boolean; prized?: boolean }) {
  return (
    <div
      className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm ${
        highlight ? "bg-accent-lime/12" : "bg-bg-surface"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">
          {prized && entry.rank <= 3 ? MEDALS[entry.rank - 1] : entry.rank}
        </span>
        <span className={highlight ? "font-semibold text-accent-lime" : "text-ink-chalk"}>{entry.display_name}</span>
        <UserBadge badge={entry.active_badge} />
      </div>
      <span className="font-mono font-bold text-accent-cyan">{entry.value}</span>
    </div>
  );
}
