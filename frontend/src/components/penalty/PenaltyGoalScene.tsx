import { useEffect, useRef } from "react";

import type { PenaltyDirection } from "@/types";

export interface PenaltyGoalKick {
  shotZone: PenaltyDirection;
  diveZone: PenaltyDirection;
  outcome: "goal" | "saved" | "miss";
}

export interface PenaltyGoalSceneProps {
  /** "own" = your goal is under attack, your (red) keeper dives.
   *  "opponent" = you're attacking, their (blue) keeper dives. */
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

// A little wider and a little shorter than a plain box, nudging toward real
// goal proportions (7.32m x 2.44m ≈ 3:1) without going all the way there.
const GOAL = { left: 20, right: 280, top: 42, bottom: 182 };
const GOAL_CENTER_X = (GOAL.left + GOAL.right) / 2;

const KEEPER_BASE = { x: GOAL_CENTER_X, y: (GOAL.top + GOAL.bottom) / 2 };
// The ball rests on the penalty spot, which is also drawn as a pitch marking
// — same coordinates, so the two always line up exactly.
const BALL_REST = { x: GOAL_CENTER_X, y: GOAL.bottom + 34 };

// Half-width/height of the glove art's bounding box — used both to draw the
// mask and to size zone offsets so the glove never crosses the posts/crossbar.
const GLOVE_HALF = 30;

// One shared aim point per zone — both the keeper's glove center and the
// ball's flight target land here, so a correct guess (diveZone === shotZone)
// always puts the ball exactly in the middle of the gloves. Bottom shots go
// noticeably lower than top ones (down near the goal line, not just past
// the midpoint) — bottom dives skip the tilt (see ZONE_KEEPER_TILT) so the
// glove's un-rotated bounding box leaves enough headroom to go that low
// and still stay fully inside the goal frame.
const ZONE_TARGET: Record<PenaltyDirection, { x: number; y: number }> = {
  top_left: { x: GOAL_CENTER_X - 64, y: KEEPER_BASE.y - 20 },
  top_center: { x: GOAL_CENTER_X, y: KEEPER_BASE.y - 20 },
  top_right: { x: GOAL_CENTER_X + 64, y: KEEPER_BASE.y - 20 },
  bottom_left: { x: GOAL_CENTER_X - 64, y: KEEPER_BASE.y + 32 },
  bottom_center: { x: GOAL_CENTER_X, y: KEEPER_BASE.y + 32 },
  bottom_right: { x: GOAL_CENTER_X + 64, y: KEEPER_BASE.y + 32 },
};

const ZONE_KEEPER_OFFSET: Record<PenaltyDirection, { x: number; y: number }> = Object.fromEntries(
  Object.entries(ZONE_TARGET).map(([zone, p]) => [zone, { x: p.x - KEEPER_BASE.x, y: p.y - KEEPER_BASE.y }]),
) as Record<PenaltyDirection, { x: number; y: number }>;

// Keeper tilts toward whichever side it's diving, on top of the translate —
// a straight-armed dive reads as more athletic than a purely upright slide.
// Bottom dives stay untilted: they already sit close to the goal line, and
// a rotated bounding box would need more clearance than is available there.
const ZONE_KEEPER_TILT: Record<PenaltyDirection, number> = {
  top_left: -10,
  top_center: 0,
  top_right: 10,
  bottom_left: 0,
  bottom_center: 0,
  bottom_right: 0,
};

const ZONE_BALL_TARGET = ZONE_TARGET;

const KEEPER_COLOR = { own: "#e6483b", opponent: "#3b82f6" };
const LINE = "#eef2ee";
const GRASS = ["#1e4a2a", "#234f2e"];

export default function PenaltyGoalScene({ keeperSide, kick, outcomeLabel, outcomeGood }: PenaltyGoalSceneProps) {
  const maskRef = useRef<SVGMaskElement>(null);
  useEffect(() => {
    // mask-type isn't a recognized React/JSX style key, so it's set
    // imperatively — "alpha" (not the SVG default "luminance") is required
    // because the source PNG is a solid black shape on a transparent
    // background: luminance masking would treat pure-black as invisible.
    maskRef.current?.setAttribute("mask-type", "alpha");
  }, []);

  const keeperOffset = kick ? ZONE_KEEPER_OFFSET[kick.diveZone] : { x: 0, y: 0 };
  const keeperTilt = kick ? ZONE_KEEPER_TILT[kick.diveZone] : 0;
  const ballTarget = kick ? ZONE_BALL_TARGET[kick.shotZone] : BALL_REST;

  const frameState = outcomeLabel ? (outcomeGood ? "good" : "bad") : "idle";

  return (
    <div
      className={`relative overflow-hidden rounded-[20px] border px-4 pb-3.5 pt-5 transition-[border-color,box-shadow] duration-300 ${
        frameState === "good"
          ? "border-[#3ecf6e]/70 shadow-[0_0_28px_-6px_rgba(62,207,110,0.55)]"
          : frameState === "bad"
            ? "border-[#e6483b]/70 shadow-[0_0_28px_-6px_rgba(230,72,59,0.55)]"
            : "border-white/5"
      } bg-[#0d1a10]`}
    >
      <div className="pointer-events-none absolute -inset-x-[20%] -top-[40%] h-[140px] bg-gradient-to-r from-accent-cyan via-accent-green to-accent-lime opacity-[0.16] blur-[30px]" />

      <div className="relative mx-auto my-1.5 max-w-[340px]">
        <svg className="block w-full overflow-visible" viewBox="0 0 300 258">
          {/* Turf — real mowed-stripe pattern instead of a flat void, so the
              ground reads as an actual pitch. */}
          <clipPath id="penaltyGrassClip">
            <rect x={0} y={GOAL.bottom} width={300} height={258 - GOAL.bottom} />
          </clipPath>
          <g clipPath="url(#penaltyGrassClip)">
            {Array.from({ length: 5 }, (_, i) => GOAL.bottom + i * 17).map((y, i) => (
              <rect key={`stripe${y}`} x={0} y={y} width={300} height={17} fill={GRASS[i % 2]} />
            ))}
          </g>

          {/* Goal line — drawn wider than the posts so it reads as the pitch
              marking the posts sit on, not just the base of the frame. */}
          <line x1={0} y1={GOAL.bottom} x2={300} y2={GOAL.bottom} stroke={LINE} strokeWidth={2.5} opacity={0.9} />

          {/* Goal frame + net */}
          <path
            d={`M ${GOAL.left} ${GOAL.bottom} L ${GOAL.left} ${GOAL.top} L ${GOAL.right} ${GOAL.top} L ${GOAL.right} ${GOAL.bottom}`}
            fill="none" stroke={LINE} strokeWidth={4} strokeLinecap="round"
          />
          <g stroke="rgba(238,242,238,0.28)" strokeWidth={1}>
            {Array.from({ length: 14 }, (_, i) => GOAL.left + i * 20).map((x) => (
              <line key={`v${x}`} x1={x} y1={GOAL.top} x2={x} y2={GOAL.bottom} />
            ))}
            {Array.from({ length: 8 }, (_, i) => GOAL.top + i * 20).map((y) => (
              <line key={`h${y}`} x1={GOAL.left} y1={y} x2={GOAL.right} y2={y} />
            ))}
          </g>

          <defs>
            <mask ref={maskRef} id="penaltyGloveMask" maskUnits="userSpaceOnUse" x={-GLOVE_HALF} y={-GLOVE_HALF} width={GLOVE_HALF * 2} height={GLOVE_HALF * 2}>
              <image href="/penalty/gk-gloves.png" x={-GLOVE_HALF} y={-GLOVE_HALF} width={GLOVE_HALF * 2} height={GLOVE_HALF * 2} />
            </mask>
          </defs>
          <g
            style={{
              // The glove art is drawn centered on local (0,0) (the
              // -GLOVE_HALF..GLOVE_HALF rect/mask), not on KEEPER_BASE —
              // transform-origin must match that local center, or rotate()
              // pivots around a point far from the glove itself and swings
              // it way off target.
              transformOrigin: "0px 0px",
              transform: `translate(${KEEPER_BASE.x + keeperOffset.x}px, ${KEEPER_BASE.y + keeperOffset.y}px) rotate(${keeperTilt}deg) scale(${kick ? 1.08 : 1})`,
              transition: "transform 420ms cubic-bezier(0.2,0.9,0.3,1.3)",
            }}
          >
            <ellipse cx={0} cy={GLOVE_HALF - 2} rx={GLOVE_HALF - 2} ry={5} fill="rgba(0,0,0,0.35)" />
            <rect
              x={-GLOVE_HALF} y={-GLOVE_HALF} width={GLOVE_HALF * 2} height={GLOVE_HALF * 2}
              mask="url(#penaltyGloveMask)"
              fill={KEEPER_COLOR[keeperSide]}
              style={{ transition: "fill 200ms linear" }}
            />
          </g>

          {/* Penalty spot — a single fixed marking painted on the grass. It
              never moves: real penalty spots don't follow the ball around,
              so this stays put whether the ball is resting on it or has
              already flown off toward a corner. */}
          <circle cx={BALL_REST.x} cy={BALL_REST.y} r={7} fill="rgba(238,242,238,0.8)" />

          <g
            style={{
              transformOrigin: `${BALL_REST.x}px ${BALL_REST.y}px`,
              transform: `translate(${ballTarget.x - BALL_REST.x}px, ${ballTarget.y - BALL_REST.y}px) scale(${kick ? 1.3 : 1.55})`,
              transition: "transform 550ms cubic-bezier(0.16,0.85,0.35,1)",
            }}
          >
            <g transform={`translate(${BALL_REST.x},${BALL_REST.y}) translate(-10.377,-10.047) translate(-1.623,-1.913)`}>
              <circle fill="#f3f6f2" cx={12} cy={12} r={9} />
              <path fill="#2ca9bc" d="M14.33,3.31,12,5,9.67,3.31a8.91,8.91,0,0,1,4.66,0ZM4.46,7.1A9,9,0,0,0,3,11.53L5.34,9.84ZM8,17.89l-.07-.23H5A8.92,8.92,0,0,0,8.78,20.4ZM12,8,8.5,10.67,9.84,15h4.32l1.34-4.33Zm4.11,9.66-.07.23-.82,2.51A8.92,8.92,0,0,0,19,17.66ZM19.54,7.11l-.88,2.73L21,11.53a8.93,8.93,0,0,0-1.46-4.42Z" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.67,3.31,12,5l2.33-1.69" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.02,11.53,5.34,9.84,4.46,7.1" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18,18l-1.92-.04-.73,2.38" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6,18l1.92-.04.73,2.38" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.55,7.1l-.89,2.74,2.32,1.69" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12,8V5M8.41,10.65,5.34,9.84M9.84,15,7.89,18m6.27-3,1.95,3m-.61-7.33,3.16-.83M12,8,8.5,10.67,9.84,15h4.32l1.34-4.33Zm0-5a9,9,0,1,0,9,9A9,9,0,0,0,12,3Z" />
            </g>
          </g>
        </svg>

        {outcomeLabel && (
          <span
            className={`absolute -top-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full px-2.5 py-1 font-mono text-xs font-extrabold uppercase tracking-wider ${
              outcomeGood ? "bg-[#3ecf6e]/20 text-[#3ecf6e]" : "bg-[#e6483b]/20 text-[#e6483b]"
            }`}
          >
            {outcomeLabel}
          </span>
        )}
      </div>
    </div>
  );
}
