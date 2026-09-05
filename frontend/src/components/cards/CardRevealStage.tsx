import { motion } from "framer-motion";
import { useMemo } from "react";

import { IconGlobe, IconHelp, IconStadium, IconTag } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_LABELS } from "@/lib/rarity";
import type { Player } from "@/types";

export type Stage = "position" | "rarity" | "country" | "club" | "silhouette" | "reveal";
export const STAGES: Stage[] = ["position", "rarity", "country", "club", "silhouette", "reveal"];
export const STAGE_DURATION_MS = 900;

// Structural rather than `OpenedCard` directly — reused by ClubPackOpenPage.tsx for
// OpenedClubCard, whose `card` wrapper (ClubCard) carries different bookkeeping fields
// (serial_number/acquired_at/is_in_lineup vs. a regular UserCard's) but the same `player`
// shape, and which has no `duplicate_count` concept at all (a club's cards aren't
// deduplicated the way a personal collection's are).
export interface RevealableOpenedCard {
  card: { player: Player };
  is_new: boolean;
  duplicate_count?: number;
}

export function RevealStage({
  opened,
  stage,
  index,
  total,
  onTap,
}: {
  opened: RevealableOpenedCard;
  stage: Stage;
  index: number;
  total: number;
  onTap: () => void;
}) {
  const player = opened.card.player;
  const showFrom = (s: Stage) => STAGES.indexOf(stage) >= STAGES.indexOf(s);
  const revealed = showFrom("reveal");

  return (
    <div
      onClick={onTap}
      role="button"
      tabIndex={0}
      className="flex flex-1 cursor-pointer flex-col items-center justify-center gap-5 px-6 text-center"
    >
      {total > 1 && <p className="font-mono text-xs text-ink-mist-dim">Карточка {index + 1} / {total}</p>}

      <div className="relative">
        {revealed && (
          <motion.div
            initial={{ opacity: 0, scale: 0.7 }}
            animate={{ opacity: 0.55, scale: 1.35 }}
            transition={{ duration: 0.7, ease: "easeOut" }}
            className="pointer-events-none absolute inset-0 -z-10 rounded-full bg-floodlight blur-3xl"
          />
        )}
        {revealed && player.rarity === "legendary" && <LegendaryConfetti />}
        {revealed && player.rarity === "diamond" && <DiamondSparkle />}
        <motion.div
          initial={{ scale: 0.85, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className={`relative flex aspect-square w-64 flex-col items-center justify-center overflow-hidden rounded-3xl bg-gradient-to-b ${
            showFrom("rarity") ? RARITY_GRADIENTS[player.rarity] : "from-bg-raised to-bg-surface"
          } p-[3px] ${showFrom("rarity") ? RARITY_GLOW[player.rarity] : ""}`}
        >
          <div className="flex h-full w-full flex-col items-center justify-center rounded-[22px] bg-bg-surface">
            {revealed ? (
              <motion.img
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                src={staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt={player.display_name}
                className="h-full w-full object-cover"
              />
            ) : showFrom("silhouette") ? (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="h-32 w-32 rounded-full bg-bg-raised" />
            ) : (
              <IconHelp size={44} className="text-ink-mist-dim" />
            )}
          </div>

          {showFrom("position") && (
            <span className="absolute left-2 top-2 rounded-md bg-black/70 px-2 py-1 font-mono text-[11px] font-bold text-ink-chalk">
              {player.position}
            </span>
          )}
          {showFrom("rarity") && (
            <span className="absolute right-2 top-2 rounded-md bg-black/70 px-2 py-1 text-[11px] font-bold text-ink-chalk">
              {RARITY_LABELS[player.rarity]}
            </span>
          )}
        </motion.div>
      </div>

      <div className="min-h-[70px] space-y-1">
        {showFrom("country") && (
          <p className="flex items-center justify-center gap-1.5 text-sm text-ink-mist">
            <IconGlobe size={14} />
            {player.country}
          </p>
        )}
        {showFrom("club") && (
          <p className="flex items-center justify-center gap-1.5 text-sm text-ink-mist">
            <IconStadium size={14} />
            {player.club}
          </p>
        )}
        {revealed && (
          <>
            <p className="font-display text-lg font-bold text-ink-chalk">{player.display_name}</p>
            <p className="font-mono text-base font-semibold text-accent-cyan">Рейтинг {player.rating}</p>
            <p className="font-mono text-xs text-ink-mist">АТК {player.attack_rating} · ЗЩТ {player.defense_rating}</p>
            {player.collection_name && (
              <p className="flex items-center justify-center gap-1 text-xs font-semibold text-accent-lime">
                <IconTag size={12} />
                {player.collection_name}
              </p>
            )}
            {opened.is_new && (
              <span className="inline-block rounded-full bg-accent-green px-2 py-0.5 text-[11px] font-bold text-bg-base">Новая!</span>
            )}
            {!!opened.duplicate_count && opened.duplicate_count > 1 && (
              <span className="ml-1 inline-block rounded-full bg-white/10 px-2 py-0.5 font-mono text-[11px] text-ink-mist">
                ×{opened.duplicate_count} в коллекции
              </span>
            )}
          </>
        )}
      </div>

      {stage !== "reveal" && <p className="text-xs text-ink-mist-dim">Нажми, чтобы продолжить</p>}
    </div>
  );
}

const CONFETTI_COLORS = ["#facc15", "#f59e0b", "#fde68a", "#fbbf24", "#fcd34d"];

function LegendaryConfetti() {
  const pieces = useMemo(
    () =>
      Array.from({ length: 26 }, (_, i) => {
        const angle = (Math.PI * 2 * i) / 26 + Math.random() * 0.4;
        const distance = 90 + Math.random() * 100;
        return {
          id: i,
          x: Math.cos(angle) * distance,
          y: Math.sin(angle) * distance * 0.6 + 70, // biased downward for a "falling" feel
          rotate: Math.random() * 360,
          delay: Math.random() * 0.2,
          color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
        };
      }),
    []
  );

  return (
    <div className="pointer-events-none absolute inset-0 overflow-visible">
      {pieces.map((piece) => (
        <motion.span
          key={piece.id}
          initial={{ x: 0, y: 0, opacity: 1, rotate: 0, scale: 1 }}
          animate={{ x: piece.x, y: piece.y, opacity: 0, rotate: piece.rotate, scale: 0.6 }}
          transition={{ duration: 1.5, delay: piece.delay, ease: "easeOut" }}
          className="absolute left-1/2 top-1/2 h-2.5 w-1.5 rounded-[1px]"
          style={{ backgroundColor: piece.color }}
        />
      ))}
    </div>
  );
}

// Icy/violet star sparks + a slowly-rotating prismatic halo behind the card —
// a diamond reveal should read as "light refracting", distinct from
// legendary's warm falling gold confetti.
const DIAMOND_SPARK_COLORS = ["#67e8f9", "#f0abfc", "#c4b5fd", "#5eead4", "#ffffff"];

function DiamondSparkle() {
  const pieces = useMemo(
    () =>
      Array.from({ length: 22 }, (_, i) => {
        const angle = (Math.PI * 2 * i) / 22 + Math.random() * 0.3;
        const distance = 80 + Math.random() * 110;
        return {
          id: i,
          x: Math.cos(angle) * distance,
          y: Math.sin(angle) * distance,
          rotate: Math.random() * 360,
          // repeat: Infinity below loops each star forever — delay staggers
          // the first spawn, repeatDelay staggers every spawn after that, so
          // stars keep flickering in for as long as the reveal is on screen
          // instead of firing once and going dark.
          delay: Math.random() * 1.4,
          repeatDelay: 0.5 + Math.random() * 1.3,
          duration: 1.0 + Math.random() * 0.5,
          scale: 0.6 + Math.random() * 0.7,
          color: DIAMOND_SPARK_COLORS[i % DIAMOND_SPARK_COLORS.length],
        };
      }),
    []
  );

  return (
    <div className="pointer-events-none absolute inset-0 overflow-visible">
      <motion.div
        initial={{ opacity: 0, rotate: 0, scale: 0.8 }}
        animate={{ opacity: 0.55, rotate: 360, scale: 1.6 }}
        transition={{
          opacity: { duration: 0.6 },
          scale: { duration: 0.6 },
          rotate: { duration: 6, repeat: Infinity, ease: "linear" },
        }}
        className="absolute inset-0 -z-10 rounded-full blur-2xl"
        style={{ background: "conic-gradient(from 0deg, #67e8f9, #f0abfc, #c4b5fd, #5eead4, #67e8f9)" }}
      />
      {pieces.map((piece) => (
        <motion.span
          key={piece.id}
          initial={{ x: 0, y: 0, opacity: 0, rotate: 0, scale: 0 }}
          animate={{ x: [0, piece.x], y: [0, piece.y], opacity: [0, 1, 0], rotate: piece.rotate, scale: [0, piece.scale, piece.scale] }}
          transition={{
            duration: piece.duration,
            delay: piece.delay,
            repeat: Infinity,
            repeatDelay: piece.repeatDelay,
            ease: "easeOut",
          }}
          className="absolute left-1/2 top-1/2 text-base leading-none"
          style={{ color: piece.color }}
        >
          ✦
        </motion.span>
      ))}
    </div>
  );
}
