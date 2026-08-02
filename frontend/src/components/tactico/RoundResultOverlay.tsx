import { AnimatePresence, motion } from "framer-motion";

import { CATEGORY_POSITIONS } from "@/lib/formation";
import { staticUrl } from "@/lib/api";
import { RARITY_GLOW, RARITY_GRADIENTS } from "@/lib/rarity";
import type { TacticoCard, TacticoRound } from "@/types";

// Mirrors the backend's default tactico_phase_bonus_pct — a display-only
// figure (the server already decided the winner), same simplification the
// rules modal already makes rather than plumbing the admin-tunable value
// through every round payload.
const BONUS_MULT = 1.15;
const BONUS_PCT_LABEL = "+15%";

const PHASE_LABELS: Record<string, { label: string; emoji: string; stat: string }> = {
  attack: { label: "Атакующий эпизод", emoji: "⚔️", stat: "АТК" },
  defense: { label: "Оборонительный эпизод", emoji: "🛡", stat: "ЗЩТ" },
};

const WINNER_LABELS: Record<string, string> = {
  user: "Ты выиграл раунд!",
  opponent: "Соперник выиграл раунд",
  draw: "Ничья — очко не досталось никому",
};

function hasBonus(card: TacticoCard, phase: string): boolean {
  const positions = phase === "attack" ? CATEGORY_POSITIONS.FWD : [...CATEGORY_POSITIONS.GK, ...CATEGORY_POSITIONS.DEF];
  return positions.includes(card.position);
}

function statValue(card: TacticoCard, phase: string): number {
  return phase === "attack" ? card.attack_rating : card.defense_rating;
}

function otherStatValue(card: TacticoCard, phase: string): number {
  return phase === "attack" ? card.defense_rating : card.attack_rating;
}

// The phase sub-stat after the position bonus (never applied to overall rating).
function boostedStat(card: TacticoCard, phase: string): number {
  const raw = statValue(card, phase);
  return hasBonus(card, phase) ? Math.round(raw * BONUS_MULT) : raw;
}

// The single number that actually decides the round: overall rating plus
// the phase-relevant sub-stat (boosted by the position bonus, if any).
function totalValue(card: TacticoCard, phase: string): number {
  return card.rating + boostedStat(card, phase);
}

export default function RoundResultOverlay({ round, onDismiss }: { round: TacticoRound; onDismiss: () => void }) {
  if (!round.user_card || !round.opponent_card) return null;
  const phase = PHASE_LABELS[round.phase];
  const userValue = totalValue(round.user_card, round.phase);
  const opponentValue = totalValue(round.opponent_card, round.phase);

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-5"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onDismiss}
      >
        <motion.div
          className="w-full max-w-sm rounded-3xl border border-white/10 bg-bg-surface p-5 text-center"
          initial={{ scale: 0.85, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          transition={{ type: "spring", damping: 20, stiffness: 260 }}
        >
          <p className="font-display text-sm font-bold text-ink-chalk">
            {phase.emoji} {phase.label}
          </p>

          <div className="mt-4 flex items-center justify-center gap-3">
            <BattleCardTile card={round.user_card} phase={round.phase} won={round.winner === "user"} />
            <span className="font-display text-xs font-bold text-ink-mist-dim">VS</span>
            <BattleCardTile card={round.opponent_card} phase={round.phase} won={round.winner === "opponent"} />
          </div>

          <motion.div
            className="mt-4 flex items-center justify-center gap-3"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
          >
            <span className={`font-mono text-3xl font-black ${round.winner === "user" ? "text-accent-green" : "text-ink-mist-dim"}`}>
              {userValue}
            </span>
            <span className="font-mono text-lg text-ink-mist-dim">:</span>
            <span className={`font-mono text-3xl font-black ${round.winner === "opponent" ? "text-accent-green" : "text-ink-mist-dim"}`}>
              {opponentValue}
            </span>
          </motion.div>
          <p className="text-[10px] text-ink-mist-dim">Итоговый показатель раунда — рейтинг + {phase.stat} с учётом бонуса за позицию</p>

          <motion.p
            className={`mt-3 font-display text-base font-bold ${
              round.winner === "user" ? "text-accent-green" : round.winner === "opponent" ? "text-red-400" : "text-ink-mist"
            }`}
            initial={{ y: 6, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.45 }}
          >
            {round.winner ? WINNER_LABELS[round.winner] : ""}
          </motion.p>

          <p className="mt-2 text-[11px] text-ink-mist-dim">Нажми, чтобы продолжить</p>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function BattleCardTile({ card, phase, won }: { card: TacticoCard; phase: string; won: boolean }) {
  const imageUrl = staticUrl(card.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp");
  const bonus = hasBonus(card, phase);
  const activeLabel = phase === "attack" ? "АТК" : "ЗЩТ";
  const inactiveLabel = phase === "attack" ? "ЗЩТ" : "АТК";
  const raw = statValue(card, phase);
  const boosted = boostedStat(card, phase);
  const inactive = otherStatValue(card, phase);

  return (
    <motion.div
      className={`flex w-28 flex-col overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[card.rarity]} ${
        won ? "shadow-glow-legendary" : RARITY_GLOW[card.rarity]
      } p-[2px]`}
      animate={won ? { scale: [1, 1.06, 1] } : {}}
      transition={{ delay: 0.3, duration: 0.5 }}
    >
      <div className={`flex flex-col overflow-hidden rounded-[14px] bg-bg-surface/90 ${won ? "" : "opacity-70"}`}>
        <div className="relative aspect-[3/4] w-full overflow-hidden">
          <img src={imageUrl} alt={card.display_name} className="h-full w-full object-cover" />
          <span className="absolute right-1 top-1 rounded-md bg-black/60 px-1 py-0.5 font-mono text-[9px] font-bold text-white">
            ★{card.rating}
          </span>
          {bonus && (
            <span className="absolute left-1 top-1 rounded-md bg-accent-lime px-1 py-0.5 font-mono text-[9px] font-bold text-bg-base">
              {BONUS_PCT_LABEL}
            </span>
          )}
        </div>
        <div className="border-t border-white/10 bg-black/30 px-1.5 py-1.5 text-center">
          <p className="truncate font-display text-[10px] font-semibold text-ink-chalk">{card.display_name}</p>
          <p className="mt-0.5 font-mono text-xs font-bold text-accent-cyan">
            {activeLabel} {raw}
            {bonus && <span className="text-accent-lime"> →{boosted}</span>}
          </p>
          <p className="font-mono text-[9px] text-ink-mist-dim">{inactiveLabel} {inactive}</p>
        </div>
      </div>
    </motion.div>
  );
}
