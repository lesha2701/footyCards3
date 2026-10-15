import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchPathState } from "@/api/path";
import PathSheet from "@/components/path/PathSheet";
import TalentBlock from "@/components/path/TalentBlock";
import { levelFraction, shownLevelXp, pathFraction, stageIcon } from "@/lib/pathCards";
import type { Player } from "@/types";

/** «Начало пути» block of the card detail sheet: stage, path progress, the
 * next level, the talent and the button to the full «Путь» screen. */
export default function PathPanel({ cardId, player }: { cardId: number; player: Player }) {
  const [open, setOpen] = useState(false);
  const { data: state } = useQuery({ queryKey: ["path", cardId], queryFn: () => fetchPathState(cardId) });
  if (!state) return null;
  const tasksLeft = state.stages.find((s) => s.current)?.tasks.filter((t) => !t.done).length ?? 0;
  return (
    <div className="path-ui mt-3 space-y-2">
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full rounded-2xl border border-emerald-400/30 bg-emerald-400/5 p-3 text-left"
      >
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
            🌱 {state.title} · {stageIcon(state.stage)} {state.stage_name}
          </p>
          <span className="font-mono text-xs text-ink-mist">
            {state.rating} → {state.ceiling}
          </span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-black/30" aria-label="Прогресс пути">
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-lime-300"
            style={{ width: `${Math.round(pathFraction(state) * 100)}%` }}
          />
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[11px] text-ink-mist">
          <span>
            {state.xp_for_next
              ? `Опыт до ${state.rating + 1}: ${shownLevelXp(state)}/${state.xp_for_next} (${Math.round(levelFraction(state) * 100)}%)`
              : "Путь пройден"}
          </span>
          {tasksLeft > 0 && <span className="text-amber-300">заданий: {tasksLeft}</span>}
        </div>
        <p className="mt-2 text-center text-sm font-semibold text-emerald-300">Открыть путь →</p>
      </button>
      {state.talent && <TalentBlock talent={state.talent} compact />}
      {open && <PathSheet cardId={cardId} player={player} onClose={() => setOpen(false)} />}
    </div>
  );
}
