import { animate, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

import { IconGlobe } from "@/components/icons";
import type { Stage } from "@/components/cards/revealStages";
import { countryFlagUrl } from "@/lib/countryFlags";
import { POSITION_LABELS, RARITY_LABELS } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { Player } from "@/types";

const TONE = {
  legendary: { beam: "rgba(251,191,36,0.85)", glow: "rgba(251,191,36,0.35)", text: "text-amber-300" },
  diamond: { beam: "rgba(103,232,249,0.85)", glow: "rgba(192,132,252,0.35)", text: "text-cyan-200" },
} as const;

/** The legendary/diamond «выход», one scene per stage before the card
 * turns over: the lights go down and a beam of the card's colour comes up,
 * then its rarity, the flag, the position and the rating counting up.
 * No club crest anywhere — only what the player is. The page remounts
 * this per stage, so each scene plays its entrance once. */
export default function LegendWalkout({ player, stage }: { player: Player; stage: Stage }) {
  const tone = player.rarity === "diamond" ? TONE.diamond : TONE.legendary;
  const reduce = useReducedMotion();

  // Warm the flag up while the lights are still down.
  useEffect(() => {
    const url = countryFlagUrl(player.country);
    if (url && stage === "position") new Image().src = url;
  }, [player.country, stage]);

  useEffect(() => {
    if (stage === "rarity" || stage === "country" || stage === "club") haptic("medium");
  }, [stage]);

  return (
    <div className="relative flex w-full flex-1 flex-col items-center justify-center" data-testid="legend-walkout">
      <WalkoutBackdrop rarity={player.rarity} dim={stage === "position"} rise={stage === "position"} />

      <div className="flex min-h-[260px] flex-col items-center justify-center gap-3 px-6 text-center">
        {stage === "position" && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 1, 0.6, 1] }}
            transition={{ duration: 1.2, delay: 0.3 }}
            className="font-display text-sm font-bold uppercase tracking-[0.4em] text-ink-mist"
          >
            Кто-то выходит…
          </motion.p>
        )}

        {stage === "rarity" && (
          <motion.p
            initial={reduce ? false : { opacity: 0, scale: 1.8, letterSpacing: "0.6em" }}
            animate={{ opacity: 1, scale: 1, letterSpacing: "0.04em" }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className={`max-w-full break-words font-display text-[clamp(22px,8vw,40px)] font-black uppercase leading-tight ${tone.text} drop-shadow-[0_0_24px_currentColor]`}
          >
            {RARITY_LABELS[player.rarity]}
          </motion.p>
        )}

        {stage === "country" && <CountryScene country={player.country} />}

        {stage === "club" && (
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
            className="flex flex-col items-center gap-2"
          >
            <span className={`font-display text-7xl font-black ${tone.text} drop-shadow-[0_0_20px_currentColor]`}>
              {player.position}
            </span>
            <span className="text-sm font-semibold uppercase tracking-[0.2em] text-ink-chalk">
              {POSITION_LABELS[player.position] ?? player.position}
            </span>
          </motion.div>
        )}

        {stage === "silhouette" && <RatingCount rating={player.rating} toneClass={tone.text} />}
      </div>

      <p className="text-xs text-ink-mist-dim">Нажми, чтобы продолжить</p>
    </div>
  );
}

/** The dark stage and the beam, also kept behind the card once it turns. */
export function WalkoutBackdrop({ rarity, dim = false, rise = false }: { rarity: Player["rarity"]; dim?: boolean; rise?: boolean }) {
  const tone = rarity === "diamond" ? TONE.diamond : TONE.legendary;
  const reduce = useReducedMotion();
  const beamStrength = dim ? 0.55 : 1;
  return (
    <>
      {/* The lights go down over the whole page (under its skip button). */}
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 bg-black/95" />
      {/* The beam: a column of light from the floor, wider at the top. */}
      <motion.div
        aria-hidden="true"
        initial={reduce || !rise ? false : { scaleY: 0, opacity: 0 }}
        animate={{ scaleY: 1, opacity: beamStrength }}
        transition={{ duration: 1.1, ease: "easeOut" }}
        className="pointer-events-none fixed bottom-0 left-1/2 -z-10 h-[85%] w-56 origin-bottom blur-xl"
        style={{
          x: "-50%",
          background: `linear-gradient(to top, ${tone.beam}, ${tone.glow} 55%, transparent)`,
          clipPath: "polygon(38% 100%, 62% 100%, 100% 0, 0 0)",
        }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none fixed bottom-[-60px] left-1/2 -z-10 h-40 w-80 -translate-x-1/2 rounded-full blur-3xl"
        style={{ background: tone.beam, opacity: beamStrength * 0.6 }}
      />
      {!reduce && <Dust />}
    </>
  );
}

function CountryScene({ country }: { country: string }) {
  const reduce = useReducedMotion();
  const flag = countryFlagUrl(country);
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, scale: 0.6, rotate: -8 }}
      animate={{ opacity: 1, scale: 1, rotate: 0 }}
      transition={{ type: "spring", stiffness: 260, damping: 16 }}
      className="flex flex-col items-center gap-3"
    >
      {flag ? (
        <img
          src={flag}
          alt=""
          className="h-24 w-32 rounded-lg object-cover shadow-[0_8px_40px_rgba(255,255,255,0.25)] ring-1 ring-white/20"
          data-testid="walkout-flag"
        />
      ) : (
        <IconGlobe size={88} className="text-ink-chalk" />
      )}
      <span className="font-display text-2xl font-bold uppercase tracking-[0.15em] text-ink-chalk">{country}</span>
    </motion.div>
  );
}

/** The rating runs up to its value, the phone buzzing harder as it climbs. */
function RatingCount({ rating, toneClass }: { rating: number; toneClass: string }) {
  const reduce = useReducedMotion();
  const from = Math.max(0, rating - 25);
  const [shown, setShown] = useState(reduce ? rating : from);

  useEffect(() => {
    if (reduce) {
      haptic("heavy");
      return;
    }
    let lastTick = from;
    const controls = animate(from, rating, {
      duration: 0.9,
      ease: "easeIn",
      onUpdate: (v) => {
        const n = Math.round(v);
        setShown(n);
        if (n - lastTick >= 5 && n < rating) {
          lastTick = n;
          haptic(n > rating - 10 ? "medium" : "light");
        }
      },
      onComplete: () => {
        haptic("heavy");
        hapticNotify("success");
      },
    });
    return () => controls.stop();
  }, [from, rating, reduce]);

  const done = shown >= rating;
  return (
    <div className="flex flex-col items-center gap-1">
      <span className="text-xs font-semibold uppercase tracking-[0.3em] text-ink-mist">Рейтинг</span>
      <motion.span
        animate={done && !reduce ? { scale: [1, 1.25, 1] } : undefined}
        transition={{ duration: 0.35 }}
        className={`font-mono text-8xl font-black tabular-nums ${toneClass} drop-shadow-[0_0_28px_currentColor]`}
        data-testid="walkout-rating"
      >
        {shown}
      </motion.span>
    </div>
  );
}

/** Specks of light drifting up the beam. */
function Dust() {
  const [specks] = useState(() =>
    Array.from({ length: 14 }, (_, i) => ({
      id: i,
      x: (Math.random() - 0.5) * 120,
      delay: Math.random() * 1.5,
      duration: 2 + Math.random() * 1.5,
      size: 2 + Math.random() * 3,
    })),
  );
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10">
      {specks.map((s) => (
        <motion.span
          key={s.id}
          initial={{ y: 0, opacity: 0 }}
          animate={{ y: -420, opacity: [0, 0.9, 0] }}
          transition={{ duration: s.duration, delay: s.delay, repeat: Infinity, ease: "easeOut" }}
          className="absolute bottom-10 left-1/2 rounded-full bg-white"
          style={{ marginLeft: s.x, width: s.size, height: s.size }}
        />
      ))}
    </div>
  );
}
