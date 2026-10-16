import { motion } from "framer-motion";
import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

import PlayerCard from "@/components/cards/PlayerCard";
import { IconCoin, IconPack, IconParty } from "@/components/icons";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { Rarity, UserCard } from "@/types";

/** One look for "you got something": tasks, daily rewards, wheel prizes,
 * gifts. Same backdrop, panel, rhythm (icon pops, then the rewards appear
 * one after another), one primary button and a success haptic. A rare
 * reward (legendary/diamond card) gets a rarity-tinted frame and a heavier
 * haptic. Display only — every caller keeps its own claim logic.
 *
 * Staged card reveals (packs, a wheel-won card), league promotions and
 * «Академия» stage-ups stay their own bigger moments. */
export default function RewardModal({
  title,
  subtitle,
  icon,
  hero,
  rarity = null,
  items,
  buttonLabel = "Отлично!",
  onClose,
}: {
  title: string;
  subtitle?: ReactNode;
  /** Small icon in the popping circle (default: confetti). Ignored when `hero` is set. */
  icon?: ReactNode;
  /** A bigger picture in place of the icon (e.g. a collectible gift). */
  hero?: ReactNode;
  /** Highest rarity among the rewards — legendary/diamond get the special frame. */
  rarity?: Rarity | null;
  /** Each entry appears in turn. */
  items: ReactNode[];
  buttonLabel?: string;
  onClose: () => void;
}) {
  const special = rarity === "legendary" || rarity === "diamond";

  useEffect(() => {
    if (special) haptic("heavy");
    hapticNotify("success");
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // Only on open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const frame = rarity === "diamond"
    ? "from-fuchsia-400 via-cyan-300 to-violet-500 shadow-glow-diamond"
    : rarity === "legendary"
      ? "from-amber-400 via-orange-500 to-red-500 shadow-glow-legendary"
      : "from-white/10 to-white/10";

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", damping: 20, stiffness: 300 }}
        className={`w-full max-w-xs rounded-3xl bg-gradient-to-b p-[2px] ${frame}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="max-h-[85vh] overflow-y-auto rounded-[22px] bg-bg-surface p-5 text-center">
          <motion.div
            initial={{ scale: 0.6, rotate: -10 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: "spring", damping: 12, stiffness: 260, delay: 0.1 }}
            className="flex justify-center"
          >
            {hero ?? (
              <span className="flex h-16 w-16 items-center justify-center rounded-full bg-accent-lime/15 text-accent-lime">
                {icon ?? <IconParty size={30} />}
              </span>
            )}
          </motion.div>
          <p className="mt-3 font-display text-lg font-bold text-ink-chalk">{title}</p>
          {subtitle && <p className="mt-0.5 text-xs text-ink-mist">{subtitle}</p>}

          <div className="mt-3 flex flex-col items-center gap-2">
            {items.map((item, i) => (
              <motion.div
                key={i}
                className="flex w-full justify-center"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.25 + i * 0.12, duration: 0.25 }}
              >
                {item}
              </motion.div>
            ))}
          </div>

          <button
            onClick={onClose}
            className="mt-5 w-full rounded-2xl bg-floodlight py-3 font-display text-sm font-bold text-bg-base active:scale-95"
          >
            {buttonLabel}
          </button>
        </div>
      </motion.div>
    </div>,
    document.body,
  );
}

export function RewardCoins({ amount }: { amount: number }) {
  return (
    <p className="flex items-center justify-center gap-1.5 font-mono text-2xl font-bold text-accent-lime">
      +{amount}
      <IconCoin size={20} />
    </p>
  );
}

export function RewardPack({ name }: { name: string }) {
  return (
    <p className="flex items-center justify-center gap-1.5 text-sm font-semibold text-ink-chalk">
      <IconPack size={16} className="text-accent-cyan" />
      Пак «{name}»
    </p>
  );
}

export function RewardCard({ card }: { card: UserCard }) {
  return (
    <div className="w-28">
      <PlayerCard player={card.player} size="sm" stars={card.stars} pathStage={card.path_stage} prestige={card.prestige} animated />
    </div>
  );
}
