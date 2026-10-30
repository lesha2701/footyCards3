import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { fetchMyPlayerGiftOptions, fetchMyPlayerGifts, type MyPlayerGiftFriend } from "@/api/myPlayer";
import { formatGameError } from "@/lib/errors";
import { CELEBRATION_EMOJI, WALKOUT_EMOJI } from "@/lib/myPlayer";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { hapticNotify } from "@/lib/telegram";

import PlayerAvatar from "./PlayerAvatar";

const KIND_ICON: Record<string, string> = {
  training: "🏋️", pro: "💎", accessory: "🕶️", background: "🖼️", effect: "✨", hair: "💇", celebration: "🎉", walkout: "🚇", showcase: "🏆",
};

function icon(code: string, kind: string): string {
  const item = code.startsWith("cosmetic:") ? code.slice(9) : code;
  return CELEBRATION_EMOJI[item] ?? WALKOUT_EMOJI[item] ?? KIND_ICON[kind] ?? "🎁";
}

/** «Подарки»: a training, a style item or «Карьера Pro» for a friend's
 * player — Telegram Stars only. Gifts sent make you a «Меценат». */
export default function MyPlayerGifts() {
  const { data } = useQuery({ queryKey: ["my-player", "gifts"], queryFn: fetchMyPlayerGifts });
  const [friend, setFriend] = useState<MyPlayerGiftFriend | null>(null);
  if (!data) return null;
  const patron = data.patron;
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4" data-testid="gifts">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">🎁 Подарки друзьям</h2>
        {patron.name && <span className="rounded-full bg-amber-400/20 px-2.5 py-1 text-micro font-bold text-amber-300">{patron.name}</span>}
      </div>
      <p className="-mt-1 text-caption text-ink-mist">
        Подари игроку друга тренировку, стиль или «Карьеру Pro» — за звёзды.
        {patron.next_at != null && ` Подарено: ${patron.sent}, до ${patron.level ? "следующего уровня" : "статуса «Меценат»"} — ${patron.next_at - patron.sent}.`}
      </p>
      {data.friends.length === 0 ? (
        <p className="text-sm text-ink-mist">Ни у кого из друзей пока нет своего игрока.</p>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {data.friends.map((f) => (
            <button key={f.user_id} onClick={() => setFriend(f)} className="flex w-20 shrink-0 flex-col items-center gap-1 rounded-xl bg-bg-raised p-2">
              <span className="h-12 w-12 overflow-hidden rounded-lg">
                <PlayerAvatar appearance={f.player.appearance} accessory={f.player.accessory} backdrop={f.player.background} className="h-full w-full" />
              </span>
              <span className="w-full truncate text-center text-micro font-semibold text-ink-chalk">{f.user_name}</span>
              <span className="text-micro font-bold text-amber-300">Подарить</span>
            </button>
          ))}
        </div>
      )}
      {data.received.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-micro font-bold uppercase tracking-wide text-ink-mist">Тебе подарили</p>
          {data.received.slice(0, 5).map((g) => (
            <p key={g.id} className="truncate text-caption text-ink-chalk">🎁 {g.name} <span className="text-ink-mist">от {g.from_name}</span></p>
          ))}
        </div>
      )}
      <AnimatePresence>{friend && <GiftSheet friend={friend} onClose={() => setFriend(null)} />}</AnimatePresence>
    </section>
  );
}

function GiftSheet({ friend, onClose }: { friend: MyPlayerGiftFriend; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["my-player", "gifts", friend.user_id], queryFn: () => fetchMyPlayerGiftOptions(friend.user_id) });
  const [busy, setBusy] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const give = async (code: string, name: string) => {
    setError(null);
    setBusy(code);
    try {
      if ((await payMyPlayerWithStars({ purchase: "gift", friendId: friend.user_id, code })) === "paid") {
        hapticNotify("success");
        setDone(name);
        await queryClient.invalidateQueries({ queryKey: ["my-player", "gifts"] });
      }
    } catch (err) {
      setError(formatGameError(err, "Не получилось подарить"));
    } finally {
      setBusy(null);
    }
  };
  return (
    <motion.div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      exit={{ opacity: 0 }} onClick={onClose}>
      <motion.div className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-bg-surface p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))]"
        initial={{ y: 80 }} animate={{ y: 0 }} onClick={(e) => e.stopPropagation()} data-testid="gift-sheet">
        <p className="font-display text-lg font-bold text-ink-chalk">Подарок для {friend.player_name}</p>
        <p className="text-caption text-ink-mist">Игрок {friend.user_name} · оплата звёздами</p>
        {done ? (
          <div className="mt-4 text-center">
            <p className="text-5xl">🎁</p>
            <p className="mt-2 text-sm text-ink-chalk">Подарено: <b>{done}</b>. Друг получит уведомление!</p>
            <button onClick={onClose} className="mt-3 w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base">Готово</button>
          </div>
        ) : !data ? (
          <p className="mt-4 text-center text-sm text-ink-mist">Загрузка…</p>
        ) : (
          <div className="mt-3 grid grid-cols-2 gap-2">
            {data.options.map((o) => (
              <button key={o.code} disabled={busy !== null} onClick={() => void give(o.code, o.name)}
                className="flex flex-col items-start gap-1 rounded-xl bg-bg-raised p-3 text-left disabled:opacity-50">
                <span className="text-2xl">{icon(o.code, o.kind)}</span>
                <span className="line-clamp-2 text-xs font-semibold text-ink-chalk">{o.name}</span>
                {o.limited && <span className="text-micro text-amber-300">лимитка · {o.limited} шт.</span>}
                <span className="mt-auto rounded-lg bg-amber-400 px-2 py-0.5 text-micro font-bold text-bg-base">{busy === o.code ? "…" : `${o.stars} ⭐`}</span>
              </button>
            ))}
          </div>
        )}
        {error && <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
      </motion.div>
    </motion.div>
  );
}
