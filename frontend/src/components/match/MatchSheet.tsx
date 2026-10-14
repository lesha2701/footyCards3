import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, type ReactNode } from "react";

/**
 * Full-height sheet that slides over the page for a live match, so the match
 * is on screen the moment it starts instead of somewhere below the lineup.
 *
 * It can't be dismissed by tapping the backdrop — while a match is live the
 * only ways out are finishing it or the explicit forfeit inside `footer`
 * (leaving the page is still covered by matchGuardStore). `onClose` is only
 * offered by the caller once the match is over.
 */
export default function MatchSheet({
  open,
  title,
  headerAside,
  footer,
  children,
}: {
  open: boolean;
  title: string;
  headerAside?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const reduceMotion = useReducedMotion();

  // Lock the page underneath so a swipe inside the sheet doesn't scroll the
  // lineup behind it.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/70"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          role="dialog"
          aria-modal="true"
          aria-label={title}
        >
          <motion.div
            className="flex h-[calc(100dvh-12px-env(safe-area-inset-top))] w-full max-w-lg flex-col rounded-t-3xl border border-white/10 bg-bg-base"
            initial={reduceMotion ? false : { y: "100%" }}
            animate={{ y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { y: "100%" }}
            transition={{ type: "spring", damping: 28, stiffness: 260 }}
          >
            <div className="flex shrink-0 flex-col items-center px-4 pt-2">
              <span className="h-1 w-10 rounded-full bg-white/10" />
              <div className="mt-2 flex w-full items-center justify-between gap-2">
                <p className="font-display text-base font-bold text-ink-chalk">{title}</p>
                {headerAside}
              </div>
            </div>
            <div className="flex min-h-0 flex-1 flex-col px-4 pt-3">{children}</div>
            {footer && (
              <div className="shrink-0 px-4 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3">{footer}</div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
