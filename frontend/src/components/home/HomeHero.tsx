import { useNavigate } from "react-router-dom";

import { Skeleton } from "@/components/common/Skeleton";
import { UserBadge } from "@/components/common/UserBadge";
import {
  IconChevronRight,
  IconFire,
  IconPlay,
  IconTarget,
  IconTrophy,
  IconUsers,
  type IconProps,
} from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { usePersistentState } from "@/lib/usePersistentState";
import type { LeagueStatus, ProfilePrivate } from "@/types";

const GAME_TITLES: Record<string, string> = {
  "/play/arena": "Card Arena",
  "/play/tactico": "Тактико",
  "/play/stratego": "Стратего",
  "/play/magnate": "Магнат",
  "/player-tournament": "Турнир",
  "/play/career": "Карьера",
  "/play/penalty": "Пенальти",
  "/play/fut-draft": "FUT Draft",
  "/play/memory": "Memory",
  "/play/saboteur": "Фанат",
  "/play/free-kick": "Штрафной",
  "/play/hangman": "Буквы",
  "/play/pairs": "Пары",
};

/** The top of the home screen: who you are and where you stand (avatar,
 * streak, league progress as a ring around the avatar plus one short line
 * under the name) and the four shortcuts that are NOT already in the
 * bottom nav — the last game, clubs, tasks and the leaderboard. */
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

  const showLeague = leaguesEnabled && !!league && !!tier;
  // League progress is drawn as a ring around the avatar (tap = /league).
  const RING = 2 * Math.PI * 30;

  return (
    <section className="relative overflow-hidden rounded-3xl bg-bg-surface p-5">
      <div className="pointer-events-none absolute -right-10 -top-12 h-40 w-40 rounded-full bg-accent-lime/10 blur-3xl" />

      <div className="relative flex items-center gap-3">
        <button
          type="button"
          onClick={() => showLeague && navigate("/league")}
          disabled={!showLeague}
          className="relative h-16 w-16 shrink-0 active:scale-95"
          aria-label={showLeague ? `Лига: ${league!.current_league?.name ?? "пока вне лиги"}, прогресс ${progress}%` : undefined}
        >
          {showLeague && (
            <svg viewBox="0 0 64 64" className="absolute inset-0 h-full w-full -rotate-90" aria-hidden>
              <circle cx="32" cy="32" r="30" fill="none" strokeWidth="3" className="stroke-white/10" />
              <circle
                cx="32" cy="32" r="30" fill="none" strokeWidth="3" strokeLinecap="round"
                className="stroke-accent-lime transition-[stroke-dashoffset] duration-700"
                strokeDasharray={RING}
                strokeDashoffset={RING * (1 - progress / 100)}
              />
            </svg>
          )}
          <img decoding="async"
            src={profile.avatar_url ?? "/brand/victor-fc-crest.jpg"}
            alt=""
            className={`absolute inset-[5px] h-[54px] w-[54px] rounded-full object-cover ${showLeague ? "" : "ring-2 ring-accent-lime/60"}`}
          />
          {showLeague && (
            <span
              className={`absolute -bottom-0.5 -right-0.5 flex h-6 w-6 items-center justify-center overflow-hidden rounded-full border-2 border-bg-surface bg-bg-raised ${
                league!.current_league ? "" : "opacity-50"
              }`}
            >
              {tier!.image_path ? (
                <img decoding="async" src={staticUrl(tier!.image_path) ?? undefined} alt="" className="h-full w-full object-cover" />
              ) : (
                <IconTrophy size={12} style={{ color: tier!.color }} />
              )}
            </span>
          )}
          {showLeague && league!.unseen_rewards.length > 0 && (
            <span className="absolute -left-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-lime px-1 font-mono text-micro font-bold text-bg-base">
              {league!.unseen_rewards.length}
            </span>
          )}
        </button>
        <div className="min-w-0 flex-1">
          <p className="font-mono text-micro uppercase tracking-wider text-ink-mist">С возвращением</p>
          <p className="flex items-center gap-1.5 truncate font-display text-lg font-bold text-ink-chalk">
            <span className="truncate">{name}</span>
            <UserBadge badge={profile.active_badge} />
          </p>
          {showLeague && (
            <button
              type="button"
              onClick={() => navigate("/league")}
              className="flex max-w-full items-center gap-1 truncate text-left text-caption text-ink-mist active:opacity-70"
            >
              <span className="truncate font-semibold text-ink-chalk">
                {league!.current_league ? league!.current_league.name : "Вне лиги"}
              </span>
              {league!.next_league && (
                <span className="shrink-0 text-ink-mist-dim">· ещё {league!.points_to_next}</span>
              )}
              <IconChevronRight size={12} className="shrink-0 text-ink-mist-dim" />
            </button>
          )}
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

      <div className="relative mt-4 grid grid-cols-4 gap-2">
        <QuickAction
          Icon={IconPlay}
          label={continueTitle ?? "Играть"}
          hint={continueTitle ? "продолжить" : undefined}
          onClick={() => navigate(lastGame && continueTitle ? lastGame : "/play")}
          accent
        />
        <QuickAction Icon={IconUsers} label="Клубы" onClick={() => navigate("/clubs")} />
        <QuickAction Icon={IconTarget} label="Задания" onClick={() => navigate("/tasks")} badge={claimableTasks} />
        <QuickAction Icon={IconTrophy} label="Рейтинг" onClick={() => navigate("/ranking")} />
      </div>
    </section>
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
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-lime px-1 font-mono text-micro font-bold text-bg-base">
            {badge > 9 ? "9+" : badge}
          </span>
        )}
      </span>
      <span className="w-full truncate text-center text-xs leading-tight text-ink-mist">{label}</span>
      {hint && <span className="-mt-1 text-micro uppercase tracking-wider text-ink-mist-dim">{hint}</span>}
    </button>
  );
}
