import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";

import EmptyState from "@/components/common/EmptyState";
import { IconCollection } from "@/components/icons";
import CardSkillBadge from "@/components/cards/CardSkillBadge";
import PlayerCard from "@/components/cards/PlayerCard";
import { collapseCopies } from "@/lib/person";
import type { UserCard } from "@/types";

interface Props {
  open: boolean;
  title: string;
  cards: UserCard[];
  disabledCardIds?: number[];
  onSelect: (card: UserCard) => void;
  onClose: () => void;
  // Controlled search box, rendered at the top when provided — the parent
  // owns the value and feeds it into its own card-fetching query (server-
  // side search), so cards beyond whatever page size it fetches are still
  // reachable instead of just being cut off.
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  /** Show each copy's skill badge — only where skills have a match effect
   * (Card Arena lineup, tournament squads), never in unrelated mini-games. */
  showSkills?: boolean;
  /** Extra per-card note under the card (e.g. "+2 хим." for this slot). */
  cardNote?: (card: UserCard) => ReactNode;
}

export default function CardPickerModal({
  open, title, cards, disabledCardIds = [], onSelect, onClose, searchValue, onSearchChange, showSkills = false, cardNote,
}: Props) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="safe-bottom max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-t-3xl border border-white/10 bg-bg-base p-5"
            initial={{ y: 100 }}
            animate={{ y: 0 }}
            exit={{ y: 100 }}
            transition={{ type: "spring", damping: 26, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <p className="font-display text-lg font-bold text-slate-100">{title}</p>
              <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm text-slate-300">Закрыть</button>
            </div>
            {onSearchChange && (
              <input
                value={searchValue ?? ""}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="Поиск по имени..."
                className="mb-3 w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
              />
            )}
            {cards.length === 0 ? (
              <EmptyState icon={IconCollection} title="Нет подходящих карточек" description="Открой паки, чтобы получить игроков этой позиции" />
            ) : (
              <div className="grid grid-cols-3 gap-3">
                {/* Identical copies are one tile (×N): picking any of them is the same. */}
                {collapseCopies(cards).map(({ card, count }) => {
                  const playerCard = (
                    <PlayerCard
                      key={card.id}
                      player={card.player}
                      stars={card.stars}
                      pathStage={card.path_stage} prestige={card.prestige} talentOverride={card.talent_override}
                      size="sm"
                      badge={showSkills ? <CardSkillBadge code={card.skill_code} level={card.skill_level} /> : undefined}
                      dimmed={disabledCardIds.includes(card.id)}
                      onClick={() => !disabledCardIds.includes(card.id) && onSelect(card)}
                    />
                  );
                  const note = cardNote?.(card);
                  if (note == null && count < 2) return playerCard;
                  return (
                    <div key={card.id} className="relative flex flex-col items-center gap-1">
                      {playerCard}
                      {count > 1 && (
                        <span className="absolute right-1 top-1 z-10 rounded-full bg-black/80 px-1.5 font-mono text-micro font-bold text-ink-chalk ring-1 ring-white/20">
                          ×{count}
                        </span>
                      )}
                      {note}
                    </div>
                  );
                })}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
