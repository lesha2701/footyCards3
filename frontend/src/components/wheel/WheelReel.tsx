import { motion } from "framer-motion";

import { IconCard, IconCoin, IconPack } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatPercent, glyphBgClass, prizeLabel, prizeOdds, type WheelTheme } from "@/lib/wheel";
import type { WheelPrize } from "@/types";

export function PrizeGlyph({ prize }: { prize: WheelPrize }) {
  if (prize.prize_type === "coins") return <IconCoin size={26} />;
  if (prize.prize_type === "pack") return <IconPack size={26} />;
  if (prize.prize_type === "card_rarity") return <IconCard size={26} />;
  if (prize.badge?.image_path) return <img decoding="async" src={staticUrl(prize.badge.image_path) ?? undefined} className="h-6 w-6 rounded-full object-cover" />;
  return <span className="text-lg leading-none">{prize.badge?.icon ?? "🏅"}</span>;
}

const THEME: Record<WheelTheme, { frame: string; pointer: string; outline: string }> = {
  regular: { frame: "bg-bg-surface", pointer: "text-accent", outline: "outline-accent" },
  golden: {
    frame: "bg-gradient-to-b from-amber-500/25 via-bg-surface to-bg-surface ring-1 ring-amber-400/40",
    pointer: "text-amber-300",
    outline: "outline-amber-300",
  },
  jackpot: {
    frame: "bg-gradient-to-b from-fuchsia-500/30 via-amber-500/15 to-bg-surface ring-2 ring-fuchsia-400/50",
    pointer: "text-fuchsia-300",
    outline: "outline-fuchsia-300",
  },
};

const CHIP_WIDTH = 88;

/** The horizontal prize strip used by «Колесо фортуны» and by the «21»
 * reward wheels. The parent owns centerIndex: to spin, bump it a few loops
 * past the won prize's index while `spinning` is true, wait WHEEL_SPIN_MS,
 * then snap it back modulo prizes.length with spinning=false. */
export function WheelReel({
  prizes, centerIndex, spinning, theme = "regular",
}: {
  prizes: WheelPrize[];
  centerIndex: number;
  spinning: boolean;
  theme?: WheelTheme;
}) {
  const strip = Array.from({ length: prizes.length * 6 }, (_, i) => prizes[i % prizes.length]);
  const t = THEME[theme];
  return (
    <div className={`relative overflow-hidden rounded-3xl pb-8 pt-12 ${t.frame}`}>
      <div className={`pointer-events-none absolute left-1/2 top-1 z-10 -translate-x-1/2 ${t.pointer}`}>▼</div>
      <motion.div
        className="flex"
        animate={{ x: -centerIndex * CHIP_WIDTH }}
        transition={{ duration: spinning ? 2.4 : 0, ease: [0.12, 0.8, 0.2, 1] }}
        style={{ paddingLeft: "calc(50% - 44px)" }}
      >
        {strip.map((prize, i) => {
          const isCenter = i === centerIndex && !spinning;
          return (
            <div key={i} className="flex shrink-0 flex-col items-center gap-2" style={{ width: CHIP_WIDTH }}>
              <div
                className={`flex h-16 w-16 items-center justify-center rounded-2xl transition-all ${glyphBgClass(prize)} ${
                  isCenter ? `scale-125 outline outline-2 ${t.outline}` : "scale-90 opacity-50"
                }`}
              >
                <PrizeGlyph prize={prize} />
              </div>
            </div>
          );
        })}
      </motion.div>
    </div>
  );
}

/** "Шансы" list, like the drop rates shown for packs. */
export function PrizeOddsList({ prizes, title }: { prizes: WheelPrize[]; title: string }) {
  const odds = prizeOdds(prizes);
  if (!odds.length) return null;
  return (
    <details className="rounded-2xl bg-bg-surface px-4 py-3 text-sm">
      <summary className="cursor-pointer font-display font-bold text-ink-chalk">{title}</summary>
      <ul className="mt-2 flex flex-col gap-1.5">
        {odds.map(({ prize, percent }) => (
          <li key={prize.id} className="flex items-center justify-between gap-3 text-ink-mist">
            <span className="flex items-center gap-2">
              <span className={`flex h-7 w-7 items-center justify-center rounded-lg ${glyphBgClass(prize)} [&_svg]:h-4 [&_svg]:w-4`}>
                <PrizeGlyph prize={prize} />
              </span>
              {prizeLabel(prize)}
            </span>
            <span className="font-mono text-xs text-ink-chalk">{formatPercent(percent)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
