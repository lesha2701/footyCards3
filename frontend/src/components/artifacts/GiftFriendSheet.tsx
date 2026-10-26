import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";

import { fetchFriends } from "@/api/friends";

/** Pick the friend a Stars gift goes to. */
export default function GiftFriendSheet({
  title, note, busy, onPick, onClose,
}: {
  title: string;
  note: string;
  busy: boolean;
  onPick: (friendId: number, friendName: string) => void;
  onClose: () => void;
}) {
  const { data: friends } = useQuery({ queryKey: ["friends"], queryFn: fetchFriends });
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60" onClick={onClose}>
      <motion.div
        initial={{ y: 40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-bg-surface p-5 pb-8"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="font-display text-lg font-bold text-ink-chalk">{title}</p>
        <p className="mb-3 mt-0.5 text-caption text-ink-mist">{note}</p>
        <div className="flex flex-col gap-1.5">
          {friends && friends.friends.length === 0 && (
            <p className="text-xs text-ink-mist-dim">Пока нет друзей — добавь их в профиле.</p>
          )}
          {friends?.friends.map((f) => {
            const name = f.user.first_name ?? f.user.username ?? `Игрок #${f.user.id}`;
            return (
              <button
                key={f.user.id}
                onClick={() => onPick(f.user.id, name)}
                disabled={busy}
                className="rounded-xl bg-white/5 px-3 py-2.5 text-left text-sm text-ink-chalk active:scale-[0.98] disabled:opacity-40"
              >
                {name}
              </button>
            );
          })}
        </div>
        <button onClick={onClose} className="mt-3 w-full text-xs text-ink-mist">
          Отмена
        </button>
      </motion.div>
    </div>
  );
}
