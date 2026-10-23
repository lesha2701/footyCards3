import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { setActiveMuse, type MuseAlbum } from "@/api/muses";
import MuseArt from "@/components/muses/MuseArt";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

/** «Выбери музу»: the player's own Muses; tapping one makes her the active
 * one (only she gives her bonus). Used by the profile and home cards. */
export default function MusePickerSheet({ album, open, onClose }: { album: MuseAlbum; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const choose = useMutation({
    mutationFn: (museId: number) => setActiveMuse(museId),
    onSuccess: (next) => {
      hapticNotify("success");
      queryClient.setQueryData(["muses"], next);
      queryClient.invalidateQueries({ queryKey: ["my-player"] });
      setError(null);
      onClose();
    },
    onError: (err) => setError(formatGameError(err, "Не получилось выбрать музу")),
  });
  const owned = album.collections.flatMap((c) => c.muses).filter((m) => m.owned);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="safe-bottom flex max-h-[85vh] w-full max-w-md flex-col gap-3 overflow-y-auto rounded-t-3xl border border-white/10 bg-bg-surface p-4"
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            <p className="font-display text-lg font-bold text-ink-chalk">Выбери музу</p>
            <p className="-mt-2 text-xs text-ink-mist">Активной может быть только одна — её бонус и получает «Мой футболист».</p>
            {error && <p className="text-xs text-red-400">{error}</p>}
            <div className="grid grid-cols-3 gap-2">
              {owned.map((muse) => (
                <button
                  key={muse.id}
                  onClick={() => !muse.is_active && choose.mutate(muse.id)}
                  disabled={choose.isPending}
                  className={`relative flex flex-col rounded-2xl p-1 text-left active:scale-95 disabled:opacity-60 ${muse.is_active ? "bg-pink-500/20 ring-2 ring-pink-400" : ""}`}
                >
                  <MuseArt muse={muse} className="aspect-[3/4] w-full rounded-2xl" />
                  <span className="mt-1 truncate text-caption font-semibold text-ink-chalk">{muse.name}</span>
                  <span className="line-clamp-2 text-micro text-accent-lime">{muse.effect_label}</span>
                  {muse.is_active && (
                    <span className="absolute left-2 top-2 rounded-full bg-pink-500 px-1.5 py-0.5 text-micro font-bold text-white">активна</span>
                  )}
                </button>
              ))}
            </div>
            <button onClick={onClose} className="rounded-full bg-white/5 py-2.5 text-xs font-semibold text-ink-mist active:scale-95">
              Закрыть
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
