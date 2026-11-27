import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { installMusic, isMusicRoute, nextMusicTrack, setMusicRoute } from "@/lib/music";
import { useMusic } from "@/lib/useMusic";

/** Keeps the soundtrack in step with the screen (see `lib/music.ts`) and
 * shows «Сейчас играет» for a few seconds when a new track starts. */
export default function MenuMusic() {
  const { pathname } = useLocation();
  const { track, playing } = useMusic();
  const [shown, setShown] = useState<string | null>(null);
  const announced = useRef<string | null>(null);
  useEffect(() => installMusic(), []);
  useEffect(() => setMusicRoute(isMusicRoute(pathname)), [pathname]);
  useEffect(() => {
    if (!track || !playing || announced.current === track.key + track.url) return;
    announced.current = track.key + track.url;
    setShown(track.title);
    const t = setTimeout(() => setShown(null), 4000);
    return () => clearTimeout(t);
  }, [track, playing]);
  return (
    <AnimatePresence>
      {shown && isMusicRoute(pathname) && (
        <motion.div
          key={shown}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 16 }}
          className="fixed inset-x-0 bottom-24 z-[60] mx-auto flex w-max max-w-[calc(100%-32px)] items-center gap-2 rounded-full border border-white/10 bg-bg-surface/95 py-1.5 pl-3 pr-1.5 text-xs shadow-lg backdrop-blur"
          data-testid="now-playing"
        >
          <span className="animate-pulse">🎵</span>
          <span className="truncate text-ink-mist">
            Сейчас играет: <b className="text-ink-chalk">{shown}</b>
          </span>
          <button
            onClick={() => nextMusicTrack()}
            className="rounded-full bg-white/10 px-2 py-1 font-bold text-ink-chalk active:scale-95"
            aria-label="Следующий трек"
          >
            ⏭
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
