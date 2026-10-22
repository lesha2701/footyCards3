import { AnimatePresence, motion } from "framer-motion";

import { staticUrl } from "@/lib/api";
import { GLOVE_FILTERS, SHORTS_STYLES } from "@/lib/cosmetics";
import { RARITY_GRADIENTS } from "@/lib/rarity";
import type { MordoboiExchange, MordoboiFighter, Rarity } from "@/types";

import { ACTION_META, pct } from "./mordoboiMeta";

interface Props {
  me: MordoboiFighter;
  opponent: MordoboiFighter | null;
  /** The exchange being animated right now (null = idle). */
  hit: MordoboiExchange | null;
}

/** Two boxers facing each other; a fresh exchange throws both gloves, the
 *  one taking damage recoils and the damage floats up. */
export default function BoxingRing({ me, opponent, hit }: Props) {
  return (
    <div className="relative overflow-hidden rounded-3xl bg-gradient-to-b from-yellow-500/15 via-bg-surface to-bg-surface p-4">
      {/* ropes */}
      <div className="pointer-events-none absolute inset-x-0 top-6 h-px bg-red-400/40" aria-hidden />
      <div className="pointer-events-none absolute inset-x-0 top-10 h-px bg-white/20" aria-hidden />
      <div className="pointer-events-none absolute inset-x-0 top-14 h-px bg-sky-400/40" aria-hidden />
      <div className="relative grid grid-cols-2 gap-3">
        <Corner fighter={me} side="left" hit={hit} />
        {opponent ? (
          <Corner fighter={opponent} side="right" hit={hit} />
        ) : (
          <div className="flex flex-col items-center justify-center gap-2 text-center text-caption text-ink-mist">
            <span className="text-3xl">❔</span>
            Соперник ещё не вышел на ринг
          </div>
        )}
      </div>
    </div>
  );
}

function Corner({ fighter, side, hit }: { fighter: MordoboiFighter; side: "left" | "right"; hit: MordoboiExchange | null }) {
  const mine = side === "left";
  const action = hit ? (mine ? hit.my_action : hit.opponent_action) : null;
  const taken = hit ? (mine ? hit.opponent_damage : hit.my_damage) : 0;
  const striking = action === "jab" || action === "hook" || action === "uppercut";
  const dir = mine ? 1 : -1;
  const lowHp = fighter.hp / Math.max(1, fighter.max_hp) < 0.3;
  const rarity = (fighter.card?.rarity ?? "common") as Rarity;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-36 w-full">
        <motion.div
          key={hit ? `body-${hit.n}` : "body"}
          className={`absolute inset-x-3 top-2 bottom-2 overflow-hidden rounded-2xl bg-gradient-to-b p-[2px] ${RARITY_GRADIENTS[rarity] ?? ""}`}
          initial={false}
          animate={
            taken > 0
              ? { x: [0, -10 * dir, 6 * dir, 0], rotate: [0, -6 * dir, 2 * dir, 0] }
              : action === "dodge"
                ? { y: [0, 14, 0], x: [0, -8 * dir, 0] }
                : { x: 0, y: 0, rotate: 0 }
          }
          transition={{ duration: 0.55, ease: "easeOut" }}
        >
          <div className="relative flex h-full w-full items-end justify-center overflow-hidden rounded-[14px] bg-bg-base">
            {fighter.card?.image_path ? (
              <img
                src={staticUrl(fighter.card.image_path)}
                alt=""
                className="h-full w-full object-cover object-top"
              />
            ) : (
              <span className="mb-6 font-display text-3xl font-bold text-ink-mist">
                {(fighter.card?.display_name ?? fighter.name).slice(0, 2).toUpperCase()}
              </span>
            )}
            <span className="absolute left-1.5 top-1.5 rounded-md bg-black/60 px-1.5 font-mono text-micro font-bold text-ink-chalk">
              {fighter.card?.rating ?? "—"}
            </span>
            {taken > 0 && (
              <motion.span
                key={`flash-${hit?.n}`}
                className="absolute inset-0 bg-red-500/40"
                initial={{ opacity: 0.9 }}
                animate={{ opacity: 0 }}
                transition={{ duration: 0.5 }}
              />
            )}
          </div>
        </motion.div>
        {/* «Выход на ринг»: the boxer's shorts under the card */}
        <span
          className={`absolute inset-x-8 bottom-0 h-2.5 rounded-full shadow ${SHORTS_STYLES[fighter.look?.shorts ?? "red"] ?? SHORTS_STYLES.red}`}
          aria-hidden
        />

        {/* the glove flies toward the other corner */}
        <AnimatePresence>
          {hit && striking && (
            <motion.span
              key={`glove-${hit.n}`}
              className="absolute top-12 z-10 text-4xl drop-shadow-lg"
              style={{
                ...(mine ? { right: 0 } : { left: 0, transform: "scaleX(-1)" }),
                filter: fighter.look?.gloves ? GLOVE_FILTERS[fighter.look.gloves] : undefined,
              }}
              initial={{ x: 0, scale: 0.6, opacity: 0 }}
              animate={{
                x: [0, 70 * dir, 55 * dir, 40 * dir],
                y: action === "uppercut" ? [20, -10, -14, -14] : 0,
                scale: action === "uppercut" ? [0.6, 1.6, 1.3, 1] : [0.6, 1.3, 1.1, 1],
                opacity: [0, 1, 1, 0],
              }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.9, ease: "easeOut", times: [0, 0.35, 0.7, 1] }}
            >
              {ACTION_META[action].emoji}
            </motion.span>
          )}
          {hit && action === "block" && (
            <motion.span
              key={`block-${hit.n}`}
              className="absolute left-1/2 top-12 z-10 -translate-x-1/2 text-4xl"
              initial={{ scale: 0.4, opacity: 0 }}
              animate={{ scale: [0.4, 1.2, 1], opacity: [0, 1, 1, 0] }}
              transition={{ duration: 0.9 }}
            >
              🛡️
            </motion.span>
          )}
          {hit && taken > 0 && (
            <motion.span
              key={`dmg-${hit.n}`}
              className="absolute left-1/2 top-4 z-20 -translate-x-1/2 font-display text-2xl font-black text-red-400 drop-shadow"
              initial={{ y: 10, opacity: 0 }}
              animate={{ y: -18, opacity: [0, 1, 1, 0] }}
              transition={{ duration: 1.4, ease: "easeOut" }}
            >
              −{taken}
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      {fighter.look?.nickname && (
        <p className="-mb-2 w-full truncate text-center text-micro font-black uppercase tracking-wider text-yellow-400">
          «{fighter.look.nickname}»
        </p>
      )}
      <p className="w-full truncate text-center font-display text-sm font-bold text-ink-chalk">
        {fighter.card?.display_name ?? fighter.name}
      </p>
      <p className="-mt-2 w-full truncate text-center text-micro text-ink-mist-dim">{fighter.name}</p>
      <Bar label="HP" value={fighter.hp} max={fighter.max_hp} color={lowHp ? "bg-red-500" : "bg-accent-green"} />
      <Bar label="Выносл." value={fighter.stamina} max={fighter.max_stamina} color="bg-yellow-400" />
      <div className="flex w-full justify-between font-mono text-micro text-ink-mist-dim">
        <span title="Сила">💪 {fighter.power}</span>
        <span title="Скорость">⚡ {fighter.speed}</span>
        <span title="Защита">🛡 {fighter.guard}</span>
      </div>
    </div>
  );
}

function Bar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  return (
    <div className="w-full">
      <div className="mb-0.5 flex justify-between text-micro text-ink-mist">
        <span>{label}</span>
        <span className="font-mono">{value}/{max}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
        <motion.div
          className={`h-full rounded-full ${color}`}
          initial={false}
          animate={{ width: `${pct(value, max)}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}
