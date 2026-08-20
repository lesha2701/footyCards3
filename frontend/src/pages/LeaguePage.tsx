import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ackLeagueRewards, fetchLeagues, fetchLeagueStatus } from "@/api/leagues";
import { fetchRanking } from "@/api/leaderboard";
import LeagueRewardModal from "@/components/league/LeagueRewardModal";
import LeagueRulesModal from "@/components/league/LeagueRulesModal";
import { UserBadge } from "@/components/common/UserBadge";
import { IconCheck, IconCoin, IconGift, IconHelp, IconPack, IconTrophy } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { RankingEntry } from "@/types";

export default function LeaguePage() {
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();
  const [rulesOpen, setRulesOpen] = useState(false);
  const [rewardModalOpen, setRewardModalOpen] = useState(false);
  const { data: status } = useQuery({ queryKey: ["league-status"], queryFn: fetchLeagueStatus });
  const { data: tiers } = useQuery({ queryKey: ["leagues"], queryFn: fetchLeagues });
  const { data: ranking } = useQuery({ queryKey: ["ranking", "league_rating"], queryFn: () => fetchRanking("league_rating") });

  const ackMutation = useMutation({
    mutationFn: ackLeagueRewards,
    onSuccess: (updated) => {
      queryClient.setQueryData(["league-status"], updated);
      setRewardModalOpen(false);
    },
  });

  const meInTop = !!ranking?.me && ranking.top.some((e) => e.user_id === ranking.me!.user_id);
  // current_league is null for players below the lowest tier's min_rating —
  // the own-stats card still has to render (rating breakdown + "points to
  // next"), falling back to the next tier's badge, dimmed. Only the
  // no-tiers-at-all case (both null) hides the card entirely, as before.
  const ownTier = status?.current_league ?? status?.next_league ?? null;
  const unseenCount = status?.unseen_rewards.length ?? 0;

  const currentTierRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    currentTierRef.current?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }, [tiers, status?.current_league?.id]);

  const progressFloor = status?.current_league?.min_rating ?? 0;
  const progressPct =
    status?.next_league && status
      ? Math.min(100, Math.max(0, Math.round(((status.total_rating - progressFloor) / (status.next_league.min_rating - progressFloor)) * 100)))
      : null;

  const modeTotal = status ? status.arena_rating + status.tactics_rating + status.penalty_rating : 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconTrophy size={20} className="text-accent-lime" />
          Лиги
        </h1>
        <button
          onClick={() => setRulesOpen(true)}
          aria-label="Правила"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-white/5 text-ink-mist active:scale-95"
        >
          <IconHelp size={15} />
        </button>
      </div>

      {unseenCount > 0 && (
        <button
          onClick={() => setRewardModalOpen(true)}
          className="flex items-center gap-3 rounded-2xl bg-accent-lime/12 px-4 py-3 text-left active:scale-[0.98]"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-lime/20 text-accent-lime">
            <IconGift size={18} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-sm font-bold text-accent-lime">
              {unseenCount > 1 ? `Новые награды за лиги (${unseenCount})` : "Новая награда за лигу"}
            </p>
            <p className="mt-0.5 text-[11px] text-ink-mist">Нажми, чтобы забрать</p>
          </div>
        </button>
      )}

      {status && ownTier && (
        <section className="rounded-2xl bg-bg-surface p-4">
          <div className="flex items-center gap-3">
            <span
              className={`flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-full bg-bg-raised ${
                status.current_league ? "" : "opacity-40"
              }`}
            >
              {ownTier.image_path ? (
                <img src={staticUrl(ownTier.image_path) ?? undefined} className="h-full w-full object-cover" />
              ) : (
                <IconTrophy size={28} style={{ color: ownTier.color }} />
              )}
            </span>
            <div>
              <p className="font-display text-lg font-bold text-ink-chalk">
                {status.current_league ? status.current_league.name : "Пока вне лиги"}
              </p>
              <p className="text-xs text-ink-mist">Суммарный рейтинг: {status.total_rating}</p>
              {status.current_league_percent !== null && (
                <p className="text-[11px] text-ink-mist-dim">{status.current_league_percent}% игроков в этой лиге</p>
              )}
            </div>
          </div>

          {modeTotal > 0 && (
            <div className="mt-4 flex h-2 overflow-hidden rounded-full bg-white/5">
              <div className="h-full bg-accent-cyan" style={{ width: `${(status.arena_rating / modeTotal) * 100}%` }} />
              <div className="h-full bg-accent-lime" style={{ width: `${(status.tactics_rating / modeTotal) * 100}%` }} />
              <div className="h-full bg-rarity-epic" style={{ width: `${(status.penalty_rating / modeTotal) * 100}%` }} />
            </div>
          )}
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{status.arena_rating}</p>
              <p className="text-[10px] text-ink-mist-dim">Arena</p>
            </div>
            <div>
              <p className="font-mono text-sm font-bold text-accent-lime">{status.tactics_rating}</p>
              <p className="text-[10px] text-ink-mist-dim">Тактико</p>
            </div>
            <div>
              <p className="font-mono text-sm font-bold text-rarity-epic">{status.penalty_rating}</p>
              <p className="text-[10px] text-ink-mist-dim">Пенальти</p>
            </div>
          </div>

          {status.next_league && progressPct !== null && (
            <>
              <p className="mt-3 text-center text-xs text-ink-mist">
                Ещё {status.points_to_next} очков до «{status.next_league.name}»
              </p>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                <div className="h-full rounded-full bg-accent-lime" style={{ width: `${progressPct}%` }} />
              </div>
            </>
          )}
        </section>
      )}

      {tiers && tiers.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-mist">Лестница лиг</h2>
          <div className="-mx-4 flex snap-x snap-mandatory gap-5 overflow-x-auto px-6 pb-2">
            {tiers.map((t) => {
              const isCurrent = status?.current_league?.id === t.id;
              // A tier is "achieved" once claimed — compare against the
              // floor-adjusted current league, not live total_rating, so an
              // already-reached tier keeps its checkmark even if rating dips.
              const achieved = status?.current_league ? t.min_rating <= status.current_league.min_rating : false;
              return (
                <div
                  key={t.id}
                  ref={isCurrent ? currentTierRef : undefined}
                  className={`relative flex w-[84%] shrink-0 snap-center flex-col items-center gap-2 rounded-3xl px-2 py-4 text-center ${
                    isCurrent ? "bg-accent-lime/12" : "bg-bg-surface"
                  }`}
                >
                  {achieved && !isCurrent && (
                    <span className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full bg-accent-lime/20 text-accent-lime">
                      <IconCheck size={14} />
                    </span>
                  )}
                  {t.image_path ? (
                    <img src={staticUrl(t.image_path) ?? undefined} className="h-56 w-56 rounded-2xl object-cover" />
                  ) : (
                    <span className="flex h-56 w-56 items-center justify-center">
                      <IconTrophy size={100} style={{ color: t.color }} />
                    </span>
                  )}
                  <p className={`font-display text-lg leading-tight ${isCurrent ? "font-bold text-accent-lime" : "font-semibold text-ink-chalk"}`}>
                    {t.name}
                  </p>
                  <p className="text-xs text-ink-mist-dim">от {t.min_rating} рейтинга</p>
                  <div className="mt-1 flex items-center gap-3 text-sm text-ink-mist">
                    {t.reward_coins > 0 && (
                      <span className="flex items-center gap-1">
                        <IconCoin size={15} className="text-accent-lime" />+{t.reward_coins}
                      </span>
                    )}
                    {t.reward_pack_name && (
                      <span className="flex items-center gap-1 truncate">
                        <IconPack size={15} className="text-accent-cyan" />
                        {t.reward_pack_name}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section className="flex flex-col gap-2">
        <h2 className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-mist">Топ игроков</h2>
        {ranking?.top.map((entry) => (
          <RankingRow key={entry.user_id} entry={entry} highlight={entry.user_id === user?.id} />
        ))}
        {ranking?.me && !meInTop && (
          <>
            <p className="mt-1 text-center text-xs text-ink-mist-dim">⋯</p>
            <RankingRow entry={ranking.me} highlight />
          </>
        )}
      </section>

      <LeagueRulesModal open={rulesOpen} onClose={() => setRulesOpen(false)} />
      <LeagueRewardModal
        open={rewardModalOpen}
        rewards={status?.unseen_rewards ?? []}
        collecting={ackMutation.isPending}
        onCollect={() => ackMutation.mutate()}
        onClose={() => setRewardModalOpen(false)}
      />
    </div>
  );
}

function RankingRow({ entry, highlight = false }: { entry: RankingEntry; highlight?: boolean }) {
  return (
    <div className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm ${highlight ? "bg-accent-lime/12" : "bg-bg-surface"}`}>
      <div className="flex items-center gap-2">
        <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">{entry.rank}</span>
        <span className={highlight ? "font-semibold text-accent-lime" : "text-ink-chalk"}>{entry.display_name}</span>
        <UserBadge badge={entry.active_badge} />
      </div>
      <span className="font-mono font-bold text-accent-cyan">{entry.value}</span>
    </div>
  );
}
