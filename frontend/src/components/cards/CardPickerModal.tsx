import { AnimatePresence, motion } from "framer-motion";

import EmptyState from "@/components/common/EmptyState";
import PlayerCard from "@/components/cards/PlayerCard";
import type { UserCard } from "@/types";

interface Props {
  open: boolean;
  title: string;
  cards: UserCard[];
  disabledCardIds?: number[];
  onSelect: (card: UserCard) => void;
  onClose: () => void;
}

export default function CardPickerModal({ open, title, cards, disabledCardIds = [], onSelect, onClose }: Props) {
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
            {cards.length === 0 ? (
              <EmptyState icon="🃏" title="Нет подходящих карточек" description="Открой паки, чтобы получить игроков этой позиции" />
            ) : (
              <div className="grid grid-cols-3 gap-3">
                {cards.map((card) => (
                  <PlayerCard
                    key={card.id}
                    player={card.player}
                    size="sm"
                    dimmed={disabledCardIds.includes(card.id)}
                    onClick={() => !disabledCardIds.includes(card.id) && onSelect(card)}
                  />
                ))}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
