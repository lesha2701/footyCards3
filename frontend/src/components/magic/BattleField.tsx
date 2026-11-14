import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";

import type { MagicActInput } from "@/api/magic";
import Coach, { type CoachStep } from "@/components/magic/Coach";
import StackToken from "@/components/magic/StackToken";
import { useCoach } from "@/components/magic/useCoach";
import { battleArt, obstacleArt, uiArt } from "@/components/magic/art/pngArt";
import { ROMAN, describeEvent } from "@/components/magic/magicMeta";
import { sfx } from "@/components/magic/sound";
import { haptic } from "@/lib/telegram";
import type { MagicBattle, MagicEvent, MagicSpell, MagicStack } from "@/types";

const W = 10;
const H = 10;
// Bigger creatures stand bigger on the pitch (the boss biggest of all).
const TIER_SIZE: Record<number, number> = { 1: 38, 2: 41, 3: 44, 4: 50, 5: 56 };
const SHOWN = new Set(["start", "move", "hit", "shoot", "retaliate", "spell", "heal", "down", "rebirth", "cast", "defend", "round", "wait", "lucky", "morale", "hypno", "hypno_end", "hook", "ward"]);

// What a spell looks like when it lands on a stack.
const SPELL_FX: Record<string, { glyph: string; ring: string; fall?: boolean; rise?: boolean; beam?: boolean }> = {
  sunstrike: { glyph: "⚡", ring: "rgba(253,224,71,0.9)", beam: true },
  firerain: { glyph: "☄️", ring: "rgba(249,115,22,0.9)", fall: true },
  bless: { glyph: "✨", ring: "rgba(253,230,138,0.95)", rise: true },
  wall: { glyph: "🛡️", ring: "rgba(186,230,253,0.95)" },
  curse: { glyph: "💜", ring: "rgba(192,132,252,0.95)" },
  raise: { glyph: "💚", ring: "rgba(134,239,172,0.95)", rise: true },
};
type Fx = { n: number; target: string; kind: "spell" | "flash" | "skulls"; spell?: string; killed?: number };

const BATTLE_COACH: CoachStep[] = [
  { icon: "⚔️", title: "Бой по очереди", text: "Отряды ходят по одному — быстрые первыми. Тот, чей ход, светится золотом, а под полем написано «твой ход»." },
  { icon: "👣", title: "Шаг", text: "Выделенные клетки — куда отряд может дойти. Нажми клетку, и он пойдёт. Подсказка над полем скажет, какие клетки нажимать." },
  { icon: "🟥", title: "Атака", text: "Враг в красном кольце — нажми его, и отряд подбежит и ударит. Враг ответит один раз за раунд." },
  { icon: "🎯", title: "Стрелки", text: "У стрелков 🏹 враги в жёлтом кольце — выстрел издалека, без ответного удара." },
  { icon: "🚧", title: "Укрытия и ожидание", text: "Конусы, скамейки, ворота, болото и лаву на поле не пройти — прячь за ними стрелков. «Ждать» отправит отряд в конец очереди раунда: пусть враг подойдёт сам." },
  { icon: "🍀", title: "Удача и дух", text: "Иногда удар выходит двойным, а отряд ходит ещё раз. Карточки из одного клуба усиливают и то и другое — это химия." },
  { icon: "🛡️", title: "Оборона", text: "«Оборона» — отряд стоит на месте и до конца раунда получает на четверть меньше урона. Хорошо для стенки перед стрелками." },
  { icon: "ⓘ", title: "Карточка отряда", text: "Плашка под полем — карточка того, кто ходит: сила, здоровье, капитан и умение. Нажми свой отряд или врага, до которого не достать, — откроется его карточка." },
  { icon: "🪄", title: "Магия и автобой", text: "Заклинания тратят ману героя — один раз за раунд. Не хочешь думать — жми «Автобой», армия доиграет сама." },
];

// The first fight on the Lost pitch (a lair or Безликий): who they are.
const LAIR_COACH: CoachStep[] = [
  { icon: "🎭", title: "Логово Потерявших", text: "Потерявшие всё — сильные одиночки разных уровней. Запасных приходит толпа, а Отца и Мстителя — всего несколько, но каждый огромный." },
  { icon: "⛓️", title: "Их умения", text: "Мститель притягивает цепью, Банкрот ослабляет удар, Вдова поднимает павших, Отец бьёт сильнее с каждой потерей. Нажми врага, до которого не достаёшь, — прочитаешь его умение." },
  { icon: "👁️", title: "Гипноз", text: "Безликий переманивает твой сильнейший отряд на 2 раунда. Оберег святилища сгорит вместо этого — один раз." },
];

type Pos = Record<string, { x: number; y: number; count: number }>;

function snapshot(units: MagicStack[]): Pos {
  return Object.fromEntries(units.map((u) => [u.id, { x: u.x ?? 0, y: u.y ?? 0, count: u.count }]));
}

// The field's ground by the map's biome (a painted picture when there is one).
const GROUND: Record<string, string> = {
  meadow: "radial-gradient(ellipse at 50% 40%, #3f6212 0%, #1a2e05 70%, #0b1402 100%)",
  desert: "radial-gradient(ellipse at 50% 40%, #a16207 0%, #57340a 70%, #2a1904 100%)",
  snow: "radial-gradient(ellipse at 50% 40%, #64748b 0%, #334155 70%, #0f172a 100%)",
  ash: "radial-gradient(ellipse at 50% 40%, #44302a 0%, #1f1512 70%, #0b0706 100%)",
  lair: "radial-gradient(ellipse at 50% 40%, #3b1d5c 0%, #1a0d2b 70%, #0a0612 100%)",
};

// Night pitches (the Lost lair): the picture carries its own markings, so ours are not
// drawn over them; it is lifted a little, and the reachable cells glow light, not dark.
const NIGHT: Record<string, string> = { lair: "brightness(1.6) saturate(1.15)" };


/** The 10×10 battle field (a football pitch) of square cells. Plays the server's event log step by step (moves,
 *  hits, spells), then lets the player act with the stack whose turn it is. Tells the page
 *  while it is replaying, so results wait for the replay. */
export default function BattleField({ battle, events, version, spells, mana, busy, onAct, onCast, onAuto, biome = "meadow", onReplay }: {
  battle: MagicBattle;
  events: MagicEvent[];
  version: number;
  spells: MagicSpell[];
  mana: number;
  busy: boolean;
  onAct: (input: MagicActInput) => void;
  onCast: (spell: string, target: string | null) => void;
  onAuto: () => void;
  biome?: string;
  onReplay?: (playing: boolean) => void;
}) {
  const [shown, setShown] = useState<Pos>(() => snapshot(battle.units));
  const [queue, setQueue] = useState<MagicEvent[]>([]);
  const [ticker, setTicker] = useState<string | null>(null);
  const [float, setFloat] = useState<{ id: string; text: string; heal: boolean; n: number } | null>(null);
  const [acting, setActing] = useState<string | null>(null);
  // The attacker lunges towards its target; flashes, skulls and spell effects land on stacks.
  const [lunge, setLunge] = useState<{ id: string; dx: number; dy: number; n: number } | null>(null);
  const [fx, setFx] = useState<Fx[]>([]);
  const shownRef = useRef(shown);
  shownRef.current = shown;
  const [speed, setSpeed] = useState<1 | 2 | 4>(1);
  const [spell, setSpell] = useState<MagicSpell | null>(null);
  const [inspect, setInspect] = useState<string | null>(null);
  const [magicOpen, setMagicOpen] = useState(false);
  const seen = useRef(version);
  const coach = useCoach("magic_coach_battle_v2");
  const lairCoach = useCoach("magic_coach_lair_v1");

  const units = useMemo(() => new Map(battle.units.map((u) => [u.id, u])), [battle.units]);

  // A new server answer: queue its events (a battle that just started begins from its opening positions).
  useEffect(() => {
    if (seen.current === version && queue.length === 0 && events.length === 0) return;
    seen.current = version;
    const start = events.find((e) => e.kind === "start") as (MagicEvent & { units?: Record<string, [number, number, number]> }) | undefined;
    if (start?.units) {
      setShown(Object.fromEntries(Object.entries(start.units).map(([id, [x, y, count]]) => [id, { x, y, count }])));
    }
    const list = events.filter((e) => SHOWN.has(e.kind));
    setTicker(null); // a stale line from the previous answer would read as if it just happened
    if (list.length) setQueue(list);
    else setShown(snapshot(battle.units));
    setSpell(null);
  }, [version]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!queue.length) {
      setShown(snapshot(battle.units));
      setActing(null);
      return;
    }
    const [e, ...rest] = queue;
    const delay = (e.kind === "move" ? 300 : e.kind === "round" || e.kind === "start" ? 450 : 520) / speed;
    const t = setTimeout(() => {
      const line = describeEvent(e, units);
      if (line) setTicker(line);
      setActing(e.src && e.src !== "hero" ? e.src : null);
      setShown((s) => {
        const next = { ...s };
        if (e.kind === "move" && e.src && next[e.src]) next[e.src] = { ...next[e.src], x: e.x!, y: e.y! };
        if (e.target && e.count !== undefined && next[e.target]) next[e.target] = { ...next[e.target], count: e.count };
        return next;
      });
      if (e.target && (e.kind === "hit" || e.kind === "shoot" || e.kind === "retaliate" || e.kind === "spell")) {
        setFloat({ id: e.target, text: `−${e.damage}`, heal: false, n: e.n });
        haptic(e.killed ? "medium" : "light");
        const add: Fx[] = [{ n: e.n, target: e.target, kind: "flash" }];
        if (e.killed) add.push({ n: e.n + 0.5, target: e.target, kind: "skulls", killed: e.killed });
        setFx((f) => [...f.slice(-8), ...add]);
        sfx(e.kind === "shoot" ? "shoot" : "hit");
      }
      if ((e.kind === "hit" || e.kind === "retaliate") && e.src && e.target) {
        const a = shownRef.current[e.src];
        const b = shownRef.current[e.target];
        if (a && b) setLunge({ id: e.src, dx: Math.sign(b.x - a.x), dy: Math.sign(b.y - a.y), n: e.n });
      }
      if (e.kind === "cast" && e.spell) {
        const targets = e.targets ?? [];
        setFx((f) => [...f.slice(-8), ...targets.map((t, i) => ({ n: e.n + i / 100, target: t, kind: "spell" as const, spell: e.spell }))]);
        sfx("spell");
      }
      if (e.kind === "lucky" || e.kind === "morale") sfx("bonus");
      if (e.target && e.kind === "heal") setFloat({ id: e.target, text: `+${e.amount}`, heal: true, n: e.n });
      setQueue(rest);
    }, delay);
    return () => clearTimeout(t);
  }, [queue, speed, units, battle.units]);

  const playing = queue.length > 0;
  useEffect(() => { onReplay?.(playing); }, [playing]); // eslint-disable-line react-hooks/exhaustive-deps
  const field = battle.pitch ?? biome; // a Lost lair and Безликий have their own pitch
  const ground = battleArt(field);
  const night = !!NIGHT[field];
  const canAct = battle.can_act && !playing && !busy;
  const active = canAct && battle.turn_of ? units.get(battle.turn_of) ?? null : null;
  const moveSet = new Set(canAct ? battle.move_cells.map(([x, y]) => `${x},${y}`) : []);
  const attackMap = new Map(canAct ? battle.attack_targets.map((t) => [t.target, t.cells]) : []);
  const shootSet = new Set(canAct ? battle.shoot_targets : []);

  const tapUnit = (u: MagicStack) => {
    if (spell && canAct) {
      const ally = u.side === "me";
      if ((spell.target === "ally" && ally) || (spell.target === "enemy" && !ally)) {
        onCast(spell.code, u.id);
        setSpell(null);
        return;
      }
    }
    if (canAct && active && u.side !== "me") {
      if (shootSet.has(u.id)) return onAct({ unit: active.id, action: "shoot", target: u.id });
      const cells = attackMap.get(u.id);
      if (cells?.length) return onAct({ unit: active.id, action: "attack", target: u.id, x: cells[0][0], y: cells[0][1] });
    }
    setInspect(u.id);
  };

  const focus = active;
  const inspected = inspect ? units.get(inspect) ?? null : null;
  const hint = !active || spell
    ? null
    : active.ranged && battle.shoot_targets.length
      ? `Нажми врага — выстрел 🎯, или ${night ? "светлую" : "тёмную"} клетку — шаг`
      : `${night ? "Светлая" : "Тёмная"} клетка — идти, красный враг — атаковать`;
  const ballArt = uiArt("magic_ball");
  const finished = !!battle.winner && !playing;

  return (
    <div className="flex h-full min-h-0 flex-col gap-1.5">
      <div className="flex shrink-0 items-center justify-between text-micro text-ink-mist">
        <span className="truncate">⚔️ {battle.foe_name}</span>
        <span className="flex items-center gap-2">
          Раунд {Math.min(battle.round, battle.max_rounds)}{battle.foe_mana !== null ? ` · мана врага ${battle.foe_mana}` : ""}
          <button onClick={coach.show} className="flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-xs font-black text-amber-200" aria-label="Как играть">?</button>
        </span>
      </div>

      {/* The field: the whole width, a fixed square — nothing below it changes its size. */}
      <div className="-mx-2 flex min-h-0 flex-1 items-center justify-center" style={{ containerType: "size" }}>
      <div
        className="relative overflow-hidden"
        style={{
          aspectRatio: `${W} / ${H}`,
          width: "min(100cqw, 100cqh)",
          background: ground && !night ? `center / cover no-repeat url(${ground})` : GROUND[field] ?? GROUND.meadow,
        }}
      >
        {ground && night && (
          <div className="pointer-events-none absolute inset-0"
            style={{ background: `center / cover no-repeat url(${ground})`, filter: NIGHT[field] }} />
        )}
        {/* Pitch markings: halfway line, centre circle, boxes and goals at both ends */}
        {!(ground && night) && <svg className="pointer-events-none absolute inset-1" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
          fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth={0.06}>
          <rect x={0.04} y={0.04} width={W - 0.08} height={H - 0.08} />
          <line x1={W / 2} y1={0} x2={W / 2} y2={H} />
          <circle cx={W / 2} cy={H / 2} r={1.4} />
          <circle cx={W / 2} cy={H / 2} r={0.08} fill="rgba(255,255,255,0.55)" />
          {[0, 1].map((side) => {
            const at = (d: number) => (side ? W - d : d);
            return (
              <g key={side}>
                <polyline points={`${at(0)},${H / 2 - 3} ${at(2)},${H / 2 - 3} ${at(2)},${H / 2 + 3} ${at(0)},${H / 2 + 3}`} />
                <polyline points={`${at(0)},${H / 2 - 1.5} ${at(1)},${H / 2 - 1.5} ${at(1)},${H / 2 + 1.5} ${at(0)},${H / 2 + 1.5}`} />
                <circle cx={at(1.5)} cy={H / 2} r={0.07} fill="rgba(255,255,255,0.55)" />
                <path d={`M ${at(2)} ${H / 2 - 1.1} A 1.4 1.4 0 0 ${side ? 0 : 1} ${at(2)} ${H / 2 + 1.1}`} />
                <rect x={side ? W - 0.22 : 0} y={H / 2 - 0.8} width={0.22} height={1.6} fill="rgba(255,255,255,0.35)" strokeWidth={0.04} />
              </g>
            );
          })}
        </svg>}
        {/* Field cells: only a faint grid; the cells a stack can reach are shaded, as in Heroes */}
        <div className="absolute inset-1 grid gap-0" style={{ gridTemplateColumns: `repeat(${W}, 1fr)`, gridTemplateRows: `repeat(${H}, 1fr)` }}>
          {Array.from({ length: H }, (_, y) =>
            Array.from({ length: W }, (_, x) => {
              const k = `${x},${y}`;
              const canMove = moveSet.has(k) && !spell;
              return (
                <button
                  key={k}
                  disabled={!canMove}
                  onClick={() => active && onAct({ unit: active.id, action: "move", x, y })}
                  className={night
                    ? `border-[0.5px] border-white/[0.07] ${canMove ? "bg-violet-200/[0.13] shadow-[inset_0_0_0_1px_rgba(237,233,254,0.25)] active:bg-violet-200/30" : ""}`
                    : `border-[0.5px] border-white/[0.12] ${canMove ? "bg-black/25 active:bg-black/40" : ""}`}
                />
              );
            }),
          )}
        </div>
        {/* Rocks and trees: cover */}
        <div className="pointer-events-none absolute inset-1">
          {(battle.rocks ?? []).map(([x, y, kind]) => {
            const art = obstacleArt(kind);
            return (
              <span key={`r${x},${y}`} className="absolute flex items-center justify-center text-[18px]"
                style={{ left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%`, width: `${100 / W}%`, height: `${100 / H}%` }}>
                {art ? <img src={art} alt="" className="h-[112%] w-[112%] max-w-none object-contain" draggable={false} />
                  : kind === "tree" ? "🌳" : "🪨"}
              </span>
            );
          })}
        </div>
        {/* Stacks */}
        <div className="pointer-events-none absolute inset-1">
          {battle.units.map((u) => {
            const p = shown[u.id];
            if (!p) return null;
            const dead = p.count <= 0;
            const targetable = canAct && !dead && ((u.side !== "me" && (shootSet.has(u.id) || attackMap.has(u.id)) && !spell)
              || (spell && ((spell.target === "ally" && u.side === "me") || (spell.target === "enemy" && u.side !== "me"))));
            const isActive = active?.id === u.id || acting === u.id;
            return (
              <motion.button
                key={u.id}
                onClick={() => tapUnit(u)}
                disabled={dead}
                className="pointer-events-auto absolute flex items-center justify-center"
                style={{ width: `${100 / W}%`, height: `${100 / H}%` }}
                initial={false}
                animate={{
                  left: `${(p.x / W) * 100}%`, top: `${(p.y / H) * 100}%`, opacity: dead ? 0 : 1, scale: acting === u.id ? 1.12 : 1,
                  x: lunge?.id === u.id ? [0, lunge.dx * 16, 0] : 0, y: lunge?.id === u.id ? [0, lunge.dy * 10, 0] : 0,
                }}
                transition={{ type: "spring", stiffness: 170, damping: 20, x: { duration: 0.28 / speed }, y: { duration: 0.28 / speed } }}
              >
                {fx.filter((f) => f.target === u.id).map((f) => <FxLayer key={f.n} fx={f} speed={speed} onDone={() => setFx((all) => all.filter((x) => x.n !== f.n))} />)}
                {targetable && (
                  <span className={`absolute inset-0.5 animate-pulse rounded-full ring-2 ${
                    spell ? "ring-sky-300" : shootSet.has(u.id) ? "ring-amber-300" : "ring-red-400"
                  }`} />
                )}
                {shootSet.has(u.id) && targetable && !spell && <span className="absolute -top-1 right-0 text-xs">🎯</span>}
                <StackToken
                  unit={u.unit} tier={u.tier} count={p.count} image={u.card?.image_path} foe={u.side !== "me"}
                  size={u.unit === "lost_victor" ? 66 : (TIER_SIZE[u.tier] ?? 44)} active={isActive} bare
                />
                {u.effects.length > 0 && !dead && (
                  <span className="absolute -bottom-0.5 -left-0.5 text-[9px]">{u.effects.map((e) => (e.code === "curse" ? "💜" : e.code === "wall" ? "🛡" : e.code === "hypno" ? "🌀" : "✨")).join("")}</span>
                )}
                <AnimatePresence>
                  {float?.id === u.id && (
                    <motion.span
                      key={float.n}
                      className={`absolute -top-2 z-20 font-display text-sm font-black drop-shadow-[0_2px_3px_rgba(0,0,0,0.9)] ${float.heal ? "text-emerald-300" : "text-white"}`}
                      initial={{ y: 4, opacity: 0, scale: 0.8 }}
                      animate={{ y: -12, opacity: [0, 1, 1, 0], scale: [0.8, 1.3, 1] }}
                      transition={{ duration: 0.8 / speed }}
                    >
                      {float.text}
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.button>
            );
          })}
        </div>
        {/* A spell picked: the target comes next, on the field. */}
        {spell && active && (
          <div className="absolute inset-x-0 top-1 z-30 flex justify-center">
            <button onClick={() => setSpell(null)} className="rounded-full bg-sky-300 px-3 py-1 text-micro font-black text-black shadow-lg">
              🪄 «{spell.name}»: нажми {spell.target === "ally" ? "свой отряд" : "отряд врага"} · ✕
            </button>
          </div>
        )}
        <div className="pointer-events-none absolute inset-x-0 bottom-1 flex justify-center">
          <AnimatePresence mode="wait">
            {!finished && (playing ? ticker : hint) && (
              <motion.p key={playing ? ticker : hint} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className={`max-w-[94%] truncate rounded-full bg-black/65 px-3 py-0.5 text-center text-caption font-bold ${playing ? "text-amber-200" : "text-ink-chalk"}`}>
                {playing ? ticker : hint}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </div>
      </div>

      {/* One bar of a fixed height under the field: whose turn it is and what to do. */}
      {!finished && (
        <div className="flex shrink-0 flex-col gap-1.5">
          <button
            onClick={() => focus && setInspect(focus.id)}
            disabled={!focus}
            className="flex h-[52px] items-center gap-2 rounded-2xl bg-bg-surface px-3 text-left active:scale-[0.99]"
          >
            {focus ? (
              <>
                <StackToken unit={focus.unit} tier={focus.tier} count={shown[focus.id]?.count ?? focus.count} image={focus.card?.image_path} foe={focus.side !== "me"} size={38} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-bold text-ink-chalk">
                    {focus.unit_name} <span className="text-ink-mist-dim">{ROMAN[focus.tier]}</span>
                    <span className="ml-1 text-amber-300">— твой ход</span>
                  </span>
                  <span className="block font-mono text-micro text-ink-mist">
                    ⚔{focus.atk} 🛡{focus.defence} ❤{focus.hp} 🏃{focus.spd}{focus.ranged ? " 🏹" : ""}{focus.flying ? " 🪽" : ""}
                  </span>
                </span>
                <span className="text-micro text-ink-mist-dim">ⓘ</span>
              </>
            ) : (
              <span className="w-full text-center text-xs text-ink-mist">{playing ? "Идёт ход…" : "Ход врага…"}</span>
            )}
          </button>

          {playing ? (
            <div className="grid h-14 grid-cols-2 gap-1.5">
              <button onClick={() => setSpeed(speed === 1 ? 2 : speed === 2 ? 4 : 1)} className="rounded-2xl bg-white/10 text-xs font-bold text-ink-chalk active:scale-95">
                ⏩ Скорость ×{speed}
              </button>
              <button onClick={() => setQueue([])} className="rounded-2xl bg-amber-400 text-xs font-black text-black active:scale-95">
                ⏭ К итогу
              </button>
            </div>
          ) : (
            <div className="grid h-14 grid-cols-4 gap-1.5">
              <button
                onClick={() => setMagicOpen(true)}
                disabled={!active || spells.length === 0}
                aria-label="Магия"
                className="relative flex items-center justify-center rounded-2xl bg-indigo-950 ring-1 ring-indigo-300/40 active:scale-95 disabled:opacity-35"
              >
                {ballArt ? (
                  <img src={ballArt} alt="" className="h-11 w-11 object-contain" />
                ) : (
                  <motion.span className="text-3xl drop-shadow-[0_0_10px_rgba(167,139,250,0.95)]"
                    animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 9, ease: "linear" }}>⚽</motion.span>
                )}
                <span className="absolute -right-1 -top-1 rounded-full bg-indigo-300 px-1.5 font-mono text-[10px] font-black text-black">✨{mana}</span>
              </button>
              <button
                onClick={() => active && onAct({ unit: active.id, action: "defend" })}
                disabled={!active}
                className="flex flex-col items-center justify-center rounded-2xl bg-white/5 text-micro font-semibold text-ink-chalk active:scale-95 disabled:opacity-35"
              >
                <span className="text-lg">🛡</span>Оборона
              </button>
              <button
                onClick={() => active && onAct({ unit: active.id, action: "wait" })}
                disabled={!active}
                className="flex flex-col items-center justify-center rounded-2xl bg-white/5 text-micro font-semibold text-ink-chalk active:scale-95 disabled:opacity-35"
              >
                <span className="text-lg">⏳</span>Ждать
              </button>
              <button onClick={() => { setSpeed(2); onAuto(); }} disabled={battle.auto || busy} className="flex flex-col items-center justify-center rounded-2xl bg-white/5 text-micro font-semibold text-ink-chalk active:scale-95 disabled:opacity-35">
                <span className="text-lg">⚡</span>Автобой
              </button>
            </div>
          )}
        </div>
      )}

      <Coach open={coach.open && !finished} steps={BATTLE_COACH} onClose={coach.close} />
      <Coach open={!coach.open && lairCoach.open && battle.pitch === "lair" && !finished} steps={LAIR_COACH} onClose={lairCoach.close} />

      {/* Popups: the magic ball's spells, a stack's full card. */}
      <AnimatePresence>
        {magicOpen && (
          <Popup key="magic" onClose={() => setMagicOpen(false)}>
            <p className="text-center font-display text-base font-black text-indigo-100">🪄 Магия героя</p>
            <p className="mb-2 text-center text-micro text-ink-mist">
              ✨ {mana} маны · {battle.can_cast ? "одно заклинание за раунд" : "в этом раунде уже колдовал"}
            </p>
            <div className="flex flex-col gap-1.5">
              {spells.map((s) => {
                const ok = battle.can_cast && mana >= s.cost;
                return (
                  <button
                    key={s.code}
                    disabled={!ok}
                    onClick={() => {
                      setMagicOpen(false);
                      if (s.target === "all_enemies") onCast(s.code, null);
                      else setSpell(s);
                    }}
                    className="flex items-center gap-3 rounded-2xl bg-indigo-500/20 px-3 py-2 text-left ring-1 ring-indigo-300/30 active:scale-[0.98] disabled:opacity-40"
                  >
                    <span className="text-2xl">{SPELL_FX[s.code]?.glyph ?? "🪄"}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-bold text-ink-chalk">{s.name}</span>
                      <span className="block text-micro leading-snug text-ink-mist">{s.description}</span>
                    </span>
                    <span className="shrink-0 rounded-full bg-indigo-300 px-2 py-0.5 font-mono text-micro font-black text-black">{s.cost}</span>
                  </button>
                );
              })}
            </div>
          </Popup>
        )}
        {inspected && (
          <Popup key="inspect" onClose={() => setInspect(null)}>
            <div className="flex items-center gap-3">
              <StackToken unit={inspected.unit} tier={inspected.tier} count={shown[inspected.id]?.count ?? inspected.count} image={inspected.card?.image_path} foe={inspected.side !== "me"} size={64} />
              <div className="min-w-0 flex-1">
                <p className="text-base font-black text-ink-chalk">{inspected.unit_name} <span className="text-ink-mist-dim">{ROMAN[inspected.tier]}</span></p>
                {inspected.card && <p className="truncate text-xs text-ink-mist">{inspected.name}</p>}
                <p className="text-micro text-ink-mist-dim">{inspected.side === "me" ? "Твой отряд" : "Враг"}</p>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-1.5 text-center font-mono text-xs text-ink-chalk">
              <span className="rounded-xl bg-white/5 py-1.5">⚔ {inspected.atk}<span className="block text-[9px] text-ink-mist">атака</span></span>
              <span className="rounded-xl bg-white/5 py-1.5">🛡 {inspected.defence}<span className="block text-[9px] text-ink-mist">защита</span></span>
              <span className="rounded-xl bg-white/5 py-1.5">❤ {inspected.hp}<span className="block text-[9px] text-ink-mist">здоровье</span></span>
              <span className="rounded-xl bg-white/5 py-1.5">💥 {inspected.dmin}–{inspected.dmax}<span className="block text-[9px] text-ink-mist">урон</span></span>
              <span className="rounded-xl bg-white/5 py-1.5">🏃 {inspected.spd}<span className="block text-[9px] text-ink-mist">скорость</span></span>
              <span className="rounded-xl bg-white/5 py-1.5">{inspected.ranged ? "🏹" : inspected.flying ? "🪽" : "👣"}<span className="block text-[9px] text-ink-mist">{inspected.ranged ? "стрелок" : inspected.flying ? "летает" : "пеший"}</span></span>
            </div>
            {(inspected.ability_text || inspected.trait) && (
              <p className="mt-2 text-xs leading-snug text-ink-mist">{[inspected.ability_text, inspected.trait].filter(Boolean).join(" · ")}</p>
            )}
          </Popup>
        )}
      </AnimatePresence>
    </div>
  );
}


/** One effect on a stack: a hit flash, falling skulls for the fallen, or a spell. */
function FxLayer({ fx, speed, onDone }: { fx: Fx; speed: number; onDone: () => void }) {
  const dur = (fx.kind === "spell" ? 0.9 : 0.6) / speed;
  useEffect(() => {
    const t = setTimeout(onDone, dur * 1000 + 80);
    return () => clearTimeout(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (fx.kind === "flash") {
    return (
      <motion.span className="pointer-events-none absolute inset-1 z-10 rounded-full bg-white mix-blend-screen"
        initial={{ opacity: 0.85, scale: 0.7 }} animate={{ opacity: 0, scale: 1.25 }} transition={{ duration: dur }} />
    );
  }
  if (fx.kind === "skulls") {
    return (
      <motion.span className="pointer-events-none absolute bottom-0 z-20 whitespace-nowrap font-display text-[11px] font-black text-red-300 drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]"
        initial={{ y: 0, opacity: 1 }} animate={{ y: 18, opacity: 0 }} transition={{ duration: dur * 1.6, ease: "easeIn" }}>
        💀×{fx.killed}
      </motion.span>
    );
  }
  const s = SPELL_FX[fx.spell ?? ""] ?? { glyph: "✨", ring: "rgba(255,255,255,0.9)" };
  return (
    <>
      {s.beam && (
        <motion.span className="pointer-events-none absolute -top-24 bottom-1/2 left-1/2 z-20 w-2 -translate-x-1/2 rounded-full bg-gradient-to-b from-transparent via-yellow-200 to-white"
          initial={{ opacity: 0, scaleY: 0.2 }} animate={{ opacity: [0, 1, 0], scaleY: 1 }} transition={{ duration: dur }} style={{ originY: 1 }} />
      )}
      <motion.span className="pointer-events-none absolute inset-0 z-10 rounded-full"
        style={{ boxShadow: `0 0 18px 6px ${s.ring}, inset 0 0 12px ${s.ring}` }}
        initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: [0, 1, 0], scale: [0.6, 1.1, 1.2] }} transition={{ duration: dur }} />
      <motion.span className="pointer-events-none absolute z-20 text-xl"
        initial={{ y: s.fall ? -40 : s.rise ? 6 : 0, opacity: 0, scale: 0.6 }}
        animate={{ y: s.fall ? 0 : s.rise ? -22 : -6, opacity: [0, 1, 0], scale: [0.6, 1.3, 1] }}
        transition={{ duration: dur }}>
        {s.glyph}
      </motion.span>
    </>
  );
}


/** A bottom popup over the battle, closed by a tap outside. */
function Popup({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <motion.div className="fixed inset-0 z-40 flex items-end justify-center bg-black/55" onClick={onClose}
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <motion.div
        className="safe-bottom w-full max-w-md rounded-t-3xl bg-bg-surface px-4 pb-4 pt-3"
        onClick={(e) => e.stopPropagation()}
        initial={{ y: 60 }} animate={{ y: 0 }} exit={{ y: 60 }} transition={{ type: "spring", stiffness: 320, damping: 30 }}
      >
        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-white/20" />
        {children}
      </motion.div>
    </motion.div>
  );
}
