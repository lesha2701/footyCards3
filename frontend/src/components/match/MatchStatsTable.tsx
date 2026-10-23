import { matchStats, type SideStats } from "@/lib/matchVisual";
import type { MatchEvent } from "@/types";

const ROWS: { key: keyof SideStats; label: string }[] = [
  { key: "shots", label: "Удары" },
  { key: "onTarget", label: "В створ" },
  { key: "corners", label: "Угловые" },
  { key: "tacklesWon", label: "Отборы" },
  { key: "offsides", label: "Офсайды" },
  { key: "yellow", label: "Жёлтые" },
  { key: "red", label: "Красные" },
];

/** Post-match numbers, counted from the same event log as the commentary.
 * You on the left, the opponent on the right — same as the score and pitch. */
export default function MatchStatsTable({
  events,
  opponentName,
  leftLabel = "Ты",
}: {
  events: MatchEvent[];
  opponentName: string;
  /** Name of the left column's side (default: the player). */
  leftLabel?: string;
}) {
  const stats = matchStats(events);
  // Rare rows only when something actually happened — "0 — 0" rows are noise.
  const rows = ROWS.filter((r) => !["yellow", "red", "offsides"].includes(r.key) || stats.user[r.key] + stats.opponent[r.key] > 0);

  return (
    <div className="rounded-xl bg-black/20 px-3 py-2">
      <div className="mb-1 flex items-center justify-between text-caption font-semibold">
        <span className="max-w-[40%] truncate text-accent-green">{leftLabel}</span>
        <span className="text-ink-mist-dim">Статистика</span>
        <span className="max-w-[40%] truncate text-red-400">{opponentName}</span>
      </div>
      {rows.map(({ key, label }) => {
        const mine = stats.user[key];
        const theirs = stats.opponent[key];
        const total = mine + theirs;
        const myShare = total ? (mine / total) * 100 : 50;
        return (
          <div key={key} className="py-1">
            <div className="flex items-center justify-between font-mono text-xs">
              <span className={mine > theirs ? "font-bold text-ink-chalk" : "text-ink-mist"}>{mine}</span>
              <span className="font-body text-caption text-ink-mist">{label}</span>
              <span className={theirs > mine ? "font-bold text-ink-chalk" : "text-ink-mist"}>{theirs}</span>
            </div>
            <div className="mt-0.5 flex h-1 overflow-hidden rounded-full bg-red-400/80">
              <div className="h-full bg-accent-green/80" style={{ width: `${myShare}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
