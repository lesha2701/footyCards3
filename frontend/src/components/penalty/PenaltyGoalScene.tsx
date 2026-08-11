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

// Goal posts at real-world proportions (7.32m x 2.44m ≈ 3:1) rather than the
// old ~1.4:1 box, so it actually reads as a football goal.
const GOAL = { left: 20, right: 300, top: 55, bottom: 150 };
const GOAL_CENTER_X = (GOAL.left + GOAL.right) / 2;

const KEEPER_BASE = { x: GOAL_CENTER_X, y: (GOAL.top + GOAL.bottom) / 2 + 3 };
// The ball rests on the penalty spot, which is also drawn as a pitch marking.
const BALL_REST = { x: GOAL_CENTER_X, y: 210 };

const ZONE_KEEPER_OFFSET: Record<PenaltyDirection, { x: number; y: number }> = {
  top_left: { x: -84, y: -26 },
  top_center: { x: 0, y: -34 },
  top_right: { x: 84, y: -26 },
  bottom_left: { x: -84, y: 28 },
  bottom_center: { x: 0, y: 33 },
  bottom_right: { x: 84, y: 28 },
};

// Keeper tilts toward whichever side it's diving, on top of the translate —
// a straight-armed dive reads as more athletic than a purely upright slide.
const ZONE_KEEPER_TILT: Record<PenaltyDirection, number> = {
  top_left: -14,
  top_center: 0,
  top_right: 14,
  bottom_left: -18,
  bottom_center: 0,
  bottom_right: 18,
};

const ZONE_BALL_TARGET: Record<PenaltyDirection, { x: number; y: number }> = {
  top_left: { x: 92, y: 76 },
  top_center: { x: GOAL_CENTER_X, y: 66 },
  top_right: { x: 228, y: 76 },
  bottom_left: { x: 92, y: 134 },
  bottom_center: { x: GOAL_CENTER_X, y: 141 },
  bottom_right: { x: 228, y: 134 },
};

const KEEPER_COLOR = { own: "#e6483b", opponent: "#3b82f6" };
const LINE = "#eef2ee";

/** A single stylized goalkeeper glove: a rounded "mitten" body plus a thumb,
 * drawn so it can be filled with the team color and given a thin dark
 * outline independently — the previous version recolored a raster line-art
 * icon via an alpha mask, which could only ever produce a colored outline,
 * never an actual fill. */
function Glove({ mirror, color }: { mirror: boolean; color: string }) {
  const s = mirror ? -1 : 1;
  const fillStyle: React.CSSProperties = { transition: "fill 200ms linear" };
  return (
    <g>
      <rect
        x={s * 6} y={-40} width={22} height={54} rx={11}
        transform={`translate(${s * 22} 6) rotate(${s * 16})`}
        fill={color} style={fillStyle} stroke="#0b1310" strokeWidth={1.75} strokeLinejoin="round"
      />
      <ellipse
        cx={s * 27} cy={2} rx={7} ry={11}
        transform={`rotate(${s * 55} ${s * 27} 2)`}
        fill={color} style={fillStyle} stroke="#0b1310" strokeWidth={1.75}
      />
      <rect x={s * 14} y={2} width={18} height={9} rx={3} transform={`translate(${s * 14} 6)`} fill="#0b1310" opacity={0.55} />
    </g>
  );
}

export default function PenaltyGoalScene({ keeperSide, kick, outcomeLabel, outcomeGood }: PenaltyGoalSceneProps) {
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
      <StadiumBackdrop />

      <div className="relative mx-auto my-1.5 max-w-[340px]">
        <svg className="block w-full overflow-visible" viewBox="0 0 320 260">
          {/* Goal line — drawn wider than the posts so it reads as the pitch
              marking the posts sit on, not just the base of the frame. */}
          <line x1={0} y1={GOAL.bottom} x2={320} y2={GOAL.bottom} stroke={LINE} strokeWidth={2.5} opacity={0.9} />

          {/* 6-yard box */}
          <path
            d={`M ${GOAL_CENTER_X - 55} ${GOAL.bottom} L ${GOAL_CENTER_X - 55} ${GOAL.bottom + 34} L ${GOAL_CENTER_X + 55} ${GOAL.bottom + 34} L ${GOAL_CENTER_X + 55} ${GOAL.bottom}`}
            fill="none" stroke={LINE} strokeWidth={1.5} opacity={0.55}
          />
          {/* Penalty arc (the "D"), suggested with just the visible cap since
              the full penalty-area box is outside the viewBox at this scale. */}
          <path d={`M ${GOAL_CENTER_X - 34} 238 Q ${GOAL_CENTER_X} 214 ${GOAL_CENTER_X + 34} 238`} fill="none" stroke={LINE} strokeWidth={1.5} opacity={0.55} />
          {/* Penalty spot */}
          <circle cx={BALL_REST.x} cy={BALL_REST.y} r={2.6} fill={LINE} opacity={0.8} />

          {/* Goal frame + net */}
          <path
            d={`M ${GOAL.left} ${GOAL.bottom} L ${GOAL.left} ${GOAL.top} L ${GOAL.right} ${GOAL.top} L ${GOAL.right} ${GOAL.bottom}`}
            fill="none" stroke={LINE} strokeWidth={4} strokeLinecap="round"
          />
          <g stroke="rgba(238,242,238,0.24)" strokeWidth={1}>
            {Array.from({ length: 15 }, (_, i) => GOAL.left + i * 20).map((x) => (
              <line key={`v${x}`} x1={x} y1={GOAL.top} x2={x} y2={GOAL.bottom} />
            ))}
            {Array.from({ length: 6 }, (_, i) => GOAL.top + i * 19).map((y) => (
              <line key={`h${y}`} x1={GOAL.left} y1={y} x2={GOAL.right} y2={y} />
            ))}
          </g>

          <g
            style={{
              transformOrigin: `${KEEPER_BASE.x}px ${KEEPER_BASE.y}px`,
              transform: `translate(${KEEPER_BASE.x + keeperOffset.x}px, ${KEEPER_BASE.y + keeperOffset.y}px) rotate(${keeperTilt}deg) scale(${kick ? 1.08 : 1})`,
              transition: "transform 420ms cubic-bezier(0.2,0.9,0.3,1.3)",
            }}
          >
            <ellipse cx={0} cy={38} rx={38} ry={6} fill="rgba(0,0,0,0.35)" />
            <Glove mirror={false} color={KEEPER_COLOR[keeperSide]} />
            <Glove mirror color={KEEPER_COLOR[keeperSide]} />
          </g>

          <ellipse cx={BALL_REST.x} cy={BALL_REST.y} rx={16} ry={5} fill="rgba(238,242,238,0.5)" />
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

/** Faint tactics-board arrows behind the goal, echoing HomePage's
 * ChalkTexture — converging runs toward the box instead of random doodles. */
function StadiumBackdrop() {
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.09]" viewBox="0 0 320 220" fill="none">
      <path d="M -10 190 Q 90 150 150 100" stroke={LINE} strokeWidth={1.5} fill="none" />
      <polyline points="141,92 150,100 144,110" stroke={LINE} strokeWidth={1.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M 330 190 Q 230 150 172 102" stroke={LINE} strokeWidth={1.5} fill="none" />
      <polyline points="181,94 172,102 178,112" stroke={LINE} strokeWidth={1.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={40} cy={40} r={7} stroke={LINE} strokeWidth={1.2} />
      <circle cx={284} cy={36} r={5} stroke={LINE} strokeWidth={1.2} />
      <line x1={20} y1={200} x2={300} y2={200} stroke={LINE} strokeWidth={1} strokeDasharray="2 6" />
    </svg>
  );
}
