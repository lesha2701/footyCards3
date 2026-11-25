import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

import coverArt from "@/assets/album/cover.webp";

/** The look of the sticker album: a leather cover, paper pages, a gold
 * «СОБРАНО» stamp, numbered slots and stickers that sit a little crooked. */

/** The album's cover: an emerald leather cover (art) with the club's V
 * embossed in gold in its shield, and the title and overall progress
 * stamped on the free leather to the right. */
export function AlbumCover({ owned, total, completed }: { owned: number; total: number; completed: number }) {
  const pct = total > 0 ? Math.round((owned / total) * 100) : 0;
  return (
    <div
      className="relative aspect-[5/2] w-full overflow-hidden rounded-2xl shadow-[0_12px_30px_rgba(0,0,0,0.5)]"
      style={{ backgroundImage: `url(${coverArt})`, backgroundSize: "100% 100%" }}
      data-testid="album-cover"
    >
      {/* the club's V, embossed in gold in the shield */}
      <svg
        viewBox="0 0 100 100"
        aria-hidden="true"
        className="absolute left-[18.7%] top-[41%] w-[8.5%] -translate-x-1/2 -translate-y-1/2"
        style={{ filter: "drop-shadow(0 1px 0 rgba(0,0,0,0.7)) drop-shadow(0 -0.5px 0 rgba(255,240,190,0.5))" }}
      >
        <defs>
          <linearGradient id="album-gold" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#fff1b8" />
            <stop offset="0.45" stopColor="#e2b84f" />
            <stop offset="1" stopColor="#9a7326" />
          </linearGradient>
        </defs>
        <line x1="30" y1="28" x2="54" y2="74" stroke="url(#album-gold)" strokeWidth="24" strokeLinecap="round" />
        <circle cx="74" cy="30" r="13" fill="url(#album-gold)" />
      </svg>

      <div className="absolute inset-y-[11%] left-[36%] right-[7%] flex flex-col justify-center">
        <p className="font-mono text-[9px] font-bold uppercase tracking-[0.35em] text-amber-200/75">Victor FC</p>
        <p
          className="font-display text-[clamp(20px,7vw,30px)] font-black uppercase leading-none tracking-[0.06em]"
          style={{
            backgroundImage: "linear-gradient(180deg, #fff3c4, #e9c25a 45%, #a07a2c)",
            WebkitBackgroundClip: "text",
            color: "transparent",
            filter: "drop-shadow(0 1px 0 rgba(0,0,0,0.7))",
          }}
        >
          Альбом
        </p>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-black/45 ring-1 ring-amber-200/20">
          <div
            className="h-full rounded-full"
            style={{ width: `${pct}%`, background: "linear-gradient(90deg, #a07a2c, #f5d77a, #e9c25a)" }}
          />
        </div>
        <p className="mt-1 flex items-baseline justify-between gap-2 text-[10px] text-amber-100/70">
          <span className="truncate">{completed > 0 ? `Собрано страниц: ${completed}` : "Собери первую страницу"}</span>
          <span className="shrink-0 font-mono">
            <b className="text-xs text-amber-50">{owned}</b>/{total} · <b className="text-amber-300">{pct}%</b>
          </span>
        </p>
      </div>
    </div>
  );
}

/** The round gold stamp pressed onto a finished page. */
export function CompleteStamp({
  size = 72, className = "", golden = false,
}: { size?: number; className?: string; golden?: boolean }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { scale: 2.2, opacity: 0, rotate: -30 }}
      animate={{ scale: 1, opacity: 1, rotate: -14 }}
      transition={{ type: "spring", stiffness: 380, damping: 18, delay: 0.15 }}
      className={`pointer-events-none flex items-center justify-center rounded-full ${className}`}
      style={{
        width: size,
        height: size,
        border: "3px double rgba(233,194,90,0.95)",
        background: golden
          ? "radial-gradient(circle, #fff3c4, #e9c25a 55%, #a07a2c)"
          : "radial-gradient(circle, rgba(233,194,90,0.18), rgba(233,194,90,0.04) 70%)",
        boxShadow: golden ? "0 0 26px rgba(252,211,77,0.75)" : "0 0 18px rgba(233,194,90,0.35)",
      }}
      data-testid={golden ? "album-stamp-golden" : "album-stamp"}
    >
      <span
        className={`text-center font-display font-black uppercase leading-[1.05] ${golden ? "text-[#5a3d0a]" : "text-amber-300"}`}
        style={{ fontSize: size * (golden ? 0.15 : 0.16), letterSpacing: "0.08em" }}
      >
        ★<br />{golden ? "Золотая" : "Собрано"}<br />★
      </span>
    </motion.div>
  );
}

/** A page of the album: dark paper with faint ruling. */
export function AlbumPage({ children }: { children: ReactNode }) {
  return (
    <div
      className="relative overflow-hidden rounded-2xl p-3 ring-1 ring-white/5"
      style={{
        backgroundColor: "#111a16",
        backgroundImage:
          "repeating-linear-gradient(0deg, rgba(255,255,255,0.025) 0 1px, transparent 1px 22px), radial-gradient(120% 60% at 50% 0%, rgba(190,242,100,0.06), transparent 70%)",
      }}
    >
      {/* the binding on the left edge */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-0 w-2 bg-gradient-to-r from-black/50 to-transparent" />
      {children}
    </div>
  );
}

/** The slot's printed number, like «07» on a sticker album page. */
export function SlotNumber({ n }: { n: number }) {
  return (
    <span className="pointer-events-none absolute -left-1 -top-1 z-10 rounded-md bg-[#0b120f] px-1 font-mono text-[9px] font-bold leading-[14px] text-amber-200/80 ring-1 ring-amber-200/25">
      {String(n).padStart(2, "0")}
    </span>
  );
}

/** A sticker that sits a little crooked (fixed per player), with a shadow
 * and a curled corner; `fresh` = just got it, so it is pressed in with a
 * little bounce and a «NEW» tag. */
export function Sticker({ seed, fresh, delay = 0, children }: { seed: number; fresh: boolean; delay?: number; children: ReactNode }) {
  const reduce = useReducedMotion();
  const tilt = (((seed * 37) % 7) - 3) * 0.45;
  return (
    <motion.div
      initial={fresh && !reduce ? { scale: 1.45, rotate: tilt - 10, opacity: 0, y: -24 } : false}
      animate={{ scale: 1, rotate: tilt, opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 17, delay }}
      className="relative drop-shadow-[0_6px_8px_rgba(0,0,0,0.55)]"
    >
      {children}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute bottom-0 right-0 h-3 w-3 rounded-tl-md"
        style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.35), rgba(255,255,255,0.05) 50%, transparent 50%)" }}
      />
      {fresh && (
        <span className="absolute -right-1 -top-1 z-10 rounded-md bg-accent-lime px-1 text-[9px] font-black leading-[14px] text-bg-base shadow" data-testid="sticker-new">
          NEW
        </span>
      )}
    </motion.div>
  );
}
