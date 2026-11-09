/** A setting folded into one line: the name and what stands there now. Stays
 * mounted once opened, so a half-edited card survives folding. */
import { type ReactNode, useState } from "react";

import { IconChevronRight } from "@/components/icons";
import { haptic } from "@/lib/telegram";

export function FoldCard({ title, status, children }: { title: string; status: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [touched, setTouched] = useState(false);
  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => { setOpen(!open); setTouched(true); haptic("light"); }}
        className="flex items-center justify-between gap-3 rounded-2xl bg-bg-surface px-4 py-3 text-left active:scale-[0.99]"
      >
        <span className="font-display text-sm font-bold text-ink-chalk">{title}</span>
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate text-caption text-ink-mist">{status}</span>
          <IconChevronRight size={14} aria-hidden="true" className={`shrink-0 text-ink-mist-dim transition-transform ${open ? "rotate-90" : ""}`} />
        </span>
      </button>
      {touched && <div hidden={!open} className="flex flex-col gap-3 [&[hidden]]:hidden">{children}</div>}
    </>
  );
}
