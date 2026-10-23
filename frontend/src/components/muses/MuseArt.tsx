import type { Muse } from "@/api/muses";
import { staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS } from "@/lib/rarity";

/** A Muse portrait in her rarity frame: the uploaded photo, or her emoji
 * on a soft gradient until the admin uploads one. `locked` = not owned yet
 * (album silhouette). */
export default function MuseArt({
  muse,
  locked = false,
  className = "",
  iconClass = "text-5xl",
}: {
  muse: Pick<Muse, "name" | "icon" | "image_path" | "rarity">;
  locked?: boolean;
  className?: string;
  iconClass?: string;
}) {
  return (
    <span className={`block bg-gradient-to-b p-[2px] ${locked ? "from-white/15 to-white/5" : RARITY_GRADIENTS[muse.rarity]} ${className}`}>
      <span className="relative flex h-full w-full items-center justify-center overflow-hidden rounded-[14px] bg-bg-base">
        <span className="absolute inset-0 bg-gradient-to-b from-pink-500/15 to-transparent" aria-hidden />
        {muse.image_path ? (
          <img
            src={staticUrl(muse.image_path)}
            alt={muse.name}
            loading="lazy"
            decoding="async"
            className={`relative h-full w-full object-cover ${locked ? "opacity-25 grayscale" : ""}`}
          />
        ) : (
          <span className={`relative leading-none ${iconClass} ${locked ? "opacity-25 grayscale" : ""}`} aria-hidden>
            {muse.icon}
          </span>
        )}
        {locked && <span className="absolute font-display text-2xl font-bold text-ink-mist-dim">?</span>}
      </span>
    </span>
  );
}
