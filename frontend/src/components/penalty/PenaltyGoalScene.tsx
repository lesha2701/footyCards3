import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";

import keeperDiveLowBlue from "@/assets/shots/keeper-dive-low-blue.webp";
import keeperDiveLow from "@/assets/shots/keeper-dive-low.webp";
import keeperDiveSideBlue from "@/assets/shots/keeper-dive-side-blue.webp";
import keeperDiveSide from "@/assets/shots/keeper-dive-side.webp";
import keeperReadyBlue from "@/assets/shots/keeper-ready-blue.webp";
import keeperReady from "@/assets/shots/keeper-ready.webp";
import penaltyBg from "@/assets/shots/penalty-bg.webp";
import { haptic } from "@/lib/telegram";
import type { PenaltyDirection } from "@/types";

import { SceneBall } from "./SceneBall";

export interface PenaltyGoalKick {
  shotZone: PenaltyDirection;
  diveZone: PenaltyDirection;
  outcome: "goal" | "saved" | "miss";
}

export interface PenaltyGoalSceneProps {
  /** "own" = your goal is under attack, your (blue) keeper dives.
   *  "opponent" = you're attacking, their (red) keeper dives. */
  keeperSide: "own" | "opponent";
  /** The kick currently animating in, or null to show the idle/reset scene. */
  kick: PenaltyGoalKick | null;
  /** Text shown in the small badge above the crossbar, e.g. "Гол!". */
  outcomeLabel: string | null;
  /** Colors the badge (and the scene's frame) green (true) or red (false) —
   * "good" is relative to the viewer: scoring while attacking is good,
   * saving while defending is good. */
  outcomeGood: boolean;
}

// Everything is placed in % of the scene (the cropped stadium picture,
// 1080×750 of the 1200×1040 original). The goal mouth as it sits in it:
const SCENE_ASPECT = 1080 / 750;
const GOAL = { left: 17.0, right: 82.9, top: 22.7, bottom: 56.0 };
const GOAL_W = GOAL.right - GOAL.left;
const GOAL_H = GOAL.bottom - GOAL.top;
const SPOT = { x: 50, y: 90.4 };

const COLS = { left: 0.17, center: 0.5, right: 0.83 } as const;
const ROWS = { top: 0.28, bottom: 0.76 } as const;

function zoneParts(zone: PenaltyDirection): { row: keyof typeof ROWS; col: keyof typeof COLS } {
  const [row, col] = zone.split("_") as [keyof typeof ROWS, keyof typeof COLS];
  return { row, col };
}

/** One aim point per zone — the ball's target and the keeper's gloves both
 * land on it, so a correct guess puts the ball right in the gloves. */
function zoneTarget(zone: PenaltyDirection): { x: number; y: number } {
  const { row, col } = zoneParts(zone);
  return { x: GOAL.left + GOAL_W * COLS[col], y: GOAL.top + GOAL_H * ROWS[row] };
}

/** A miss flies past the post on its side, or over the bar through the middle. */
function missTarget(zone: PenaltyDirection): { x: number; y: number } {
  const { row, col } = zoneParts(zone);
  const t = zoneTarget(zone);
  if (col === "left") return { x: GOAL.left - 5, y: t.y - (row === "top" ? 6 : 0) };
  if (col === "right") return { x: GOAL.right + 5, y: t.y - (row === "top" ? 6 : 0) };
  return { x: t.x + 4, y: GOAL.top - 8 };
}

// Keeper art: one goalkeeper at one scale. Width in % of the scene, and the
// point of the picture (fraction of its box) that is put on the target —
// the feet when standing, the gloves when diving. Dives are drawn to the
// keeper's left as seen from the spot; right-hand dives mirror them.
const KEEPER_W = 21.5;
// Red kit = the opponent's keeper (the art as drawn); blue = your own (the
// same art with only the kit recoloured, skin and gloves untouched).
const POSES = {
  ready: { src: { opponent: keeperReady, own: keeperReadyBlue }, w: KEEPER_W, anchor: { x: 0.5, y: 1 } },
  jump: { src: { opponent: keeperReady, own: keeperReadyBlue }, w: KEEPER_W, anchor: { x: 0.5, y: 0.4 } },
  side: { src: { opponent: keeperDiveSide, own: keeperDiveSideBlue }, w: KEEPER_W * (594 / 575), anchor: { x: 0.1, y: 0.22 } },
  low: { src: { opponent: keeperDiveLow, own: keeperDiveLowBlue }, w: KEEPER_W * (577 / 575), anchor: { x: 0.1, y: 0.8 } },
} as const;

function keeperPlacement(kick: PenaltyGoalKick | null) {
  if (!kick) return { pose: POSES.ready, at: { x: 50, y: GOAL.bottom + 0.5 }, flip: false };
  const { row, col } = zoneParts(kick.diveZone);
  const at = zoneTarget(kick.diveZone);
  if (col === "center") {
    return row === "top"
      ? { pose: POSES.jump, at, flip: false }
      : { pose: POSES.ready, at: { x: 50, y: GOAL.bottom + 0.5 }, flip: false };
  }
  return { pose: row === "top" ? POSES.side : POSES.low, at, flip: col === "right" };
}

export default function PenaltyGoalScene({ keeperSide, kick, outcomeLabel, outcomeGood }: PenaltyGoalSceneProps) {
  const keeper = keeperPlacement(kick);
  const anchorX = keeper.flip ? 1 - keeper.pose.anchor.x : keeper.pose.anchor.x;
  const ball = !kick ? SPOT : kick.outcome === "miss" ? missTarget(kick.shotZone) : zoneTarget(kick.shotZone);
  const frameState = outcomeLabel ? (outcomeGood ? "good" : "bad") : "idle";
  const kickKey = kick ? `${kick.shotZone}-${kick.diveZone}-${kick.outcome}` : "idle";

  // A thud as the ball arrives: hard into the net or the gloves, soft past the post.
  useEffect(() => {
    if (!kick) return;
    const t = setTimeout(() => haptic(kick.outcome === "miss" ? "light" : "heavy"), 480);
    return () => clearTimeout(t);
  }, [kickKey]); // eslint-disable-line react-hooks/exhaustive-deps -- a new kick, not a new object

  return (
    <div
      className={`relative w-full max-w-[420px] overflow-hidden rounded-[20px] border transition-[border-color,box-shadow] duration-300 ${
        frameState === "good"
          ? "border-[#3ecf6e]/70 shadow-[0_0_28px_-6px_rgba(62,207,110,0.55)]"
          : frameState === "bad"
            ? "border-[#e6483b]/70 shadow-[0_0_28px_-6px_rgba(230,72,59,0.55)]"
            : "border-white/5"
      } bg-[#0b1530]`}
    >
      {/* Height from padding, not aspect-ratio: older Telegram WebViews
          don't support the latter and would draw the scene 0 px tall. */}
      <div className="relative w-full select-none" style={{ paddingTop: `${100 / SCENE_ASPECT}%` }}>
        <img src={penaltyBg} alt="" draggable={false} className="absolute inset-0 h-full w-full object-cover" />

        {/* Goal: the net lights up when the ball goes in. */}
        <AnimatePresence>
          {kick?.outcome === "goal" && (
            <motion.div
              key={`net-${kickKey}`}
              className="pointer-events-none absolute"
              style={{
                left: `${GOAL.left}%`, top: `${GOAL.top}%`, width: `${GOAL_W}%`, height: `${GOAL_H}%`,
                background: "radial-gradient(ellipse at center, rgba(255,255,255,0.55), rgba(255,255,255,0) 65%)",
              }}
              initial={{ opacity: 0 }}
              animate={{ opacity: [0, 0, 1, 0], scale: [1, 1, 1.03, 1] }}
              transition={{ duration: 1.1, times: [0, 0.45, 0.6, 1] }}
            />
          )}
        </AnimatePresence>

        {/* Goalkeeper — the pose swaps as he leaves his line. */}
        <motion.div
          className="pointer-events-none absolute"
          style={{ width: `${keeper.pose.w}%`, x: `${-anchorX * 100}%`, y: `${-keeper.pose.anchor.y * 100}%` }}
          initial={false}
          animate={{ left: `${keeper.at.x}%`, top: `${keeper.at.y}%` }}
          transition={{ type: "spring", stiffness: 260, damping: 22 }}
        >
          <img
            src={keeper.pose.src[keeperSide]}
            alt=""
            draggable={false}
            className="block w-full drop-shadow-[0_6px_6px_rgba(0,0,0,0.45)]"
            style={{ transform: keeper.flip ? "scaleX(-1)" : undefined }}
          />
        </motion.div>

        {/* Ball: shrinks as it flies away from the spot (perspective). */}
        <motion.div
          className="pointer-events-none absolute"
          style={{ x: "-50%", y: "-50%" }}
          initial={false}
          animate={{ left: `${ball.x}%`, top: `${ball.y}%`, width: kick ? "3.4%" : "7%", rotate: kick ? (ball.x < 50 ? -600 : 600) : 0 }}
          // The spin snaps back unseen when the ball is put on the spot again.
          transition={{ duration: kick ? 0.55 : 0.3, ease: [0.16, 0.85, 0.35, 1], rotate: kick ? { duration: 0.55, ease: "easeOut" } : { duration: 0 } }}
        >
          <SceneBall />
        </motion.div>

        {outcomeLabel && (
          <span
            className={`absolute bottom-[22%] left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full px-3 py-1 font-mono text-sm font-extrabold uppercase tracking-wider backdrop-blur-sm ${
              outcomeGood ? "bg-black/55 text-[#5ff08c]" : "bg-black/55 text-[#ff7a6e]"
            }`}
          >
            {outcomeLabel}
          </span>
        )}
      </div>
    </div>
  );
}
