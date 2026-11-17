import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

export interface CoachStep {
  icon: string;
  title: string;
  text: string;
}

/** `fixed`: over the whole screen (a page), else over its positioned parent (the map). */
export default function Coach({ open, steps, onClose, fixed = false }: {
  open: boolean; steps: CoachStep[]; onClose: () => void; fixed?: boolean;
}) {
  const [i, setI] = useState(0);
  const step = steps[Math.min(i, steps.length - 1)];
  const last = i >= steps.length - 1;
  const done = () => {
    setI(0);
    onClose();
  };
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className={`${fixed ? "fixed z-50 bg-black/70" : "absolute z-40 bg-black/45"} inset-0 flex items-end justify-center p-3 pb-28`}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <motion.div
            key={i}
            initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
            className="w-full max-w-sm rounded-3xl bg-gradient-to-b from-indigo-950 to-bg-surface p-4 ring-1 ring-amber-300/40 shadow-2xl"
          >
            <div className="flex items-start gap-3">
              <span className="text-4xl leading-none">{step.icon}</span>
              <div className="min-w-0 flex-1">
                <p className="font-display text-base font-black text-amber-200">{step.title}</p>
                <p className="mt-0.5 text-sm leading-snug text-ink-chalk">{step.text}</p>
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between">
              <span className="flex gap-1">
                {steps.map((_, n) => <span key={n} className={`h-1.5 w-1.5 rounded-full ${n === i ? "bg-amber-300" : "bg-white/20"}`} />)}
              </span>
              <span className="flex gap-2">
                {!last && <button onClick={done} className="px-2 text-xs text-ink-mist">Пропустить</button>}
                <button onClick={() => (last ? done() : setI(i + 1))} className="rounded-xl bg-amber-400 px-4 py-2 text-sm font-bold text-black active:scale-95">
                  {last ? "Понятно!" : "Дальше"}
                </button>
              </span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
