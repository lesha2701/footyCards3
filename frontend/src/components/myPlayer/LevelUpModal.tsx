import { motion } from "framer-motion";
import { useMemo } from "react";

const COLORS = ["#c6e63a", "#3ed17e", "#38bdf8", "#facc15", "#f472b6", "#ffffff"];

interface Props {
  fromLevel: number;
  toLevel: number;
  points: number;
  /** «Распределить» — close and jump to the attributes. */
  onSpend: () => void;
  onClose: () => void;
}

/** «Уровень N!»: confetti, the points the new levels brought and a button
 * straight to the attributes. Shown once per level (the server remembers). */
export default function LevelUpModal({ fromLevel, toLevel, points, onSpend, onClose }: Props) {
  const confetti = useMemo(
    () =>
      Array.from({ length: 42 }, (_, i) => ({
        id: i,
        x: (Math.random() - 0.5) * 360,
        y: -(160 + Math.random() * 260),
        rotate: Math.random() * 720 - 360,
        color: COLORS[i % COLORS.length],
        delay: Math.random() * 0.25,
        size: 6 + Math.random() * 6,
      })),
    [],
  );
  const gained = toLevel - fromLevel;

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-black/80 px-8"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
      role="dialog"
      aria-label="Новый уровень"
    >
      <div className="pointer-events-none absolute left-1/2 top-1/2">
        {confetti.map((c) => (
          <motion.span
            key={c.id}
            className="absolute block rounded-sm"
            style={{ width: c.size, height: c.size * 0.6, backgroundColor: c.color }}
            initial={{ x: 0, y: 0, rotate: 0, opacity: 1 }}
            animate={{ x: c.x, y: [0, c.y, c.y + 520], rotate: c.rotate, opacity: [1, 1, 0] }}
            transition={{ duration: 2.4, delay: c.delay, ease: "easeOut" }}
          />
        ))}
      </div>

      <motion.div
        className="relative flex w-full max-w-xs flex-col items-center gap-3 rounded-3xl bg-bg-surface p-6 text-center ring-2 ring-accent-lime/60"
        initial={{ scale: 0.6, y: 30 }}
        animate={{ scale: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 220, damping: 16 }}
        onClick={(e) => e.stopPropagation()}
      >
        <motion.span
          className="font-display text-micro font-bold uppercase tracking-[0.3em] text-accent-lime"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
        >
          Новый уровень
        </motion.span>
        <motion.span
          className="font-display text-6xl font-black text-ink-chalk"
          initial={{ scale: 2.2, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.15, type: "spring", stiffness: 260, damping: 12 }}
        >
          {toLevel}
        </motion.span>
        <p className="text-sm text-ink-mist">
          {gained > 1 ? `Сразу +${gained} уровня! ` : ""}Твой игрок стал опытнее.
        </p>
        {points > 0 && (
          <span className="flex flex-col items-center rounded-2xl bg-accent-lime px-6 py-2 text-bg-base">
            <span className="font-display text-3xl font-black leading-none">+{points}</span>
            <span className="mt-1 text-xs font-bold">
              {points === 1 ? "очко" : points < 5 ? "очка" : "очков"} характеристик
            </span>
          </span>
        )}
        <button
          onClick={onSpend}
          className="mt-2 w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-[0.99]"
        >
          Распределить
        </button>
        <button onClick={onClose} className="text-xs text-ink-mist">Позже</button>
      </motion.div>
    </motion.div>
  );
}
