import { oddsColor, pct, rarityLabel, sortedOdds } from "@/lib/packOdds";
import type { Pack } from "@/types";

/** Drop chances as one segmented bar, common → rarest, left to right. */
export function OddsBar({ pack, className = "h-1.5" }: { pack: Pack; className?: string }) {
  return (
    <span className={`flex w-full overflow-hidden rounded-full bg-white/10 ${className}`} aria-hidden>
      {sortedOdds(pack).map((rp) => (
        <span key={rp.rarity} className={oddsColor(pack, rp.rarity)} style={{ width: `${rp.probability * 100}%` }} />
      ))}
    </span>
  );
}

/** Full list of chances, rarest first. */
export function OddsList({ pack }: { pack: Pack }) {
  return (
    <ul className="flex flex-col gap-0.5">
      {sortedOdds(pack)
        .reverse()
        .map((rp) => (
          <li key={rp.rarity} className="flex items-center gap-1.5 text-caption">
            <span className={`h-2 w-2 shrink-0 rounded-full ${oddsColor(pack, rp.rarity)}`} />
            <span className="flex-1 truncate text-ink-mist">{rarityLabel(pack, rp.rarity)}</span>
            <span className="font-mono font-semibold text-ink-chalk">{pct(rp.probability)}</span>
          </li>
        ))}
    </ul>
  );
}
