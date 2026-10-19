import type { ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconClose } from "@/components/icons";
import { useSwipeDownToClose } from "@/lib/useSwipe";

/** A picture-only shop tile for a 2-column grid. A tap opens a bottom
 * sheet with a big picture and everything about the item — name, price,
 * what's inside or the effect, the full description and the buy button.
 * With a mouse, hovering slides the name in over the picture. */
export default function InfoTile({
  visual, name, badge, price, details, action, open, onToggle, accent, dimmed, isNew, shape = "portrait",
}: {
  visual: ReactNode;
  name: string;
  /** Price chip in the bottom-right corner of the picture. */
  price?: ReactNode;
  /** Small corner label on the picture (discount, «ост. 5», ✓). */
  badge?: ReactNode;
  details: ReactNode;
  action?: ReactNode;
  open: boolean;
  onToggle: () => void;
  accent?: "stars" | "selected";
  dimmed?: boolean;
  /** «НОВОЕ» in the top-right corner until the player opens it. */
  isNew?: boolean;
  /** Pack covers are portrait; gift and artifact pictures are square. */
  shape?: "portrait" | "square";
}) {
  const swipeDown = useSwipeDownToClose(onToggle);

  return (
    <>
      <div
        className={`group relative ${shape === "square" ? "aspect-square" : "aspect-[4/5]"} overflow-hidden rounded-2xl bg-bg-surface ${
          accent === "stars" ? "ring-1 ring-amber-400/40" : accent === "selected" ? "ring-2 ring-accent-lime" : "ring-1 ring-white/5"
        }`}
      >
        <button
          onClick={onToggle}
          aria-label={`${name}: подробнее`}
          className={`flex h-full w-full items-center justify-center active:scale-[0.97] ${dimmed ? "opacity-50 grayscale" : ""}`}
        >
          {visual}
        </button>
        {badge && <span className="pointer-events-none absolute left-2 top-2">{badge}</span>}
        {isNew && (
          <span className="pointer-events-none absolute right-2 top-2 rounded-full bg-accent-lime px-1.5 py-0.5 text-micro font-bold text-bg-base">
            НОВОЕ
          </span>
        )}
        {price && (
          <span className="pointer-events-none absolute bottom-2 right-2 rounded-full bg-black/75 px-2 py-0.5 font-mono text-caption font-bold backdrop-blur-sm">
            {price}
          </span>
        )}
        <span className="pointer-events-none absolute inset-x-0 bottom-0 translate-y-full bg-gradient-to-t from-black/90 to-transparent px-2.5 pb-9 pt-6 text-xs font-bold text-white transition-transform group-hover:translate-y-0">
          {name}
        </span>
      </div>

      {open &&
        createPortal(
          <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm sm:items-center sm:p-6" onClick={onToggle}>
            <div
              role="dialog"
              aria-modal="true"
              aria-label={name}
              onClick={(e) => e.stopPropagation()}
              className="safe-bottom flex max-h-[88vh] w-full max-w-md flex-col overflow-hidden rounded-t-3xl bg-bg-surface sm:max-w-sm sm:rounded-3xl"
            >
              <div {...swipeDown} className="relative px-4 pt-3">
                <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/15 sm:hidden" aria-hidden />
                <button
                  onClick={onToggle}
                  aria-label="Закрыть"
                  className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-white/5 text-ink-mist"
                >
                  <IconClose size={16} />
                </button>
                <div className={`mx-auto flex items-center justify-center overflow-hidden rounded-2xl bg-bg-raised ${shape === "square" ? "h-40 w-40" : "h-44 w-36"}`}>
                  {visual}
                </div>
                <p className="mt-3 text-center font-display text-lg font-bold text-ink-chalk">{name}</p>
              </div>
              <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain px-4 pb-2 pt-2">{details}</div>
              {action && <div className="flex flex-col border-t border-white/5 p-4 [&_button]:py-3 [&_button]:text-sm">{action}</div>}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
