import { useNavigate } from "react-router-dom";

import iconArt from "@/assets/bingo/icon.webp";
import { IconChevronRight, IconClock } from "@/components/icons";
import { bingoReady } from "@/lib/bingo";
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

/** «Событие недели»: a slim full-width strip for the weekly bingo with the
 * player's own card (lines closed, cells done) — or, on an old backend, the
 * common goals — and the time left. Hidden while it's off. */
export default function WeeklyEventStrip({ bingo }: { bingo?: BingoCurrent | null }) {
  const navigate = useNavigate();
  if (!bingo?.is_enabled) return null;

  const card = bingo.card;
  const total = card ? card.cells.length : bingo.goals.length;
  const done = card ? card.cells.filter((c) => c.done).length : bingo.goals.filter((g) => g.is_completed).length;
  const rewardReady = bingoReady(bingo);
  const finished = card ? card.full_claimed : bingo.has_claimed;
  const status = rewardReady
    ? "Награда готова — забрать"
    : finished
      ? "Карточка закрыта, награда получена"
      : card
        ? `Рядов: ${card.lines_done.length}/${card.lines.length} · клеток ${done}/${total}`
        : `Целей: ${done}/${total}`;

  return (
    <button
      onClick={() => navigate("/bingo")}
      className={`flex items-center gap-3 rounded-2xl px-3 py-2.5 text-left ring-1 active:scale-[0.98] ${
        rewardReady ? "bg-accent-lime/10 ring-accent-lime/40" : "bg-fuchsia-500/10 ring-fuchsia-400/25"
      }`}
    >
      <img src={iconArt} alt="" className="h-10 w-10 shrink-0 drop-shadow" />
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-2">
          <span className="truncate font-display text-sm font-bold text-ink-chalk">Бинго недели</span>
          {bingo.ends_at && !finished && (
            <span className="flex shrink-0 items-center gap-1 font-mono text-micro text-ink-mist">
              <IconClock size={11} />
              {formatTimeLeft(bingo.ends_at)}
            </span>
          )}
        </span>
        <span className={`block truncate text-xs ${rewardReady ? "font-semibold text-accent-lime" : "text-ink-mist"}`}>
          {status}
        </span>
        {total > 0 && !finished && (
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
