import { motion, type TargetAndTransition } from "framer-motion";

import { CELEBRATION_EMOJI } from "@/lib/myPlayer";

// How each celebration moves.
const MOTION: Record<string, TargetAndTransition> = {
  cel_siu: { y: [30, -40, 0], scale: [0.6, 1.4, 1], transition: { duration: 0.9 } },
  cel_siu_gold: { y: [30, -50, 0], scale: [0.6, 1.6, 1.1], rotate: [0, 0, 360], transition: { duration: 1.2 } },
  cel_plane: { x: [-80, 80, 0], rotate: [-20, 15, 0], transition: { duration: 1 } },
  cel_flip: { rotate: [0, 360], y: [0, -40, 0], transition: { duration: 0.9 } },
  cel_knee: { x: [-90, 0], rotate: [-10, 0], transition: { duration: 0.8 } },
  cel_dance: { rotate: [-15, 15, -15, 15, 0], transition: { duration: 1 } },
  cel_flex: { scale: [1, 1.35, 1, 1.35, 1], transition: { duration: 0.9 } },
  cel_shush: { scale: [0.6, 1.2, 1], opacity: [0, 1, 1], transition: { duration: 0.7 } },
};
const DEFAULT: TargetAndTransition = { scale: [0.5, 1.3, 1], transition: { duration: 0.7 } };

/** A goal celebration (cosmetic) as an animated emoji; the gold one shines. */
export default function CelebrationBurst({ code, size = "text-6xl" }: { code: string; size?: string }) {
  const gold = code === "cel_siu_gold";
  return (
    <div className="relative mx-auto flex h-24 w-24 items-center justify-center" data-testid="celebration">
      {gold && (
        <motion.span
          aria-hidden="true"
          className="absolute inset-0 rounded-full bg-amber-300/40 blur-xl"
          animate={{ opacity: [0, 1, 0.6], scale: [0.6, 1.3, 1] }}
          transition={{ duration: 1.2 }}
        />
      )}
      <motion.span className={`relative ${size}`} animate={MOTION[code] ?? DEFAULT}>
        {CELEBRATION_EMOJI[code] ?? "🎉"}
      </motion.span>
    </div>
  );
}
