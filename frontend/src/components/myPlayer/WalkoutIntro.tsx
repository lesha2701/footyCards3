import { motion } from "framer-motion";
import { useEffect, useRef } from "react";

import type { MyPlayer } from "@/api/myPlayer";
import { WALKOUT_EMOJI } from "@/lib/myPlayer";

import PlayerAvatar from "./PlayerAvatar";

const LABEL: Record<string, string> = {
  walk_tunnel: "Выход из тоннеля", walk_flags: "Коридор флагов", walk_smoke: "Дым и прожекторы",
  walk_fireworks: "Фейерверк", walk_legend: "Выход легенды",
};
// Backdrop of each walk-out.
const SCENE: Record<string, string> = {
  walk_tunnel: "from-zinc-900 via-zinc-800 to-black",
  walk_flags: "from-red-900 via-bg-base to-blue-900",
  walk_smoke: "from-slate-700 via-slate-900 to-black",
  walk_fireworks: "from-indigo-900 via-fuchsia-900 to-black",
  walk_legend: "from-amber-500 via-yellow-900 to-black",
};
const DURATION_MS = 1600;

/** «Выход на поле»: a short full-screen walk-out of the player's
 * footballer before a key moment or a duel. Tap skips it. */
export default function WalkoutIntro({ player, onDone }: { player: MyPlayer; onDone: () => void }) {
  const code = player.walkout ?? "walk_tunnel";
  // The latest callback, so a parent re-render doesn't restart the timer.
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    const timer = setTimeout(() => done.current(), DURATION_MS);
    return () => clearTimeout(timer);
  }, []);
  const sparks = code === "walk_fireworks" || code === "walk_legend";
  return (
    <motion.div
      className={`fixed inset-0 z-[60] flex flex-col items-center justify-center overflow-hidden bg-gradient-to-b ${SCENE[code] ?? SCENE.walk_tunnel}`}
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={() => done.current()}
      data-testid="walkout"
    >
      {code === "walk_smoke" && (
        <motion.div
          className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-white/40 to-transparent blur-2xl"
          initial={{ opacity: 0, y: 60 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1 }}
        />
      )}
      {code === "walk_flags" && (
        <div className="absolute inset-y-0 left-0 right-0 flex justify-between px-4">
          {[0, 1].map((side) => (
            <motion.div key={side} className="flex flex-col justify-center gap-4 text-4xl"
              initial={{ x: side ? 40 : -40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.6 }}>
              <span>🚩</span><span>🚩</span><span>🚩</span>
            </motion.div>
          ))}
        </div>
      )}
      {sparks && Array.from({ length: 10 }, (_, i) => (
        <motion.span
          key={i}
          className="absolute text-2xl"
          style={{ left: `${8 + i * 9}%`, top: `${12 + ((i * 37) % 40)}%` }}
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: [0, 1.4, 0], opacity: [0, 1, 0] }}
          transition={{ duration: 1.2, delay: (i % 5) * 0.12 }}
        >
          {code === "walk_legend" ? "✨" : "🎆"}
        </motion.span>
      ))}
      <motion.div
        className="relative h-56 w-48"
        initial={{ y: 120, scale: 0.6, opacity: 0 }}
        animate={{ y: 0, scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 120, damping: 14 }}
      >
        <PlayerAvatar appearance={player.appearance} number={player.number} accessory={player.accessory} backdrop={player.background}
          country={player.country} className="h-full w-full drop-shadow-[0_10px_30px_rgba(0,0,0,0.7)]" />
      </motion.div>
      <motion.p
        className={`mt-4 font-display text-2xl font-black ${code === "walk_legend" ? "text-amber-300" : "text-ink-chalk"}`}
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}
      >
        {WALKOUT_EMOJI[code] ?? "🏟️"} {player.name} #{player.number}
      </motion.p>
      <motion.p className="mt-1 text-caption text-ink-mist" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.55 }}>
        {LABEL[code] ?? "Выход на поле"}
      </motion.p>
    </motion.div>
  );
}
