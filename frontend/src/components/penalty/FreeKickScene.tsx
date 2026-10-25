import { motion } from "framer-motion";
import { useEffect, useState } from "react";

import freekickBg from "@/assets/shots/freekick-bg.webp";
import freekickWall from "@/assets/shots/freekick-wall.webp";
import keeperDiveLow from "@/assets/shots/keeper-dive-low.webp";
import keeperDiveSide from "@/assets/shots/keeper-dive-side.webp";
import keeperReady from "@/assets/shots/keeper-ready.webp";
import { haptic } from "@/lib/telegram";

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

// The opponent's keeper, at the same scale to the goal as in «Пенальти»;
// he stands on the side the wall leaves open. Dive art is drawn diving to
// the screen's left (gloves at the anchor); right-hand dives mirror it.
const KEEPER_W = 12.4;
const KEEPER_SPOT = { x: 60, y: GOAL.bottom + 0.3 };
const KEEPER_POSES = {
  ready: { src: keeperReady, w: KEEPER_W, anchor: { x: 0.5, y: 1 } },
  side: { src: keeperDiveSide, w: KEEPER_W * (594 / 575), anchor: { x: 0.1, y: 0.22 } },
  low: { src: keeperDiveLow, w: KEEPER_W * (577 / 575), anchor: { x: 0.1, y: 0.8 } },
} as const;

/** «Штрафной»: the stadium, a three-man wall, the keeper and the ball. The aim sweeps
 * across the goal with the timing bar; a kick curls over the wall to where
 * it was stopped — high for «Идеально», low for «Норм», into the wall on a
 * miss. Purely visual: the result comes from the server. */
export default function FreeKickScene({ aim, shot }: { aim: number; shot: FreeKickShot | null }) {
  const [flying, setFlying] = useState(false);
  useEffect(() => {
    if (!shot) return;
    setFlying(true);
    // A thud when the ball arrives — in the net or off the wall.
    const thud = setTimeout(() => haptic(shot.tier === "miss" ? "light" : "heavy"), 700);
    const t = setTimeout(() => setFlying(false), 1500);
    return () => { clearTimeout(thud); clearTimeout(t); };
  }, [shot]);

  const target = (() => {
    if (!shot) return SPOT;
    const x = aimX(shot.aim);
    if (shot.tier === "miss") return { x: WALL.x + (x - 50) * 0.35, y: WALL_TOP + 6 };
    return { x, y: GOAL.top + GOAL_H * (TIER_HEIGHT[shot.tier] ?? 0.5) };
  })();
  const apexY = Math.min(target.y, WALL_TOP) - (shot?.tier === "miss" ? 4 : 10);
  const scored = !!shot && shot.tier !== "miss";

  // A goal: the keeper flies at it and comes up short (his gloves stop
  // ~40% of the way). Into the wall: he doesn't have to move.
  const keeper = (() => {
    if (!flying || !scored) return { pose: KEEPER_POSES.ready, at: KEEPER_SPOT, flip: false };
    const reach = { x: KEEPER_SPOT.x + (target.x - KEEPER_SPOT.x) * 0.6, y: target.y + (target.y < GOAL.top + GOAL_H / 2 ? 1 : -1) };
    const pose = target.y < GOAL.top + GOAL_H * 0.45 ? KEEPER_POSES.side : KEEPER_POSES.low;
    return { pose, at: reach, flip: target.x > KEEPER_SPOT.x };
  })();
  const keeperAnchorX = keeper.flip ? 1 - keeper.pose.anchor.x : keeper.pose.anchor.x;

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

      {/* Keeper: behind the wall in the picture, so drawn before it. */}
      <motion.div
        className="pointer-events-none absolute"
        style={{ width: `${keeper.pose.w}%`, x: `${-keeperAnchorX * 100}%`, y: `${-keeper.pose.anchor.y * 100}%` }}
        initial={false}
        animate={{ left: `${keeper.at.x}%`, top: `${keeper.at.y}%` }}
        transition={flying ? { type: "spring", stiffness: 220, damping: 20, delay: 0.3 } : { duration: 0.3 }}
      >
        <img
          src={keeper.pose.src}
          alt=""
          draggable={false}
          className="block w-full drop-shadow-[0_4px_4px_rgba(0,0,0,0.45)]"
          style={{ transform: keeper.flip ? "scaleX(-1)" : undefined }}
        />
      </motion.div>

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
            rotate: [0, target.x >= 50 ? -540 : 540, target.x >= 50 ? -720 : 720],
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
