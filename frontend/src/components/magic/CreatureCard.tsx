import { motion } from "framer-motion";

import { pngArt, uiArt } from "@/components/magic/art/pngArt";
import { ROMAN } from "@/components/magic/magicMeta";
import type { MagicCreature } from "@/types";

const RACE_BG: Record<string, string> = {
  dawn: "from-sky-700/70 via-sky-900/60 to-amber-700/40",
  ash: "from-red-800/70 via-stone-900/70 to-purple-900/50",
  wild: "from-lime-700/60 via-emerald-900/60 to-stone-800/50",
};
const TIER_GLOW = ["", "", "drop-shadow-[0_0_6px_rgba(96,165,250,0.45)]", "drop-shadow-[0_0_8px_rgba(192,132,252,0.55)]",
  "drop-shadow-[0_0_10px_rgba(251,191,36,0.6)]", "drop-shadow-[0_0_14px_rgba(34,211,238,0.75)]"];

/** A creature card: the creature on its race's colours inside the frame of its tier.
 *  `reveal` shows the card back first and flips it (a fresh pack). `badge` replaces the count. */
export default function CreatureCard({ c, reveal = false, delay = 0, badge, onClick, dim = false }: {
  c: MagicCreature; reveal?: boolean; delay?: number; badge?: string; onClick?: () => void; dim?: boolean;
}) {
  const img = pngArt(`creatures/${c.unit}`);
  const frame = uiArt(`card_frame_${c.tier}`);
  const back = uiArt("card_back");
  const face = (
    <div className="absolute inset-0 [backface-visibility:hidden]">
      <div className={`absolute inset-[7%] rounded-md bg-gradient-to-b ${RACE_BG[c.faction] ?? RACE_BG.wild}`} />
      {img ? <img src={img} alt="" className="absolute inset-x-[12%] top-[14%] h-[52%] w-[76%] object-contain drop-shadow-lg" />
        : <span className="absolute inset-x-0 top-[22%] text-center text-3xl">{c.emoji}</span>}
      {frame && <img src={frame} alt="" className={`pointer-events-none absolute inset-0 h-full w-full ${TIER_GLOW[c.tier]}`} />}
      {uiArt(`emblem_${c.faction}`) && (
        <img src={uiArt(`emblem_${c.faction}`)!} alt="" className="absolute right-[9%] top-[7%] h-[13%] w-auto drop-shadow" />
      )}
      <span className="absolute left-[12%] top-[8%] font-display text-[10px] font-black text-white [text-shadow:0_1px_2px_#000]">{ROMAN[c.tier]}</span>
      <div className="absolute inset-x-[9%] bottom-[9%] flex flex-col items-center rounded bg-black/55 px-0.5 py-0.5">
        <span className="w-full truncate text-center text-[8.5px] font-bold leading-tight text-ink-chalk">{c.name}</span>
        <span className="font-mono text-[9px] leading-tight text-amber-200">{badge ?? `×${c.fighters}`}</span>
      </div>
    </div>
  );
  const Tag = onClick ? motion.button : motion.div;
  return (
    <Tag onClick={onClick} type={onClick ? "button" : undefined}
      initial={reveal ? { rotateY: 180, scale: 0.85, opacity: 0 } : { opacity: 0, y: 8 }}
      animate={reveal ? { rotateY: 0, scale: 1, opacity: 1 } : { opacity: dim ? 0.5 : 1, y: 0 }}
      transition={reveal ? { delay, duration: 0.6, ease: "easeOut" } : { delay }}
      style={{ transformStyle: "preserve-3d" }}
      className={`relative aspect-[5/8] w-full ${onClick ? "active:scale-95" : ""}`}>
      {face}
      {reveal && back && (
        <img src={back} alt="" className="absolute inset-0 h-full w-full [backface-visibility:hidden] [transform:rotateY(180deg)]" />
      )}
    </Tag>
  );
}
