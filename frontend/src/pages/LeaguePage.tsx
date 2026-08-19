import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchLeagues, fetchLeagueStatus } from "@/api/leagues";
import { fetchRanking } from "@/api/leaderboard";
import LeagueRulesModal from "@/components/league/LeagueRulesModal";
import { UserBadge } from "@/components/common/UserBadge";
import { IconHelp, IconTrophy } from "@/components/icons";
import { useAuthStore } from "@/store/authStore";
import type { RankingEntry } from "@/types";

export default function LeaguePage() {
  const user = useAuthStore((s) => s.user);
  const [rulesOpen, setRulesOpen] = useState(false);
  const { data: status } = useQuery({ queryKey: ["league-status"], queryFn: fetchLeagueStatus });
  const { data: tiers } = useQuery({ queryKey: ["leagues"], queryFn: fetchLeagues });
  const { data: ranking } = useQuery({ queryKey: ["ranking", "league_rating"], queryFn: () => fetchRanking("league_rating") });

  const meInTop = !!ranking?.me && ranking.top.some((e) => e.user_id === ranking.me!.user_id);
  // current_league is null for players below the lowest tier's min_rating —
  // the own-stats card still has to render (rating breakdown + "points to
  // next"), falling back to the next tier's icon, dimmed. Only the
  // no-tiers-at-all case (both null) hides the card entirely, as before.
  const ownTier = status?.current_league ?? status?.next_league ?? null;

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

      {status && ownTier && (
        <section className="rounded-2xl bg-bg-surface p-4">
          <div className="flex items-center gap-3">
            <span
              className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-bg-raised text-3xl ${
                status.current_league ? "" : "opacity-40"
              }`}
            >
              {ownTier.icon}
            </span>
            <div>
              <p className="font-display text-lg font-bold text-ink-chalk">
                {status.current_league ? status.current_league.name : "Пока вне лиги"}
              </p>
              <p className="text-xs text-ink-mist">Суммарный рейтинг: {status.total_rating}</p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center">
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{status.arena_rating}</p>
              <p className="text-[10px] text-ink-mist-dim">Arena</p>
            </div>
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{status.tactics_rating}</p>
              <p className="text-[10px] text-ink-mist-dim">Тактико</p>
            </div>
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{status.penalty_rating}</p>
              <p className="text-[10px] text-ink-mist-dim">Пенальти</p>
            </div>
          </div>
          {status.next_league && (
            <p className="mt-3 text-center text-xs text-ink-mist">
              Ещё {status.points_to_next} очков до «{status.next_league.name}»
            </p>
          )}
        </section>
      )}

      {tiers && tiers.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-mist">Лестница лиг</h2>
          {tiers.map((t) => (
            <div
              key={t.id}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${
                status?.current_league?.id === t.id ? "bg-accent-lime/12" : "bg-bg-surface"
              }`}
            >
              <span className="text-xl">{t.icon}</span>
              <div className="flex-1">
                <p className={status?.current_league?.id === t.id ? "font-semibold text-accent-lime" : "text-ink-chalk"}>
                  {t.name}
                </p>
                <p className="text-[11px] text-ink-mist-dim">от {t.min_rating} рейтинга</p>
              </div>
            </div>
          ))}
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
