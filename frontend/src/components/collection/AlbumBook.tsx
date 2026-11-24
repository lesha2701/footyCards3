import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

/** The look of the sticker album: a leather cover, paper pages, a gold
 * «СОБРАНО» stamp, numbered slots and stickers that sit a little crooked. */

/** The album's cover: dark green leather, a stitched edge, gold lettering
 * and the overall progress as a gold ribbon. */
export function AlbumCover({ owned, total, completed }: { owned: number; total: number; completed: number }) {
  const pct = total > 0 ? Math.round((owned / total) * 100) : 0;
  return (
    <div
      className="relative overflow-hidden rounded-2xl p-[3px] shadow-[0_12px_30px_rgba(0,0,0,0.45)]"
      style={{ background: "linear-gradient(135deg, #8a6a2a, #f5d77a 30%, #8a6a2a 55%, #e9c25a 80%, #6b4f1c)" }}
      data-testid="album-cover"
    >
      <div
        className="relative overflow-hidden rounded-[14px] px-4 pb-4 pt-5"
        style={{
          background:
            "radial-gradient(120% 90% at 30% 0%, #1f4a35 0%, #0f2a1e 55%, #08170f 100%)",
        }}
      >
        {/* leather grain */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-[0.18] mix-blend-overlay"
          style={{
            backgroundImage:
              "radial-gradient(rgba(255,255,255,0.5) 0.6px, transparent 0.8px), radial-gradient(rgba(0,0,0,0.6) 0.7px, transparent 0.9px)",
            backgroundSize: "5px 5px, 7px 7px",
            backgroundPosition: "0 0, 2px 3px",
          }}
        />
        {/* stitching */}
        <div aria-hidden="true" className="pointer-events-none absolute inset-2 rounded-[10px] border border-dashed border-amber-200/30" />

        <div className="relative flex items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.35em] text-amber-200/70">Victor FC</p>
            <p
              className="font-display text-3xl font-black uppercase leading-none tracking-[0.08em]"
              style={{
                backgroundImage: "linear-gradient(180deg, #fff3c4, #e9c25a 45%, #a07a2c)",
                WebkitBackgroundClip: "text",
                color: "transparent",
                filter: "drop-shadow(0 1px 0 rgba(0,0,0,0.6))",
              }}
            >
              Альбом
            </p>
            <p className="mt-1 text-[11px] text-amber-100/60">
              {completed > 0 ? `Собрано страниц: ${completed}` : "Собери первую страницу целиком"}
            </p>
          </div>
          <div className="text-right">
            <p className="whitespace-nowrap font-display text-2xl font-bold leading-none text-amber-50">
              {owned}
              <span className="text-base font-semibold text-amber-100/50"> / {total}</span>
            </p>
            <p className="mt-1 font-mono text-xs font-bold text-amber-300">{pct}%</p>
          </div>
        </div>

        <div className="relative mt-3 h-2 overflow-hidden rounded-full bg-black/40 ring-1 ring-amber-200/15">
          <div
            className="h-full rounded-full"
            style={{ width: `${pct}%`, background: "linear-gradient(90deg, #a07a2c, #f5d77a, #e9c25a)" }}
          />
        </div>
      </div>
    </div>
  );
}

/** The round gold stamp pressed onto a finished page. */
export function CompleteStamp({ size = 72, className = "" }: { size?: number; className?: string }) {
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
        background: "radial-gradient(circle, rgba(233,194,90,0.18), rgba(233,194,90,0.04) 70%)",
        boxShadow: "0 0 18px rgba(233,194,90,0.35)",
      }}
      data-testid="album-stamp"
    >
      <span
        className="text-center font-display font-black uppercase leading-[1.05] text-amber-300"
        style={{ fontSize: size * 0.16, letterSpacing: "0.08em" }}
      >
        ★<br />Собрано<br />★
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
