import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

import { fetchClub } from "@/api/clubs";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import { IconStar, IconTrophy } from "@/components/icons";

export function ClubPreviewPopup({ clubId, onClose }: { clubId: number | null; onClose: () => void }) {
  const { data: club, isLoading } = useQuery({
    queryKey: ["clubs", "preview", clubId],
    queryFn: () => fetchClub(clubId!),
    enabled: clubId !== null,
  });

  return createPortal(
    <AnimatePresence>
      {clubId !== null && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="safe-bottom w-full max-w-sm rounded-t-3xl border border-white/10 bg-bg-surface p-6 sm:rounded-3xl"
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            {isLoading && <p className="text-sm text-ink-mist">Загрузка...</p>}
            {club && (
              <div className="flex flex-col items-center gap-3 text-center">
                <ClubLogo shape={club.logo_shape} color={club.logo_color} size={64} />
                <p className="font-display text-lg font-bold text-ink-chalk">{club.name}</p>
                <p className="text-xs text-ink-mist-dim">
                  С {new Date(club.founded_at).toLocaleDateString("ru-RU")} · {club.member_count}/11 участников
                </p>
                <div className="flex gap-4 font-mono text-sm font-bold">
                  <span className="flex items-center gap-1 text-accent-lime">
                    <IconTrophy size={14} />
                    {club.cups_count}
                  </span>
                  <span className="flex items-center gap-1 text-accent-cyan">
                    <IconStar size={14} />
                    {club.stars_count}
                  </span>
                </div>
                {club.description && <p className="text-sm text-ink-mist">{club.description}</p>}
              </div>
            )}
            <button
              onClick={onClose}
              className="mt-4 w-full rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95"
            >
              Закрыть
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
