import type { ReactNode } from "react";

/** Keeps a screen's main action (start / play / send) on screen: it sticks
 * to the bottom, just above the bottom navigation, while the page scrolls
 * — what Telegram's native MainButton gave, but drawn by us so it can never
 * go missing. Its strip is solid, so nothing underneath shows through. */
export default function StickyActionBar({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`sticky z-30 -mx-4 border-t border-white/5 bg-bg-base px-4 py-2 ${className}`}
      style={{ bottom: "calc(4.4rem + env(safe-area-inset-bottom, 0px))" }}
    >
      {children}
    </div>
  );
}
