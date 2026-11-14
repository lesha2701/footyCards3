import { motion, type TargetAndTransition, type Transition } from "framer-motion";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import type { KontraUnit } from "@/types";

import BeatFx from "./BeatFx";
import { fxOf, type Shown, spots as layout } from "./battleScript";
import Pitch from "./Pitch";
import Token, { type Pulse } from "./Token";
import type { Playing } from "./useBattlePlayer";

interface Props {
  units: KontraUnit[];
  shown: Shown;
  playing: Playing | null;
  pulse: Record<string, Pulse>;
  activeId: string | null;
  targetId: string | null;
  allyTargetId: string | null;
  pickFoes: boolean;
  pickAllies: boolean;
  boss: boolean;
  bossArt?: string;
  onTap: (u: KontraUnit) => void;
  /** Overlays inside the stage (top bar, result). */
  children?: ReactNode;
}

function useSize(ref: React.RefObject<HTMLDivElement>) {
  const [size, setSize] = useState({ w: 360, h: 460 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return size;
}

/** The 2.5D battle: the pitch, both squads as standing cards, and the
 *  beat being played on top. Actors lunge, dash or flip, the camera
 *  shakes on crits, slams and ultimates. */
export default function BattleStage({
  units, shown, playing, pulse, activeId, targetId, allyTargetId, pickFoes, pickAllies, boss, bossArt, onTap, children,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const size = useSize(ref);
  const spots = useMemo(() => layout(units), [units]);
  const beat = playing?.beat;
  const plan = playing?.plan;
  const sp = playing?.speed ?? 1;
  const fx = fxOf(beat?.ability);

  // Camera shake: crits, the boss's slam, ultimates.
  const quake = plan && (beat?.ult || fx.style === "slam" || plan.impacts.some((i) => i.event.crit));
  const quakeAt = plan ? (plan.impacts.find((i) => i.event.kind === "hit")?.at ?? plan.intro) : 0;

  // Built once per beat: framer restarts keyframes whose arrays change.
  const moves = useMemo(() => {
    const out: Record<string, { animate: TargetAndTransition; transition: Transition }> = {};
    const actor = units.find((u) => u.id === beat?.actor);
    const m = actor ? actorMove(actor) : undefined;
    if (actor && m) out[actor.id] = m;
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [beat, plan, sp, size.w, size.h, spots]);
  const shake = useMemo(() => (quake
    ? { animate: { x: [0, -8, 7, -5, 3, 0], y: [0, 4, -3, 2, 0, 0] }, transition: { delay: quakeAt / 1000 / sp, duration: 0.42 / sp } }
    : { animate: {}, transition: {} }), [quake, quakeAt, sp]);

  function actorMove(u: KontraUnit): { animate: TargetAndTransition; transition: Transition } | undefined {
    if (!beat || !plan || beat.kind !== "action" || beat.actor !== u.id) return undefined;
    const first = plan.impacts.find((i) => i.event.kind === "hit" || i.event.kind === "miss");
    const from = spots[u.id];
    const to = first?.event.target ? spots[first.event.target] : undefined;
    const start = (plan.intro + (beat.ability === "strike" ? 160 : 420)) / 1000 / sp;
    if (u.role === "boss") {
      return { animate: { scale: [1, 1.12, 0.96, 1], filter: ["brightness(1)", "brightness(1.5)", "brightness(1)", "brightness(1)"] },
        transition: { delay: start - 0.2 / sp, duration: 0.6 / sp } };
    }
    if (!from || !to) {
      return { animate: { y: [0, -10, 0], scale: [1, 1.08, 1] }, transition: { delay: plan.intro / 1000 / sp, duration: 0.5 / sp } };
    }
    const dx = ((to.x - from.x) / 100) * size.w;
    const dy = ((to.y - from.y) / 100) * size.h;
    const k = fx.style === "dash" ? 0.72 : fx.style === "pierce" ? 0.22 : 0.12;
    return {
      animate: { x: [0, -dx * 0.05, dx * k, 0], y: [0, -dy * 0.05, dy * k, 0], rotate: fx.style === "flip" ? [0, 0, 360, 360] : 0 },
      transition: { delay: start - 0.12 / sp, duration: (fx.style === "dash" ? 0.75 : 0.5) / sp, times: [0, 0.2, 0.5, 1] },
    };
  }

  return (
    <motion.div
      key={quake ? `q-${beat?.key}` : "still"}
      ref={ref}
      className="relative w-full select-none overflow-hidden rounded-3xl ring-1 ring-white/10"
      style={{ aspectRatio: "4 / 5", maxHeight: "68vh" }}
      animate={shake.animate}
      transition={shake.transition}
    >
      <Pitch boss={boss} />

      {units.map((u) => {
        const move = moves[u.id];
        const s = shown[u.id] ?? { hp: u.hp, alive: u.alive, effects: u.effects };
        const pickable = s.alive && ((u.side === "foe" && pickFoes) || (u.side === "me" && pickAllies));
        return (
          <motion.div key={move ? `${u.id}-${beat?.key}` : u.id} className="pointer-events-none absolute inset-0" style={{ zIndex: Math.round(spots[u.id]?.y ?? 0) }}
            animate={move?.animate} transition={move?.transition}>
            <Token
              unit={u} shown={s} spot={spots[u.id]} active={activeId === u.id}
              targeted={(u.side === "foe" && targetId === u.id) || (u.side === "me" && pickAllies && allyTargetId === u.id)}
              pickable={pickable} pulse={pulse[u.id]} bossArt={u.role === "boss" ? bossArt : undefined}
              onTap={pickable ? () => onTap(u) : undefined}
            />
          </motion.div>
        );
      })}

      {beat && plan && (
        <BeatFx key={beat.key} beat={beat} plan={plan} speed={sp} units={units} spots={spots} size={size} />
      )}
      {children}
    </motion.div>
  );
}
