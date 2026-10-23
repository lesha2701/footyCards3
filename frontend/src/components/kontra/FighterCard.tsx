import { AnimatePresence, motion } from "framer-motion";
import { useRef, useState } from "react";

import { staticUrl } from "@/lib/api";
import type { KontraCard } from "@/types";

import { TIER_LABELS, TIER_RING } from "./kontraMeta";

const EFFECT_ICON: Record<string, string> = {
  stun: "💫", yellow: "🟨", slow: "🐢", shield: "🛡️", taunt: "📣", blind: "🚩", injury: "🩹", haste: "⚡",
};
const LONG_PRESS_MS = 380;

export interface FighterCardProps {
  card: KontraCard | null;
  tier?: string;
  name?: string;
  hp?: number;
  maxHp?: number;
  foe?: boolean;
  alive?: boolean;
  leader?: boolean;
  active?: boolean;
  targeted?: boolean;
  effects?: { code: string; label: string; turns: number }[];
  /** Keeps the hover info on screen for the outermost cards of a row. */
  edge?: "left" | "right";
  onTap?: () => void;
}

/** A big portrait card for the battle and the squad stage: picture
 *  edge to edge, HP bar on the card, effects as small icons. Name,
 *  position and rating show on hover (desktop) or a long press (phone),
 *  so the card itself stays clean. */
export default function FighterCard({
  card, tier, name, hp, maxHp, foe = false, alive = true, leader = false, active = false, targeted = false,
  effects = [], edge, onTap,
}: FighterCardProps) {
  const [info, setInfo] = useState(false);
  const [broken, setBroken] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressed = useRef(false);
  const ring = TIER_RING[tier ?? card?.tier ?? "common"] ?? TIER_RING.common;
  const pct = hp !== undefined && maxHp ? Math.max(0, Math.round((hp * 100) / maxHp)) : null;
  const low = pct !== null && pct < 30;

  const start = () => {
    longPressed.current = false;
    timer.current = setTimeout(() => { longPressed.current = true; setInfo(true); }, LONG_PRESS_MS);
  };
  const stop = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  return (
    <div className="relative">
      <motion.button
        type="button"
        onPointerDown={start}
        onPointerUp={stop}
        onPointerLeave={() => { stop(); setInfo(false); }}
        onMouseEnter={() => setInfo(true)}
        onContextMenu={(e) => e.preventDefault()}
        onClick={() => {
          if (longPressed.current) { longPressed.current = false; setInfo(false); return; }
          onTap?.();
        }}
        animate={{ y: active ? -6 : 0, scale: active ? 1.04 : 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 20 }}
        className={`relative block aspect-[3/4] w-full select-none overflow-hidden rounded-2xl bg-bg-raised ring-2 ${ring} ${
          active ? "shadow-[0_0_18px_rgba(250,204,21,0.55)]" : ""
        } ${alive ? "" : "grayscale"} touch-manipulation`}
        style={{ WebkitTouchCallout: "none" }}
        aria-label={card?.display_name ?? name ?? "Боец"}
      >
        {card?.image_path && !broken ? (
          <img src={staticUrl(card.image_path)} alt="" draggable={false} onError={() => setBroken(true)}
            className="absolute inset-0 h-full w-full object-cover object-top" />
        ) : (
          <span className={`absolute inset-0 flex items-center justify-center bg-gradient-to-b ${foe ? "from-red-900/70 to-bg-base" : "from-emerald-900/70 to-bg-base"} font-display text-xl font-black text-white/70`}>
            {(card?.display_name ?? name ?? "?").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase()}
          </span>
        )}
        <span className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/85 to-transparent" aria-hidden />

        {leader && <span className="absolute left-1/2 top-0.5 -translate-x-1/2 text-sm drop-shadow" aria-label="Лидер">👑</span>}
        {effects.length > 0 && (
          <span className="absolute left-1 top-1 flex flex-col gap-0.5">
            {effects.slice(0, 3).map((e) => (
              <span key={e.code} className="rounded-md bg-black/60 px-0.5 text-[11px] leading-tight" title={e.label}>{EFFECT_ICON[e.code] ?? "•"}</span>
            ))}
          </span>
        )}
        {targeted && (
          <span className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[11px] font-black text-white">◎</span>
        )}
        {!alive && <span className="absolute inset-0 flex items-center justify-center text-2xl">✖</span>}

        {pct !== null && (
          <span className="absolute inset-x-1.5 bottom-1.5 h-1.5 overflow-hidden rounded-full bg-white/20">
            <motion.span
              className={`block h-full rounded-full ${foe ? "bg-red-500" : low ? "bg-amber-400" : "bg-emerald-400"}`}
              initial={false}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.45, ease: "easeOut" }}
            />
          </span>
        )}
      </motion.button>

      <AnimatePresence>
        {info && (
          <motion.div
            className={`pointer-events-none absolute bottom-full z-30 mb-1.5 w-32 rounded-xl ${
              edge === "left" ? "left-0" : edge === "right" ? "right-0" : "left-1/2 -translate-x-1/2"
            } bg-black/90 px-2 py-1.5 text-center shadow-xl ring-1 ring-white/10`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            <p className="truncate text-xs font-bold text-ink-chalk">{card?.display_name ?? name}</p>
            <p className="font-mono text-micro text-ink-mist">
              {card ? `${card.position} · ${card.rating} · ${TIER_LABELS[card.tier] ?? ""}` : TIER_LABELS[tier ?? ""] ?? ""}
            </p>
            {hp !== undefined && maxHp ? <p className="font-mono text-micro text-ink-mist">HP {hp}/{maxHp}</p> : null}
            {effects.map((e) => (
              <p key={e.code} className="text-micro text-amber-300">{EFFECT_ICON[e.code]} {e.label} · {e.turns}</p>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
