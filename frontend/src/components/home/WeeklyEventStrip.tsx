import { useNavigate } from "react-router-dom";

import { IconChevronRight, IconClock, IconTarget } from "@/components/icons";
import type { BingoCurrent } from "@/types";

/** Time left until `endsAt`, short: «2 дн. 5 ч», «3 ч 10 мин», «12 мин». */
function formatTimeLeft(endsAt: string): string {
  const ms = new Date(endsAt).getTime() - Date.now();
  if (ms <= 0) return "меньше минуты";
  const days = Math.floor(ms / 86_400_000);
  const hours = Math.floor((ms % 86_400_000) / 3_600_000);
  if (days > 0) return `${days} дн. ${hours} ч`;
  const minutes = Math.floor((ms % 3_600_000) / 60_000);
  return hours > 0 ? `${hours} ч ${minutes} мин` : `${minutes} мин`;
}

/** «Событие недели»: a slim full-width strip for the weekly bingo with
 * goals done, a progress bar and the time left. Hidden while it's off. */
export default function WeeklyEventStrip({ bingo }: { bingo?: BingoCurrent | null }) {
  const navigate = useNavigate();
  if (!bingo?.is_enabled) return null;

  const total = bingo.goals.length;
  const done = bingo.goals.filter((g) => g.is_completed).length;
  const rewardReady = bingo.all_goals_completed && !bingo.has_claimed;
  const status = rewardReady
    ? "Награда готова — забрать"
    : bingo.has_claimed
      ? "Пройдено, награда получена"
      : `Целей: ${done}/${total}`;

  return (
    <button
      onClick={() => navigate("/bingo")}
      className={`flex items-center gap-3 rounded-2xl px-3 py-2.5 text-left ring-1 active:scale-[0.98] ${
        rewardReady ? "bg-accent-lime/10 ring-accent-lime/40" : "bg-fuchsia-500/10 ring-fuchsia-400/25"
      }`}
    >
      <span
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
          rewardReady ? "bg-accent-lime/20 text-accent-lime" : "bg-fuchsia-400/20 text-fuchsia-300"
        }`}
      >
        <IconTarget size={18} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-2">
          <span className="truncate font-display text-sm font-bold text-ink-chalk">Бинго недели</span>
          {bingo.ends_at && !bingo.has_claimed && (
            <span className="flex shrink-0 items-center gap-1 font-mono text-micro text-ink-mist">
              <IconClock size={11} />
              {formatTimeLeft(bingo.ends_at)}
            </span>
          )}
        </span>
        <span className={`block truncate text-xs ${rewardReady ? "font-semibold text-accent-lime" : "text-ink-mist"}`}>
          {status}
        </span>
        {total > 0 && !bingo.has_claimed && (
          <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-white/10">
            <span
              className={`block h-full rounded-full ${rewardReady ? "bg-accent-lime" : "bg-fuchsia-400"}`}
              style={{ width: `${Math.round((done / total) * 100)}%` }}
            />
          </span>
        )}
      </span>
      <IconChevronRight size={16} className="shrink-0 text-ink-mist-dim" />
    </button>
  );
}
