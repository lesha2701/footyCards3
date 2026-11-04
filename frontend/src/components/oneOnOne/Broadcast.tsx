import { AnimatePresence, motion } from "framer-motion";

import { IconCoin } from "@/components/icons";
import type { OneOnOneOutcome } from "@/types";

/** «Атака 1 на 1» on screen as on TV: the score bug in the corner and the
 * big caption of what happened. */

const DOT: Record<OneOnOneOutcome, string> = {
  goal: "bg-accent-lime",
  save: "bg-red-500",
  tackle: "bg-red-500",
  miss: "bg-red-500",
  lost: "bg-red-500",
  dispossessed: "bg-red-500",
  intercepted: "bg-red-500",
  offside: "bg-red-500",
  cleared: "bg-red-500",
  blocked: "bg-red-500",
};

/** The score bug: the series (one dot per attack), the coins, and under it
 * the striker's strip (name, rating, the feint). */
export function ScoreBug({
  index,
  total,
  results,
  coins,
  name,
  rating,
}: {
  index: number;
  total: number;
  results: OneOnOneOutcome[];
  coins: number;
  name: string;
  rating: number;
}) {
  return (
    <div className="flex flex-col items-end gap-1 font-display">
      <div className="flex items-stretch overflow-hidden rounded-md shadow-lg shadow-black/40">
        <div className="flex items-center bg-accent-lime px-2 text-[11px] font-black italic tracking-tight text-black">VFC</div>
        <div className="flex items-center gap-2 bg-[#0b1220]/90 px-2.5 py-1 backdrop-blur">
          <span className="text-[11px] font-bold uppercase tracking-wider text-white">
            Атака {index + 1}/{total}
          </span>
          <span className="flex gap-1">
            {Array.from({ length: total }, (_, i) => (
              <span
                key={i}
                className={`h-2 w-2 rounded-full ${
                  results[i] ? DOT[results[i]] : i === index ? "animate-pulse bg-white" : "bg-white/20"
                }`}
              />
            ))}
          </span>
        </div>
        <div className="flex items-center gap-0.5 bg-[#16233a]/90 px-2 font-mono text-xs font-bold text-accent-lime">
          {coins}
          <IconCoin size={11} />
        </div>
      </div>
      <div className="flex items-center gap-1.5 rounded-sm bg-black/60 px-2 py-0.5 text-[11px] uppercase tracking-wide text-white backdrop-blur">
        <span className="h-3 w-0.5 bg-accent-lime" />
        <span className="font-semibold">{name}</span>
        <span className="font-mono text-accent-lime">{rating}</span>
      </div>
    </div>
  );
}

const CAPTION: Record<OneOnOneOutcome, { text: string; band: string; fill: string; glow: string } | null> = {
  goal: { text: "ГОЛ!", band: "from-accent-lime/0 via-emerald-500/85 to-accent-lime/0", fill: "from-white via-[#f4ffc2] to-accent-lime", glow: "#c6e63a" },
  save: { text: "СЕЙВ!", band: "from-sky-500/0 via-sky-600/85 to-sky-500/0", fill: "from-white via-sky-100 to-sky-300", glow: "#38bdf8" },
  tackle: { text: "ВРАТАРЬ ЗАБРАЛ", band: "from-sky-500/0 via-sky-700/80 to-sky-500/0", fill: "from-white to-sky-200", glow: "#38bdf8" },
  miss: { text: "МИМО", band: "from-red-500/0 via-red-700/80 to-red-500/0", fill: "from-white to-red-200", glow: "#ef4444" },
  lost: { text: "МОМЕНТ УПУЩЕН", band: "from-red-500/0 via-red-700/80 to-red-500/0", fill: "from-white to-red-200", glow: "#ef4444" },
  dispossessed: { text: "ОТБОР", band: "from-red-500/0 via-red-700/80 to-red-500/0", fill: "from-white to-red-200", glow: "#ef4444" },
  intercepted: { text: "ПЕРЕХВАТ", band: "from-red-500/0 via-red-700/80 to-red-500/0", fill: "from-white to-red-200", glow: "#ef4444" },
  offside: { text: "ОФСАЙД", band: "from-amber-500/0 via-amber-600/85 to-amber-500/0", fill: "from-white to-amber-200", glow: "#f59e0b" },
  cleared: { text: "ВЫНЕСЛИ", band: "from-red-500/0 via-red-700/80 to-red-500/0", fill: "from-white to-red-200", glow: "#ef4444" },
  blocked: { text: "БЛОК", band: "from-sky-500/0 via-sky-700/80 to-sky-500/0", fill: "from-white to-sky-200", glow: "#38bdf8" },
};

/** The caption of the outcome: a slanted band across the screen and the
 * word flying in big over it (the goal with a jolt). */
export function OutcomeCaption({ outcome }: { outcome: OneOnOneOutcome | null }) {
  const c = outcome ? CAPTION[outcome] : null;
  const big = outcome === "goal" || outcome === "save";
  return (
    <AnimatePresence>
      {c && (
        <motion.div
          key={outcome}
          className="pointer-events-none absolute inset-x-0 top-[16%] flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            className={`absolute h-24 w-[140%] -skew-y-3 bg-gradient-to-r ${c.band}`}
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
          />
          <motion.span
            className={`relative bg-gradient-to-b bg-clip-text px-4 font-display font-black italic leading-none tracking-tight text-transparent ${c.fill} ${
              big ? "text-7xl" : "text-4xl"
            }`}
            style={{ WebkitTextStroke: "2px rgba(3,10,20,0.85)", filter: `drop-shadow(0 0 14px ${c.glow}) drop-shadow(0 4px 0 rgba(0,0,0,0.6))` }}
            initial={{ scale: 2.4, opacity: 0, x: -40 }}
            animate={outcome === "goal" ? { scale: [2.4, 0.92, 1.06, 1], opacity: 1, x: 0, rotate: [0, -3, 2, 0] } : { scale: 1, opacity: 1, x: 0 }}
            transition={{ duration: outcome === "goal" ? 0.6 : 0.35, ease: "easeOut" }}
          >
            {c.text}
          </motion.span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
