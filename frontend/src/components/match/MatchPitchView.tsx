import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

import { PITCH_H, PITCH_W, currentFrame, pendingFrame, pressure, type FrameTone } from "@/lib/matchVisual";
import type { MatchEvent } from "@/types";

// The pitch is green in both themes (it's grass, not a surface), so it uses
// its own fixed palette instead of the theme tokens; the labels on it are
// white-on-dark chips that read the same on either theme.
const GRASS = "#14532d";
const GRASS_STRIPE = "#166534";
const LINE = "rgba(255,255,255,0.45)";
const USER = "#3ed17e";
const OPPONENT = "#f87171";

const TONE_COLOR: Record<FrameTone, string> = { user: USER, opponent: OPPONENT, neutral: "#e2e8f0" };

/**
 * Schematic top-down view of the latest revealed event: where the ball is,
 * the shot line for chances, and a short label. Positions are illustrative
 * (the engine has no coordinates) — see lib/matchVisual.ts.
 */
export default function MatchPitchView({
  events,
  opponentName,
  pending,
}: {
  /** Revealed events only — the view never runs ahead of the commentary. */
  events: MatchEvent[];
  opponentName: string;
  /** The chance awaiting the player's choice, if any. */
  pending?: { team: string; shot_type: string } | null;
}) {
  const reduceMotion = useReducedMotion();
  const frame = (pending && pendingFrame(pending.team, pending.shot_type, events.length)) || currentFrame(events);
  const key = `${events.length}${pending ? "p" : ""}`;
  const move = reduceMotion ? { duration: 0 } : { type: "spring" as const, damping: 18, stiffness: 120 };
  const p = pressure(events);
  const userShare = Math.round(50 + p * 50);

  const labelLeft = Math.min(86, Math.max(14, frame.ball.x));
  const labelTop = (frame.ball.y / PITCH_H) * 100;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between px-0.5 text-[11px] font-semibold">
        {/* TV convention: you're on the left, defending the left goal and
            attacking right — same order as the score above. */}
        {/* Theme tokens here (not the fixed pitch palette): this text sits on
            the sheet, and the light theme maps accent-green to a darker shade. */}
        <span className="text-accent-green">Ты →</span>
        <span className="max-w-[60%] truncate text-red-400">← {opponentName}</span>
      </div>

      <div className="relative overflow-hidden rounded-xl" style={{ aspectRatio: `${PITCH_W} / ${PITCH_H}` }}>
        <svg viewBox={`0 0 ${PITCH_W} ${PITCH_H}`} className="absolute inset-0 h-full w-full" aria-hidden="true">
          <rect x="0" y="0" width={PITCH_W} height={PITCH_H} fill={GRASS} />
          {Array.from({ length: 5 }, (_, i) => (
            <rect key={i} x={i * 20 + 10} y="0" width="10" height={PITCH_H} fill={GRASS_STRIPE} />
          ))}
          <g fill="none" stroke={LINE} strokeWidth="0.4">
            <rect x="1" y="1" width={PITCH_W - 2} height={PITCH_H - 2} />
            <line x1={PITCH_W / 2} y1="1" x2={PITCH_W / 2} y2={PITCH_H - 1} />
            <circle cx={PITCH_W / 2} cy={PITCH_H / 2} r="7" />
            {/* Penalty and goal areas, both ends */}
            <rect x="1" y="15" width="15" height="30" />
            <rect x="1" y="23" width="5" height="14" />
            <rect x={PITCH_W - 16} y="15" width="15" height="30" />
            <rect x={PITCH_W - 6} y="23" width="5" height="14" />
          </g>
          {/* Goals (outside the line) */}
          <rect x="0" y="26" width="1" height="8" fill="rgba(255,255,255,0.8)" />
          <rect x={PITCH_W - 1} y="26" width="1" height="8" fill="rgba(255,255,255,0.8)" />

          {frame.goalSide && !reduceMotion && (
            <motion.rect
              key={`net-${key}`}
              x={frame.goalSide === "opponent" ? PITCH_W - 6 : 0}
              y="20"
              width="6"
              height="20"
              fill={TONE_COLOR[frame.tone]}
              initial={{ opacity: 0 }}
              animate={{ opacity: [0, 0.55, 0] }}
              transition={{ duration: 1.1 }}
            />
          )}

          {frame.from && (
            <motion.line
              key={`shot-${key}`}
              x1={frame.from.x}
              y1={frame.from.y}
              x2={frame.ball.x}
              y2={frame.ball.y}
              stroke={TONE_COLOR[frame.tone]}
              strokeWidth="0.6"
              strokeDasharray="1.6 1"
              initial={reduceMotion ? false : { pathLength: 0, opacity: 0.9 }}
              animate={{ pathLength: 1, opacity: 0.9 }}
              transition={reduceMotion ? { duration: 0 } : { duration: 0.45 }}
            />
          )}

          <motion.circle
            r="1.6"
            fill="#ffffff"
            stroke="#0b0d10"
            strokeWidth="0.4"
            initial={false}
            animate={{ cx: frame.ball.x, cy: frame.ball.y }}
            transition={move}
          />
        </svg>

        <AnimatePresence>
          {frame.label && (
            <motion.span
              key={`label-${key}`}
              className="pointer-events-none absolute whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold text-white"
              style={{
                left: `${labelLeft}%`,
                top: `${labelTop}%`,
                backgroundColor: "rgba(7,9,10,0.75)",
                border: `1px solid ${TONE_COLOR[frame.tone]}`,
                x: "-50%",
                y: labelTop < 30 ? "60%" : "-160%",
              }}
              initial={reduceMotion ? false : { opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: frame.kind === "goal" ? 1.15 : 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              {frame.label}
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      {/* Pressure: share of attacking weight over the last few events —
          you on the left, the opponent on the right, same as the pitch. */}
      <div className="flex items-center gap-2" aria-label={`Давление: ты ${userShare}%, соперник ${100 - userShare}%`}>
        <div className="flex h-1.5 flex-1 overflow-hidden rounded-full" style={{ backgroundColor: OPPONENT }}>
          <motion.div
            className="h-full"
            style={{ backgroundColor: USER }}
            initial={false}
            animate={{ width: `${userShare}%` }}
            transition={reduceMotion ? { duration: 0 } : { duration: 0.5 }}
          />
        </div>
        <span className="text-[10px] text-ink-mist-dim">давление</span>
      </div>
    </div>
  );
}
