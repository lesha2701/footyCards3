import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

import ShareButton from "@/components/common/ShareButton";
import { staticUrl } from "@/lib/api";
import { BRUTALITY_EMOJI } from "@/lib/cosmetics";
import type { MordoboiBrutality } from "@/types";

/** How each finisher enters the scene: where the prop flies in from, the
 *  cartoon sound and the particles around the victim. Unknown keys fall
 *  back to a plain punch. */
const SCENES: Record<string, { from: "top" | "left" | "below"; sound: string; particles: string[] }> = {
  flick: { from: "left", sound: "ЩЁЛК!", particles: ["⭐", "💫"] },
  fart: { from: "below", sound: "ПФФФРРР!", particles: ["💨", "🤢", "💨"] },
  underpants: { from: "top", sound: "ОПА!", particles: ["😳", "✨"] },
  wet_willy: { from: "left", sound: "ХЛЮП!", particles: ["💦", "😖"] },
  sock: { from: "left", sound: "МФФ!", particles: ["🦨", "💨"] },
  armpit: { from: "left", sound: "ФУУУ!", particles: ["💦", "🤮"] },
  cake: { from: "left", sound: "ШМЯК!", particles: ["🍰", "🍒", "🍰"] },
  diaper: { from: "top", sound: "АГУ!", particles: ["🍼", "👶"] },
  chicken: { from: "below", sound: "КО-КО-КО!", particles: ["🪶", "🥚", "🪶"] },
  clown: { from: "left", sound: "БИП-БИП!", particles: ["🎈", "🎉"] },
  tickle: { from: "left", sound: "ХИ-ХИ-ИК!", particles: ["😂", "🪶", "😂"] },
  bucket: { from: "top", sound: "ПЛЮХ!", particles: ["💧", "🥶", "💧"] },
  lipstick: { from: "left", sound: "ЧМОК!", particles: ["💄", "📸"] },
  baby_song: { from: "below", sound: "БАЮ-БАЙ!", particles: ["🌙", "💤", "⭐"] },
};

const ENTRY = {
  top: { initial: { y: -260, rotate: -20 }, animate: { y: [-260, 0, -12, 0], rotate: [-20, 8, 0] } },
  left: { initial: { x: -260, rotate: -30 }, animate: { x: [-260, 10, 0], rotate: [-30, 15, 0] } },
  below: { initial: { y: 220, scale: 0.4 }, animate: { y: [220, -10, 0], scale: [0.4, 1.3, 1] } },
};

interface Props {
  open: boolean;
  brutality: MordoboiBrutality;
  victimName: string;
  matchId: number;
  onClose: () => void;
}

/** The finisher scene after a «Мордобой» win — shown to the winner right
 *  after applying it and to the beaten side when they open the bout. */
export default function BrutalityShow({ open, brutality, victimName, matchId, onClose }: Props) {
  const scene = SCENES[brutality.style_key] ?? { from: "left" as const, sound: "БАЦ!", particles: ["💥"] };
  const emoji = BRUTALITY_EMOJI[brutality.style_key] ?? brutality.emoji;
  const entry = ENTRY[scene.from];
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[60] flex flex-col items-center justify-center bg-black/85 p-6 text-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.p
            className="font-display text-3xl font-black uppercase tracking-wider text-red-500 drop-shadow-[0_0_14px_rgba(239,68,68,0.7)]"
            initial={{ scale: 3, opacity: 0, rotate: -8 }}
            animate={{ scale: 1, opacity: 1, rotate: -4 }}
            transition={{ type: "spring", stiffness: 300, damping: 12 }}
          >
            {brutality.reflected ? "Каска! 🪖" : "Бруталити!"}
          </motion.p>

          <div className="relative mt-6 flex h-56 w-56 items-center justify-center">
            {/* the victim */}
            <motion.span
              className="text-[96px] leading-none"
              animate={{ rotate: [0, -12, 10, -6, 0], scale: [1, 0.92, 1.05, 1] }}
              transition={{ delay: 0.55, duration: 0.8 }}
            >
              {brutality.reflected ? (brutality.by_me ? "😱" : "😎") : brutality.by_me ? "😵" : "😵‍💫"}
            </motion.span>
            {/* the prop */}
            <motion.span
              className="absolute text-[72px] leading-none"
              style={scene.from === "top" ? { top: -8 } : scene.from === "below" ? { bottom: 0 } : { left: 8 }}
              initial={entry.initial}
              animate={entry.animate}
              transition={{ duration: 0.8, ease: "easeOut" }}
            >
              {brutality.image_path ? (
                <img src={staticUrl(brutality.image_path)} alt="" className="h-24 w-24 rounded-2xl object-cover shadow-xl" />
              ) : (
                emoji
              )}
            </motion.span>
            {/* particles */}
            {scene.particles.map((p, i) => (
              <motion.span
                key={i}
                className="absolute text-3xl"
                initial={{ opacity: 0, x: 0, y: 0, scale: 0.4 }}
                animate={{ opacity: [0, 1, 1, 0], x: (i - 1) * 70, y: -60 - i * 18, scale: [0.4, 1.2, 1] }}
                transition={{ delay: 0.7 + i * 0.12, duration: 1.4, repeat: 1, repeatDelay: 0.4 }}
              >
                {p}
              </motion.span>
            ))}
            <motion.span
              className="absolute -right-4 top-2 rotate-12 rounded-xl bg-yellow-400 px-2 py-1 font-display text-base font-black text-bg-base"
              initial={{ scale: 0 }}
              animate={{ scale: [0, 1.3, 1] }}
              transition={{ delay: 0.75, duration: 0.4 }}
            >
              {scene.sound}
            </motion.span>
          </div>

          <motion.p
            className="mt-4 max-w-xs font-display text-lg font-bold text-ink-chalk"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1 }}
          >
            {brutality.reflected ? brutality.text : brutality.by_me ? `Ты ${brutality.text}` : `Соперник ${brutality.text}`}
          </motion.p>
          <p className="mt-1 text-caption text-ink-mist">
            {brutality.reflected
              ? brutality.by_me ? "Бумеранг! Купи себе Каску в магазине «Стиль»." : `${victimName} такого не ожидал.`
              : brutality.by_me ? `${victimName} это запомнит.` : "Отыграйся — и ответь своим бруталити."} «{brutality.name}»
          </p>
          {brutality.by_me && brutality.bonus_coins > 0 && (
            <p className="mt-1 font-mono text-sm font-bold text-accent-lime">+{brutality.bonus_coins} монет к выигрышу</p>
          )}

          <div className="mt-5 flex w-full max-w-xs flex-col gap-2" onClick={(e) => e.stopPropagation()}>
            {brutality.by_me !== brutality.reflected && <ShareButton kind="mordoboi_win" id={matchId} label="Похвастаться в чате" />}
            <button onClick={onClose} className="rounded-xl bg-white/10 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
              Закрыть
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
