import type { ReactNode } from "react";

import { artOf } from "@/lib/gameArt";

/** A game page header: the game's picture large, on a blurred copy of itself, with the
 * title (an <h1>) and an optional line under it; `children` go on the right. Falls back to
 * a plain title when the game has no picture. */
export default function GameHero({ game, title, subtitle, children }: {
  game: string; title: ReactNode; subtitle?: ReactNode; children?: ReactNode;
}) {
  const art = artOf(game);
  if (!art) {
    return (
      <div className="flex items-center gap-2">
        <h1 className="min-w-0 flex-1 font-display text-xl font-bold text-ink-chalk">{title}</h1>
        {children}
      </div>
    );
  }
  return (
    <header className="relative overflow-hidden rounded-3xl bg-bg-surface ring-1 ring-white/10">
      {/* A soft glow of the picture's own colours behind it — the card itself stays the app's surface. */}
      <img src={art} alt="" aria-hidden className="absolute -left-6 top-1/2 h-32 w-32 -translate-y-1/2 rounded-full object-cover opacity-45 blur-2xl" />
      <div className="relative flex items-center gap-3 p-3">
        <img
          src={art}
          alt=""
          className="h-16 w-16 shrink-0 rounded-2xl object-cover shadow-[0_10px_24px_-8px_rgba(0,0,0,0.8)] ring-1 ring-white/20"
        />
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-xl font-bold leading-tight text-ink-chalk">{title}</h1>
          {subtitle && <p className="mt-0.5 text-caption text-ink-mist">{subtitle}</p>}
        </div>
        {children}
      </div>
    </header>
  );
}
