import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

import { stageIcon } from "@/lib/pathCards";

/** Full-screen «новый этап!» moment. With prefers-reduced-motion it is a
 * plain fade with no scaling, burst or confetti. */
export default function StageUpCelebration({
  open,
  stageIndex,
  stageName,
  talentText,
  onClose,
}: {
  open: boolean;
  stageIndex: number;
  stageName: string;
  /** e.g. «Талант открыт: 🔥 Большие матчи I» when this stage unlocks it. */
  talentText?: string | null;
  onClose: () => void;
}) {
  const reduced = useReducedMotion();
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/80 p-6 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          aria-label={`Новый этап: ${stageName}`}
        >
          {!reduced && (
            <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
              {Array.from({ length: 14 }).map((_, i) => (
                <motion.span
                  key={i}
                  className="absolute left-1/2 top-1/2 text-xl"
                  initial={{ x: 0, y: 0, opacity: 0, scale: 0.4 }}
                  animate={{
                    x: Math.cos((i / 14) * Math.PI * 2) * (120 + (i % 3) * 30),
                    y: Math.sin((i / 14) * Math.PI * 2) * (120 + (i % 3) * 30),
                    opacity: [0, 1, 0],
                    scale: 1,
                  }}
                  transition={{ duration: 1.4, delay: 0.15 + (i % 4) * 0.05, ease: "easeOut" }}
                >
                  {i % 2 ? "🍃" : "✨"}
                </motion.span>
              ))}
            </div>
          )}
          <motion.div
            className="relative w-full max-w-xs rounded-3xl bg-gradient-to-b from-emerald-300 via-lime-200 to-cyan-300 p-[3px] shadow-[0_0_40px_rgba(110,231,183,0.5)]"
            initial={reduced ? { opacity: 0 } : { scale: 0.6, opacity: 0, y: 30 }}
            animate={reduced ? { opacity: 1 } : { scale: 1, opacity: 1, y: 0 }}
            transition={reduced ? { duration: 0.2 } : { type: "spring", stiffness: 260, damping: 18 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="path-ui rounded-[21px] bg-bg-surface px-5 py-6 text-center">
              <motion.div
                className="mx-auto grid h-20 w-20 place-items-center rounded-full bg-emerald-400/15 text-5xl"
                initial={reduced ? false : { rotate: -20, scale: 0.5 }}
                animate={reduced ? undefined : { rotate: 0, scale: 1 }}
                transition={{ type: "spring", stiffness: 200, damping: 12, delay: 0.1 }}
                aria-hidden
              >
                {stageIcon(stageIndex)}
              </motion.div>
              <p className="mt-3 text-[11px] font-semibold uppercase tracking-widest text-emerald-300">Новый этап пути</p>
              <p className="mt-1 font-display text-2xl font-bold text-ink-chalk">{stageName}</p>
              {talentText && <p className="mt-2 rounded-xl bg-emerald-400/10 px-3 py-2 text-sm text-ink-chalk">{talentText}</p>}
              <button
                type="button"
                onClick={onClose}
                className="mt-5 w-full rounded-2xl bg-emerald-400 py-2.5 text-sm font-bold text-black"
              >
                Отлично!
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
