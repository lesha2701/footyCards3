import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchMyAttention } from "@/api/profile";
import { Skeleton } from "@/components/common/Skeleton";
import { UserBadge } from "@/components/common/UserBadge";
import {
  IconChevronRight,
  IconFire,
  IconPlay,
  IconSwap,
  IconTarget,
  IconTrophy,
  type IconProps,
} from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { usePersistentState } from "@/lib/usePersistentState";
import type { LeagueStatus, ProfilePrivate } from "@/types";

const GAME_TITLES: Record<string, string> = {
  "/play/arena": "Card Arena",
  "/play/tactico": "Тактико",
  "/player-tournament": "Турнир",
  "/play/penalty": "Пенальти",
  "/play/fut-draft": "FUT Draft",
  "/play/memory": "Memory",
  "/play/saboteur": "Фанат",
  "/play/free-kick": "Штрафной",
  "/play/hangman": "Буквы",
  "/play/pairs": "Пары",
};

/** The top of the home screen: who you are and where you stand (level,
 * streak, league progress, rating) plus the four shortcuts that are NOT
 * already in the bottom nav — the last game, trades, tasks and the
 * leaderboard. The league row replaces the separate league banner. */
export default function HomeHero({
  profile,
  league,
  leaguesEnabled,
  claimableTasks,
}: {
  profile?: ProfilePrivate;
  league?: LeagueStatus;
  leaguesEnabled: boolean;
  claimableTasks: number;
}) {
  const navigate = useNavigate();
  const [lastGame] = usePersistentState<string | null>("play.last", null);
  const { data: attention } = useQuery({ queryKey: ["attention"], queryFn: fetchMyAttention, refetchInterval: 60000 });

  if (!profile) {
    return (
      <section className="flex flex-col gap-4 rounded-3xl bg-bg-surface p-5" aria-busy="true">
        <div className="flex items-center gap-3">
          <Skeleton className="h-14 w-14 rounded-full" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-5 w-40" />
          </div>
        </div>
        <Skeleton className="h-12 w-full rounded-2xl" />
        <div className="grid grid-cols-4 gap-2">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 rounded-2xl" />)}
        </div>
      </section>
    );
  }

  const name = profile.first_name || profile.username || "игрок";
  const tier = league?.current_league ?? league?.next_league ?? null;
  const floor = league?.current_league?.min_rating ?? 0;
  const progress = league?.next_league
    ? Math.min(100, Math.max(0, Math.round(((league.total_rating - floor) / (league.next_league.min_rating - floor)) * 100)))
    : 100;
  const continueTitle = lastGame ? GAME_TITLES[lastGame] : undefined;

  return (
    <section className="relative overflow-hidden rounded-3xl bg-bg-surface p-5">
      <div className="pointer-events-none absolute -right-10 -top-12 h-40 w-40 rounded-full bg-accent-lime/10 blur-3xl" />

      <div className="relative flex items-center gap-3">
        <div className="relative shrink-0">
          <img
            src={profile.avatar_url ?? "/brand/victor-fc-crest.jpg"}
            alt=""
            className="h-14 w-14 rounded-full object-cover ring-2 ring-accent-lime/60"
          />
          <span className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-accent-lime px-1.5 font-mono text-[9px] font-bold leading-4 text-bg-base ring-2 ring-bg-surface">
            ур. {profile.level}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-mist">С возвращением</p>
          <p className="flex items-center gap-1.5 truncate font-display text-lg font-bold text-ink-chalk">
            <span className="truncate">{name}</span>
            <UserBadge badge={profile.active_badge} />
          </p>
        </div>
        {profile.daily_login_streak > 0 && (
          <span
            className="flex shrink-0 items-center gap-1 rounded-full bg-orange-500/15 px-2.5 py-1 font-mono text-xs font-bold text-orange-300"
            title="Дней подряд в игре"
          >
            <IconFire size={13} />
            {profile.daily_login_streak}
          </span>
        )}
      </div>

      {leaguesEnabled && league && tier && (
        <button
          onClick={() => navigate("/league")}
          className="relative mt-4 flex w-full items-center gap-3 rounded-2xl bg-bg-raised/60 px-3 py-2.5 text-left active:scale-[0.99]"
        >
          <span
            className={`relative flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-bg-raised ${
              league.current_league ? "" : "opacity-40"
            }`}
          >
            {tier.image_path ? (
              <img src={staticUrl(tier.image_path) ?? undefined} alt="" className="h-full w-full object-cover" />
            ) : (
              <IconTrophy size={18} style={{ color: tier.color }} />
            )}
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-baseline justify-between gap-2">
              <span className="truncate font-display text-sm font-bold text-ink-chalk">
                {league.current_league ? league.current_league.name : "Пока вне лиги"}
              </span>
              <span className="shrink-0 font-mono text-[10px] text-ink-mist">
                {league.next_league ? `ещё ${league.points_to_next} до «${league.next_league.name}»` : "высшая лига"}
              </span>
            </span>
            <span className="mt-1.5 block h-1.5 w-full overflow-hidden rounded-full bg-white/5">
              <span className="block h-full rounded-full bg-accent-lime" style={{ width: `${progress}%` }} />
            </span>
          </span>
          {league.unseen_rewards.length > 0 && (
            <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-lime px-1 font-mono text-[9px] font-bold text-bg-base">
              {league.unseen_rewards.length}
            </span>
          )}
          <IconChevronRight size={14} className="shrink-0 text-ink-mist-dim" />
        </button>
      )}

      <div className="relative mt-3 grid grid-cols-3 divide-x divide-white/5 rounded-2xl bg-bg-raised/40 py-2 text-center">
        <Stat label="Рейтинг Arena" value={profile.arena_rating} />
        <Stat label="Место" value={`#${profile.arena_rank}`} />
        <Stat label="Уникальных" value={profile.unique_cards} />
      </div>

      <div className="relative mt-4 grid grid-cols-4 gap-2">
        <QuickAction
          Icon={IconPlay}
          label={continueTitle ?? "Играть"}
          hint={continueTitle ? "продолжить" : undefined}
          onClick={() => navigate(lastGame && continueTitle ? lastGame : "/play")}
          accent
        />
        <QuickAction Icon={IconSwap} label="Обмены" onClick={() => navigate("/trades")} badge={attention?.incoming_trades} />
        <QuickAction Icon={IconTarget} label="Задания" onClick={() => navigate("/tasks")} badge={claimableTasks} />
        <QuickAction Icon={IconTrophy} label="Рейтинг" onClick={() => navigate("/ranking")} />
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="px-1">
      <p className="font-display text-base font-bold text-ink-chalk">{value}</p>
      <p className="text-[10px] text-ink-mist">{label}</p>
    </div>
  );
}

function QuickAction({
  Icon, label, hint, onClick, badge, accent,
}: {
  Icon: (props: IconProps) => JSX.Element;
  label: string;
  hint?: string;
  onClick: () => void;
  badge?: number;
  accent?: boolean;
}) {
  return (
    <button onClick={onClick} className="flex min-w-0 flex-col items-center gap-1.5 active:scale-95">
      <span
        className={`relative flex h-12 w-12 items-center justify-center rounded-full ${
          accent ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"
        }`}
      >
        <Icon size={20} />
        {!!badge && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-lime px-1 font-mono text-[9px] font-bold text-bg-base">
            {badge > 9 ? "9+" : badge}
          </span>
        )}
      </span>
      <span className="w-full truncate text-center text-xs leading-tight text-ink-mist">{label}</span>
      {hint && <span className="-mt-1 text-[9px] uppercase tracking-wider text-ink-mist-dim">{hint}</span>}
    </button>
  );
}
