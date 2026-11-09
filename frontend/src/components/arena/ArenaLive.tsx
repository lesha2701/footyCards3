/** The live layer of a Card Arena match: the decision with its duels and
 * clock, half-time, the late all-in call, the penalty in the 3D scene and the
 * full-screen goal. The server decides everything; these only ask. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  IconBoot, IconGloves, IconGoal, IconSwap, IconUsers, type IconProps,
} from "@/components/icons";
import SetPieceScene, { type SceneInput } from "@/components/match3d/SetPieceScene";
import type { MatchActExtra } from "@/api/matches";
import { staticUrl } from "@/lib/api";
import { TACTIC_LABELS, TACTICS } from "@/lib/formation";
import type { SceneKick, SceneOutcome } from "@/lib/match3d/core";
import { haptic } from "@/lib/telegram";
import type { ArenaActionKind, ArenaPendingMoment, LineupTactic, Match, MatchDuelActor, MatchEvent } from "@/types";

export type ArenaAct = (action: ArenaActionKind, extra?: MatchActExtra) => void;

const ACTION_LABELS: Partial<Record<ArenaActionKind, { label: string; Icon: (props: IconProps) => JSX.Element }>> = {
  shoot: { label: "Ударить", Icon: IconBoot },
  pass: { label: "Отдать пас", Icon: IconSwap },
  dribble: { label: "Обвести", Icon: IconBoot },
  tackle: { label: "Подкат", Icon: IconUsers },
  block: { label: "Блок", Icon: IconGoal },
  keeper: { label: "Вратарь", Icon: IconGloves },
  strike: { label: "Ударить!", Icon: IconBoot },
};

const RISK: Record<"low" | "mid" | "high", { label: string; className: string }> = {
  low: { label: "Надёжно", className: "bg-accent-green/15 text-accent-green" },
  mid: { label: "Риск", className: "bg-amber-400/15 text-amber-300" },
  high: { label: "Большой риск", className: "bg-red-500/15 text-red-300" },
};

const PLACEHOLDER = "players/placeholder/player_placeholder.webp";
const SCENE_SKIP_MS = 12_000;

function Face({ actor }: { actor: MatchDuelActor }) {
  return (
    <span className="flex min-w-0 flex-col items-center">
      <span className="relative h-8 w-8 overflow-hidden rounded-md bg-black/40">
        <img
          src={staticUrl(actor.image_path ?? undefined) ?? staticUrl(PLACEHOLDER)}
          alt="" className="h-full w-full object-cover" loading="lazy" decoding="async"
        />
        <span className="absolute inset-x-0 bottom-0 bg-black/75 text-center font-mono text-[9px] font-bold leading-[11px] text-accent-cyan">{actor.rating}</span>
      </span>
      <span className="mt-0.5 w-full truncate text-center text-[9px] leading-none text-ink-mist">{actor.name.trim().split(/\s+/).pop()}</span>
    </span>
  );
}

/** Runs out into `onExpire`; restarts with `resetKey`. */
function Clock({ seconds, resetKey, onExpire }: { seconds: number; resetKey: number; onExpire: () => void }) {
  const [left, setLeft] = useState(seconds);
  const expire = useRef(onExpire);
  expire.current = onExpire;

  useEffect(() => {
    setLeft(seconds);
    const started = Date.now();
    const timer = window.setInterval(() => {
      const rest = seconds - (Date.now() - started) / 1000;
      setLeft(Math.max(0, rest));
      if (rest <= 0) {
        window.clearInterval(timer);
        expire.current();
      }
    }, 100);
    return () => window.clearInterval(timer);
  }, [seconds, resetKey]);

  const hot = left <= 3;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
      <div className={`h-full rounded-full ${hot ? "bg-red-400" : "bg-accent-lime"}`} style={{ width: `${(left / seconds) * 100}%` }} />
    </div>
  );
}

/** Attack or defense: each option with who duels whom and what it risks,
 *  side by side, so the whole choice is in view on any screen. */
export function ArenaMomentPrompt({ pending, disabled, onAct }: { pending: ArenaPendingMoment; disabled: boolean; onAct: ArenaAct }) {
  const answered = useRef(false);
  useEffect(() => { answered.current = false; }, [pending.seq]);
  const pick = (action: ArenaActionKind) => {
    if (answered.current) return;
    answered.current = true;
    haptic("light");
    onAct(action, { expected_seq: pending.seq });
  };
  const options = pending.options ?? [];

  return (
    <div className="mt-2 flex shrink-0 flex-col gap-1.5 rounded-2xl bg-black/20 p-2">
      {!!pending.seconds && !disabled && <Clock seconds={pending.seconds} resetKey={pending.seq} onExpire={() => pick("auto")} />}
      <p className="text-center text-xs font-semibold leading-snug text-ink-chalk">{pending.description}</p>
      {options.length > 0 ? (
        <div className={`grid gap-1.5 ${options.length >= 3 ? "grid-cols-3" : options.length === 2 ? "grid-cols-2" : "grid-cols-1"}`}>
          {options.map((option) => {
            const meta = ACTION_LABELS[option.action];
            const risk = RISK[option.risk];
            return (
              <button
                key={option.action}
                onClick={() => pick(option.action)}
                disabled={disabled}
                title={option.note}
                className="flex min-w-0 flex-col items-center gap-1 rounded-xl bg-bg-surface px-1 py-1.5 text-center active:scale-[0.98] disabled:opacity-40"
              >
                <span className="flex items-center justify-center gap-1 text-xs font-bold leading-tight text-ink-chalk">
                  {meta && <meta.Icon size={13} />}{meta?.label ?? option.action}
                </span>
                <span className={`rounded-full px-1.5 py-px text-[9px] font-bold leading-tight ${risk.className}`}>{risk.label}</span>
                <span className="grid w-full grid-cols-[1fr_auto_1fr] items-center gap-0.5">
                  <Face actor={option.me} />
                  <span className="text-[9px] font-bold text-ink-mist-dim">vs</span>
                  <Face actor={option.vs} />
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="grid grid-flow-col gap-2">
          {pending.actions.map((action) => {
            const meta = ACTION_LABELS[action];
            return (
              <button
                key={action}
                onClick={() => pick(action)}
                disabled={disabled}
                className="flex flex-col items-center gap-1 rounded-2xl bg-bg-surface px-3 py-3 text-sm font-semibold text-ink-chalk active:scale-90 disabled:opacity-40"
              >
                {meta && <meta.Icon size={16} />}{meta?.label ?? action}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** The break: the opponent's real style is out, change yours or keep it. */
export function ArenaHalftimePrompt({ match, pending, disabled, onAct }: { match: Match; pending: ArenaPendingMoment; disabled: boolean; onAct: ArenaAct }) {
  const mine = match.arena?.user_style;
  const theirs = match.arena?.opponent_style;
  return (
    <div className="mt-2 flex shrink-0 flex-col gap-2 rounded-2xl bg-black/20 p-3 text-center">
      {!!pending.seconds && !disabled && <Clock seconds={pending.seconds + 4} resetKey={pending.seq} onExpire={() => onAct("auto", { expected_seq: pending.seq })} />}
      <p className="text-sm font-bold text-ink-chalk">Перерыв</p>
      {theirs && <p className="text-caption text-ink-mist">Соперник играет в «{TACTIC_LABELS[theirs]}». Его бьёт «{TACTICS.find((t) => t.beats === theirs)?.label}».</p>}
      <div className="grid grid-cols-2 gap-1.5">
        {TACTICS.map((t) => {
          const current = t.value === mine;
          const beats = t.beats === theirs;
          return (
            <button
              key={t.value}
              disabled={disabled}
              onClick={() => (current ? onAct("keep_style", { expected_seq: pending.seq }) : onAct("change_style", { expected_seq: pending.seq, style: t.value as LineupTactic }))}
              className={`rounded-xl px-2 py-2 text-xs font-bold active:scale-95 disabled:opacity-40 ${
                current ? "bg-floodlight text-bg-base" : beats ? "bg-accent-green/15 text-accent-green" : "bg-bg-surface text-ink-chalk"
              }`}
            >
              {current ? `Оставить «${t.label}»` : t.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Behind late on: throw everyone forward or keep the shape. */
export function ArenaLateCallPrompt({ pending, disabled, onAct }: { pending: ArenaPendingMoment; disabled: boolean; onAct: ArenaAct }) {
  return (
    <div className="mt-2 flex shrink-0 flex-col gap-2 rounded-2xl bg-black/20 p-3 text-center">
      {!!pending.seconds && !disabled && <Clock seconds={pending.seconds} resetKey={pending.seq} onExpire={() => onAct("auto", { expected_seq: pending.seq })} />}
      <p className="text-sm font-semibold text-ink-chalk">{pending.description}</p>
      <div className="grid grid-cols-2 gap-2">
        <button
          disabled={disabled}
          onClick={() => onAct("all_in", { expected_seq: pending.seq })}
          className="rounded-2xl bg-red-500/80 px-2 py-3 font-display text-sm font-bold text-white active:scale-95 disabled:opacity-40"
        >
          Все вперёд
        </button>
        <button
          disabled={disabled}
          onClick={() => onAct("hold", { expected_seq: pending.seq })}
          className="rounded-2xl bg-bg-surface px-2 py-3 font-display text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
        >
          Держать схему
        </button>
      </div>
    </div>
  );
}

/** The penalty in the game's own scene, over the whole screen. The scene plays
 *  the seed the server gave; the server replays what the player did. */
export function ArenaPenaltyScene({ pending, onAct }: { pending: ArenaPendingMoment; onAct: ArenaAct }) {
  const box = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(() => window.innerHeight);
  useEffect(() => {
    const measure = () => setHeight(box.current?.clientHeight ?? window.innerHeight);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  const kick = useMemo<SceneKick>(() => ({
    kind: pending.team === "user" ? "penalty" : "keep",
    seed: pending.seed ?? 1, rating: pending.rating ?? 75, distance: 11, offset: 0,
  }), [pending.team, pending.seed, pending.rating]);

  const toBox = useCallback((x: number, y: number) => {
    const rect = box.current?.getBoundingClientRect();
    return { x: x - (rect?.left ?? 0), y: y - (rect?.top ?? 0) };
  }, []);

  const sent = useRef(false);
  const done = useCallback((outcome: SceneOutcome | null, input?: SceneInput) => {
    if (sent.current) return;
    sent.current = true;
    const expected_seq = pending.seq;
    if (outcome === null) {
      onAct("auto", { expected_seq });
    } else if (pending.team === "user" && input?.swipe) {
      const { dx, dy, curve, durationMs } = input.swipe;
      onAct("kick", { expected_seq, swipe: { dx, dy, curve, duration_ms: durationMs } });
    } else {
      const dive = input?.dive;
      onAct("dive", { expected_seq, dive: dive ? { x: dive.x, y: dive.y, reaction_ms: dive.reactionMs } : null });
    }
  }, [onAct, pending.seq, pending.team]);

  // A phone that can't draw the scene must not be stuck on it.
  const [canSkip, setCanSkip] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setCanSkip(true), SCENE_SKIP_MS);
    return () => window.clearTimeout(timer);
  }, []);

  return createPortal(
    <div ref={box} className="fixed inset-0 z-[70] overflow-hidden bg-black">
      <SetPieceScene kick={kick} toBox={toBox} height={height} onDone={done} />
      {canSkip && (
        <button
          onClick={() => done(null)}
          className="absolute bottom-14 left-1/2 z-10 -translate-x-1/2 rounded-full bg-black/50 px-3 py-1.5 text-caption font-semibold text-white"
        >
          Доверить исполнителю
        </button>
      )}
      {pending.taker && (
        <p className="pointer-events-none absolute inset-x-0 bottom-6 text-center text-sm font-bold text-white [text-shadow:0_1px_4px_rgba(0,0,0,.8)]">
          {pending.taker.name} · {pending.taker.rating}
        </p>
      )}
    </div>,
    document.body,
  );
}

const asScorer = (event: MatchEvent) => event.payload?.scorer as MatchDuelActor | undefined;

/** The goal fills the screen for a moment: who, when and the score. */
export function ArenaGoalOverlay({ event, opponentName }: { event: MatchEvent; opponentName: string }) {
  const mine = event.team === "user";
  const scorer = asScorer(event);
  const score = event.payload?.score as [number, number] | undefined;
  const assist = typeof event.payload?.assisted_by === "string" ? event.payload.assisted_by : null;
  const context = typeof event.payload?.context === "string" ? event.payload.context : null;
  return (
    <div className={`pointer-events-none absolute inset-0 z-20 flex animate-goal-overlay flex-col items-center justify-center gap-2 rounded-2xl text-center ${mine ? "bg-emerald-950/90" : "bg-red-950/90"}`}>
      <p className={`font-display text-5xl font-black tracking-wide ${mine ? "text-accent-lime" : "text-red-300"}`}>ГОЛ!</p>
      {scorer ? (
        <>
          <img
            src={staticUrl(scorer.image_path ?? undefined) ?? staticUrl(PLACEHOLDER)}
            alt="" className="h-24 w-24 rounded-2xl bg-black/40 object-cover" decoding="async"
          />
          <p className="font-display text-lg font-bold text-ink-chalk">{scorer.name}</p>
        </>
      ) : (
        !mine && <p className="font-display text-lg font-bold text-ink-chalk">{opponentName}</p>
      )}
      <p className="font-mono text-sm text-ink-mist">
        {event.minute}&apos;{assist ? ` · пас: ${assist}` : ""}
      </p>
      {score && <p className="font-mono text-3xl font-bold tabular-nums text-ink-chalk">{score[0]} : {score[1]}</p>}
      {context && <p className="px-6 text-sm font-semibold text-ink-chalk">{context}</p>}
    </div>
  );
}
