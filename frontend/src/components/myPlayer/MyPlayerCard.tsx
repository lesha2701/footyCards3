import { motion, useMotionTemplate, useTransform } from "framer-motion";

import type { MyPlayer, MyPlayerSponsorBadge } from "@/api/myPlayer";
import { ATTR_ORDER, ATTR_SHORT, TIER_FRAMES, TIER_TEXT } from "@/lib/myPlayer";

import CardEffect from "./CardEffect";
import PlayerAvatar from "./PlayerAvatar";
import { useCardTilt } from "./useCardTilt";

interface Props {
  player: MyPlayer;
  level?: number | null;
  /** sm — lists, md — profile, lg — the hero on «Мой игрок» (tilt, holo, big stats). */
  size?: "sm" | "md" | "lg";
  /** This week's sponsor — a patch on the kit. */
  sponsor?: MyPlayerSponsorBadge | null;
}

/** «Мой игрок» as a collectible-style card; the frame follows the tier. */
export default function MyPlayerCard({ player, level, size = "md", sponsor }: Props) {
  if (size === "lg") return <HeroCard player={player} level={level} sponsor={sponsor} />;
  const small = size === "sm";
  return (
    <div
      className={`relative aspect-[3/4] w-full overflow-hidden rounded-2xl bg-gradient-to-b p-[3px] ${TIER_FRAMES[player.tier]}`}
      data-testid="my-player-card"
    >
      <div className="relative flex h-full w-full flex-col overflow-hidden rounded-[13px] bg-gradient-to-b from-bg-raised to-bg-surface">
        <div className="relative flex-1">
          <div className="absolute left-2 top-2 z-10 flex flex-col items-center leading-none drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]">
            <span className={`font-display font-black text-ink-chalk ${small ? "text-lg" : "text-3xl"}`}>{player.rating}</span>
            <span className={`font-display font-bold text-ink-mist ${small ? "text-micro" : "text-xs"}`}>{player.position}</span>
          </div>
          <div className="absolute right-2 top-2 z-10 text-right leading-tight drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]">
            <span className={`block font-display text-micro font-bold ${TIER_TEXT[player.tier]}`}>{player.tier_label.toUpperCase()}</span>
            {level != null && <span className="block font-mono text-micro text-ink-mist">ур. {level}</span>}
          </div>
          <PlayerAvatar
            appearance={player.appearance} number={player.number} accessory={player.accessory} backdrop={player.background} country={player.country}
            sponsor={sponsor} className="absolute inset-0 h-full w-full"
          />
        </div>
        <div className="border-t border-white/10 bg-black/30 px-2 py-1.5 text-center">
          <p className={`truncate font-display font-bold text-ink-chalk ${small ? "text-micro" : "text-sm"}`}>
            {player.name} <span className="text-ink-mist">#{player.number}</span>
          </p>
          {!small && (
            <p className="mt-0.5 flex items-center justify-center gap-3 font-mono text-micro text-ink-mist">
              {ATTR_ORDER.map((a) => (
                <span key={a}>
                  {ATTR_SHORT[a]} <b className="text-accent-cyan">{player.attributes[a]}</b>
                </span>
              ))}
            </p>
          )}
        </div>
        <CardEffect effect={player.effect} />
      </div>
    </div>
  );
}

const HOLO_TIERS = new Set(["gold", "legend"]);

function HeroCard({ player, level, sponsor }: { player: MyPlayer; level?: number | null; sponsor?: MyPlayerSponsorBadge | null }) {
  const tilt = useCardTilt();
  const holo = HOLO_TIERS.has(player.tier);
  // The sheen and the glare slide with the tilt.
  const sheenX = useTransform(tilt.rotateY, [-12, 12], [0, 100]);
  const sheenY = useTransform(tilt.rotateX, [-12, 12], [100, 0]);
  const sheenPosition = useMotionTemplate`${sheenX}% ${sheenY}%`;
  const glare = useMotionTemplate`radial-gradient(circle at ${sheenX}% ${sheenY}%, rgba(255,255,255,0.28), transparent 55%)`;

  return (
    <div style={{ perspective: 900 }} className="w-full" data-testid="my-player-card">
      <motion.div
        onPointerMove={tilt.onPointerMove}
        onPointerLeave={tilt.onPointerLeave}
        onPointerUp={tilt.onPointerLeave}
        style={{ rotateX: tilt.rotateX, rotateY: tilt.rotateY, transformStyle: "preserve-3d" }}
        className={`relative aspect-[3/4] w-full touch-pan-y overflow-hidden rounded-[22px] bg-gradient-to-b p-[4px] ${TIER_FRAMES[player.tier]}`}
      >
        <div className="relative h-full w-full overflow-hidden rounded-[18px] bg-bg-surface">
          <PlayerAvatar
            appearance={player.appearance} number={player.number} accessory={player.accessory} backdrop={player.background} country={player.country}
            sponsor={sponsor} className="absolute inset-0 h-full w-full"
          />
          <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/85 via-black/40 to-transparent" />

          <div className="absolute left-4 top-3 flex flex-col items-center leading-none drop-shadow-[0_2px_6px_rgba(0,0,0,0.9)]">
            <span className="font-display text-5xl font-black text-ink-chalk">{player.rating}</span>
            <span className="mt-1 font-display text-sm font-bold text-ink-mist">{player.position}</span>
          </div>
          <div className="absolute right-3 top-3 flex flex-col items-end gap-1">
            <span className={`rounded-full bg-black/55 px-2.5 py-1 font-display text-micro font-bold tracking-wider ${TIER_TEXT[player.tier]}`}>
              {player.tier_label.toUpperCase()}
            </span>
            {level != null && <span className="rounded-full bg-black/55 px-2 py-0.5 font-mono text-micro text-ink-chalk">ур. {level}</span>}
          </div>

          <div className="absolute inset-x-3 bottom-3 rounded-2xl border border-white/10 bg-black/45 px-3 py-2.5 backdrop-blur-sm">
            <p className="truncate text-center font-display text-lg font-bold text-ink-chalk">
              {player.name} <span className="text-ink-mist">#{player.number}</span>
            </p>
            <div className="mt-1.5 grid grid-cols-2 divide-x divide-white/15">
              {ATTR_ORDER.map((a) => (
                <div key={a} className="flex items-baseline justify-center gap-1.5">
                  <span className={`font-display text-3xl font-black ${player.key_attr === a ? "text-accent-lime" : "text-ink-chalk"}`}>
                    {player.attributes[a]}
                  </span>
                  <span className="font-display text-xs font-bold text-ink-mist">{ATTR_SHORT[a]}</span>
                </div>
              ))}
            </div>
          </div>

          {holo && (
            <motion.div
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 mix-blend-color-dodge"
              style={{
                backgroundImage:
                  "linear-gradient(115deg, transparent 20%, rgba(255,255,255,0.35) 32%, rgba(255,0,200,0.25) 42%, rgba(0,255,255,0.3) 52%, rgba(255,230,0,0.25) 62%, transparent 75%)",
                backgroundSize: "250% 250%",
                backgroundPosition: sheenPosition,
                opacity: player.tier === "legend" ? 0.65 : 0.45,
              }}
              data-testid="holo-sheen"
            />
          )}
          <motion.div aria-hidden="true" className="pointer-events-none absolute inset-0" style={{ backgroundImage: glare }} />
          <CardEffect effect={player.effect} />
        </div>
      </motion.div>
    </div>
  );
}
