import { AnimatePresence, motion } from "framer-motion";

import EmptyState from "@/components/common/EmptyState";
import { IconCollection } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { BOOST_TYPE_LABELS } from "@/lib/coaches";
import { RARITY_LABELS } from "@/lib/rarity";
import type { ClubCoachCard } from "@/types";

interface Props {
  open: boolean;
  cards: ClubCoachCard[];
  onSelect: (card: ClubCoachCard | null) => void;
  onClose: () => void;
}

export default function ClubCoachCardPickerModal({ open, cards, onSelect, onClose }: Props) {
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
              <p className="font-display text-lg font-bold text-slate-100">Выбери тренера</p>
              <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm text-slate-300">Закрыть</button>
            </div>
            <button
              onClick={() => onSelect(null)}
              className="mb-3 w-full rounded-xl border border-dashed border-white/15 py-2.5 text-xs font-semibold text-ink-mist-dim active:scale-[0.99]"
            >
              Без тренера
            </button>
            {cards.length === 0 ? (
              <EmptyState icon={IconCollection} title="У клуба пока нет тренера" description="Открой клубные паки, чтобы получить тренера" />
            ) : (
              <div className="flex flex-col gap-2">
                {cards.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => onSelect(c)}
                    className="flex items-center gap-3 rounded-xl bg-white/5 p-2.5 text-left active:scale-[0.99]"
                  >
                    <div className="h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-black/40">
                      <img
                        src={staticUrl(c.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                        alt="" className="h-full w-full object-cover"
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-ink-chalk">{c.coach.display_name}</p>
                      <p className="text-[10px] text-ink-mist-dim">{RARITY_LABELS[c.coach.rarity]}</p>
                      <p className="mt-0.5 truncate text-[10px] text-ink-mist">
                        {c.coach.boosts.map((b) => `${BOOST_TYPE_LABELS[b.boost_type]} +${b.magnitude}`).join(" · ")}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
