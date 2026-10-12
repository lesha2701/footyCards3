import { AnimatePresence, motion } from "framer-motion";
import { useMemo } from "react";

import { IconCoin, IconTrophy } from "@/components/icons";
import type { StrategoMatch } from "@/types";

import { WIN_REASON_LABELS } from "./strategoMeta";

const CONFETTI_COLORS = ["#22d3c4", "#3ed17e", "#c6e63a", "#8fe3b8", "#ffffff"];
const TITLES: Record<string, string> = { win: "Победа!", draw: "Ничья", loss: "Поражение" };

interface Props {
  match: StrategoMatch | null;
  onClose: () => void;
  onRematch?: () => void;
  onShare?: () => void;
  rematchLabel?: string;
}

/** End-of-match screen: brand-colour confetti and the cup on a win, the
 *  rewards, and quick «Реванш» / «Поделиться» actions. */
export default function VictoryOverlay({ match, onClose, onRematch, onShare, rematchLabel = "Реванш" }: Props) {
  const win = match?.result === "win";
  const pieces = useMemo(
    () => Array.from({ length: 36 }, (_, i) => ({
      left: Math.random() * 100,
      delay: Math.random() * 0.6,
      duration: 1.8 + Math.random() * 1.4,
      size: 5 + Math.random() * 6,
      color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      spin: (Math.random() - 0.5) * 720,
    })),
    [],
  );
  const puzzle = match?.mode === "puzzle";
  const title = puzzle ? (win && match?.win_reason === "cup_captured" ? "Задача решена!" : "Не вышло") : TITLES[match?.result ?? "draw"];

  return (
    <AnimatePresence>
      {match && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-black/75 px-6 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          {win && pieces.map((p, i) => (
            <motion.span
              key={i}
              className="pointer-events-none absolute top-0 rounded-sm"
              style={{ left: `${p.left}%`, width: p.size, height: p.size * 0.5, background: p.color }}
              initial={{ y: -20, rotate: 0, opacity: 1 }}
              animate={{ y: "105vh", rotate: p.spin, opacity: [1, 1, 0.6] }}
              transition={{ delay: p.delay, duration: p.duration, ease: "easeIn" }}
            />
          ))}
          <motion.div
            className="relative flex w-full max-w-sm flex-col items-center gap-2 rounded-3xl border border-white/10 bg-bg-surface p-6 text-center shadow-glow"
            initial={{ scale: 0.8, y: 30 }}
            animate={{ scale: 1, y: 0 }}
            transition={{ type: "spring", damping: 18, stiffness: 260 }}
          >
            <motion.span
              className={`flex h-16 w-16 items-center justify-center rounded-full ${win ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-mist"}`}
              initial={{ rotate: -20, scale: 0 }}
              animate={{ rotate: 0, scale: 1 }}
              transition={{ delay: 0.15, type: "spring", damping: 10 }}
            >
              <IconTrophy size={30} />
            </motion.span>
            <p className={`font-display text-2xl font-bold ${win ? "text-accent-lime" : match.result === "loss" ? "text-red-400" : "text-ink-chalk"}`}>
              {title}
            </p>
            {match.win_reason && <p className="text-xs text-ink-mist">{WIN_REASON_LABELS[match.win_reason]}</p>}
            <div className="mt-1 flex items-center gap-3 text-sm font-bold text-ink-chalk">
              <span className="flex items-center gap-1"><IconCoin size={14} /> +{match.reward_coins}</span>
              {match.mode === "normal" && match.opponent_type !== "friend" && (
                <span className={match.rating_delta >= 0 ? "text-accent-green" : "text-red-400"}>
                  Рейтинг {match.rating_delta >= 0 ? "+" : ""}{match.rating_delta}
                </span>
              )}
            </div>
            {match.my_player_xp > 0 && <p className="text-[11px] text-accent-lime">Мой игрок: +{match.my_player_xp} опыта</p>}
            <div className="mt-3 flex w-full flex-col gap-2">
              {onRematch && (
                <button onClick={onRematch} className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95">
                  {rematchLabel}
                </button>
              )}
              {onShare && win && (
                <button onClick={onShare} className="rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-chalk active:scale-95">
                  Поделиться в чат
                </button>
              )}
              <button onClick={onClose} className="py-2 text-xs text-ink-mist">Посмотреть поле</button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
