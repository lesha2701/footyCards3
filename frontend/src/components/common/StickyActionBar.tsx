import type { ReactNode } from "react";

/** Keeps a screen's main action (start / play / send) on screen: it sticks
 * to the bottom, just above the bottom navigation, while the page scrolls
 * — what Telegram's native MainButton gave, but drawn by us so it can never
 * go missing. A soft fade behind it keeps the content underneath readable. */
export default function StickyActionBar({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`sticky z-30 -mx-4 bg-gradient-to-t from-bg-base via-bg-base/95 to-transparent px-4 pb-2 pt-4 ${className}`}
      style={{ bottom: "calc(4.4rem + env(safe-area-inset-bottom, 0px))" }}
    >
      {children}
    </div>
  );
}
