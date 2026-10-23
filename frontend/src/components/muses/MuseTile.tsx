import MuseArt from "@/components/muses/MuseArt";
import type { OpenedMuse } from "@/types";

/** A pack slot that dropped a «Муза» (pack recap grids). */
export default function MuseTile({ opened }: { opened: OpenedMuse }) {
  return (
    <div className="relative">
      <MuseArt muse={opened.muse} className="aspect-[3/4] w-full rounded-2xl" />
      <p className="mt-1 truncate text-center text-caption font-bold text-ink-chalk">{opened.muse.name}</p>
      <p className="truncate text-center text-micro text-pink-300">Муза · {opened.muse.effect_label}</p>
      {opened.is_new && (
        <span className="absolute left-1 top-1 rounded-full bg-accent-green px-1.5 py-0.5 text-micro font-bold text-bg-base">NEW</span>
      )}
      {opened.copies > 1 && (
        <span className="absolute right-1 top-1 rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-micro font-bold text-ink-chalk">
          ×{opened.copies}
        </span>
      )}
    </div>
  );
}
