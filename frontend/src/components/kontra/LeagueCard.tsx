import { motion } from "framer-motion";

import { IconCoin } from "@/components/icons";
import type { KontraLeague } from "@/types";

function left(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "итоги подводятся";
  const h = Math.floor(ms / 3600000);
  return h >= 24 ? `${Math.floor(h / 24)} д ${h % 24} ч` : `${h} ч ${Math.floor((ms % 3600000) / 60000)} мин`;
}

const TINT = [
  "from-amber-900/70 to-bg-surface ring-amber-700/40",
  "from-slate-600/60 to-bg-surface ring-slate-400/40",
  "from-yellow-600/50 to-bg-surface ring-yellow-400/50",
  "from-cyan-700/50 to-bg-surface ring-cyan-300/50",
  "from-fuchsia-700/50 to-bg-surface ring-fuchsia-300/60",
];

/** The weekly arena league: set by the best rating of the week, paid in
 *  coins when the week ends (claimed on the «Контратака» screen). */
export default function LeagueCard({ league, compact = false }: { league: KontraLeague; compact?: boolean }) {
  const prev = league.tiers[league.index]?.at ?? 0;
  const pct = league.next_at ? Math.max(0, Math.min(100, ((league.week_best - prev) * 100) / Math.max(1, league.next_at - prev))) : 100;
  return (
    <section className={`rounded-2xl bg-gradient-to-br p-3 ring-1 ${TINT[league.index] ?? TINT[0]}`}>
      <div className="flex items-center gap-3">
        <motion.span className="text-3xl" initial={{ scale: 0.6, rotate: -20 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring" }}>
          {league.icon}
        </motion.span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mist">Лига недели</p>
          <p className="font-display text-lg font-black leading-tight text-ink-chalk">{league.name}</p>
          <p className="text-micro text-ink-mist">Лучший рейтинг недели: <b className="text-ink-chalk">{league.week_best || "—"}</b> · до итогов {left(league.week_ends)}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="flex items-center justify-end gap-1 font-mono text-sm font-black text-amber-300">{league.coins} <IconCoin size={12} /></p>
          <p className="text-[10px] text-ink-mist">за неделю</p>
        </div>
      </div>
      {!compact && (
        <>
          <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-black/40">
            <motion.div className="h-full rounded-full bg-gradient-to-r from-amber-300 to-orange-500" initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.8 }} />
          </div>
          <div className="mt-1.5 flex justify-between gap-1">
            {league.tiers.map((t, i) => (
              <span key={t.name} className={`flex flex-col items-center text-[10px] leading-tight ${i <= league.index ? "text-ink-chalk" : "text-ink-mist-dim"}`}>
                <span className={`text-base ${i <= league.index ? "" : "opacity-40 grayscale"}`}>{t.icon}</span>
                <span className="font-mono">{t.at || "старт"}</span>
              </span>
            ))}
          </div>
          {league.next_name && (
            <p className="mt-1 text-center text-micro text-ink-mist">
              {league.week_best
                ? <>До лиги «{league.next_name}» — {league.next_at! - league.week_best} рейтинга · награда {league.next_coins} <IconCoin size={10} className="inline" /></>
                : "Сыграй бой на арене — лига считается по лучшему рейтингу недели"}
            </p>
          )}
        </>
      )}
    </section>
  );
}
