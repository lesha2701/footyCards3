import { motion, useMotionTemplate, useReducedMotion, useTransform } from "framer-motion";
import type { ReactNode } from "react";

import { useCardTilt } from "@/components/myPlayer/useCardTilt";
import type { Rarity } from "@/types";

/** How strong the rainbow foil is by rarity: a common card only tilts and
 * catches the light, the rarer the card the brighter its foil. */
export const HOLO_OPACITY: Record<Rarity, number> = {
  common: 0,
  rare: 0.18,
  epic: 0.3,
  legendary: 0.42,
  diamond: 0.55,
};

const FOIL: Record<Rarity, string> = {
  common: "",
  rare: "linear-gradient(115deg, transparent 25%, rgba(120,200,255,0.5) 45%, rgba(255,255,255,0.4) 50%, transparent 70%)",
  epic: "linear-gradient(115deg, transparent 20%, rgba(200,120,255,0.45) 38%, rgba(120,220,255,0.4) 50%, rgba(255,140,220,0.35) 62%, transparent 78%)",
  legendary:
    "linear-gradient(115deg, transparent 18%, rgba(255,215,90,0.55) 34%, rgba(255,255,255,0.45) 46%, rgba(255,170,40,0.45) 58%, transparent 76%)",
  diamond:
    "linear-gradient(115deg, transparent 15%, rgba(255,255,255,0.4) 28%, rgba(255,0,200,0.3) 40%, rgba(0,255,255,0.35) 52%, rgba(255,230,0,0.3) 64%, rgba(120,255,160,0.3) 74%, transparent 86%)",
};

/** A card in focus (pack reveal, card sheet): it tilts after the finger
 * and, in Telegram, after the phone itself, and its foil and glare slide
 * with the tilt. `rounded` is the card's corner class, so the overlays
 * don't spill past them. Off under «reduce motion». */
export default function HoloTilt({
  rarity, enabled = true, rounded = "rounded-3xl", className = "", children,
}: {
  rarity: Rarity;
  enabled?: boolean;
  rounded?: string;
  className?: string;
  children: ReactNode;
}) {
  const reduce = useReducedMotion();
  const on = enabled && !reduce;
  const tilt = useCardTilt(on);
  const sheenX = useTransform(tilt.rotateY, [-12, 12], [0, 100]);
  const sheenY = useTransform(tilt.rotateX, [-12, 12], [100, 0]);
  const foilPosition = useMotionTemplate`${sheenX}% ${sheenY}%`;
  const glare = useMotionTemplate`radial-gradient(circle at ${sheenX}% ${sheenY}%, rgba(255,255,255,0.3), transparent 55%)`;

  // One structure whether on or off: turning it on (the card turns over)
  // must not remount the card and replay its entrance.
  return (
    <div style={{ perspective: 800 }} className={className}>
      <motion.div
        onPointerMove={on ? tilt.onPointerMove : undefined}
        onPointerLeave={on ? tilt.onPointerLeave : undefined}
        onPointerUp={on ? tilt.onPointerLeave : undefined}
        style={{ rotateX: tilt.rotateX, rotateY: tilt.rotateY, transformStyle: "preserve-3d" }}
        className={`relative touch-pan-y ${rounded}`}
        data-testid={on ? "holo-tilt" : undefined}
      >
        {children}
        {on && HOLO_OPACITY[rarity] > 0 && (
          <motion.div
            aria-hidden="true"
            className={`pointer-events-none absolute inset-0 overflow-hidden mix-blend-color-dodge ${rounded}`}
            style={{
              backgroundImage: FOIL[rarity],
              backgroundSize: "250% 250%",
              backgroundPosition: foilPosition,
              opacity: HOLO_OPACITY[rarity],
            }}
            data-testid="holo-foil"
          />
        )}
        {on && (
          <motion.div
            aria-hidden="true"
            className={`pointer-events-none absolute inset-0 ${rounded}`}
            style={{ backgroundImage: glare }}
          />
        )}
      </motion.div>
    </div>
  );
}
