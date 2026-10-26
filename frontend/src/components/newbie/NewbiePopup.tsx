import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";

import type { IconProps } from "@/components/icons";

/** The «Путь дебютанта» popup: one message, one big green button that leads
 * to the next step. */
export default function NewbiePopup({
  open, Icon, kicker, title, text, cta, onCta, busy, error, secondary, onSecondary,
}: {
  open: boolean;
  Icon: (props: IconProps) => JSX.Element;
  kicker?: string;
  title: string;
  text?: ReactNode;
  cta: string;
  onCta: () => void;
  busy?: boolean;
  error?: string | null;
  secondary?: string;
  onSecondary?: () => void;
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="newbie-popup"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[70] flex items-end justify-center bg-black/60 px-4 pb-[calc(1.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-sm sm:items-center"
        >
          <motion.div
            initial={{ y: 40, scale: 0.96 }}
            animate={{ y: 0, scale: 1 }}
            exit={{ y: 40, opacity: 0 }}
            transition={{ type: "spring", damping: 22, stiffness: 260 }}
            className="w-full max-w-sm rounded-3xl bg-bg-surface p-5 text-center shadow-2xl ring-1 ring-accent-lime/25"
          >
            <motion.span
              initial={{ scale: 0.5, rotate: -10 }}
              animate={{ scale: [0.5, 1.15, 1], rotate: [-10, 6, 0] }}
              transition={{ duration: 0.6 }}
              className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-lime/15 text-accent-lime"
            >
              <Icon size={34} />
            </motion.span>
            {kicker && <p className="font-mono text-micro uppercase tracking-wider text-accent-lime">{kicker}</p>}
            <p className="mt-1 font-display text-xl font-bold leading-tight text-ink-chalk">{title}</p>
            {text && <div className="mt-2 text-sm leading-snug text-ink-mist">{text}</div>}
            {error && <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <button
              onClick={onCta}
              disabled={busy}
              className="animate-claim-glow mt-4 w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-60"
            >
              {busy ? "Секунду..." : cta}
            </button>
            {secondary && onSecondary && (
              <button onClick={onSecondary} className="mt-2 w-full py-1.5 text-xs font-semibold text-ink-mist-dim">
                {secondary}
              </button>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
