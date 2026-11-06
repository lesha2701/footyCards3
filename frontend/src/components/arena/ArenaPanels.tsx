import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconBolt, IconCoin, IconTrophy } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { SkillIcon } from "@/components/icons/skills";
import { artOf } from "@/lib/gameArt";
import { RARITY_GRADIENTS } from "@/lib/rarity";
import { stageIcon, talentByCode, usePathCatalog } from "@/lib/pathCards";
import { TACTIC_LABELS, TACTICS } from "@/lib/formation";
import { formationLabel } from "@/lib/formationLayout";
import type {
  ArenaChances,
  ArenaDivision,
  ArenaLineCompare,
  ArenaMatchup,
  ArenaPreview,
  LineupTactic,
  Match,
  MatchDuelActor,
  MatchResult,
  Rarity,
} from "@/types";

const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : "0");

const matchupClass = (m: ArenaMatchup) =>
  m === "win" ? "text-accent-green" : m === "loss" ? "text-red-400" : "text-ink-mist";

/** The one line on top of the screen: division, how far to the next one and
 *  the form. Everything else about the division is a tap away. */
export function ArenaStatusStrip({ division, form, onOpen }: {
  division: ArenaDivision;
  form: (MatchResult | null)[];
  onOpen: () => void;
}) {
  const span = division.next_min_points != null ? division.next_min_points - division.min_points : null;
  const done = division.points - division.min_points;
  const progress = span ? Math.min(100, Math.max(0, (done / span) * 100)) : 100;
  return (
    <button onClick={onOpen} className="flex items-center gap-3 rounded-2xl bg-bg-surface px-3 py-2 text-left active:scale-[0.99]">
      <span className="shrink-0 font-display text-sm font-bold text-ink-chalk">
        Дивизион {division.division}{division.shield_matches > 0 ? " 🛡" : ""}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block h-1.5 overflow-hidden rounded-full bg-white/10">
          <span className="block h-full rounded-full bg-accent-cyan transition-all" style={{ width: `${progress}%` }} />
        </span>
      </span>
      <span className="shrink-0 font-mono text-caption font-bold text-accent-cyan">
        {span ? `${done}/${span}` : division.points}
      </span>
      {form.length > 0 && (
        <span className="flex shrink-0 gap-1" aria-label="Форма">
          {form.map((r, i) => (
            <span key={i} className={`h-2 w-2 rounded-full ${r === "win" ? "bg-accent-green" : r === "loss" ? "bg-red-400" : "bg-white/25"}`} />
          ))}
        </span>
      )}
    </button>
  );
}

/** What is left of the hour's matches: instead of a dead button, what
 *  happened and when it ends, ticking down to the moment Play comes back. */
export function ArenaLimitPanel({ seconds, limit, onDone }: { seconds: number; limit: number; onDone: () => void }) {
  const [left, setLeft] = useState(seconds);
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    const started = Date.now();
    setLeft(seconds);
    const timer = window.setInterval(() => {
      const rest = Math.max(0, seconds - Math.floor((Date.now() - started) / 1000));
      setLeft(rest);
      if (rest === 0) {
        window.clearInterval(timer);
        done.current();
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [seconds]);
  const clock = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-bg-raised px-4 py-2.5 ring-1 ring-red-400/30">
      <span className="text-2xl leading-none" aria-hidden>⏳</span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-bold leading-tight text-ink-chalk">Матчи закончились</span>
        <span className="block text-micro text-ink-mist-dim">{limit} в час · новые через</span>
      </span>
      <span className="font-mono text-2xl font-bold tabular-nums text-accent-cyan">{clock}</span>
    </div>
  );
}

/** Where you are stronger: one difference per line, always in view. */
export function ArenaLinesRow({ lines }: { lines: ArenaLineCompare[] }) {
  return (
    <div className="grid grid-cols-4 divide-x divide-white/5 rounded-2xl bg-bg-surface py-1.5" aria-label="Расклад по линиям">
      {lines.map((line) => {
        const diff = line.user - line.opponent;
        return (
          <div key={line.key} className="min-w-0 px-1 text-center">
            <p className={`font-mono text-base font-bold leading-tight ${diff > 0 ? "text-accent-green" : diff < 0 ? "text-red-400" : "text-ink-mist"}`}>
              {signed(diff)}
            </p>
            <p className="truncate text-micro text-ink-mist-dim">{line.label}</p>
          </div>
        );
      })}
    </div>
  );
}

function DuelCard({ actor, align }: { actor: MatchDuelActor; align: "left" | "right" }) {
  const rarity = actor.rarity as Rarity | null | undefined;
  const surname = actor.name.trim().split(/\s+/).pop();
  return (
    <div className={`flex min-w-0 flex-1 items-center gap-2 ${align === "right" ? "flex-row-reverse text-right" : "text-left"}`}>
      <span className={`relative h-16 w-16 shrink-0 rounded-xl bg-gradient-to-b p-[2px] [@media(min-height:800px)]:h-20 [@media(min-height:800px)]:w-20 ${rarity ? RARITY_GRADIENTS[rarity] : "from-white/30 to-white/10"}`}>
        <span className="block h-full w-full overflow-hidden rounded-[10px] bg-black/40">
          <img
            src={staticUrl(actor.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
            alt="" className="h-full w-full object-cover object-top" loading="lazy" decoding="async"
          />
        </span>
      </span>
      <span className="min-w-0">
        <span className="block truncate text-xs font-semibold leading-tight text-ink-chalk">{surname}</span>
        <span className="block font-mono text-xl font-bold leading-tight text-accent-cyan">{actor.rating}</span>
        <span className="block font-mono text-micro leading-none text-ink-mist-dim">{actor.position}</span>
      </span>
    </div>
  );
}

/** Your star against the man in his way. Hidden on low screens, so the Play
 *  button never drops below the fold for the sake of a picture. */
export function ArenaKeyDuel({ duel }: { duel: { me: MatchDuelActor; vs: MatchDuelActor } }) {
  return (
    <section
      aria-label="Ключевая дуэль"
      className="relative hidden items-center gap-1 overflow-hidden rounded-2xl bg-bg-surface p-2 [@media(min-height:760px)]:flex"
    >
      <span className="pointer-events-none absolute inset-y-0 left-0 w-1/2 bg-gradient-to-r from-accent-green/10 to-transparent" />
      <span className="pointer-events-none absolute inset-y-0 right-0 w-1/2 bg-gradient-to-l from-red-500/10 to-transparent" />
      <div className="relative flex min-w-0 flex-1 items-center gap-1">
        <DuelCard actor={duel.me} align="left" />
        <IconBolt size={20} className="shrink-0 text-accent-lime" />
        <DuelCard actor={duel.vs} align="right" />
      </div>
    </section>
  );
}

/** Around a pitch tile: stars, the «Академия» stage and talent, the skill. */
export function ArenaTileSide({ stars = 0, pathStage, talentCode, skillCode, skillLevel, skillOff }: {
  stars?: number;
  pathStage?: number;
  talentCode?: string | null;
  skillCode?: string | null;
  skillLevel?: number | null;
  skillOff?: string | null;
}) {
  const { data: catalog } = usePathCatalog(!!talentCode);
  const talent = talentCode ? talentByCode(catalog, talentCode) : undefined;
  return (
    <>
      {stars > 0 && <span className="font-mono text-[9px] font-bold leading-none text-amber-300">★{stars}</span>}
      {talentCode && <span className="text-[12px] leading-none" title="Академия">{pathStage != null ? stageIcon(pathStage) : "🌱"}</span>}
      {talent && <span className="text-[11px] leading-none" title={talent.name}>{talent.emoji}</span>}
      {skillCode && !!skillLevel && (
        <span className={`rounded bg-black/60 p-0.5 ${skillOff ? "text-ink-mist-dim" : "text-accent-lime"}`} title={skillOff ?? undefined}>
          <SkillIcon code={skillCode} size={10} strokeWidth={2.4} aria-hidden />
        </span>
      )}
    </>
  );
}

/** A square entry to a panel: one number, one word. */
export function ArenaTile({ icon, value, label, badge, tone, onClick }: {
  icon: ReactNode;
  value?: ReactNode;
  label: string;
  badge?: number;
  tone?: "amber";
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative flex flex-col items-center gap-0.5 rounded-2xl py-2 active:scale-95 ${tone === "amber" ? "bg-amber-400/15" : "bg-bg-surface"}`}
    >
      {!!badge && (
        <span className="absolute right-1.5 top-1.5 rounded-full bg-red-500 px-1.5 font-mono text-micro font-bold leading-4 text-white">{badge}</span>
      )}
      <span className="flex h-5 items-center gap-1 font-mono text-sm font-bold text-ink-chalk">
        {icon}{value}
      </span>
      <span className={`text-micro ${tone === "amber" ? "text-amber-300" : "text-ink-mist-dim"}`}>{label}</span>
    </button>
  );
}

/** A bottom sheet for what doesn't belong on the main screen; unlike
 *  MatchSheet it closes with a tap outside. */
export function ArenaSheet({ open, title, onClose, children }: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          aria-label={title}
        >
          <motion.div
            className="flex max-h-[75dvh] w-full max-w-lg flex-col rounded-t-3xl border border-white/10 bg-bg-base px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-2"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            <span className="mx-auto h-1 w-10 shrink-0 rounded-full bg-white/10" />
            <p className="mb-3 mt-2 shrink-0 font-display text-base font-bold text-ink-chalk">{title}</p>
            <div className="min-h-0 overflow-y-auto overscroll-contain">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

/** Division N of M, points, the bar to the next division and the shield. */
export function ArenaDivisionCard({ division, rank }: { division: ArenaDivision; rank: number | null }) {
  const span = division.next_min_points != null ? division.next_min_points - division.min_points : null;
  const progress = span ? Math.min(100, Math.max(0, ((division.points - division.min_points) / span) * 100)) : 100;
  return (
    <section>
      <div className="flex items-start justify-between gap-3">
        <div>
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

/** The next opponent, the one thing the screen is about: you vs him, one
 *  block for chances and points, the style. The rest opens on a tap. */
export function ArenaOpponentCard({
  preview,
  onStyle,
  stylePending,
}: {
  preview: ArenaPreview;
  onStyle: (style: LineupTactic) => void;
  stylePending: boolean;
}) {
  const [details, setDetails] = useState(false);
  const h2h = preview.head_to_head;
  const hasDetails = !preview.opponent_is_bot || !!h2h
    || Object.keys(preview.opponent_malus ?? {}).length > 0 || Object.keys(preview.user_malus ?? {}).length > 0;
  const art = artOf("arena");
  const { user_strength: mine, opponent_strength: his } = preview;
  const outcomes = [
    { key: "win", label: "Победа", value: preview.chances.win, tone: "text-accent-green", align: "text-left" },
    { key: "draw", label: "Ничья", value: preview.chances.draw, tone: "text-ink-mist", align: "text-center" },
    { key: "loss", label: "Поражение", value: preview.chances.loss, tone: "text-red-400", align: "text-right" },
  ] as const;
  return (
    <section className="relative overflow-hidden rounded-3xl bg-bg-surface p-4 ring-1 ring-white/10">
      {art && <img src={art} alt="" aria-hidden className="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full object-cover opacity-25 blur-2xl" />}

      <button onClick={() => hasDetails && setDetails((v) => !v)} className="relative block w-full text-left" aria-expanded={details}>
        {preview.revenge && <p className="mb-1 text-center text-caption font-bold text-red-400">⚔️ Реванш</p>}
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-ink-chalk">Ты</p>
            <p className={`font-mono text-3xl font-bold leading-tight ${mine > his ? "text-accent-green" : "text-ink-chalk"}`}>{mine}</p>
            <p className="truncate text-micro text-ink-mist-dim">{formationLabel(preview.user_formation)}</p>
          </div>
          <span className="font-display text-xs font-bold text-ink-mist-dim">VS</span>
          <div className="min-w-0 text-right">
            <p className="truncate text-sm font-semibold text-ink-chalk">{preview.opponent_name}</p>
            <p className={`font-mono text-3xl font-bold leading-tight ${his > mine ? "text-red-400" : "text-ink-chalk"}`}>{his}</p>
            <p className="truncate text-micro text-ink-mist-dim">{formationLabel(preview.opponent_formation)}</p>
          </div>
        </div>
        {hasDetails && <span className="mt-0.5 block text-center text-micro leading-none text-ink-mist-dim">{details ? "▲" : "▼"}</span>}
      </button>

      {details && (
        <div className="relative mt-2 flex flex-col gap-2 rounded-2xl bg-black/20 p-2.5">
          <p className="text-caption text-ink-mist">
            {preview.opponent_is_bot ? "Бот твоего уровня" : `Дивизион ${preview.opponent_division} · ${preview.opponent_points} очков`}
            {h2h && <> · встречи <span className="font-mono font-semibold text-ink-chalk">{h2h.win}·{h2h.draw}·{h2h.loss}</span></>}
          </p>
          {/* Already counted in the strengths and lines above. */}
          <OpponentMalusNote malus={preview.opponent_malus} who="Твой тренер и стадион отнимают у соперника" />
          <OpponentMalusNote malus={preview.user_malus} who="Тренер и стадион соперника отнимают у тебя" />
        </div>
      )}

      <div className="relative mt-3">
        <div className="flex h-2 overflow-hidden rounded-full">
          <div className="bg-accent-green" style={{ width: `${preview.chances.win}%` }} />
          <div className="bg-white/25" style={{ width: `${preview.chances.draw}%` }} />
          <div className="bg-red-400" style={{ width: `${preview.chances.loss}%` }} />
        </div>
        <div className="mt-1.5 grid grid-cols-3">
          {outcomes.map((o) => (
            <div key={o.key} className={o.align}>
              <p className={`font-mono text-lg font-bold leading-tight ${o.tone}`}>{o.value}%</p>
              <p className="text-micro text-ink-mist-dim">
                {o.label} <span className="font-mono font-bold text-ink-mist">{signed(preview.points_at_stake[o.key])}</span>
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="relative mt-3">
        <div className="grid grid-cols-4 gap-1">
          {TACTICS.map((t) => {
            const active = preview.user_style === t.value;
            const beatsHim = t.beats === preview.opponent_style_hint;
            return (
              <button
                key={t.value}
                onClick={() => !active && onStyle(t.value)}
                disabled={stylePending}
                className={`rounded-xl py-2 text-center text-micro font-bold leading-tight disabled:opacity-60 ${
                  active ? "bg-floodlight text-bg-base" : beatsHim ? "bg-accent-green/15 text-accent-green" : "bg-white/5 text-ink-mist"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
        <p className="mt-1.5 text-center text-micro text-ink-mist-dim">
          Соперник скорее: <span className="font-semibold text-ink-mist">{TACTIC_LABELS[preview.opponent_style_hint]}</span>
        </p>
      </div>

      {preview.goal_text && (
        <p className="relative mt-2 flex items-center justify-center gap-1 text-caption font-semibold text-accent-lime">
          🎯 {preview.goal_text} +{preview.goal_bonus_coins} <IconCoin size={11} />
        </p>
      )}
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
      {arena.user_formation && <> · {formationLabel(arena.user_formation)} vs {formationLabel(arena.opponent_formation)}</>}
      {arena.chances && <> · шанс на победу ≈{arena.chances.win}%</>}
    </p>
  );
}

/** After the whistle: points/division movement and the «Разбор матча». */
export function ArenaMatchReport({ match, division }: { match: Match; division?: ArenaDivision | null }) {
  const { ladder, report } = match;
  if (!ladder && !report) return null;
  const goal = report?.goal;
  const span = division?.next_min_points != null ? division.next_min_points - division.min_points : null;
  return (
    <div className="flex flex-col gap-2">
      {report?.mvp && (
        <div className="flex items-center gap-3 rounded-xl bg-accent-lime/10 px-3 py-2">
          <img
            src={staticUrl(report.mvp.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
            alt="" className="h-11 w-11 rounded-lg object-cover" loading="lazy" decoding="async"
          />
          <div className="min-w-0">
            <p className="text-micro font-semibold uppercase tracking-wide text-accent-lime">Игрок матча</p>
            <p className="truncate text-sm font-bold text-ink-chalk">{report.mvp.name}</p>
          </div>
          <span className="ml-auto font-mono text-sm font-bold text-ink-chalk">{report.mvp.rating}</span>
        </div>
      )}
      {report?.cup && (
        <div className="rounded-xl bg-white/5 px-3 py-2 text-xs font-semibold text-ink-chalk">
          🏆 {report.cup.status === "champion" ? "Кубок выходных твой!" : report.cup.status === "lost" ? "Кубок на этой неделе окончен" : `Раунд ${report.cup.round} пройден`}
          {report.cup.coins > 0 && <span className="ml-1 inline-flex items-center gap-0.5 text-accent-lime">+{report.cup.coins} <IconCoin size={11} /></span>}
        </div>
      )}
      {goal && (
        <p className={`rounded-xl px-3 py-2 text-xs font-semibold ${goal.done ? "bg-accent-green/10 text-accent-green" : "bg-white/5 text-ink-mist"}`}>
          {goal.done ? "✓" : "✗"} Цель матча: {goal.text}{goal.done ? ` · +${goal.bonus}` : ""}
          {goal.done && <IconCoin size={11} className="ml-0.5 inline" />}
        </p>
      )}
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
          {division && span != null && !ladder.promoted && (
            <div className="mt-1.5">
              <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-accent-cyan" style={{ width: `${Math.min(100, Math.max(0, ((division.points - division.min_points) / span) * 100))}%` }} />
              </div>
              <p className="mt-0.5 text-micro text-ink-mist-dim">До дивизиона {division.division + 1}: {division.next_min_points! - division.points} очков</p>
            </div>
          )}
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

const MALUS_LINES: [("FWD" | "MID" | "DEF" | "GK"), string][] = [["FWD", "атака"], ["MID", "центр"], ["DEF", "защита"], ["GK", "вратарь"]];

/** «☠ Сопернику: атака −11, защита −7…» — what my coach and stadium take off him. */
export function OpponentMalusNote({ malus, who = "Сопернику" }: {
  malus?: Partial<Record<"FWD" | "MID" | "DEF" | "GK", number>>; who?: string;
}) {
  const parts = MALUS_LINES.filter(([key]) => (malus?.[key] ?? 0) > 0).map(([key, label]) => `${label} −${malus![key]}`);
  if (!parts.length) return null;
  return (
    <p className="mt-2 rounded-xl bg-red-500/10 px-3 py-2 text-caption font-semibold text-red-300">
      ☠ {who}: {parts.join(" · ")}
    </p>
  );
}
