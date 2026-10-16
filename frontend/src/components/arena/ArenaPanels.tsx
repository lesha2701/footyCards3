import { IconCoin, IconTrophy } from "@/components/icons";
import { TACTIC_LABELS, TACTICS } from "@/lib/formation";
import type {
  ArenaChances,
  ArenaDivision,
  ArenaLineCompare,
  ArenaMatchup,
  ArenaPreview,
  LineupTactic,
  Match,
} from "@/types";

const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : "0");

const matchupClass = (m: ArenaMatchup) =>
  m === "win" ? "text-accent-green" : m === "loss" ? "text-red-400" : "text-ink-mist";

/** Division N of M, points, the bar to the next division and the shield. */
export function ArenaDivisionCard({ division, rank }: { division: ArenaDivision; rank: number | null }) {
  const span = division.next_min_points != null ? division.next_min_points - division.min_points : null;
  const progress = span ? Math.min(100, Math.max(0, ((division.points - division.min_points) / span) * 100)) : 100;
  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-caption text-ink-mist-dim">Дивизион арены</p>
          <p className="font-display text-2xl font-bold leading-tight text-ink-chalk">
            {division.division}
            <span className="ml-1 text-sm font-semibold text-ink-mist-dim">из {division.total_divisions}</span>
          </p>
        </div>
        <div className="text-right">
          <p className="font-mono text-lg font-bold text-accent-cyan">{division.points}</p>
          <p className="text-micro text-ink-mist-dim">очков{rank != null ? ` · #${rank}` : ""}</p>
        </div>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-accent-cyan transition-all" style={{ width: `${progress}%` }} />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-caption text-ink-mist">
        {division.next_min_points != null ? (
          <span className="flex items-center gap-1">
            До дивизиона {division.division + 1}: {division.next_min_points - division.points} очков
            {!!division.next_reward_coins && (
              <span className="flex items-center gap-0.5 text-accent-lime">
                · +{division.next_reward_coins} <IconCoin size={11} />
              </span>
            )}
          </span>
        ) : (
          <span className="flex items-center gap-1 text-accent-lime"><IconTrophy size={12} /> Высший дивизион</span>
        )}
        {division.coin_pct !== 100 && <span>Монеты за матч ×{(division.coin_pct / 100).toFixed(2)}</span>}
      </div>
      {division.shield_matches > 0 && (
        <p className="mt-2 rounded-lg bg-accent-green/10 px-2.5 py-1.5 text-caption text-accent-green">
          🛡 Защита от вылета ещё {division.shield_matches} {plural(division.shield_matches, "матч", "матча", "матчей")}
        </p>
      )}
    </section>
  );
}

function plural(n: number, one: string, few: string, many: string) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

/** Your line vs his, the bigger number highlighted. */
export function ArenaLinesCompare({ lines, opponentName }: { lines: ArenaLineCompare[]; opponentName: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between text-micro text-ink-mist-dim">
        <span>Вы</span>
        <span className="max-w-[60%] truncate">{opponentName}</span>
      </div>
      {lines.map((line) => {
        const total = line.user + line.opponent || 1;
        const userWins = line.user > line.opponent;
        const oppWins = line.opponent > line.user;
        return (
          <div key={line.key}>
            <div className="mb-0.5 flex items-center justify-between font-mono text-caption">
              <span className={userWins ? "font-bold text-accent-green" : "text-ink-mist"}>{line.user}</span>
              <span className="font-sans text-micro text-ink-mist-dim">{line.label}</span>
              <span className={oppWins ? "font-bold text-red-400" : "text-ink-mist"}>{line.opponent}</span>
            </div>
            <div className="flex h-1.5 overflow-hidden rounded-full bg-white/5">
              <div className={userWins ? "bg-accent-green" : "bg-white/25"} style={{ width: `${(line.user / total) * 100}%` }} />
              <div className={oppWins ? "bg-red-400" : "bg-white/15"} style={{ width: `${(line.opponent / total) * 100}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function ArenaChancesBar({ chances }: { chances: ArenaChances }) {
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full">
        <div className="bg-accent-green" style={{ width: `${chances.win}%` }} />
        <div className="bg-white/25" style={{ width: `${chances.draw}%` }} />
        <div className="bg-red-400" style={{ width: `${chances.loss}%` }} />
      </div>
      <div className="mt-1 flex justify-between font-mono text-micro">
        <span className="text-accent-green">Победа ≈{chances.win}%</span>
        <span className="text-ink-mist">Ничья ≈{chances.draw}%</span>
        <span className="text-red-400">Поражение ≈{chances.loss}%</span>
      </div>
    </div>
  );
}

/** The next opponent before kickoff: who, how strong, the style matchup,
 *  ≈ chances and the points at stake; the style can be changed right here. */
export function ArenaOpponentCard({
  preview,
  onStyle,
  stylePending,
}: {
  preview: ArenaPreview;
  onStyle: (style: LineupTactic) => void;
  stylePending: boolean;
}) {
  const diff = preview.user_strength - preview.opponent_strength;
  const counter = TACTICS.find((t) => t.beats === preview.opponent_style);
  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-caption text-ink-mist-dim">Следующий соперник</p>
          <p className="truncate font-display text-base font-bold text-ink-chalk">{preview.opponent_name}</p>
          <p className="text-caption text-ink-mist">
            {preview.opponent_is_bot ? "Бот вашего уровня" : `Дивизион ${preview.opponent_division} · ${preview.opponent_points} очков`}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="font-mono text-sm font-bold text-ink-chalk">
            {preview.user_strength} <span className="text-ink-mist-dim">vs</span> {preview.opponent_strength}
          </p>
          <p className={`text-micro ${diff > 0 ? "text-accent-green" : diff < 0 ? "text-red-400" : "text-ink-mist-dim"}`}>
            {diff === 0 ? "Равные силы" : diff > 0 ? `Вы сильнее на ${diff}` : `Соперник сильнее на ${-diff}`}
          </p>
        </div>
      </div>

      <div className="mt-3">
        <ArenaLinesCompare lines={preview.lines} opponentName={preview.opponent_name} />
      </div>

      <div className="mt-4">
        <p className="mb-1.5 text-caption text-ink-mist">
          Стиль соперника: <span className="font-semibold text-ink-chalk">{TACTIC_LABELS[preview.opponent_style]}</span>
          {counter && <span className="text-ink-mist-dim"> · его бьёт «{counter.label}»</span>}
        </p>
        <div className="grid grid-cols-4 gap-1.5">
          {TACTICS.map((t) => {
            const active = preview.user_style === t.value;
            const beatsHim = t.beats === preview.opponent_style;
            return (
              <button
                key={t.value}
                onClick={() => !active && onStyle(t.value)}
                disabled={stylePending}
                className={`rounded-xl px-1 py-1.5 text-center text-micro font-bold leading-tight disabled:opacity-60 ${
                  active ? "bg-floodlight text-bg-base" : beatsHim ? "bg-accent-green/15 text-accent-green" : "bg-white/5 text-ink-mist"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
        <p className={`mt-1.5 text-caption ${matchupClass(preview.matchup)}`}>
          {preview.matchup_text}
          {preview.matchup_bonus_pct > 0 && ` (${preview.matchup === "win" ? "+" : "−"}${preview.matchup_bonus_pct}% к силе)`}
        </p>
      </div>

      <div className="mt-4">
        <p className="mb-1 text-caption text-ink-mist">Шансы</p>
        <ArenaChancesBar chances={preview.chances} />
      </div>

      <div className="mt-3 grid grid-cols-3 gap-1.5 text-center">
        {(["win", "draw", "loss"] as const).map((r) => (
          <div key={r} className="rounded-lg bg-white/5 py-1.5">
            <p className={`font-mono text-sm font-bold ${preview.points_at_stake[r] > 0 ? "text-accent-green" : preview.points_at_stake[r] < 0 ? "text-red-400" : "text-ink-mist"}`}>
              {signed(preview.points_at_stake[r])}
            </p>
            <p className="text-micro text-ink-mist-dim">{r === "win" ? "за победу" : r === "draw" ? "за ничью" : "за поражение"}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/** Short styles + chances line for the live match header. */
export function ArenaMatchupLine({ match }: { match: Match }) {
  const arena = match.arena;
  if (!arena) return null;
  return (
    <p className="mt-0.5 shrink-0 text-center text-micro text-ink-mist-dim">
      <span className={matchupClass(arena.matchup)}>
        {TACTIC_LABELS[arena.user_style]} vs {TACTIC_LABELS[arena.opponent_style]}
      </span>
      {arena.chances && <> · шанс на победу ≈{arena.chances.win}%</>}
    </p>
  );
}

/** After the whistle: points/division movement and the «Разбор матча». */
export function ArenaMatchReport({ match }: { match: Match }) {
  const { ladder, report } = match;
  if (!ladder && !report) return null;
  return (
    <div className="flex flex-col gap-2">
      {ladder && (
        <div className="rounded-xl bg-white/5 px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-ink-mist">Очки арены</span>
            <span className="font-mono text-sm font-bold">
              <span className={ladder.delta > 0 ? "text-accent-green" : ladder.delta < 0 ? "text-red-400" : "text-ink-mist"}>
                {signed(ladder.delta)}
              </span>
              <span className="text-ink-mist-dim"> → </span>
              <span className="text-ink-chalk">{ladder.points_after}</span>
            </span>
          </div>
          {ladder.promoted && (
            <p className="mt-1 text-xs font-bold text-accent-green">
              ⬆ Повышение! Дивизион {ladder.division_after}
              {ladder.rewards.map((r) => (
                <span key={r.division} className="ml-1 inline-flex items-center gap-0.5 text-accent-lime">
                  +{r.coins} <IconCoin size={11} />
                </span>
              ))}
            </p>
          )}
          {ladder.relegated && <p className="mt-1 text-xs font-bold text-red-400">⬇ Вылет в дивизион {ladder.division_after}</p>}
          {ladder.shield_used && <p className="mt-1 text-xs text-accent-green">🛡 Защита после повышения сохранила дивизион</p>}
        </div>
      )}
      {report && (
        <div className="rounded-xl bg-white/5 px-3 py-2.5">
          <p className="text-caption font-semibold uppercase tracking-wide text-ink-mist-dim">Разбор матча</p>
          <p className="mt-1 text-sm font-bold text-ink-chalk">{report.verdict}</p>
          <ul className="mt-1.5 flex flex-col gap-1 text-caption leading-snug text-ink-mist">
            {report.reasons.map((reason, i) => (
              <li key={i} className="flex gap-1.5">
                <span className="text-ink-mist-dim">•</span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
          <div className="mt-2.5">
            <ArenaLinesCompare lines={report.lines} opponentName={match.opponent_name} />
          </div>
          <div className="mt-2.5">
            <p className="mb-1 text-micro text-ink-mist-dim">Шансы до матча</p>
            <ArenaChancesBar chances={report.chances} />
          </div>
        </div>
      )}
    </div>
  );
}
