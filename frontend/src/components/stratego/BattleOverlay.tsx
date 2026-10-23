import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";

import type { StrategoCombatPiece, StrategoMove } from "@/types";

import RoleIcon from "./RoleIcon";
import { ROLE_META } from "./strategoMeta";

const RARITY_RING: Record<string, string> = {
  common: "border-rarity-common", rare: "border-rarity-rare", epic: "border-rarity-epic",
  legendary: "border-rarity-legendary", diamond: "border-rarity-diamond",
};

/** Full-screen duel reveal: both pieces flip face-up, then the loser is
 *  knocked out and the survivor glows. Auto-closes; a tap skips it. */
export default function BattleOverlay({ move, onClose }: { move: StrategoMove | null; onClose: () => void }) {
  useEffect(() => {
    if (!move) return;
    const t = setTimeout(onClose, 2400);
    return () => clearTimeout(t);
  }, [move, onClose]);

  const c = move?.combat;
  const outcome = c
    ? c.survivor === "both" ? "Обе фишки выбыли" : c.survivor === "attacker" ? "Атака удалась" : "Защита устояла"
    : "";
  return (
    <AnimatePresence>
      {move && c && (
        <motion.div
          className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-black/70 px-6 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <p className="font-mono text-caption uppercase tracking-wider text-ink-mist">
            {move.mine ? "Твоя атака" : "Атака соперника"}{move.auto ? " · автоход" : ""}
          </p>
          <div className="flex items-center gap-4">
            <DuelCard piece={c.attacker} attacking lost={c.survivor !== "attacker"} from="left" />
            <motion.span
              className="font-display text-xl font-bold text-accent-lime"
              initial={{ scale: 0 }}
              animate={{ scale: [0, 1.4, 1] }}
              transition={{ delay: 0.35, duration: 0.4 }}
            >
              VS
            </motion.span>
            <DuelCard piece={c.defender} lost={c.survivor !== "defender"} from="right" />
          </div>
          <motion.p
            className="font-display text-lg font-bold text-ink-chalk"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.1 }}
          >
            {outcome}
          </motion.p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function DuelCard({ piece, attacking, lost, from }: {
  piece: StrategoCombatPiece; attacking?: boolean; lost: boolean; from: "left" | "right";
}) {
  const skillBonus = piece.card?.skill_bonus && piece.card.skill_kind === (attacking ? "atk" : "def") ? piece.card.skill_bonus : 0;
  const ring = piece.card ? RARITY_RING[piece.card.rarity] ?? "border-white/20" : "border-accent-lime/60";
  return (
    <motion.div
      className={`relative flex w-32 flex-col items-center gap-1.5 rounded-2xl border-2 ${ring} ${
        piece.mine ? "bg-gradient-to-b from-bg-raised to-bg-base" : "bg-gradient-to-b from-[#5c1820] to-[#2a090d]"
      } p-3 text-center shadow-lg`}
      // Every property uses the same 3 keyframes so `times` applies cleanly:
      // fly in face-down → flip face-up → winner grows / loser is knocked aside.
      style={{ transformPerspective: 600 }}
      initial={{ x: from === "left" ? -140 : 140, rotateY: 90, opacity: 0, scale: 0.9, rotate: 0 }}
      animate={{
        x: [from === "left" ? -140 : 140, 0, 0],
        rotateY: [90, 0, 0],
        opacity: [0, 1, lost ? 0.35 : 1],
        scale: [0.9, 1, lost ? 0.88 : 1.08],
        rotate: [0, 0, lost ? (from === "left" ? -6 : 6) : 0],
      }}
      transition={{ duration: 1.3, times: [0, 0.45, 1], ease: "easeOut" }}
    >
      <span className={piece.mine ? "text-accent-lime" : "text-red-200"}>
        <RoleIcon role={piece.role} size={30} />
      </span>
      <p className="font-display text-sm font-bold text-ink-chalk">{ROLE_META[piece.role].label}</p>
      {piece.card && <p className="line-clamp-2 text-caption leading-tight text-ink-mist">{piece.card.display_name}</p>}
      {piece.power > 0 && (
        <p className="font-mono text-lg font-bold text-ink-chalk">
          {piece.power}
          {skillBonus > 0 && <span className="ml-1 text-xs text-accent-lime">+{skillBonus}</span>}
        </p>
      )}
      {skillBonus > 0 && <p className="text-micro text-accent-lime">{piece.card?.skill_name}</p>}
      <span className="text-micro text-ink-mist-dim">{piece.mine ? "твоя" : "соперника"}</span>
      {!lost && (
        <motion.span
          className="pointer-events-none absolute inset-0 rounded-2xl shadow-glow"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 0, 1] }}
          transition={{ duration: 1.3, times: [0, 0.6, 1] }}
        />
      )}
    </motion.div>
  );
}
