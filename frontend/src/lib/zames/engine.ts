/**
 * «Замес» — a pure beat 'em up engine: one fan against waves of rivals.
 *
 * Plain data + `step(state, dt, inputs)`, no DOM, a seeded generator — the
 * same seed and inputs always play the same fight (tests rely on it). The
 * arena is a single screen seen from the side: `x` 0…ARENA_W left→right,
 * `z` 0…ARENA_D near→far (the floor's depth), `y` the height above the floor.
 * The renderer (components/zames) only reads the state and drains `events`.
 *
 * The server can't see this fight: it pays by the clock-bounded number of
 * cleared waves (backend zames_service), so nothing here touches coins.
 */

export const ARENA_W = 100;
export const ARENA_D = 30;
export const DERBY_WAVES = 6; // 5 waves + the boss

export type Mode = "derby" | "endless";
export type Kind = "hero" | "runt" | "brute" | "drummer" | "loud" | "kuzmich" | "chair" | "boss" | "sinyak";
/** What flies: a bottle (Синяк), a stadium seat (Креслолом), a spit (Кузьмич). */
export type ShotKind = "bottle" | "chair" | "spit";
export type Act =
  | "idle" | "walk" | "p1" | "p2" | "p3" | "kick" | "spin" | "sweep" | "block" | "rage"
  | "windup" | "strike" | "shout" | "drum" | "slam" | "charge" | "hurt" | "air" | "down" | "getup" | "ko" | "cheer";

export type Input =
  | { k: "tap"; x: number; z: number; target?: number }
  | { k: "kick"; dir: 1 | -1 }
  | { k: "spin" }
  | { k: "sweep" }
  | { k: "hold" }
  | { k: "release" }
  | { k: "rage" };

export interface Look {
  skin: string;
  shirt: string;
  stripe: string;
  hat: "beanie" | "cap" | "bald" | "hood" | "bandana";
  hatColor: string;
  hair: string;
}

export interface Fighter {
  id: number;
  kind: Kind;
  x: number;
  z: number;
  y: number;
  vx: number;
  vz: number;
  vy: number;
  face: 1 | -1;
  hp: number;
  maxHp: number;
  act: Act;
  t: number; // seconds in the current act
  dur: number; // the act's length (0 = open-ended)
  hit: number[]; // ids already hit by the current attack
  cool: number; // enemy: until the next attack may start
  token: boolean; // enemy: allowed to close in and attack
  buff: number; // enemy: drum-fired for this long
  flash: number; // white flash after a hit
  ko: boolean; // knocked out — flying away / lying for good
  out: boolean; // gone from the arena (removed next tick)
  entering: boolean; // still walking in from off-screen
  special: number; // enemy: drum / shout / summon timer
  look: Look;
  scale: number;
  counted?: boolean; // its knockout is already on the score
  calls?: number; // boss: times it called for backup
  next?: Act; // boss: the attack its wind-up leads into
  // hero only
  tx?: number;
  tz?: number;
  targetId?: number;
  holding?: boolean;
}

export type GameEvent =
  | { t: "hit"; x: number; y: number; z: number; dmg: number; heavy: boolean; by: "hero" | "enemy" }
  | { t: "block"; x: number; y: number; z: number }
  | { t: "whoosh"; x: number; z: number; kind: Act }
  | { t: "ko"; x: number; z: number; out: boolean; kind: Kind }
  | { t: "land"; x: number; z: number; heavy: boolean }
  | { t: "wave"; n: number; boss: boolean }
  | { t: "clear"; n: number }
  | { t: "combo"; n: number }
  | { t: "shout"; x: number; z: number; face: 1 | -1 }
  | { t: "drum"; x: number; z: number }
  | { t: "heal"; x: number; z: number; amount: number }
  | { t: "rage" }
  | { t: "summon"; x: number; z: number }
  | { t: "throw"; x: number; z: number; kind: ShotKind }
  | { t: "smash"; x: number; z: number; kind: ShotKind }
  | { t: "deflect"; x: number; y: number; z: number; kind: ShotKind }
  | { t: "over"; won: boolean };

export interface Pickup {
  id: number;
  x: number;
  z: number;
  heal: number;
  t: number;
}

/** A thrown thing: flies in an arc at where the hero stood; the hero's blow sends it back. */
export interface Shot {
  id: number;
  kind: ShotKind;
  x: number;
  z: number;
  y: number;
  vx: number;
  vz: number;
  vy: number;
  dmg: number;
  t: number;
  mine: boolean; // knocked back by the hero: now it hits rivals
}

export interface State {
  mode: Mode;
  seed: number;
  rng: number; // generator state
  time: number;
  nextId: number;
  hero: Fighter;
  enemies: Fighter[];
  pickups: Pickup[];
  shots: Shot[];
  wave: number; // 1-based, the wave being fought (0 before the first)
  queue: Kind[]; // still to spawn this wave
  spawnIn: number;
  pause: number; // intermission before the next wave
  banner: { text: string; sub: string; t: number } | null;
  combo: number;
  comboT: number; // since the last landed hit
  bestCombo: number;
  rage: number; // 0…100
  spinCd: number;
  buffered: Input | null;
  bufferedT: number;
  knockouts: number;
  wavesCleared: number;
  freeze: number; // hit-stop
  slow: number; // slow motion left
  shake: number;
  finished: boolean;
  won: boolean;
  overIn: number; // delay between the last blow and `finished`
  events: GameEvent[];
}

// ---------------------------------------------------------------------------
// Tuning
// ---------------------------------------------------------------------------

interface HeroMove {
  dur: number;
  from: number; // active window
  to: number;
  range: number; // reach in front (or radius for spin)
  depth: number; // |dz| that still connects
  dmg: number;
  kb: number; // knockback speed
  launch: number; // upward speed (0 = stays grounded)
  heavy?: boolean;
  around?: boolean; // hits both sides
  knockdown?: boolean;
  lunge?: number; // forward speed during the wind-up
  cancel: number; // from here the next move may start
}

export const HERO_MOVES: Record<"p1" | "p2" | "p3" | "kick" | "spin" | "sweep", HeroMove> = {
  p1: { dur: 0.24, from: 0.06, to: 0.13, range: 9, depth: 4.5, dmg: 9, kb: 7, launch: 0, cancel: 0.13 },
  p2: { dur: 0.24, from: 0.06, to: 0.13, range: 9, depth: 4.5, dmg: 10, kb: 8, launch: 0, cancel: 0.13 },
  p3: { dur: 0.38, from: 0.1, to: 0.19, range: 10, depth: 5, dmg: 15, kb: 26, launch: 13, heavy: true, lunge: 10, cancel: 0.3 },
  kick: { dur: 0.42, from: 0.12, to: 0.22, range: 12.5, depth: 5, dmg: 17, kb: 34, launch: 12, heavy: true, lunge: 22, cancel: 0.32 },
  spin: { dur: 0.52, from: 0.1, to: 0.36, range: 13.5, depth: 6.5, dmg: 21, kb: 36, launch: 19, heavy: true, around: true, cancel: 0.42 },
  sweep: { dur: 0.4, from: 0.1, to: 0.21, range: 11.5, depth: 5, dmg: 11, kb: 6, launch: 0, knockdown: true, lunge: 8, cancel: 0.3 },
};
const SPIN_COOLDOWN = 0.9;
const RAGE_DUR = 1.7;
const HERO_SPEED = 34;
const HERO_HP = 100;
const COMBO_WINDOW = 2.2;
const BUFFER_TTL = 0.4;
const GRAVITY = 46;
const WAVE_HEAL = 20;

interface EnemySpec {
  hp: number;
  speed: number;
  dmg: number;
  windup: number;
  strike: number;
  range: number;
  cool: [number, number];
  scale: number;
  mass: number;
  armor: boolean; // light hits don't stagger
}

export const ENEMIES: Record<Exclude<Kind, "hero">, EnemySpec> = {
  runt: { hp: 28, speed: 21, dmg: 6, windup: 0.45, strike: 0.24, range: 8, cool: [1.0, 1.9], scale: 0.86, mass: 1, armor: false },
  brute: { hp: 85, speed: 10, dmg: 13, windup: 0.78, strike: 0.34, range: 9.5, cool: [1.6, 2.5], scale: 1.28, mass: 2.2, armor: true },
  drummer: { hp: 40, speed: 13, dmg: 5, windup: 0.5, strike: 0.26, range: 8, cool: [1.4, 2.2], scale: 1.0, mass: 1.2, armor: false },
  loud: { hp: 36, speed: 13, dmg: 9, windup: 0.95, strike: 0.45, range: 30, cool: [3.0, 4.2], scale: 0.95, mass: 1.1, armor: false },
  kuzmich: { hp: 30, speed: 11, dmg: 5, windup: 0.6, strike: 0.3, range: 16, cool: [1.8, 2.8], scale: 0.95, mass: 1.1, armor: false },
  chair: { hp: 45, speed: 12, dmg: 12, windup: 0.9, strike: 0.35, range: 22, cool: [2.6, 3.6], scale: 1.05, mass: 1.4, armor: false },
  boss: { hp: 420, speed: 11, dmg: 18, windup: 0.85, strike: 0.4, range: 12, cool: [1.3, 2.0], scale: 1.7, mass: 4, armor: true },
  sinyak: { hp: 380, speed: 9, dmg: 14, windup: 0.7, strike: 0.35, range: 10, cool: [1.4, 2.2], scale: 1.55, mass: 3.5, armor: true },
};

/** Throwers keep their distance and throw from afar. */
const THROWS: Partial<Record<Kind, ShotKind>> = { kuzmich: "spit", chair: "chair" };
const SHOT: Record<ShotKind, { speed: number; gravity: number; dmg: number }> = {
  bottle: { speed: 40, gravity: 44, dmg: 9 },
  chair: { speed: 30, gravity: 44, dmg: 12 },
  spit: { speed: 56, gravity: 18, dmg: 5 },
};
export const isBoss = (k: Kind) => k === "boss" || k === "sinyak";

export const ENEMY_NAMES: Record<Exclude<Kind, "hero">, string> = {
  runt: "Шустрик",
  brute: "Шкаф",
  drummer: "Барабанщик",
  loud: "Мегафон",
  kuzmich: "Кузьмич",
  chair: "Креслолом",
  boss: "Главный по сектору",
  sinyak: "Синяк",
};

const DERBY: Kind[][] = [
  ["runt", "runt", "runt"],
  ["runt", "runt", "brute", "runt", "runt"],
  ["runt", "kuzmich", "brute", "runt", "drummer", "runt"],
  ["runt", "loud", "chair", "runt", "brute", "kuzmich", "runt"],
  ["runt", "drummer", "brute", "chair", "loud", "runt", "kuzmich", "brute", "runt"],
  ["boss", "runt", "runt"],
];

// ---------------------------------------------------------------------------
// Random
// ---------------------------------------------------------------------------

function rand(s: State): number {
  // mulberry32
  s.rng = (s.rng + 0x6d2b79f5) | 0;
  let t = s.rng;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

const between = (s: State, a: number, b: number) => a + (b - a) * rand(s);
const pick = <T,>(s: State, list: readonly T[]): T => list[Math.floor(rand(s) * list.length)];
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

const SKINS = ["#f2c7a5", "#e0a98a", "#c68863", "#9c6744", "#f5d6bd"];
const HAIR = ["#2b1d14", "#5a3a22", "#c8a15a", "#1a1a1a", "#8a4b2a"];
const RIVAL_SHIRTS = ["#2f5fd0", "#1f3f9a", "#3b7be0", "#26408f", "#4a5fc9"];
const RIVAL_STRIPES = ["#f4f0e6", "#9fc4ff", "#1d1d24"];
const HATS: Look["hat"][] = ["beanie", "cap", "bald", "hood", "bandana"];

function rivalLook(s: State, kind: Kind): Look {
  const shirt = kind === "boss" ? "#e0702a" : kind === "kuzmich" ? "#6b6f78" : pick(s, RIVAL_SHIRTS);
  return {
    skin: kind === "sinyak" ? "#e8a08a" : pick(s, SKINS),
    shirt,
    stripe: kind === "boss" ? "#26262e" : kind === "kuzmich" ? "#3b7be0" : pick(s, RIVAL_STRIPES),
    hat: kind === "boss" ? "bald" : kind === "drummer" ? "bandana" : kind === "kuzmich" ? "cap" : kind === "sinyak" ? "beanie" : pick(s, HATS),
    hatColor: kind === "kuzmich" ? "#4a4d55" : kind === "sinyak" ? "#6b4a2e" : pick(s, RIVAL_SHIRTS),
    hair: kind === "kuzmich" ? "#c9c9c9" : pick(s, HAIR),
  };
}

/** Which boss leads the boss wave: derby — by the seed, endless — in turns (Синяк first). */
export function bossOf(s: Pick<State, "mode" | "seed" | "wave">): "boss" | "sinyak" {
  if (s.mode === "derby") return s.seed % 2 === 0 ? "boss" : "sinyak";
  return Math.floor(s.wave / 6) % 2 === 1 ? "sinyak" : "boss";
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

function fighter(s: State, kind: Kind, x: number, z: number, look: Look): Fighter {
  const spec = kind === "hero" ? null : ENEMIES[kind];
  const hp = spec ? spec.hp : HERO_HP;
  return {
    id: s.nextId++, kind, x, z, y: 0, vx: 0, vz: 0, vy: 0, face: x < ARENA_W / 2 ? 1 : -1,
    hp, maxHp: hp, act: "idle", t: 0, dur: 0, hit: [], cool: spec ? between(s, 0.6, 1.4) : 0,
    token: false, buff: 0, flash: 0, ko: false, out: false, entering: kind !== "hero", special: between(s, 2, 4),
    look, scale: spec ? spec.scale : 1,
  };
}

export const HERO_LOOK: Look = {
  skin: "#f0c09c", shirt: "#d9302c", stripe: "#f4f0e6", hat: "hood", hatColor: "#1d1d24", hair: "#5a3416",
};

export function createGame(mode: Mode, seed: number, look: Look = HERO_LOOK): State {
  const s: State = {
    mode, seed, rng: seed | 0, time: 0, nextId: 1,
    hero: null as unknown as Fighter,
    enemies: [], pickups: [], shots: [], wave: 0, queue: [], spawnIn: 0, pause: 1.2, banner: null,
    combo: 0, comboT: 0, bestCombo: 0, rage: 0, spinCd: 0, buffered: null, bufferedT: 0,
    knockouts: 0, wavesCleared: 0, freeze: 0, slow: 0, shake: 0,
    finished: false, won: false, overIn: 0, events: [],
  };
  s.hero = fighter(s, "hero", ARENA_W / 2, ARENA_D * 0.4, look);
  s.hero.face = 1;
  return s;
}

export function waveList(mode: Mode, n: number): Kind[] {
  if (mode === "derby") return DERBY[Math.min(n, DERBY.length) - 1].slice();
  const list: Kind[] = [];
  const boss = n % 6 === 0;
  if (boss) list.push("boss");
  const runts = Math.min(9, 2 + Math.floor(n / 2));
  for (let i = 0; i < runts; i++) list.push("runt");
  for (let i = 0; i < Math.min(4, Math.floor(n / 3)); i++) list.splice(1 + i * 2, 0, "brute");
  if (n % 4 === 3 || n > 8) list.splice(2, 0, "drummer");
  if (n >= 4 && (n % 3 === 1 || n > 10)) list.splice(3, 0, "loud");
  if (n >= 3 && (n % 2 === 1 || n > 9)) list.splice(2, 0, "kuzmich");
  if (n >= 5 && (n % 3 === 2 || n > 9)) list.splice(4, 0, "chair");
  return list;
}

export function totalWaves(mode: Mode): number | null {
  return mode === "derby" ? DERBY_WAVES : null;
}

function isBossWave(s: State): boolean {
  return s.mode === "derby" ? s.wave === DERBY_WAVES : s.wave % 6 === 0;
}

function startWave(s: State): void {
  s.wave += 1;
  s.queue = waveList(s.mode, s.wave);
  s.spawnIn = 0.3;
  const boss = isBossWave(s);
  s.banner = boss
    ? { text: "БОСС!", sub: ENEMY_NAMES[bossOf(s)], t: 0 }
    : { text: `ВОЛНА ${s.wave}`, sub: s.mode === "derby" ? `из ${DERBY_WAVES}` : "держись", t: 0 };
  s.events.push({ t: "wave", n: s.wave, boss });
}

function maxAlive(s: State): number {
  return Math.min(7, 4 + Math.floor(s.wave / 3));
}

function spawn(s: State, kind: Kind): void {
  if (kind === "boss") kind = bossOf(s);
  const left = rand(s) < 0.5;
  const x = left ? -8 : ARENA_W + 8;
  const z = between(s, 3, ARENA_D - 3);
  const f = fighter(s, kind, x, z, rivalLook(s, kind));
  f.face = left ? 1 : -1;
  if (isBoss(kind) && s.mode === "endless") {
    const k = 1 + (s.wave / 6 - 1) * 0.35;
    f.hp = f.maxHp = Math.round(ENEMIES[kind as "boss" | "sinyak"].hp * k);
  }
  s.enemies.push(f);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const alive = (f: Fighter) => !f.ko && !f.out;
const grounded = (f: Fighter) => f.act !== "air" && f.act !== "down" && f.act !== "getup" && f.act !== "ko";
const heroBusy = (h: Fighter) =>
  h.act === "p1" || h.act === "p2" || h.act === "p3" || h.act === "kick" || h.act === "spin" || h.act === "sweep"
  || h.act === "rage" || h.act === "hurt";

function setAct(f: Fighter, act: Act, dur = 0): void {
  f.act = act;
  f.t = 0;
  f.dur = dur;
  f.hit = [];
}

function nearestEnemy(s: State, x: number, z: number, filter?: (e: Fighter) => boolean): Fighter | null {
  let best: Fighter | null = null;
  let bestD = Infinity;
  for (const e of s.enemies) {
    if (!alive(e) || e.entering || (filter && !filter(e))) continue;
    const d = Math.hypot(e.x - x, (e.z - z) * 1.6);
    if (d < bestD) {
      bestD = d;
      best = e;
    }
  }
  return best;
}

export function isFinished(s: State): boolean {
  return s.finished;
}

export function rageReady(s: State): boolean {
  return s.rage >= 100 && !s.finished && s.hero.act !== "rage" && s.hero.hp > 0;
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function startHeroMove(s: State, act: keyof typeof HERO_MOVES, face?: 1 | -1): void {
  const h = s.hero;
  if (face) h.face = face;
  setAct(h, act, HERO_MOVES[act].dur);
  h.holding = false;
  h.targetId = undefined;
  if (act === "spin") s.spinCd = SPIN_COOLDOWN;
  s.events.push({ t: "whoosh", x: h.x, z: h.z, kind: act });
  // Homing: drift onto the depth line of the nearest rival in front.
  const target = nearestEnemy(s, h.x, h.z, (e) => (e.x - h.x) * h.face > -2 && Math.abs(e.x - h.x) < 22);
  h.vz = target && Math.abs(target.z - h.z) < 7 ? clamp((target.z - h.z) * 7, -24, 24) : 0;
}

function punch(s: State): void {
  const h = s.hero;
  const chain = h.act === "p1" ? "p2" : h.act === "p2" ? "p3" : "p1";
  startHeroMove(s, chain);
}

function canAct(s: State): boolean {
  const h = s.hero;
  if (h.hp <= 0 || s.finished) return false;
  if (h.act === "hurt" || h.act === "rage") return false;
  if (h.act in HERO_MOVES) return h.t >= HERO_MOVES[h.act as keyof typeof HERO_MOVES].cancel;
  return true;
}

function applyInput(s: State, input: Input): boolean {
  const h = s.hero;
  if (input.k === "release") {
    if (h.act === "block") setAct(h, "idle");
    h.holding = false;
    return true;
  }
  if (input.k === "hold") {
    h.holding = true;
    if (canAct(s) && !heroBusy(h)) setAct(h, "block");
    return true;
  }
  if (input.k === "rage") {
    if (!rageReady(s) || h.act === "hurt") return true;
    setAct(h, "rage", RAGE_DUR);
    s.rage = 0;
    s.slow = 0.5;
    s.shake = Math.max(s.shake, 6);
    s.events.push({ t: "rage" });
    return true;
  }
  if (!canAct(s)) return false;
  if (input.k === "kick") {
    startHeroMove(s, "kick", input.dir);
    return true;
  }
  if (input.k === "spin") {
    if (s.spinCd > 0) startHeroMove(s, "kick", h.face);
    else startHeroMove(s, "spin");
    return true;
  }
  if (input.k === "sweep") {
    const e = nearestEnemy(s, h.x, h.z);
    startHeroMove(s, "sweep", e ? (e.x >= h.x ? 1 : -1) : h.face);
    return true;
  }
  // tap
  let target = input.target !== undefined ? s.enemies.find((e) => e.id === input.target && alive(e)) ?? null : null;
  if (!target) {
    const near = nearestEnemy(s, input.x, input.z);
    if (near && Math.hypot(near.x - input.x, (near.z - input.z) * 1.4) < 10) target = near;
  }
  if (target) {
    h.face = target.x >= h.x ? 1 : -1;
    const reach = HERO_MOVES.p1.range * target.scale + 1;
    if (Math.abs(target.x - h.x) <= reach && Math.abs(target.z - h.z) <= 3.5) punch(s);
    else {
      h.targetId = target.id;
      if (h.act !== "walk") setAct(h, "walk");
    }
    return true;
  }
  const pickup = s.pickups.find((p) => Math.hypot(p.x - input.x, p.z - input.z) < 7);
  const dist = Math.hypot(input.x - h.x, input.z - h.z);
  if (pickup || dist > 10) {
    h.tx = pickup ? pickup.x : clamp(input.x, 3, ARENA_W - 3);
    h.tz = pickup ? pickup.z : clamp(input.z, 1, ARENA_D - 1);
    h.targetId = undefined;
    setAct(h, "walk");
    return true;
  }
  h.face = input.x >= h.x ? 1 : -1;
  punch(s);
  return true;
}

function heroAttackHits(s: State, move: HeroMove): void {
  const h = s.hero;
  for (const e of s.enemies) {
    if (!alive(e) || e.entering || h.hit.includes(e.id)) continue;
    if (e.act === "down" || e.act === "getup") continue;
    const dx = e.x - h.x;
    const reach = move.range + 2 * (e.scale - 1);
    const inFront = move.around ? Math.abs(dx) <= reach : dx * h.face >= -1.5 && Math.abs(dx) <= reach;
    if (!inFront || Math.abs(e.z - h.z) > move.depth) continue;
    h.hit.push(e.id);
    const dir: 1 | -1 = move.around ? (dx >= 0 ? 1 : -1) : h.face;
    hitEnemy(s, e, move.dmg, move.kb, move.launch, !!move.heavy, !!move.knockdown, dir);
  }
}

function hitEnemy(s: State, e: Fighter, dmg: number, kb: number, launch: number, heavy: boolean, knockdown: boolean, dir: 1 | -1): void {
  const spec = ENEMIES[e.kind as Exclude<Kind, "hero">];
  const juggle = e.act === "air";
  const real = Math.round(dmg * (juggle ? 1.15 : 1) * (s.hero.act === "rage" ? 1.1 : 1));
  e.hp = Math.max(0, e.hp - real);
  e.flash = 0.12;
  e.face = (-dir) as 1 | -1;
  e.token = false;
  s.combo += 1;
  s.comboT = 0;
  s.bestCombo = Math.max(s.bestCombo, s.combo);
  if (s.combo === 5 || s.combo === 10 || s.combo === 20 || s.combo % 25 === 0) s.events.push({ t: "combo", n: s.combo });
  if (s.hero.act !== "rage") s.rage = Math.min(100, s.rage + real * 0.55 + (heavy ? 3 : 0));
  s.freeze = Math.max(s.freeze, heavy ? 0.075 : 0.04);
  s.shake = Math.max(s.shake, heavy ? 5 : 2);
  s.events.push({ t: "hit", x: e.x, y: e.y + 11 * e.scale, z: e.z, dmg: real, heavy, by: "hero" });

  if (e.hp <= 0) {
    e.ko = true;
    setAct(e, "air");
    e.vy = 12 + launch * 0.6 + (heavy ? 6 : 0);
    e.vx = dir * (kb + 22) / Math.sqrt(spec.mass);
    e.vz = 0;
    return;
  }
  if (juggle) {
    e.vy = Math.max(e.vy, 9 + launch * 0.2);
    e.vx = dir * Math.max(6, kb * 0.4) / spec.mass;
    return;
  }
  if (knockdown && e.kind !== "boss") {
    setAct(e, "air");
    e.vy = 7;
    e.vx = dir * 4;
    return;
  }
  const lift = launch / Math.sqrt(spec.mass);
  if (launch > 0 && lift > 7 && e.kind !== "boss") {
    setAct(e, "air");
    e.vy = lift;
    e.vx = (dir * kb) / spec.mass;
    return;
  }
  if (spec.armor && !heavy) {
    e.vx = (dir * kb * 0.3) / spec.mass;
    return; // shrugs it off, keeps going
  }
  if (e.kind === "boss" && (e.act === "slam" || e.act === "charge")) return;
  setAct(e, "hurt", heavy ? 0.42 : 0.3);
  e.vx = (dir * kb) / spec.mass;
}

function hurtHero(s: State, fromX: number, dmg: number): void {
  const h = s.hero;
  if (h.hp <= 0) return;
  const dir: 1 | -1 = h.x >= fromX ? 1 : -1;
  const facing = h.face === -dir;
  if (h.act === "spin" && h.t >= HERO_MOVES.spin.from && h.t <= HERO_MOVES.spin.to) return; // spinning through it
  if (h.act === "rage") return;
  if (h.act === "block" && facing) {
    const chip = Math.max(1, Math.round(dmg * 0.15));
    h.hp = Math.max(1, h.hp - chip);
    h.vx = dir * 10;
    s.rage = Math.min(100, s.rage + 4);
    s.events.push({ t: "block", x: h.x + h.face * 3, y: 11, z: h.z });
    return;
  }
  h.hp = Math.max(0, h.hp - dmg);
  h.flash = 0.15;
  h.holding = false;
  s.combo = 0;
  s.shake = Math.max(s.shake, 7);
  s.events.push({ t: "hit", x: h.x, y: 11, z: h.z, dmg, heavy: dmg >= 12, by: "enemy" });
  if (h.hp <= 0) {
    h.ko = true;
    setAct(h, "air");
    h.vy = 16;
    h.vx = dir * 22;
    s.slow = 1.2;
    s.overIn = 2.2;
    return;
  }
  setAct(h, "hurt", 0.32);
  h.vx = dir * 14;
}

function updateHero(s: State, dt: number): void {
  const h = s.hero;
  h.t += dt;
  if (h.flash > 0) h.flash -= dt;
  if (h.act === "air") {
    airborne(s, h, dt);
    return;
  }
  if (h.act === "ko") return;

  if (h.act in HERO_MOVES) {
    const move = HERO_MOVES[h.act as keyof typeof HERO_MOVES];
    if (move.lunge && h.t < move.to) h.vx = h.face * move.lunge;
    if (h.t >= move.from && h.t <= move.to) heroAttackHits(s, move);
    if (h.t >= move.dur) setAct(h, h.holding ? "block" : "idle");
  } else if (h.act === "rage") {
    // A storm of blows: everything near takes a hit every 0.16 s, then a blast.
    const tick = Math.floor(h.t / 0.16);
    const prev = Math.floor((h.t - dt) / 0.16);
    h.face = (tick % 2 === 0 ? 1 : -1) as 1 | -1;
    if (h.t < RAGE_DUR - 0.35 && tick !== prev) {
      h.hit = [];
      heroAttackHits(s, { dur: 0, from: 0, to: 0, range: 20, depth: 9, dmg: 7, kb: 10, launch: 0, around: true, cancel: 0 });
      s.events.push({ t: "whoosh", x: h.x, z: h.z, kind: "rage" });
    }
    if (h.t >= RAGE_DUR - 0.35 && h.t - dt < RAGE_DUR - 0.35) {
      h.hit = [];
      heroAttackHits(s, { dur: 0, from: 0, to: 0, range: 60, depth: 30, dmg: 26, kb: 40, launch: 22, heavy: true, around: true, cancel: 0 });
      s.shake = 12;
      s.freeze = 0.12;
    }
    if (h.t >= RAGE_DUR) setAct(h, "idle");
  } else if (h.act === "hurt") {
    if (h.t >= h.dur) setAct(h, h.holding ? "block" : "idle");
  } else if (h.act === "walk") {
    let tx = h.tx ?? h.x;
    let tz = h.tz ?? h.z;
    const target = h.targetId !== undefined ? s.enemies.find((e) => e.id === h.targetId && alive(e)) : undefined;
    if (h.targetId !== undefined && !target) {
      h.targetId = undefined;
      setAct(h, "idle");
    } else if (target) {
      const side = h.x <= target.x ? -1 : 1;
      tx = target.x + side * (HERO_MOVES.p1.range * 0.75);
      tz = target.z;
      h.face = target.x >= h.x ? 1 : -1;
      if (Math.abs(target.x - h.x) <= HERO_MOVES.p1.range * target.scale && Math.abs(target.z - h.z) <= 3) {
        h.targetId = undefined;
        punch(s);
        return;
      }
    }
    const dx = tx - h.x;
    const dz = tz - h.z;
    const d = Math.hypot(dx, dz);
    if (d < 0.8) {
      h.vx = 0;
      h.vz = 0;
      if (h.act === "walk") setAct(h, "idle");
    } else {
      h.vx = (dx / d) * HERO_SPEED;
      h.vz = (dz / d) * HERO_SPEED * 0.75;
      if (!target && Math.abs(dx) > 0.5) h.face = dx > 0 ? 1 : -1;
    }
  }
  if (h.act === "idle" || h.act === "block") {
    const e = nearestEnemy(s, h.x, h.z);
    if (e && h.act === "idle") h.face = e.x >= h.x ? 1 : -1;
  }

  // movement
  h.x = clamp(h.x + h.vx * dt, 3, ARENA_W - 3);
  h.z = clamp(h.z + h.vz * dt, 1, ARENA_D - 1);
  if (h.act !== "walk") {
    h.vx *= Math.exp(-10 * dt);
    h.vz *= Math.exp(-10 * dt);
  }
  // pickups
  for (const p of s.pickups) {
    if (p.t > 0 && Math.hypot(p.x - h.x, p.z - h.z) < 4) {
      p.t = -1;
      h.hp = Math.min(h.maxHp, h.hp + p.heal);
      s.events.push({ t: "heal", x: p.x, z: p.z, amount: p.heal });
    }
  }
  s.pickups = s.pickups.filter((p) => p.t > 0);
}

// ---------------------------------------------------------------------------
// Enemies
// ---------------------------------------------------------------------------

function airborne(s: State, f: Fighter, dt: number): void {
  f.x += f.vx * dt;
  f.y += f.vy * dt;
  f.vy -= GRAVITY * dt;
  if (f.ko && (f.x < -14 || f.x > ARENA_W + 14)) {
    if (f.kind !== "hero") {
      f.out = true;
      knockedOut(s, f, true);
    }
    return;
  }
  if (f.y <= 0) {
    f.y = 0;
    if (f.ko || f.kind === "hero" || Math.abs(f.vy) < 14) {
      s.events.push({ t: "land", x: f.x, z: f.z, heavy: f.scale > 1.2 });
      if (f.ko) {
        setAct(f, "ko", 1.1);
        f.vx *= 0.3;
        if (f.kind !== "hero") knockedOut(s, f, false);
      } else {
        setAct(f, "down", f.kind === "brute" ? 0.6 : 0.75);
        f.vx *= 0.25;
      }
      f.vy = 0;
    } else {
      f.vy = -f.vy * 0.35; // bounce
      f.vx *= 0.6;
    }
  }
}

function knockedOut(s: State, f: Fighter, out: boolean): void {
  if (f.counted) return;
  f.counted = true;
  s.knockouts += 1;
  s.events.push({ t: "ko", x: clamp(f.x, 2, ARENA_W - 2), z: f.z, out, kind: f.kind });
  const dropChance = isBoss(f.kind) ? 0 : f.kind === "brute" ? 0.3 : 0.12;
  if (rand(s) < dropChance && s.pickups.length < 2) {
    s.pickups.push({ id: s.nextId++, x: clamp(f.x, 6, ARENA_W - 6), z: f.z, heal: 22, t: 9 });
  }
}

function assignTokens(s: State): void {
  const h = s.hero;
  const max = s.wave >= 4 ? 3 : 2;
  const live = s.enemies.filter((e) => alive(e) && !e.entering && e.kind !== "loud" && e.kind !== "drummer" && !THROWS[e.kind] && grounded(e));
  for (const e of s.enemies) if (!live.includes(e)) e.token = false;
  let held = live.filter((e) => e.token).length;
  if (held >= max) return;
  live.sort((a, b) => Math.abs(a.x - h.x) + Math.abs(a.z - h.z) - (Math.abs(b.x - h.x) + Math.abs(b.z - h.z)));
  for (const e of live) {
    if (held >= max) break;
    if (!e.token) {
      e.token = true;
      held += 1;
    }
  }
  const boss = live.find((e) => isBoss(e.kind));
  if (boss) boss.token = true;
}

function updateEnemy(s: State, e: Fighter, dt: number): void {
  const spec = ENEMIES[e.kind as Exclude<Kind, "hero">];
  const h = s.hero;
  e.t += dt;
  if (e.flash > 0) e.flash -= dt;
  if (e.buff > 0) e.buff -= dt;
  if (e.cool > 0) e.cool -= dt;
  const pace = e.buff > 0 ? 1.3 : 1;

  if (e.act === "air") {
    airborne(s, e, dt);
    return;
  }
  if (e.act === "ko") {
    if (e.t >= e.dur) e.out = true;
    return;
  }
  if (e.act === "down") {
    if (e.t >= e.dur) setAct(e, "getup", 0.4);
    return;
  }
  if (e.act === "getup") {
    if (e.t >= e.dur) setAct(e, "idle");
    return;
  }
  if (e.act === "hurt") {
    e.x += e.vx * dt;
    e.vx *= Math.exp(-9 * dt);
    if (e.t >= e.dur) {
      setAct(e, "idle");
      e.cool = Math.max(e.cool, 0.35);
    }
    e.x = clamp(e.x, 2, ARENA_W - 2);
    return;
  }
  if (h.hp <= 0) {
    if (e.act !== "cheer") setAct(e, "cheer");
    return;
  }

  const dx = h.x - e.x;
  const dz = h.z - e.z;

  if (e.act === "windup") {
    e.face = dx >= 0 ? 1 : -1;
    if (e.t >= spec.windup / pace) {
      const next: Act = e.kind === "loud" ? "shout" : e.kind === "boss" ? (e.next ?? "slam") : "strike";
      setAct(e, next, next === "charge" ? 0.8 : e.kind === "sinyak" && e.next === "shout" ? 0.8 : spec.strike);
      if (next === "shout") s.events.push({ t: "shout", x: e.x, z: e.z, face: e.face });
      if (next === "slam") s.shake = Math.max(s.shake, 8);
      if (next === "charge") e.vx = e.face * 58;
    }
    return;
  }
  if (e.act === "strike" || e.act === "shout" || e.act === "slam" || e.act === "charge") {
    if (e.act === "charge") {
      e.x += e.vx * dt;
      if (!e.hit.includes(h.id) && Math.abs(h.x - e.x) < 6 && Math.abs(dz) < 4) {
        e.hit.push(h.id);
        hurtHero(s, e.x, Math.round(spec.dmg * 0.85 * pace));
      }
      if (e.x < 4 || e.x > ARENA_W - 4) e.t = e.dur;
      e.x = clamp(e.x, 3, ARENA_W - 3);
    } else if (THROWS[e.kind] || (e.kind === "sinyak" && e.next === "shout")) {
      // throwers: the arm comes forward and the thing flies; Синяк throws a volley of three
      const volley = e.kind === "sinyak" ? [0.05, 0.3, 0.55] : [0.05];
      for (const at of volley) if (e.t >= at && e.t - dt < at) throwAt(s, e, THROWS[e.kind] ?? "bottle", volley.length > 1);
    } else if (!e.hit.includes(h.id) && e.t >= 0.05) {
      e.hit.push(h.id);
      let lands = false;
      if (e.act === "shout") lands = dx * e.face > 0 && Math.abs(dx) <= spec.range && Math.abs(dz) <= 3.5;
      else if (e.act === "slam") lands = Math.hypot(dx, dz * 1.4) <= spec.range;
      else lands = dx * e.face > -1 && Math.abs(dx) <= spec.range * e.scale + 1 && Math.abs(dz) <= 3.5;
      if (lands) hurtHero(s, e.x, Math.round(spec.dmg * pace));
    }
    if (e.t >= e.dur) {
      setAct(e, "idle");
      e.cool = between(s, spec.cool[0], spec.cool[1]) / pace;
      if (e.kind === "sinyak") e.next = undefined;
    }
    return;
  }
  if (e.act === "drum") {
    if (e.t >= 0.9) {
      for (const o of s.enemies) if (alive(o) && o !== e) o.buff = 4;
      s.events.push({ t: "drum", x: e.x, z: e.z });
      setAct(e, "idle");
      e.special = between(s, 4.5, 6);
    }
    return;
  }

  // Thinking: idle / walk.
  e.special -= dt;
  if (e.kind === "sinyak") {
    const k = e.hp / e.maxHp;
    const calls = e.calls ?? 0;
    if ((k < 0.6 && calls === 0) || (k < 0.3 && calls === 1)) {
      e.calls = calls + 1;
      s.queue.push("kuzmich", "runt");
      s.spawnIn = 0.2;
      s.events.push({ t: "summon", x: e.x, z: e.z });
    }
  }
  if (e.kind === "boss") {
    const k = e.hp / e.maxHp;
    const calls = e.calls ?? 0;
    if ((k < 0.6 && calls === 0) || (k < 0.3 && calls === 1)) {
      e.calls = calls + 1;
      s.queue.push("runt", "runt");
      s.spawnIn = 0.2;
      s.events.push({ t: "summon", x: e.x, z: e.z });
    }
  }
  let tx = e.x;
  let tz = e.z;
  const side = e.x <= h.x ? -1 : 1;
  if (e.kind === "loud") {
    tx = h.x + side * 20;
    tz = h.z;
    if (Math.abs(dz) < 2.5 && Math.abs(Math.abs(dx) - 20) < 6 && e.cool <= 0) {
      e.face = dx >= 0 ? 1 : -1;
      setAct(e, "windup");
      return;
    }
  } else if (THROWS[e.kind]) {
    // keeps its distance and throws from there
    tx = h.x + side * spec.range;
    tz = clamp(h.z + (e.id % 2 ? 5 : -5), 2, ARENA_D - 2);
    if (!e.entering && e.cool <= 0 && Math.abs(dx) > 7 && Math.abs(dx) < 46) {
      e.face = dx >= 0 ? 1 : -1;
      setAct(e, "windup");
      return;
    }
  } else if (e.kind === "drummer") {
    tx = h.x + side * 26;
    tz = clamp(h.z + (e.id % 2 ? 7 : -7), 2, ARENA_D - 2);
    if (e.special <= 0 && !e.entering) {
      setAct(e, "drum");
      return;
    }
    if (Math.abs(dx) < spec.range && Math.abs(dz) < 3 && e.cool <= 0) {
      setAct(e, "windup");
      return;
    }
  } else if (e.token) {
    const reach = isBoss(e.kind) ? spec.range - 1.5 : spec.range * e.scale;
    tx = h.x + side * reach * 0.8;
    tz = h.z;
    if (e.kind === "sinyak" && e.special <= 0 && e.cool <= 0 && Math.abs(dx) > 14) {
      e.next = "shout"; // marks the bottle volley (the act played is "strike")
      e.special = between(s, 3, 4.5);
      e.face = dx >= 0 ? 1 : -1;
      setAct(e, "windup");
      return;
    }
    if (e.kind === "sinyak") tz = h.z + Math.sin(s.time * 2.6 + e.id) * 3; // staggers
    if (e.kind === "boss" && e.special <= 0 && e.cool <= 0 && Math.abs(dx) > 16 && Math.abs(dz) < 3) {
      e.next = "charge";
      e.special = between(s, 4, 6);
      e.face = dx >= 0 ? 1 : -1;
      setAct(e, "windup");
      return;
    }
    if (Math.abs(dx) <= reach + 0.5 && Math.abs(dz) <= 2.6 && e.cool <= 0) {
      e.next = e.kind === "sinyak" ? undefined : "slam";
      e.face = dx >= 0 ? 1 : -1;
      setAct(e, "windup");
      return;
    }
  } else {
    // waits its turn around the edge of the brawl, shuffling
    tx = h.x + side * (18 + (e.id % 3) * 3);
    tz = clamp(h.z + ((e.id * 7) % 11) - 5, 2, ARENA_D - 2);
  }
  tx = clamp(tx, e.entering ? -10 : 3, e.entering ? ARENA_W + 10 : ARENA_W - 3);
  // keep a little apart from each other
  let px = 0;
  let pz = 0;
  for (const o of s.enemies) {
    if (o === e || !alive(o) || !grounded(o)) continue;
    const ox = e.x - o.x;
    const oz = e.z - o.z;
    const d = Math.hypot(ox, oz * 1.5);
    if (d < 5 && d > 0.01) {
      px += (ox / d) * (5 - d);
      pz += (oz / d) * (5 - d);
    }
  }
  const mx = tx - e.x + px * 2;
  const mz = tz - e.z + pz * 2;
  const md = Math.hypot(mx, mz);
  const speed = spec.speed * pace * (e.token ? 1 : 0.6);
  if (md > 0.8) {
    e.x += (mx / md) * speed * dt;
    e.z += (mz / md) * speed * 0.7 * dt;
    if (e.act !== "walk") setAct(e, "walk");
  } else if (e.act !== "idle") setAct(e, "idle");
  e.face = dx >= 0 ? 1 : -1;
  e.z = clamp(e.z, 1, ARENA_D - 1);
  if (e.entering && e.x > 4 && e.x < ARENA_W - 4) e.entering = false;
}

// ---------------------------------------------------------------------------
// Thrown things
// ---------------------------------------------------------------------------

function throwAt(s: State, e: Fighter, kind: ShotKind, spread: boolean): void {
  const h = s.hero;
  const spec = SHOT[kind];
  const tx = clamp(h.x + (spread ? between(s, -6, 6) : 0), 2, ARENA_W - 2);
  const tz = clamp(h.z + (spread ? between(s, -3, 3) : 0), 1, ARENA_D - 1);
  const x0 = e.x + e.face * 3 * e.scale;
  const y0 = 13 * e.scale;
  const T = Math.max(0.35, Math.hypot(tx - x0, (tz - e.z) * 1.5) / spec.speed);
  s.shots.push({
    id: s.nextId++, kind, x: x0, z: e.z, y: y0,
    vx: (tx - x0) / T, vz: (tz - e.z) / T, vy: (0.5 * spec.gravity * T * T - y0) / T,
    dmg: spec.dmg, t: 0, mine: false,
  });
  s.events.push({ t: "throw", x: x0, z: e.z, kind });
}

/** The hero's blow (a punch, a kick, a spin, the rage) that is live now and reaches `x, z`. */
function heroSwats(s: State, x: number, z: number): boolean {
  const h = s.hero;
  if (h.act === "rage") return Math.abs(x - h.x) < 22 && Math.abs(z - h.z) < 9;
  const move = HERO_MOVES[h.act as keyof typeof HERO_MOVES];
  if (!move || h.t < move.from - 0.04 || h.t > move.to + 0.04) return false;
  const dx = x - h.x;
  if (!move.around && dx * h.face < -1) return false;
  return Math.abs(dx) <= move.range + 1.5 && Math.abs(z - h.z) <= move.depth;
}

function updateShots(s: State, dt: number): void {
  const h = s.hero;
  for (const p of s.shots) {
    p.t += dt;
    p.x += p.vx * dt;
    p.z = clamp(p.z + p.vz * dt, 0.5, ARENA_D - 0.5);
    p.y += p.vy * dt;
    p.vy -= SHOT[p.kind].gravity * dt;
    if (!p.mine) {
      if (h.hp > 0 && p.y < 20 && heroSwats(s, p.x, p.z)) {
        // knocked back the way it came — now it flies into them
        p.mine = true;
        p.vx = (p.x >= h.x ? 1 : -1) * Math.max(42, Math.abs(p.vx) * 1.4);
        p.vz = 0;
        p.vy = 9;
        p.y = Math.max(p.y, 9);
        s.rage = Math.min(100, s.rage + 6);
        s.freeze = Math.max(s.freeze, 0.05);
        s.events.push({ t: "deflect", x: p.x, y: p.y, z: p.z, kind: p.kind });
        continue;
      }
      if (h.hp > 0 && p.y < 17 && Math.abs(p.x - h.x) < 3.2 && Math.abs(p.z - h.z) < 2.6) {
        p.t = -1;
        hurtHero(s, p.x - p.vx, p.dmg);
        s.events.push({ t: "smash", x: p.x, z: p.z, kind: p.kind });
        continue;
      }
    } else {
      const e = s.enemies.find((o) => alive(o) && !o.entering && grounded(o)
        && Math.abs(o.x - p.x) < 4 * o.scale && Math.abs(o.z - p.z) < 3.2 && p.y < 18 * o.scale);
      if (e) {
        p.t = -1;
        hitEnemy(s, e, Math.round(p.dmg * 1.6) + 6, 26, 11, true, false, p.vx >= 0 ? 1 : -1);
        s.events.push({ t: "smash", x: p.x, z: p.z, kind: p.kind });
        continue;
      }
    }
    if (p.y <= 0) {
      p.t = -1;
      s.events.push({ t: "smash", x: p.x, z: p.z, kind: p.kind });
    } else if (p.x < -12 || p.x > 112) p.t = -1;
  }
  s.shots = s.shots.filter((p) => p.t >= 0);
}

// ---------------------------------------------------------------------------
// Step
// ---------------------------------------------------------------------------

export function step(s: State, rawDt: number, inputs: Input[] = []): void {
  if (s.finished) return;
  for (const input of inputs) {
    if (!applyInput(s, input)) {
      s.buffered = input;
      s.bufferedT = 0;
    }
  }
  if (s.buffered) {
    s.bufferedT += rawDt;
    if (s.bufferedT > BUFFER_TTL) s.buffered = null;
    else if (canAct(s) && applyInput(s, s.buffered)) s.buffered = null;
  }
  if (s.freeze > 0) {
    s.freeze -= rawDt;
    return;
  }
  const dt = s.slow > 0 ? rawDt * 0.35 : rawDt;
  if (s.slow > 0) s.slow -= rawDt;
  s.time += dt;
  if (s.shake > 0) s.shake = Math.max(0, s.shake - rawDt * 30);
  if (s.banner) {
    s.banner.t += rawDt;
    if (s.banner.t > 1.8) s.banner = null;
  }
  s.comboT += dt;
  if (s.comboT > COMBO_WINDOW) s.combo = 0;
  if (s.spinCd > 0) s.spinCd -= dt;
  for (const p of s.pickups) p.t -= dt;

  updateHero(s, dt);
  assignTokens(s);
  for (const e of s.enemies) updateEnemy(s, e, dt);
  updateShots(s, dt);
  s.enemies = s.enemies.filter((e) => !e.out);

  if (s.overIn > 0) {
    s.overIn -= rawDt;
    if (s.overIn <= 0) {
      s.finished = true;
      s.events.push({ t: "over", won: s.won });
    }
    return;
  }

  // waves
  if (s.pause > 0) {
    s.pause -= rawDt;
    if (s.pause <= 0) startWave(s);
    return;
  }
  const fighting = s.enemies.filter(alive).length;
  if (s.queue.length > 0) {
    s.spawnIn -= dt;
    if (s.spawnIn <= 0 && fighting < maxAlive(s)) {
      spawn(s, s.queue.shift() as Kind);
      s.spawnIn = 0.75;
    }
  } else if (fighting === 0 && s.wave > 0) {
    s.wavesCleared = s.wave;
    s.events.push({ t: "clear", n: s.wave });
    s.slow = 0.6;
    s.hero.hp = Math.min(s.hero.maxHp, s.hero.hp + WAVE_HEAL);
    if (s.mode === "derby" && s.wave >= DERBY_WAVES) {
      s.won = true;
      s.overIn = 1.6;
      s.banner = { text: "ПОБЕДА!", sub: "сектор твой", t: 0 };
      setAct(s.hero, "cheer");
      return;
    }
    s.banner = { text: "ЧИСТО!", sub: `+${WAVE_HEAL} здоровья`, t: 0 };
    s.pause = 2.2;
  }
}
