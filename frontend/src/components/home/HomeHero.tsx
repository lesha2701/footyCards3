import { useNavigate } from "react-router-dom";

import { Skeleton } from "@/components/common/Skeleton";
import { UserBadge } from "@/components/common/UserBadge";
import { IconFire, IconTrophy } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import type { LeagueStatus, ProfilePrivate } from "@/types";

/** The top of the home screen: who you are and where you stand. League
 * progress is a ring around the avatar (tap = /league) with the league
 * emblem on it, the login streak sits on the photo above the emblem, and
 * the rating chip on the right opens the leaderboard. */
export default function HomeHero({
  profile,
  league,
  leaguesEnabled,
}: {
  profile?: ProfilePrivate;
  league?: LeagueStatus;
  leaguesEnabled: boolean;
}) {
  const navigate = useNavigate();

  if (!profile) {
    return (
      <section className="flex items-center gap-3 rounded-3xl bg-bg-surface p-5" aria-busy="true">
        <Skeleton className="h-16 w-16 rounded-full" />
        <div className="flex flex-1 flex-col gap-2">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-5 w-40" />
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
  const showLeague = leaguesEnabled && !!league && !!tier;
  const streak = profile.daily_login_streak;
  const RING = 2 * Math.PI * 30;

  return (
    <section className="relative overflow-hidden rounded-3xl bg-bg-surface p-4">
      <div className="pointer-events-none absolute -right-10 -top-12 h-40 w-40 rounded-full bg-accent-lime/10 blur-3xl" />

      <div className="relative flex items-center gap-3">
        <button
          type="button"
          onClick={() => showLeague && navigate("/league")}
          disabled={!showLeague}
          className="relative h-16 w-16 shrink-0 active:scale-95"
          aria-label={
            showLeague
              ? `Лига: ${league!.current_league?.name ?? "пока вне лиги"}, прогресс ${progress}%` +
                (league!.next_league ? `, до следующей ${league!.points_to_next}` : "")
              : undefined
          }
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
          {streak > 0 && (
            <span
              className="absolute -right-2 -top-1 flex items-center gap-0.5 rounded-full border-2 border-bg-surface bg-orange-500 px-1.5 py-px font-mono text-micro font-bold leading-tight text-white"
              title="Дней подряд в игре"
              aria-label={`Дней подряд в игре: ${streak}`}
            >
              <IconFire size={10} />
              {streak}
            </span>
          )}
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
        </div>
        {profile.arena_rank > 0 && (
          <button
            type="button"
            onClick={() => navigate("/ranking")}
            className="flex shrink-0 flex-col items-end rounded-2xl bg-accent-lime/10 px-2.5 py-1 active:scale-95"
            aria-label={`Место в рейтинге: ${profile.arena_rank}`}
          >
            <span className="flex items-center gap-1 font-mono text-sm font-bold text-accent-lime tabular-nums">
              <IconTrophy size={13} />#{profile.arena_rank}
            </span>
            <span className="text-micro uppercase tracking-wider text-ink-mist">рейтинг</span>
          </button>
        )}
      </div>
    </section>
  );
}
