import { motion } from "framer-motion";
import { useEffect, useState } from "react";

import freekickBg from "@/assets/shots/freekick-bg.webp";
import freekickWall from "@/assets/shots/freekick-wall.webp";

import { SceneBall } from "./SceneBall";

export interface FreeKickShot {
  /** Changes with every kick (restarts the flight). */
  id: number;
  /** Where the aim stood when the player struck, 0..100 across the goal. */
  aim: number;
  tier: "perfect" | "good" | "ok" | "miss" | string;
}

// % of the scene (the cropped 800×710 stadium picture). The goal as it sits in it:
const SCENE_ASPECT = 800 / 710;
const GOAL = { left: 30.9, right: 69.0, top: 18.3, bottom: 33.1 };
const GOAL_W = GOAL.right - GOAL.left;
const GOAL_H = GOAL.bottom - GOAL.top;
const SPOT = { x: 50, y: 86 };
// The wall stands between the ball and the goal; its heads are at WALL_TOP.
const WALL = { x: 47, feet: 47, width: 18 };
const WALL_TOP = 28;

const aimX = (aim: number) => GOAL.left + GOAL_W * (0.12 + 0.76 * (aim / 100));
// How high in the goal each result goes in (fraction of the goal's height).
const TIER_HEIGHT: Record<string, number> = { perfect: 0.15, good: 0.35, ok: 0.55 };

/** «Штрафной»: the stadium, a three-man wall and the ball. The aim sweeps
 * across the goal with the timing bar; a kick curls over the wall to where
 * it was stopped — high for «Идеально», low for «Норм», into the wall on a
 * miss. Purely visual: the result comes from the server. */
export default function FreeKickScene({ aim, shot }: { aim: number; shot: FreeKickShot | null }) {
  const [flying, setFlying] = useState(false);
  useEffect(() => {
    if (!shot) return;
    setFlying(true);
    const t = setTimeout(() => setFlying(false), 1500);
    return () => clearTimeout(t);
  }, [shot]);

  const target = (() => {
    if (!shot) return SPOT;
    const x = aimX(shot.aim);
    if (shot.tier === "miss") return { x: WALL.x + (x - 50) * 0.35, y: WALL_TOP + 6 };
    return { x, y: GOAL.top + GOAL_H * (TIER_HEIGHT[shot.tier] ?? 0.5) };
  })();
  const apexY = Math.min(target.y, WALL_TOP) - (shot?.tier === "miss" ? 4 : 10);
  const scored = !!shot && shot.tier !== "miss";

  return (
    // Height from padding, not aspect-ratio (older Telegram WebViews lack it).
    <div className="relative w-full max-w-sm select-none overflow-hidden rounded-[20px] border border-white/5" style={{ paddingTop: `${100 / SCENE_ASPECT}%` }}>
      <img src={freekickBg} alt="" draggable={false} className="absolute inset-0 h-full w-full object-cover" />

      {/* Aim: sweeps across the goal while the player waits for the moment. */}
      {!flying && (
        <div
          className="pointer-events-none absolute h-[7%] w-[7%] -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent-lime shadow-[0_0_10px_rgba(190,242,100,0.8)]"
          style={{ left: `${aimX(aim)}%`, top: `${GOAL.top + GOAL_H * 0.4}%` }}
          aria-hidden
        >
          <span className="absolute left-1/2 top-1/2 h-1 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent-lime" />
        </div>
      )}

      {/* The net lights up on a goal. */}
      {flying && scored && (
        <motion.div
          key={`net-${shot!.id}`}
          className="pointer-events-none absolute"
          style={{
            left: `${GOAL.left}%`, top: `${GOAL.top}%`, width: `${GOAL_W}%`, height: `${GOAL_H}%`,
            background: "radial-gradient(ellipse at center, rgba(255,255,255,0.6), rgba(255,255,255,0) 70%)",
          }}
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 0, 1, 0] }}
          transition={{ duration: 1.2, times: [0, 0.5, 0.62, 1] }}
        />
      )}

      <img
        src={freekickWall}
        alt=""
        draggable={false}
        className="pointer-events-none absolute -translate-x-1/2 -translate-y-full drop-shadow-[0_6px_6px_rgba(0,0,0,0.45)]"
        style={{ left: `${WALL.x}%`, top: `${WALL.feet}%`, width: `${WALL.width}%` }}
      />

      {/* Ball: on the spot, or curling over the wall toward the target. */}
      {flying && shot ? (
        <motion.div
          key={`ball-${shot.id}`}
          className="pointer-events-none absolute"
          style={{ x: "-50%", y: "-50%" }}
          initial={{ left: `${SPOT.x}%`, top: `${SPOT.y}%`, width: "6%" }}
          animate={{
            left: [`${SPOT.x}%`, `${(SPOT.x + target.x) / 2 + (target.x >= 50 ? -6 : 6)}%`, `${target.x}%`],
            top: [`${SPOT.y}%`, `${apexY}%`, `${target.y}%`],
            width: ["6%", "3.6%", "2.6%"],
          }}
          transition={{ duration: 0.75, ease: "easeOut", times: [0, 0.55, 1] }}
        >
          <SceneBall />
        </motion.div>
      ) : (
        <div className="pointer-events-none absolute w-[6%] -translate-x-1/2 -translate-y-1/2" style={{ left: `${SPOT.x}%`, top: `${SPOT.y}%` }}>
          <SceneBall />
        </div>
      )}
    </div>
  );
}
