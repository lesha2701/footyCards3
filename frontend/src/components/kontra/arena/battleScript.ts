import type { KontraEvent, KontraUnit } from "@/types";

/** One thing that happens on the pitch: a fighter's action with everything
 *  it caused, an injury tick, a skipped (stunned) turn… The server sends a
 *  flat event log; the battle screen plays it beat by beat. */
export interface Beat {
  key: string;
  kind: "action" | "tick" | "stunned" | "heal";
  actor?: string;
  ability?: string;
  name?: string;
  ult?: boolean;
  /** hit / miss / heal / effect / meter / down / passive, in log order. */
  events: KontraEvent[];
}

const ATTACHED = new Set(["hit", "miss", "heal", "effect", "meter", "down", "passive"]);

export function toBeats(events: KontraEvent[]): Beat[] {
  const beats: Beat[] = [];
  let current: Beat | null = null;
  for (const e of events) {
    if (e.kind === "ability") {
      current = { key: `a${e.n}`, kind: "action", actor: e.actor, ability: e.ability, name: e.name, ult: Boolean(e.ult), events: [] };
      beats.push(current);
    } else if (e.kind === "tick") {
      current = { key: `t${e.n}`, kind: "tick", actor: e.target, events: [e] };
      beats.push(current);
    } else if (e.kind === "stunned") {
      beats.push({ key: `s${e.n}`, kind: "stunned", actor: e.target, events: [e] });
      current = null;
    } else if (e.kind === "turn" || e.kind === "end") {
      current = null;
    } else if (ATTACHED.has(e.kind)) {
      if (current) current.events.push(e);
      else {
        // A start-of-turn heal («Медбригада» set) or a lone passive.
        current = { key: `h${e.n}`, kind: "heal", actor: e.target, events: [e] };
        beats.push(current);
      }
    }
  }
  return beats;
}

/** How an ability looks on the pitch. */
export type FxStyle = "shot" | "dash" | "flip" | "lob" | "pierce" | "buff" | "offside" | "slam" | "card" | "chant";

export interface AbilityFx {
  icon: string;
  style: FxStyle;
  /** Accent colour (banner, trail, glow). */
  color: string;
}

export const ABILITY_FX: Record<string, AbilityFx> = {
  strike: { icon: "⚽", style: "shot", color: "#e2e8f0" },
  hat_trick: { icon: "🎩", style: "shot", color: "#facc15" },
  penalty: { icon: "🎯", style: "shot", color: "#fb923c" },
  bicycle: { icon: "🤸", style: "flip", color: "#f472b6" },
  through_ball: { icon: "🪄", style: "shot", color: "#a78bfa" },
  pressing: { icon: "🟨", style: "dash", color: "#facc15" },
  conductor: { icon: "🎼", style: "buff", color: "#a78bfa" },
  tackle: { icon: "🦵", style: "dash", color: "#60a5fa" },
  wall: { icon: "🧱", style: "buff", color: "#f97316" },
  offside: { icon: "🚩", style: "offside", color: "#fde047" },
  save: { icon: "🧤", style: "buff", color: "#22d3ee" },
  medics: { icon: "⛑️", style: "buff", color: "#4ade80" },
  long_kick: { icon: "🚀", style: "lob", color: "#38bdf8" },
  boss_slam: { icon: "💥", style: "slam", color: "#ef4444" },
  boss_card: { icon: "🟥", style: "card", color: "#ef4444" },
  boss_chant: { icon: "📢", style: "chant", color: "#f43f5e" },
  ult_attacker: { icon: "🔥", style: "pierce", color: "#f97316" },
  ult_midfielder: { icon: "✨", style: "buff", color: "#c084fc" },
  ult_defender: { icon: "🛡️", style: "buff", color: "#38bdf8" },
  ult_goalkeeper: { icon: "💚", style: "buff", color: "#4ade80" },
};

export const fxOf = (code?: string): AbilityFx => ABILITY_FX[code ?? ""] ?? ABILITY_FX.strike;

/** A change that lands at `at` ms into the beat (HP, a knock-down, an
 *  effect) — the screen applies them on time, the FX layer draws them. */
export interface Impact {
  at: number;
  event: KontraEvent;
  /** When a projectile for this impact leaves the actor (shots only). */
  launch?: number;
}

export interface BeatPlan {
  /** Ultimate cut-in before the action. */
  intro: number;
  impacts: Impact[];
  duration: number;
}

const FLIGHT: Partial<Record<FxStyle, number>> = { shot: 330, flip: 330, lob: 520, pierce: 380, card: 420 };

/** Timings of a beat at speed ×1 (ms). Pure — the tests pin them down. */
export function planBeat(beat: Beat): BeatPlan {
  if (beat.kind !== "action") {
    const impacts = beat.events.map((event, i) => ({ at: 260 + i * 60, event }));
    return { intro: 0, impacts, duration: 760 };
  }
  const fx = fxOf(beat.ability);
  const intro = beat.ult ? 1100 : 0;
  const windup = beat.ability === "strike" ? 160 : 420; // the banner reads first
  const flight = FLIGHT[fx.style];
  const start = intro + windup + (fx.style === "flip" ? 260 : 0);
  const impacts: Impact[] = [];
  let shot = 0;
  let last = start;
  for (const event of beat.events) {
    if ((event.kind === "hit" || event.kind === "miss") && event.actor === beat.actor && flight !== undefined) {
      const launch = start + shot * 210;
      last = launch + flight;
      impacts.push({ at: last, event, launch });
      shot += 1;
    } else if (event.kind === "hit" || event.kind === "miss") {
      // dash / slam / offside: the contact time
      last = start + (fx.style === "dash" ? 300 : fx.style === "slam" ? 280 : 200) + shot * 90;
      impacts.push({ at: last, event });
      shot += 1;
    } else {
      // effects, heals, downs follow the last contact
      const at = event.kind === "down" ? last + 120 : Math.max(last, start + 200);
      impacts.push({ at, event });
    }
  }
  const tail = beat.ult ? 700 : 480;
  return { intro, impacts, duration: Math.max(last, start + 300) + tail };
}

/** What the screen shows for a fighter while the log plays. */
export interface ShownUnit {
  hp: number;
  alive: boolean;
  effects: { code: string; label: string; turns: number }[];
}
export type Shown = Record<string, ShownUnit>;

export function snapshot(units: KontraUnit[], fresh = false): Shown {
  return Object.fromEntries(units.map((u) => [u.id, fresh
    ? { hp: u.max_hp, alive: true, effects: [] }
    : { hp: u.hp, alive: u.alive, effects: u.effects }]));
}

export const EFFECT_ICON: Record<string, string> = {
  stun: "💫", yellow: "🟨", slow: "🐢", shield: "🛡️", taunt: "📣", blind: "🚩", injury: "🩹", haste: "⚡",
};

export const EFFECT_LABEL: Record<string, string> = {
  stun: "Оглушение", yellow: "Жёлтая карточка", slow: "Замедление", shield: "Щит",
  taunt: "Провокация", blind: "Офсайд", injury: "Травма", haste: "Ускорение",
};

/** Applies one landed event to the shown state. `team` / `foes` targets
 *  are resolved against the actor's side. */
export function applyImpact(shown: Shown, e: KontraEvent, units: KontraUnit[], actorSide?: string): Shown {
  const next = { ...shown };
  const set = (id: string, patch: Partial<ShownUnit>) => {
    if (next[id]) next[id] = { ...next[id], ...patch };
  };
  const addEffect = (id: string, code: string) => {
    const cur = next[id];
    if (!cur || !cur.alive || cur.effects.some((x) => x.code === code)) return;
    set(id, { effects: [...cur.effects, { code, label: EFFECT_LABEL[code] ?? code, turns: 2 }] });
  };
  const side = (s?: string) => units.filter((u) => u.side === s).map((u) => u.id);
  const other = actorSide === "me" ? "foe" : "me";
  switch (e.kind) {
    case "hit":
      if (e.target) {
        set(e.target, { hp: e.hp ?? next[e.target]?.hp ?? 0 });
        // a shield that took the whole blow may be gone — the final state fixes it
      }
      break;
    case "tick":
    case "heal":
      if (e.target) set(e.target, { hp: e.hp ?? next[e.target]?.hp ?? 0 });
      break;
    case "down":
      if (e.target) set(e.target, { hp: 0, alive: false, effects: [] });
      break;
    case "effect": {
      const ids = e.target === "team" ? side(actorSide) : e.target === "foes" ? side(other) : e.target ? [e.target] : [];
      if (e.effect === "cleanse") {
        for (const id of ids) {
          const cur = next[id];
          if (cur) set(id, { effects: cur.effects.filter((x) => x.code === "shield" || x.code === "taunt" || x.code === "haste") });
        }
      } else if (e.effect) {
        for (const id of ids) addEffect(id, e.effect);
        if (e.effect === "taunt" && e.target) addEffect(e.target, "shield");
      }
      break;
    }
    default:
      break;
  }
  return next;
}

/** Where fighters stand on the pitch, in % of the stage. Your squad along
 *  the bottom, the opponent along the top (smaller — further away). */
export interface Spot { x: number; y: number; w: number }

export function spots(units: KontraUnit[]): Record<string, Spot> {
  const out: Record<string, Spot> = {};
  for (const side of ["me", "foe"] as const) {
    const list = units.filter((u) => u.side === side);
    const n = list.length;
    list.forEach((u, i) => {
      if (u.role === "boss") {
        out[u.id] = { x: 50, y: 29, w: 40 };
        return;
      }
      const d = i - (n - 1) / 2;
      const gap = n >= 5 ? 18.5 : n === 4 ? 21 : 24;
      out[u.id] = side === "me"
        ? { x: 50 + d * gap, y: 72 + Math.abs(d) * 2.4, w: 16 }
        : { x: 50 + d * (gap * 0.84), y: 31 - Math.abs(d) * 2, w: 12.5 };
    });
  }
  return out;
}
