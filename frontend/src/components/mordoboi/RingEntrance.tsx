import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";
import { createPortal } from "react-dom";

import { ENTRANCE_EMOJI, GLOVE_FILTERS } from "@/lib/cosmetics";
import type { MordoboiFighter } from "@/types";

/** Particles per entrance style; a plain spotlight for boxers without one. */
const PARTICLES: Record<string, string[]> = {
  confetti: ["🎊", "🎉", "🎊", "✨", "🎉"],
  spotlight: ["✨", "⭐", "✨"],
  smoke: ["🌫️", "🌫️", "💨", "🌫️"],
  fireworks: ["🎆", "🎇", "🎆", "✨", "🎇"],
  lightning: ["⚡", "⚡", "🌩️", "⚡"],
};

interface Props {
  open: boolean;
  me: MordoboiFighter;
  opponent: MordoboiFighter;
  onDone: () => void;
}

/** «Выход на ринг»: shown once when a bout starts — each boxer walks out
 *  with their nickname, gloves and entrance effect, then «БОКС!». */
export default function RingEntrance({ open, me, opponent, onDone }: Props) {
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(onDone, 3600);
    return () => clearTimeout(t);
  }, [open, onDone]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[60] flex flex-col items-center justify-center gap-6 bg-black/90 p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onDone}
        >
          <Boxer fighter={opponent} from="right" delay={0.1} />
          <motion.p
            className="font-display text-4xl font-black italic text-yellow-400"
            initial={{ scale: 0, rotate: -10 }}
            animate={{ scale: [0, 1.4, 1], rotate: -4 }}
            transition={{ delay: 2.2, duration: 0.5 }}
          >
            БОКС!
          </motion.p>
          <Boxer fighter={me} from="left" delay={1.1} />
          <p className="absolute bottom-8 text-caption text-ink-mist-dim">Нажми, чтобы пропустить</p>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

function Boxer({ fighter, from, delay }: { fighter: MordoboiFighter; from: "left" | "right"; delay: number }) {
  const style = fighter.look?.entrance ?? null;
  const particles = style ? PARTICLES[style] ?? [] : [];
  const dir = from === "left" ? -1 : 1;
  return (
    <motion.div
      className="relative flex w-full max-w-xs items-center gap-3 rounded-3xl bg-white/5 px-4 py-3"
      initial={{ x: 320 * dir, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ delay, type: "spring", stiffness: 140, damping: 16 }}
    >
      {style === "spotlight" && (
        <motion.span
          className="pointer-events-none absolute -top-24 left-1/2 h-40 w-40 -translate-x-1/2 rounded-full bg-yellow-200/20 blur-2xl"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 1, 0.7] }}
          transition={{ delay, duration: 1.2 }}
        />
      )}
      <span className="text-5xl" style={{ filter: fighter.look?.gloves ? GLOVE_FILTERS[fighter.look.gloves] : undefined }}>🥊</span>
      <span className="min-w-0 flex-1">
        {fighter.look?.nickname && (
          <span className="block text-micro font-black uppercase tracking-wider text-yellow-400">«{fighter.look.nickname}»</span>
        )}
        <span className="block truncate font-display text-lg font-bold text-ink-chalk">{fighter.card?.display_name ?? fighter.name}</span>
        <span className="block truncate text-caption text-ink-mist">{fighter.name}</span>
      </span>
      {style && <span className="text-2xl">{ENTRANCE_EMOJI[style]}</span>}
      {particles.map((p, i) => (
        <motion.span
          key={i}
          className="pointer-events-none absolute text-2xl"
          style={{ left: `${10 + i * 18}%`, top: "50%" }}
          initial={{ opacity: 0, y: 0, scale: 0.5 }}
          animate={{ opacity: [0, 1, 0], y: -70 - (i % 2) * 30, scale: [0.5, 1.3, 1] }}
          transition={{ delay: delay + 0.3 + i * 0.1, duration: 1.3 }}
        >
          {p}
        </motion.span>
      ))}
    </motion.div>
  );
}
