import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ComponentType, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { attackClubRaid, fetchClubRaid, type ClubRaid } from "@/api/events";
import { IconBrain, IconCheck, IconClock, IconGift, IconGoal, IconShirt } from "@/components/icons";
import { raidBossArt } from "@/lib/bossArt";
import { useOpenClubSheet } from "@/lib/clubSheet";
import { formatGameError } from "@/lib/errors";
import { formatCountdown } from "@/lib/format";
import { hapticNotify } from "@/lib/telegram";
import type { Club } from "@/types";

const GAMES: { key: "game" | "penalty" | "position_match"; to: string; title: string; icon: ComponentType<{ size?: number; className?: string }> }[] = [
  { key: "penalty", to: "/clubs/penalty", title: "Пенальти", icon: IconGoal },
  { key: "game", to: "/clubs/game", title: "Порядок", icon: IconBrain },
  { key: "position_match", to: "/clubs/position-match", title: "Позиции", icon: IconShirt },
];

function Row({ done, children }: { done: boolean; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 py-2.5">
      <span
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${done ? "bg-accent-lime text-bg-base" : "ring-[1.5px] ring-inset ring-ink-mist-dim/60"}`}
        aria-label={done ? "сделано" : "не сделано"}
      >
        {done && <IconCheck size={12} />}
      </span>
      <div className="flex min-w-0 flex-1 items-center gap-2.5">{children}</div>
    </div>
  );
}

function goals(n: number) {
  const d = n % 10;
  if (n % 100 >= 11 && n % 100 <= 14) return `${n} голов`;
  return `${n} ${d === 1 ? "гол" : d >= 2 && d <= 4 ? "гола" : "голов"}`;
}

/** «Дела на сегодня»: what a member comes to the club for — the daily
 * reward, the raid boss and the club games — done right here, without
 * opening a section. */
export function ClubToday({ club, onClaim, claiming }: { club: Club; onClaim: () => void; claiming: boolean }) {
  const navigate = useNavigate();
  const openSheet = useOpenClubSheet();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<ClubRaid["last"]>(null);
  const { data: raid } = useQuery({ queryKey: ["clubs", "raid"], queryFn: fetchClubRaid });
  const attack = useMutation({
    mutationFn: attackClubRaid,
    onSuccess: (view) => {
      queryClient.setQueryData(["clubs", "raid"], view);
      setLast(view.last);
      setError(null);
      hapticNotify(view.last?.defeated_now ? "success" : "warning");
      if (view.last?.defeated_now) void queryClient.invalidateQueries({ queryKey: ["clubs", "me"] });
    },
    onError: (err) => setError(formatGameError(err, "Атака не удалась")),
  });

  const rewardReady = club.daily_reward_seconds_remaining === null;
  const games = club.games_rewards_left;
  const gamesLeft = games ? games.game + games.penalty + games.position_match : 0;
  const showRaid = !!raid?.enabled;
  const raidDone = !!raid && (raid.defeated || raid.attacks_left === 0);
  const items = [!rewardReady, ...(showRaid ? [raidDone] : []), ...(games ? [gamesLeft === 0] : [])];
  const done = items.filter(Boolean).length;
  const hpPct = raid ? Math.round((Math.max(0, raid.hp - raid.damage) / raid.hp) * 100) : 0;
  const bossArt = raid ? raidBossArt(raid.boss.code) : undefined;

  return (
    <section className="rounded-3xl bg-bg-surface px-4 pb-1.5 pt-3.5" aria-label="Дела на сегодня">
      <div className="flex items-center justify-between">
        <p className="font-display text-sm font-bold text-ink-chalk">Дела на сегодня</p>
        <span className={`font-mono text-xs font-bold tabular-nums ${done === items.length ? "text-accent-lime" : "text-ink-mist"}`}>
          {done}/{items.length}
        </span>
      </div>

      <div className="divide-y divide-white/5">
        <Row done={!rewardReady}>
          <IconGift size={16} className="shrink-0 text-accent-lime" />
          <span className="min-w-0 flex-1 text-sm text-ink-chalk">Награда дня</span>
          {rewardReady ? (
            <button
              onClick={onClaim}
              disabled={claiming}
              className="shrink-0 rounded-xl bg-floodlight px-3.5 py-1.5 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              Забрать
            </button>
          ) : (
            <span className="flex shrink-0 items-center gap-1 text-caption text-ink-mist">
              <IconClock size={12} /> {formatCountdown(club.daily_reward_seconds_remaining ?? 0)}
            </span>
          )}
        </Row>

        {showRaid && raid && (
          <Row done={raidDone}>
            <button onClick={() => openSheet("raid")} className="flex min-w-0 flex-1 items-center gap-2.5 text-left active:scale-[0.99]">
              {bossArt ? (
                <img src={bossArt} alt="" className={`h-9 w-9 shrink-0 rounded-xl object-cover ${raid.defeated ? "grayscale" : ""}`} />
              ) : (
                <span className="text-2xl">{raid.boss.emoji}</span>
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink-chalk">
                  {raid.defeated ? `${raid.boss.name} повержен` : `Босс: ${raid.boss.name}`}
                </span>
                {last ? (
                  <span className="block truncate text-caption font-semibold text-accent-lime">
                    {goals(last.goals)} · −{last.damage.toLocaleString("ru-RU")} {last.defeated_now ? "· повержен!" : ""}
                  </span>
                ) : (
                  <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-black/40">
                    <span
                      className={`block h-full rounded-full ${raid.defeated ? "bg-accent-green" : "bg-gradient-to-r from-red-500 to-orange-400"}`}
                      style={{ width: `${raid.defeated ? 100 : hpPct}%` }}
                    />
                  </span>
                )}
              </span>
            </button>
            {!raid.defeated && raid.attacks_left > 0 ? (
              <button
                onClick={() => attack.mutate()}
                disabled={attack.isPending}
                className="shrink-0 rounded-xl bg-gradient-to-r from-red-500 to-orange-500 px-3 py-1.5 text-xs font-bold text-white active:scale-95 disabled:opacity-50"
              >
                {attack.isPending ? "…" : `Удар ${raid.attacks_left}/${raid.attacks_per_day}`}
              </button>
            ) : (
              <span className="shrink-0 text-caption text-ink-mist">{raid.defeated ? "награда в магазине" : "завтра ещё"}</span>
            )}
          </Row>
        )}

        {games && (
          <Row done={gamesLeft === 0}>
            <div className="grid min-w-0 flex-1 grid-cols-3 gap-1.5">
              {GAMES.map(({ key, to, title, icon: Icon }) => (
                <button
                  key={key}
                  onClick={() => navigate(to)}
                  className={`flex min-w-0 flex-col items-center gap-0.5 rounded-xl py-2 active:scale-95 ${games[key] ? "bg-accent-lime/10" : "bg-white/5"}`}
                >
                  <Icon size={16} className={games[key] ? "text-accent-lime" : "text-ink-mist-dim"} />
                  <span className="w-full truncate px-1 text-center text-caption font-semibold text-ink-chalk">{title}</span>
                  <span className="text-micro text-ink-mist">{games[key] ? `наград: ${games[key]}` : "всё взято"}</span>
                </button>
              ))}
            </div>
          </Row>
        )}
      </div>
      {error && <p className="mb-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
    </section>
  );
}
