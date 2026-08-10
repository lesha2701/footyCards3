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
  /** Colors the badge green (true) or red (false) — "good" is relative to
   * the viewer: scoring while attacking is good, saving while defending is good. */
  outcomeGood: boolean;
}

const KEEPER_BASE = { x: 150, y: 118 };
const BALL_REST = { x: 150, y: 234 };

const ZONE_KEEPER_OFFSET: Record<PenaltyDirection, { x: number; y: number }> = {
  top_left: { x: -78, y: -58 },
  top_center: { x: 0, y: -68 },
  top_right: { x: 78, y: -58 },
  bottom_left: { x: -78, y: 34 },
  bottom_center: { x: 0, y: 40 },
  bottom_right: { x: 78, y: 34 },
};

const ZONE_BALL_TARGET: Record<PenaltyDirection, { x: number; y: number }> = {
  top_left: { x: 80, y: 55 },
  top_center: { x: 150, y: 45 },
  top_right: { x: 220, y: 55 },
  bottom_left: { x: 80, y: 168 },
  bottom_center: { x: 150, y: 176 },
  bottom_right: { x: 220, y: 168 },
};

const KEEPER_COLOR = { own: "#e6483b", opponent: "#3b82f6" };

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
  const ballTarget = kick ? ZONE_BALL_TARGET[kick.shotZone] : BALL_REST;

  return (
    <div className="relative overflow-hidden rounded-[20px] border border-white/5 bg-[#0d1a10] px-4 pb-3.5 pt-5">
      <div className="pointer-events-none absolute -inset-x-[20%] -top-[40%] h-[140px] bg-gradient-to-r from-accent-cyan via-accent-green to-accent-lime opacity-[0.16] blur-[30px]" />

      <div className="relative mx-auto my-1.5 max-w-[300px]">
        <svg className="block w-full overflow-visible" viewBox="0 0 300 258">
          <path d="M 30 200 L 30 30 L 270 30 L 270 200" fill="none" stroke="#eef2ee" strokeWidth={4} strokeLinecap="round" />
          <g stroke="rgba(238,242,238,0.28)" strokeWidth={1}>
            {Array.from({ length: 13 }, (_, i) => 30 + i * 20).map((x) => (
              <line key={`v${x}`} x1={x} y1={30} x2={x} y2={200} />
            ))}
            {Array.from({ length: 9 }, (_, i) => 30 + i * 21).map((y) => (
              <line key={`h${y}`} x1={30} y1={y} x2={270} y2={y} />
            ))}
          </g>

          <defs>
            <mask ref={maskRef} id="penaltyGloveMask" maskUnits="userSpaceOnUse" x={-40} y={-40} width={80} height={80}>
              <image href="/penalty/gk-gloves.png" x={-40} y={-40} width={80} height={80} />
            </mask>
          </defs>
          <g
            style={{
              transformOrigin: `${KEEPER_BASE.x}px ${KEEPER_BASE.y}px`,
              transform: `translate(${KEEPER_BASE.x + keeperOffset.x}px, ${KEEPER_BASE.y + keeperOffset.y}px) scale(${kick ? 1.05 : 1})`,
              transition: "transform 420ms cubic-bezier(0.2,0.9,0.3,1.3)",
            }}
          >
            <ellipse cx={0} cy={36} rx={36} ry={6} fill="rgba(0,0,0,0.35)" />
            <rect
              x={-40} y={-40} width={80} height={80}
              mask="url(#penaltyGloveMask)"
              fill={KEEPER_COLOR[keeperSide]}
              style={{ transition: "fill 200ms linear" }}
            />
          </g>

          <ellipse cx={BALL_REST.x} cy={BALL_REST.y} rx={10} ry={3.5} fill="rgba(238,242,238,0.55)" />
          <g
            style={{
              transformOrigin: `${BALL_REST.x}px ${BALL_REST.y}px`,
              transform: `translate(${ballTarget.x - BALL_REST.x}px, ${ballTarget.y - BALL_REST.y}px) scale(${kick ? 0.75 : 1})`,
              transition: "transform 550ms cubic-bezier(0.16,0.85,0.35,1)",
            }}
          >
            <g transform={`translate(${BALL_REST.x},${BALL_REST.y}) scale(1.06) translate(-10.377,-10.047) translate(-1.623,-1.913)`}>
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
              outcomeGood ? "bg-accent-green/20 text-accent-green" : "bg-[#e6483b]/20 text-[#e6483b]"
            }`}
          >
            {outcomeLabel}
          </span>
        )}
      </div>
    </div>
  );
}
