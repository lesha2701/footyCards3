import { AnimatePresence, motion } from "framer-motion";
import { memo, useState } from "react";

import { staticUrl } from "@/lib/api";
import type { KontraUnit } from "@/types";

import { TIER_RING } from "../kontraMeta";
import { EFFECT_ICON, type ShownUnit, type Spot } from "./battleScript";


// Constant keyframes: a re-render must not restart them.
const SHAKE = { x: [0, -7, 6, -4, 2, 0] };
const CRIT_SHAKE = { x: [0, -9, 8, -5, 2, 0], scale: [1, 0.92, 1.04, 1] };
const HEAL_POP = { scale: [1, 1.06, 1] };
const STILL = {};

export interface Pulse { n: number; kind: "hit" | "crit" | "heal" | "block" | "miss" }

interface Props {
  unit: KontraUnit;
  shown: ShownUnit;
  spot: Spot;
  active: boolean;
  targeted: boolean;
  pickable: boolean;
  pulse?: Pulse;
  bossArt?: string;
  onTap?: () => void;
}

/** A fighter standing on the pitch: the card as a portrait «fishka» with a
 *  ground shadow, HP bar, effect auras and reactions to hits. */
function Token({ unit, shown, spot, active, targeted, pickable, pulse, bossArt, onTap }: Props) {
  const [broken, setBroken] = useState(false);
  const boss = unit.role === "boss";
  const foe = unit.side === "foe";
  const pct = Math.max(0, Math.min(100, Math.round((shown.hp * 100) / Math.max(1, unit.max_hp))));
  const has = (code: string) => shown.effects.some((e) => e.code === code);
  const ring = TIER_RING[unit.tier] ?? TIER_RING.common;
  const img = boss ? bossArt : unit.card?.image_path && !broken ? staticUrl(unit.card.image_path) : undefined;
  const initials = (unit.card?.display_name ?? unit.name).split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const shake = pulse && (pulse.kind === "hit" || pulse.kind === "crit");

  return (
    <div
      className="pointer-events-auto absolute"
      style={{ left: `${spot.x}%`, top: `${spot.y}%`, width: `${spot.w}%`, transform: "translate(-50%, -50%)", zIndex: Math.round(spot.y) }}
    >
      {/* ground: shadow, active halo, taunt pulse, target reticle */}
      <div className="pointer-events-none absolute left-1/2 top-[92%] h-[22%] w-[120%] -translate-x-1/2 rounded-[50%] bg-black/45 blur-[2px]" />
      {active && (
        <div className="pointer-events-none absolute left-1/2 top-[92%] h-[26%] w-[135%] -translate-x-1/2 rounded-[50%] border-2 border-amber-300 shadow-[0_0_18px_rgba(252,211,77,0.8)]">
          <div className="kontra-pulse-ring absolute inset-0 rounded-[50%] border-2 border-amber-300" />
        </div>
      )}
      {has("taunt") && shown.alive && (
        <div className="pointer-events-none absolute left-1/2 top-[90%] h-[30%] w-[150%] -translate-x-1/2">
          <div className="kontra-pulse-ring absolute inset-0 rounded-[50%] border-2 border-red-500/80" />
        </div>
      )}

      <motion.button
        type="button"
        onClick={onTap}
        disabled={!onTap}
        className={`relative block w-full touch-manipulation select-none ${shown.alive ? "" : "pointer-events-none"}`}
        style={{ WebkitTouchCallout: "none" }}
        aria-label={unit.card?.display_name ?? unit.name}
        animate={shown.alive ? { y: active ? -8 : 0, rotate: 0, opacity: 1 } : { y: 6, rotate: foe ? -14 : 14, opacity: 0.55 }}
        transition={{ type: "spring", stiffness: 260, damping: 18 }}
      >
        <div className={shown.alive && !active ? "kontra-bob" : ""} style={{ animationDelay: `${(spot.x % 7) * 0.17}s` }}>
          <motion.div
            key={pulse ? `p${pulse.n}` : "idle"}
            animate={shake ? (pulse?.kind === "crit" ? CRIT_SHAKE : SHAKE) : pulse?.kind === "heal" ? HEAL_POP : STILL}
            transition={{ duration: 0.38 }}
            className={`relative overflow-hidden ${boss ? "aspect-square rounded-[28%]" : "aspect-[3/4] rounded-xl"} bg-bg-raised ring-2 ${boss ? "ring-red-500/90 shadow-[0_0_40px_rgba(239,68,68,0.55)]" : ring} ${
              shown.alive ? "" : "grayscale"
            } ${targeted ? "shadow-[0_0_0_3px_rgba(239,68,68,0.9)]" : pickable ? "shadow-[0_0_14px_rgba(248,113,113,0.55)]" : ""}`}
          >
            {img ? (
              <img src={img} alt="" draggable={false} onError={() => setBroken(true)}
                className={`absolute inset-0 h-full w-full object-cover ${boss ? "" : "object-top"}`} />
            ) : (
              <span className={`absolute inset-0 flex items-center justify-center bg-gradient-to-b ${foe ? "from-red-900/80 to-bg-base" : "from-emerald-800/80 to-bg-base"} font-display text-lg font-black text-white/75`}>
                {boss ? "👹" : initials}
              </span>
            )}
            <span className="absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-black/85 to-transparent" />
            {!boss && unit.card && (
              <span className="absolute left-0.5 top-0.5 rounded bg-black/60 px-1 font-mono text-[9px] font-bold leading-tight text-white">{unit.card.position}</span>
            )}
            {!boss && unit.card && (
              <span className="absolute bottom-0.5 right-1 font-mono text-[10px] font-black text-white drop-shadow">{unit.card.rating}</span>
            )}
            {has("slow") && <span className="absolute inset-0 bg-sky-500/25 mix-blend-screen" />}
            {has("yellow") && <span className="absolute right-0.5 top-0.5 h-3.5 w-2.5 rotate-12 rounded-[2px] bg-yellow-300 shadow" />}
            {/* white flash on a hit */}
            {shake && (
              <motion.span key={`f${pulse!.n}`} className="absolute inset-0 bg-white" initial={{ opacity: 0.85 }} animate={{ opacity: 0 }} transition={{ duration: 0.3 }} />
            )}
            {pulse?.kind === "heal" && (
              <motion.span key={`h${pulse.n}`} className="absolute inset-0 bg-emerald-300" initial={{ opacity: 0.6 }} animate={{ opacity: 0 }} transition={{ duration: 0.5 }} />
            )}
          </motion.div>

          {/* shield bubble */}
          <AnimatePresence>
            {has("shield") && shown.alive && (
              <motion.span
                className="pointer-events-none absolute -inset-[9%] rounded-[40%] border-2 border-cyan-300/80 bg-cyan-300/10 shadow-[0_0_16px_rgba(103,232,249,0.6),inset_0_0_14px_rgba(103,232,249,0.4)]"
                initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 1.3, opacity: 0 }}
              />
            )}
          </AnimatePresence>
          {has("haste") && shown.alive && (
            <span className="pointer-events-none absolute -inset-[4%] rounded-xl shadow-[0_0_14px_rgba(250,204,21,0.7)]" />
          )}
        </div>

        {leaderCrown(unit)}
        {has("stun") && shown.alive && (
          <span className="kontra-spin pointer-events-none absolute -top-[18%] left-1/2 -ml-[0.6em] text-base">💫</span>
        )}

        {!shown.alive && (
          <motion.span initial={{ scale: 2.2, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
            className="absolute inset-0 flex items-center justify-center font-display text-2xl font-black text-red-500 drop-shadow-[0_2px_2px_rgba(0,0,0,0.9)]">
            ✖
          </motion.span>
        )}
      </motion.button>

      {/* HP bar + effect chips */}
      {!boss && (
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-black/60 ring-1 ring-white/10">
          <motion.div
            className={`h-full rounded-full ${foe ? "bg-gradient-to-r from-red-600 to-rose-400" : pct < 30 ? "bg-amber-400" : "bg-gradient-to-r from-emerald-500 to-lime-300"}`}
            initial={false} animate={{ width: `${pct}%` }} transition={{ duration: 0.4, ease: "easeOut" }}
          />
        </div>
      )}
      {shown.alive && shown.effects.length > 0 && (
        <div className="pointer-events-none absolute -top-[16%] right-[-6%] flex flex-col gap-0.5">
          {shown.effects.filter((e) => e.code !== "shield" && e.code !== "stun").slice(0, 3).map((e) => (
            <span key={e.code} className="rounded-md bg-black/70 px-0.5 text-[10px] leading-tight">{EFFECT_ICON[e.code] ?? "•"}</span>
          ))}
        </div>
      )}
      {targeted && shown.alive && (
        <>
          <div className="kontra-pulse-ring pointer-events-none absolute -inset-x-[10%] -top-[7%] bottom-[5%] rounded-2xl border-2 border-red-400" />
          <span className="pointer-events-none absolute -top-[30%] left-1/2 -translate-x-1/2 text-sm drop-shadow">🎯</span>
        </>
      )}
    </div>
  );
}

function leaderCrown(unit: KontraUnit) {
  if (!unit.leader) return null;
  return <span className="pointer-events-none absolute -top-[13%] left-1/2 -translate-x-1/2 text-sm drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]" aria-label="Лидер">👑</span>;
}

export default memo(Token);
