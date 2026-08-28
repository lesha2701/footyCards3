import { useEffect, useRef, useState } from "react";

import type { MatchEvent } from "@/types";

const EVENT_STEP_MS = 950;

export function TournamentMatchReplay({
  events,
  clubAName,
  clubBName,
  scoreA,
  scoreB,
}: {
  events: MatchEvent[];
  clubAName: string;
  clubBName: string;
  scoreA: number;
  scoreB: number;
}) {
  const [revealedCount, setRevealedCount] = useState(0);
  const [autoSkip, setAutoSkip] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const total = events.length;
  const caughtUp = revealedCount >= total;

  useEffect(() => {
    if (caughtUp) return;
    if (autoSkip) {
      setRevealedCount(total);
      return;
    }
    timerRef.current = setTimeout(() => setRevealedCount((c) => c + 1), EVENT_STEP_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [revealedCount, caughtUp, autoSkip, total]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [revealedCount]);

  const skip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setAutoSkip(true);
  };

  const revealed = events.slice(0, revealedCount);
  const currentMinute = revealed.length ? revealed[revealed.length - 1].minute : 0;
  const liveScoreA = revealed.filter((e) => e.event_type === "goal" && e.team === "a").length;
  const liveScoreB = revealed.filter((e) => e.event_type === "goal" && e.team === "b").length;

  if (total === 0) {
    return (
      <section className="rounded-2xl bg-bg-surface p-4 text-center">
        <p className="text-sm text-ink-mist">Матч не сыгран — один из клубов выбыл из турнира</p>
        <div className="mt-2 flex items-center justify-center gap-2 font-mono text-lg font-bold text-ink-chalk">
          <span className="w-8 text-right">{scoreA}</span>
          <span>:</span>
          <span className="w-8 text-left">{scoreB}</span>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-ink-mist-dim">
          {caughtUp ? "Матч завершён" : autoSkip ? "Пропускаем матч..." : `${currentMinute}' · идёт матч...`}
        </span>
        {!caughtUp && !autoSkip && (
          <button onClick={skip} className="rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold text-ink-chalk">
            Пропустить
          </button>
        )}
      </div>

      <div className="mt-1 flex items-center justify-center gap-2 font-mono text-lg font-bold text-ink-chalk">
        <span className="w-8 text-right">{liveScoreA}</span>
        <span>:</span>
        <span className="w-8 text-left">{liveScoreB}</span>
      </div>
      <p className="text-center text-sm text-ink-mist">{clubAName} vs {clubBName}</p>

      {caughtUp && (
        <div className="mt-1 flex items-center justify-center gap-2 font-display text-sm font-bold text-ink-chalk">
          <span>Итоговый счёт:</span>
          <span className="w-6 text-right">{scoreA}</span>
          <span>:</span>
          <span className="w-6 text-left">{scoreB}</span>
        </div>
      )}

      <div ref={logRef} className="mt-3 max-h-64 space-y-1 overflow-y-auto text-xs">
        {revealed.map((e, i) => (
          <p key={i} className={e.team === "a" ? "text-accent-green" : "text-ink-mist"}>
            <span className="font-mono text-ink-mist-dim">{e.minute}&apos;</span> {e.description}
          </p>
        ))}
      </div>
    </section>
  );
}
