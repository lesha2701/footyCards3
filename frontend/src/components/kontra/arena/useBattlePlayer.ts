import { useCallback, useEffect, useRef, useState } from "react";

import { haptic } from "@/lib/telegram";
import type { KontraBattle, KontraEvent, KontraUnit } from "@/types";

import { applyImpact, type Beat, type BeatPlan, planBeat, type Shown, snapshot, toBeats } from "./battleScript";
import type { Pulse } from "./Token";

export interface Playing {
  beat: Beat;
  plan: BeatPlan;
  speed: number;
}

/** Plays the server's event log beat by beat: HP, knock-downs and effects
 *  land at the moments the FX layer draws them. When the queue runs out
 *  the screen snaps to the authoritative state the server sent. */
export function useBattlePlayer(battle: KontraBattle | null, speed: number) {
  const [shown, setShown] = useState<Shown>({});
  const [queue, setQueue] = useState<Beat[]>([]);
  const [playing, setPlaying] = useState<Playing | null>(null);
  const [pulse, setPulse] = useState<Record<string, Pulse>>({});
  const [dealt, setDealt] = useState(0); // damage to the other side while playing (boss counter)
  // The squads' ultimate charge as the log plays (mirrors kontra_engine:
  // +18 per own action, +6 per hit taken, the ultimate spends it).
  const [charge, setCharge] = useState({ me: 0, foe: 0 });
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const units = useRef<KontraUnit[]>([]);
  units.current = battle?.units ?? [];
  const n = useRef(0);

  const clear = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  useEffect(() => clear, []);

  /** A fresh battle starts from full HP; a mid-battle one from the screen. */
  const start = useCallback((b: KontraBattle, events: KontraEvent[], fresh: boolean) => {
    if (fresh) {
      setShown(snapshot(b.units, true));
      setCharge({ me: 0, foe: 0 });
    }
    setDealt(fresh ? 0 : b.damage - events.filter((e) => e.kind === "hit" && b.units.find((u) => u.id === e.target)?.side === "foe")
      .reduce((sum, e) => sum + (e.damage ?? 0), 0));
    setQueue((q) => [...q, ...toBeats(events)]);
  }, []);

  const reset = useCallback((b: KontraBattle) => {
    clear();
    setQueue([]);
    setPlaying(null);
    setShown(snapshot(b.units));
    setDealt(b.damage);
    setCharge({ me: b.charge_me, foe: b.charge_foe });
  }, []);

  // Next beat.
  useEffect(() => {
    if (playing || !queue.length) return;
    const [beat, ...rest] = queue;
    const plan = planBeat(beat);
    // Long autoplay logs run faster.
    const pace = speed * (rest.length > 24 ? 2 : rest.length > 10 ? 1.4 : 1);
    const actorSide = units.current.find((u) => u.id === beat.actor)?.side;
    const bump = (side: string | undefined, add: number, zero = false) => {
      if (side !== "me" && side !== "foe") return;
      setCharge((c) => ({ ...c, [side]: zero ? 0 : Math.min(100, c[side] + add) }));
    };
    if (beat.kind === "action") bump(actorSide, 18, Boolean(beat.ult));
    for (const imp of plan.impacts) {
      timers.current.push(setTimeout(() => {
        const e = imp.event;
        setShown((sh) => applyImpact(sh, e, units.current, actorSide));
        if (e.target && (e.kind === "hit" || e.kind === "heal" || e.kind === "miss")) {
          n.current += 1;
          const kind: Pulse["kind"] = e.kind === "heal" ? "heal" : e.kind === "miss" ? "miss"
            : !e.damage && e.absorbed ? "block" : e.crit ? "crit" : "hit";
          setPulse((p) => ({ ...p, [e.target!]: { n: n.current, kind } }));
          if (e.kind === "hit") {
            haptic(e.crit ? "heavy" : "light");
            bump(units.current.find((u) => u.id === e.target)?.side, 6);
            if (units.current.find((u) => u.id === e.target)?.side === "foe") setDealt((d) => d + (e.damage ?? 0));
          }
        }
      }, imp.at / pace));
    }
    if (beat.ult) timers.current.push(setTimeout(() => haptic("heavy"), 80));
    timers.current.push(setTimeout(() => setPlaying(null), plan.duration / pace));
    setPlaying({ beat, plan, speed: pace });
    setQueue(rest);
  }, [queue, playing, speed]);

  // The log is over: the server's state is the truth.
  const busy = Boolean(playing) || queue.length > 0;
  useEffect(() => {
    if (!busy && battle) {
      setShown(snapshot(battle.units));
      setDealt(battle.damage);
      setCharge({ me: battle.charge_me, foe: battle.charge_foe });
    }
  }, [busy, battle]);

  const skip = useCallback(() => {
    if (battle) reset(battle);
  }, [battle, reset]);

  return { shown, playing, pulse, busy, dealt, charge, start, reset, skip };
}
