import type { ReactNode } from "react";

/** A section heading of «Менеджер» with its art as a small glossy icon. */
export default function SectionTitle({ art, children, size = 40 }: { art: string; children: ReactNode; size?: number }) {
  return (
    <span className="flex min-w-0 items-center gap-2.5">
      <img src={art} alt="" width={size} height={size} className="shrink-0 rounded-xl shadow-[0_4px_14px_-4px_rgba(0,0,0,0.7)] ring-1 ring-white/10" />
      <span className="min-w-0 font-display text-base font-bold text-ink-chalk">{children}</span>
    </span>
  );
}
