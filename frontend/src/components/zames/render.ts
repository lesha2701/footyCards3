/**
 * «Замес» canvas renderer: paper-doll fans on a skeleton (limbs are thick
 * outlined strokes posed by joint angles), comic hit effects, the HUD. It
 * only reads the engine state; `drainEvents` turns engine events into
 * particles. No game rules live here.
 */
import {
  ARENA_D, ARENA_W, DERBY_WAVES, ENEMY_NAMES, HERO_MOVES, isBoss, type Fighter, type GameEvent, type Kind, type ShotKind,
  type State,
} from "@/lib/zames/engine";

import bottleUrl from "@/assets/zames/props/bottle.webp";
import chairUrl from "@/assets/zames/props/chair.webp";

import { drawSprite } from "./sprites";

// ---------------------------------------------------------------------------
// View / projection
// ---------------------------------------------------------------------------

export interface View {
  w: number;
  h: number;
  floorTop: number;
  floorBottom: number;
}

/** Where the floor of each arena picture starts (share of the height). */
export const ARENA_FLOOR: Record<string, number> = { parking: 0.44, tunnel: 0.41 };

export function makeView(w: number, h: number, arena = "parking"): View {
  return { w, h, floorTop: h * (ARENA_FLOOR[arena] ?? 0.42), floorBottom: h * 0.93 };
}

/** Pixels per world unit for a fighter at depth z (bigger when near). */
export function unitAt(v: View, z: number): number {
  const t = z / ARENA_D;
  return (v.w / ARENA_W) * (1.95 - 0.65 * t);
}

export function project(v: View, x: number, z: number, y = 0): { sx: number; sy: number; k: number } {
  const t = z / ARENA_D;
  const k = unitAt(v, z);
  const sx = v.w / 2 + (x - ARENA_W / 2) * (v.w / ARENA_W) * (0.96 - 0.12 * t);
  const sy = v.floorBottom - (v.floorBottom - v.floorTop) * t - y * k;
  return { sx, sy, k };
}

/** Screen → floor point (for taps on empty floor). */
export function unproject(v: View, sx: number, sy: number): { x: number; z: number } {
  const t = Math.max(0, Math.min(1, (v.floorBottom - sy) / (v.floorBottom - v.floorTop)));
  const z = t * ARENA_D;
  const x = ARENA_W / 2 + (sx - v.w / 2) / ((v.w / ARENA_W) * (0.96 - 0.12 * t));
  return { x, z };
}

/** The fighter under a tap: its body box, the front-most first. */
export function pickFighter(v: View, s: State, sx: number, sy: number): Fighter | null {
  let best: Fighter | null = null;
  for (const e of s.enemies) {
    if (e.ko || e.out) continue;
    const p = project(v, e.x, e.z, e.y);
    const k = p.k * e.scale;
    const halfW = Math.max(5 * k, 26);
    if (sx < p.sx - halfW || sx > p.sx + halfW || sy < p.sy - 19 * k || sy > p.sy + 14) continue;
    if (!best || e.z < best.z) best = e;
  }
  return best;
}

// ---------------------------------------------------------------------------
// Particles
// ---------------------------------------------------------------------------

type PKind = "star" | "word" | "num" | "dust" | "item" | "ring" | "note" | "heal" | "wave";

interface Particle {
  kind: PKind;
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  max: number;
  size: number;
  rot: number;
  vr: number;
  text?: string;
  color: string;
  item?: number;
  face?: 1 | -1;
}

export interface Fx {
  particles: Particle[];
  combo: { n: number; t: number } | null;
  flash: number; // red screen edge when hurt
  rageFlash: number;
}

export function makeFx(): Fx {
  return { particles: [], combo: null, flash: 0, rageFlash: 0 };
}

const WORDS = ["БАЦ!", "ХРЯСЬ!", "БУМ!", "ПЫЩ!", "ТЫДЫЩ!", "ШМЯК!", "БДЫЩ!"];
const COMBO_WORDS: Record<number, string> = { 5: "НЕПЛОХО!", 10: "ЗАМЕС!", 20: "РАЗГРОМ!", 25: "МАШИНА!", 50: "ЛЕГЕНДА!" };

let wordSeed = 0;
const nextWord = () => WORDS[(wordSeed = (wordSeed + 3) % WORDS.length)];

let screenW = 390;

function add(fx: Fx, p: Partial<Particle> & { kind: PKind; x: number; y: number }): void {
  const part = { vx: 0, vy: 0, life: 0, max: 0.8, size: 1, rot: 0, vr: 0, color: "#fff", ...p };
  if (part.kind === "word") {
    // keep the whole word on screen
    const half = ((part.text?.length ?? 4) * 9 * part.size) + 8;
    part.x = Math.max(half, Math.min(screenW - half, part.x));
  }
  fx.particles.push(part);
}

export function drainEvents(v: View, s: State, fx: Fx, onHaptic?: (kind: "light" | "medium" | "heavy" | "success" | "error") => void): void {
  screenW = v.w;
  const events = s.events.splice(0, s.events.length);
  for (const ev of events) handle(v, s, fx, ev, onHaptic);
}

function handle(v: View, s: State, fx: Fx, ev: GameEvent, onHaptic?: (kind: "light" | "medium" | "heavy" | "success" | "error") => void): void {
  switch (ev.t) {
    case "hit": {
      const p = project(v, ev.x, ev.z, ev.y);
      const n = ev.heavy ? 7 : 4;
      for (let i = 0; i < n; i++) {
        const a = (i / n) * Math.PI * 2 + Math.random();
        const sp = (ev.heavy ? 260 : 170) * (0.6 + Math.random() * 0.6);
        add(fx, { kind: "star", x: p.sx, y: p.sy, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 60, max: 0.45, size: ev.heavy ? 1.2 : 0.8, color: i % 2 ? "#ffe14a" : "#ffffff", vr: 8 });
      }
      add(fx, { kind: "ring", x: p.sx, y: p.sy, max: 0.25, size: ev.heavy ? 1.6 : 1, color: ev.by === "hero" ? "#ffffff" : "#ff5a4a" });
      if (ev.heavy && ev.by === "hero") add(fx, { kind: "word", x: p.sx + (Math.random() - 0.5) * 30, y: p.sy - 30, vy: -60, max: 0.7, size: 1, text: nextWord(), color: "#ffe14a", rot: (Math.random() - 0.5) * 0.5 });
      add(fx, { kind: "num", x: p.sx + 10, y: p.sy - 10, vy: -90, max: 0.7, text: `-${ev.dmg}`, color: ev.by === "hero" ? "#ffffff" : "#ff6b5e" });
      if (ev.by === "enemy") {
        fx.flash = 0.35;
        onHaptic?.("heavy");
      } else onHaptic?.(ev.heavy ? "medium" : "light");
      break;
    }
    case "block": {
      const p = project(v, ev.x, ev.z, ev.y);
      add(fx, { kind: "ring", x: p.sx, y: p.sy, max: 0.3, size: 1.3, color: "#22d3c4" });
      add(fx, { kind: "word", x: p.sx, y: p.sy - 26, vy: -40, max: 0.6, text: "БЛОК", color: "#22d3c4", size: 0.75 });
      onHaptic?.("light");
      break;
    }
    case "ko": {
      const p = project(v, ev.x, ev.z, 8);
      for (let i = 0; i < 3; i++) {
        add(fx, {
          kind: "item", x: p.sx, y: p.sy, vx: (Math.random() - 0.5) * 300, vy: -300 - Math.random() * 200, max: 1.3,
          item: i, vr: (Math.random() - 0.5) * 16, color: ["#ffffff", "#e0702a", "#c6e63a"][i],
        });
      }
      add(fx, { kind: "word", x: Math.max(60, Math.min(v.w - 60, p.sx)), y: p.sy - 40, vy: -50, max: 0.9, size: ev.out ? 1.25 : 1.05, text: ev.out ? "ВЫНОС!" : isBoss(ev.kind) ? "НОКАУТ!" : "В АУТ!", color: ev.out ? "#c6e63a" : "#ffffff", rot: (Math.random() - 0.5) * 0.4 });
      onHaptic?.("medium");
      break;
    }
    case "land": {
      const p = project(v, ev.x, ev.z);
      for (let i = 0; i < (ev.heavy ? 6 : 4); i++) add(fx, { kind: "dust", x: p.sx, y: p.sy, vx: (Math.random() - 0.5) * 160, vy: -30 - Math.random() * 40, max: 0.6, size: ev.heavy ? 1.4 : 1, color: "rgba(220,220,230,0.5)" });
      break;
    }
    case "combo":
      fx.combo = { n: ev.n, t: 0 };
      break;
    case "shout": {
      const p = project(v, ev.x, ev.z, 12);
      for (let i = 0; i < 4; i++) add(fx, { kind: "wave", x: p.sx + ev.face * 20, y: p.sy, vx: ev.face * 320, max: 0.7, size: 1 + i * 0.25, life: -i * 0.08, color: "#ffb347", face: ev.face });
      break;
    }
    case "drum": {
      const p = project(v, ev.x, ev.z, 10);
      for (let i = 0; i < 5; i++) add(fx, { kind: "note", x: p.sx + (Math.random() - 0.5) * 40, y: p.sy, vx: (Math.random() - 0.5) * 60, vy: -80 - Math.random() * 60, max: 1.1, color: "#ffe14a", text: i % 2 ? "♪" : "♫" });
      add(fx, { kind: "word", x: p.sx, y: p.sy - 30, vy: -30, max: 0.9, text: "БУМ-БУМ!", color: "#ffb347", size: 0.8 });
      break;
    }
    case "heal": {
      const p = project(v, ev.x, ev.z, 10);
      add(fx, { kind: "heal", x: p.sx, y: p.sy, vy: -70, max: 0.9, text: `+${ev.amount}`, color: "#c6e63a" });
      onHaptic?.("success");
      break;
    }
    case "throw": {
      if (ev.kind === "spit") {
        const p = project(v, ev.x, ev.z, 16);
        add(fx, { kind: "word", x: p.sx, y: p.sy - 14, vy: -40, max: 0.6, text: "ТЬФУ!", color: "#b8f0a0", size: 0.75 });
      }
      break;
    }
    case "smash": {
      const p = project(v, ev.x, ev.z, 2);
      const color = ev.kind === "bottle" ? "#5fbf6a" : ev.kind === "chair" ? "#2f5fd0" : "#d8f5c8";
      for (let i = 0; i < (ev.kind === "spit" ? 4 : 7); i++) {
        const a = Math.PI + (i / 6) * Math.PI;
        add(fx, { kind: "star", x: p.sx, y: p.sy, vx: Math.cos(a) * 170 * Math.random(), vy: Math.sin(a) * 200 - 40, max: 0.45, size: 0.6, color, vr: 10 });
      }
      if (ev.kind !== "spit") add(fx, { kind: "word", x: p.sx, y: p.sy - 24, vy: -40, max: 0.55, text: ev.kind === "bottle" ? "ДЗЫНЬ!" : "БАМС!", color: "#ffffff", size: 0.7 });
      break;
    }
    case "deflect": {
      const p = project(v, ev.x, ev.z, ev.y);
      add(fx, { kind: "ring", x: p.sx, y: p.sy, max: 0.3, size: 1.4, color: "#c6e63a" });
      add(fx, { kind: "word", x: p.sx, y: p.sy - 26, vy: -60, max: 0.7, text: "ОТБИЛ!", color: "#c6e63a", size: 0.9 });
      onHaptic?.("medium");
      break;
    }
    case "summon": {
      const p = project(v, ev.x, ev.z, 22);
      add(fx, { kind: "word", x: p.sx, y: p.sy, vy: -30, max: 1.2, text: "ПАЦАНЫ, СЮДА!", color: "#ff8a3d", size: 0.85 });
      break;
    }
    case "rage":
      fx.rageFlash = 0.6;
      onHaptic?.("heavy");
      break;
    case "over":
      onHaptic?.(ev.won ? "success" : "error");
      break;
    case "wave":
    case "clear":
    case "whoosh":
      break;
  }
}

export function updateFx(fx: Fx, dt: number): void {
  for (const p of fx.particles) {
    p.life += dt;
    if (p.life < 0) continue;
    p.x += p.vx * dt;
    p.y += p.vy * dt;
    p.rot += p.vr * dt;
    if (p.kind === "star" || p.kind === "item") p.vy += (p.kind === "item" ? 900 : 500) * dt;
    if (p.kind === "dust") {
      p.vx *= 0.92;
      p.vy *= 0.92;
    }
  }
  fx.particles = fx.particles.filter((p) => p.life < p.max);
  if (fx.combo) {
    fx.combo.t += dt;
    if (fx.combo.t > 1.2) fx.combo = null;
  }
  if (fx.flash > 0) fx.flash -= dt;
  if (fx.rageFlash > 0) fx.rageFlash -= dt;
}

// ---------------------------------------------------------------------------
// Background
// ---------------------------------------------------------------------------

export function drawBackground(ctx: CanvasRenderingContext2D, v: View, img: HTMLImageElement | null, time: number): void {
  if (img && img.complete && img.naturalWidth > 0) {
    const scale = Math.max(v.w / img.naturalWidth, v.h / img.naturalHeight);
    const dw = img.naturalWidth * scale;
    const dh = img.naturalHeight * scale;
    ctx.drawImage(img, (v.w - dw) / 2, (v.h - dh) / 2, dw, dh);
    return;
  }
  // sky
  const sky = ctx.createLinearGradient(0, 0, 0, v.floorTop);
  sky.addColorStop(0, "#070b18");
  sky.addColorStop(1, "#1a2440");
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, v.w, v.floorTop + 2);
  // floodlights
  for (const fxp of [0.12, 0.88]) {
    const x = v.w * fxp;
    const g = ctx.createRadialGradient(x, v.h * 0.08, 2, x, v.h * 0.08, v.w * 0.45);
    g.addColorStop(0, "rgba(220,240,255,0.55)");
    g.addColorStop(0.15, "rgba(160,220,255,0.18)");
    g.addColorStop(1, "rgba(160,220,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, v.w, v.floorTop);
    ctx.fillStyle = "#0c1222";
    ctx.fillRect(x - 3, v.h * 0.08, 6, v.floorTop - v.h * 0.08);
    ctx.fillStyle = "#e9f6ff";
    ctx.fillRect(x - 16, v.h * 0.065, 32, 9);
  }
  // stadium wall
  const wallTop = v.floorTop - v.h * 0.16;
  ctx.fillStyle = "#222b45";
  ctx.beginPath();
  ctx.moveTo(0, wallTop + 20);
  ctx.quadraticCurveTo(v.w / 2, wallTop - 26, v.w, wallTop + 20);
  ctx.lineTo(v.w, v.floorTop);
  ctx.lineTo(0, v.floorTop);
  ctx.closePath();
  ctx.fill();
  // stand windows / glow
  ctx.fillStyle = "rgba(198,230,58,0.10)";
  for (let i = 0; i < 9; i++) {
    const x = (i + 0.5) * (v.w / 9);
    ctx.fillRect(x - 10, wallTop + 26 + Math.sin(i) * 4, 20, 10);
  }
  // fence with scarves
  ctx.strokeStyle = "rgba(170,185,210,0.35)";
  ctx.lineWidth = 1;
  for (let x = 0; x < v.w; x += 9) {
    ctx.beginPath();
    ctx.moveTo(x, v.floorTop - 34);
    ctx.lineTo(x, v.floorTop);
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(170,185,210,0.45)";
  ctx.fillRect(0, v.floorTop - 36, v.w, 3);
  const scarves = ["#22d3c4", "#c6e63a", "#e0702a", "#8e3fd1"];
  for (let i = 0; i < 6; i++) {
    const x = (i + 0.3) * (v.w / 6);
    const sway = Math.sin(time * 1.5 + i) * 2;
    ctx.fillStyle = scarves[i % scarves.length];
    ctx.beginPath();
    ctx.moveTo(x, v.floorTop - 34);
    ctx.lineTo(x + 26, v.floorTop - 34);
    ctx.lineTo(x + 24 + sway, v.floorTop - 22);
    ctx.lineTo(x + 2 + sway, v.floorTop - 22);
    ctx.fill();
  }
  // asphalt
  const floor = ctx.createLinearGradient(0, v.floorTop, 0, v.h);
  floor.addColorStop(0, "#2d3242");
  floor.addColorStop(1, "#191c26");
  ctx.fillStyle = floor;
  ctx.fillRect(0, v.floorTop, v.w, v.h - v.floorTop);
  // parking lines in perspective
  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.lineWidth = 2;
  for (let x = -20; x <= ARENA_W + 20; x += 20) {
    const a = project(v, x, ARENA_D);
    const b = project(v, x, 0);
    ctx.beginPath();
    ctx.moveTo(a.sx, a.sy);
    ctx.lineTo(b.sx + (b.sx - a.sx) * 0.15, v.h);
    ctx.stroke();
  }
  const mid = project(v, 0, ARENA_D * 0.5).sy;
  ctx.strokeStyle = "rgba(255,225,74,0.12)";
  ctx.setLineDash([18, 14]);
  ctx.beginPath();
  ctx.moveTo(0, mid);
  ctx.lineTo(v.w, mid);
  ctx.stroke();
  ctx.setLineDash([]);
  // floodlight pools on the floor
  for (const fxp of [0.25, 0.75]) {
    const g = ctx.createRadialGradient(v.w * fxp, v.floorTop + (v.floorBottom - v.floorTop) * 0.5, 4, v.w * fxp, v.floorTop + (v.floorBottom - v.floorTop) * 0.5, v.w * 0.4);
    g.addColorStop(0, "rgba(200,230,255,0.08)");
    g.addColorStop(1, "rgba(200,230,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, v.floorTop, v.w, v.h - v.floorTop);
  }
}

// ---------------------------------------------------------------------------
// Fighters
// ---------------------------------------------------------------------------

type Joint = [number, number]; // [upper angle, lower angle relative]

interface Pose {
  lean: number;
  crouch: number;
  lift: number;
  rot: number;
  squash: number;
  aF: Joint;
  aB: Joint;
  lF: Joint;
  lB: Joint;
  mood: "normal" | "angry" | "hurt" | "ko" | "yell" | "happy" | "dizzy";
  prop?: "megaphone" | "drum";
}

const GUARD_F: Joint = [0.55, 1.95];
const GUARD_B: Joint = [0.3, 2.15];
const STANCE_F: Joint = [0.32, -0.25];
const STANCE_B: Joint = [-0.3, -0.12];

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const lj = (a: Joint, b: Joint, t: number): Joint => [lerp(a[0], b[0], t), lerp(a[1], b[1], t)];

/** 0 → 1 over the active window, back to 0 at the end. */
function ext(t: number, from: number, to: number, dur: number): number {
  if (t < from) return Math.min(1, t / Math.max(0.001, from)) * 0.25;
  if (t < to) return 0.25 + 0.75 * Math.min(1, (t - from) / Math.max(0.001, (to - from) * 0.5));
  return Math.max(0, 1 - (t - to) / Math.max(0.001, dur - to));
}

function walkCycle(time: number, speed: number): Pick<Pose, "lF" | "lB" | "lift"> {
  const ph = time * speed;
  const sw = Math.sin(ph);
  return {
    lF: [0.1 + 0.6 * sw, -0.25 - 0.5 * Math.max(0, -sw)],
    lB: [0.1 - 0.6 * sw, -0.25 - 0.5 * Math.max(0, sw)],
    lift: Math.abs(Math.cos(ph)) * 0.5,
  };
}

function poseOf(f: Fighter, time: number): Pose {
  const breathe = Math.sin(time * 4 + f.id) * 0.04;
  const base: Pose = {
    lean: 0.08, crouch: 0.4, lift: 0, rot: 0, squash: 1, aF: [GUARD_F[0] + breathe, GUARD_F[1]], aB: GUARD_B,
    lF: STANCE_F, lB: STANCE_B, mood: f.kind === "hero" ? "normal" : "angry",
  };
  if (f.kind === "loud") base.prop = "megaphone";
  if (f.kind === "drummer") base.prop = "drum";
  const t = f.t;
  switch (f.act) {
    case "walk": {
      const speed = f.kind === "hero" ? 13 : f.kind === "brute" || isBoss(f.kind) ? 8 : 11;
      return { ...base, ...walkCycle(time + f.id, speed), lean: 0.14 };
    }
    case "p1": {
      const m = HERO_MOVES.p1;
      const e = ext(t, m.from, m.to, m.dur);
      return { ...base, lean: 0.12 + 0.12 * e, aF: lj(GUARD_F, [1.58, 0.05], e) };
    }
    case "p2": {
      const m = HERO_MOVES.p2;
      const e = ext(t, m.from, m.to, m.dur);
      return { ...base, lean: 0.16 + 0.12 * e, squash: 1 - 0.12 * e, aB: lj(GUARD_B, [1.62, 0.05], e) };
    }
    case "p3": {
      const m = HERO_MOVES.p3;
      const e = ext(t, m.from, m.to, m.dur);
      return { ...base, lean: lerp(0.3, -0.1, e), crouch: lerp(1.6, 0.2, e), lift: e * 1.2, aF: lj([-0.3, 1.3], [2.7, 0.2], e), lF: lj(STANCE_F, [0.2, -0.1], e) };
    }
    case "kick": {
      const m = HERO_MOVES.kick;
      const e = ext(t, m.from, m.to, m.dur);
      return { ...base, lean: -0.35 * e, crouch: 0.2, lF: lj(STANCE_F, [1.7, -0.02], e), lB: [-0.15, -0.1], aF: lj(GUARD_F, [1.0, 1.0], e), aB: lj(GUARD_B, [-0.7, 0.7], e) };
    }
    case "spin": {
      const m = HERO_MOVES.spin;
      const p = Math.min(1, t / m.dur);
      const e = ext(t, m.from, m.to, m.dur);
      return {
        ...base, squash: Math.cos(p * Math.PI * 2), lean: -0.25 * e, lift: e * 2.2, crouch: 0,
        lF: lj(STANCE_F, [1.72, 0], e), lB: [-0.1, -0.3], aF: [1.9, 0.3], aB: [-1.4, 0.3], mood: "yell",
      };
    }
    case "sweep": {
      const m = HERO_MOVES.sweep;
      const e = ext(t, m.from, m.to, m.dur);
      return { ...base, crouch: lerp(0.4, 4.6, Math.min(1, e * 1.5)), lean: 0.45 * e, lF: lj(STANCE_F, [1.5, 0], e), lB: lj(STANCE_B, [-1.0, -1.9], e), aF: [1.2, 0.4], aB: [-0.8, 0.6] };
    }
    case "block":
      return { ...base, lean: 0.02, crouch: 0.9, aF: [1.25, 2.3], aB: [1.05, 2.45] };
    case "rage": {
      const w = Math.sin(time * 40);
      return { ...base, squash: Math.cos(time * 26), lift: 1.5, lean: 0, aF: [1.6 + 0.6 * w, 0.1], aB: [1.6 - 0.6 * w, 0.1], lF: [1.2 * w, -0.2], lB: [-1.2 * w, -0.2], mood: "yell" };
    }
    case "windup": {
      if (f.kind === "chair") return { ...base, lean: -0.2, aF: [2.9, 0.3], aB: [2.7, 0.4], mood: "yell" };
      if (f.kind === "kuzmich") return { ...base, lean: -0.3, aF: [0.4, 0.9], mood: "yell" };
      if (f.kind === "boss") return { ...base, lean: -0.2, aF: [2.9, 0.3], aB: [2.7, 0.4], mood: "yell" };
      if (f.kind === "loud") return { ...base, lean: -0.15, aF: [1.2, 0.7], mood: "angry" };
      const shake = Math.sin(time * 50) * 0.05;
      return { ...base, lean: -0.25 + shake, aF: [-0.95, 1.5], mood: "angry" };
    }
    case "strike":
      return { ...base, lean: 0.32, aF: [1.58, 0.05], lF: [0.5, -0.2] };
    case "slam":
      return { ...base, lean: 0.5, crouch: 1.8, aF: [1.0, 0.1], aB: [1.1, 0.1], mood: "yell" };
    case "charge":
      return { ...base, ...walkCycle(time, 20), lean: 0.6, aF: [-0.6, 0.6], aB: [-0.8, 0.5], mood: "yell" };
    case "shout":
      return { ...base, lean: 0.2, aF: [1.5, 0.1], mood: "yell" };
    case "drum": {
      const w = Math.sin(time * 22);
      return { ...base, aF: [0.9 + 0.35 * w, 1.5], aB: [0.9 - 0.35 * w, 1.5], mood: "yell" };
    }
    case "hurt":
      return { ...base, lean: -0.45, crouch: 0.6, aF: [0.7, 0.5], aB: [-0.5, 0.6], lF: [0.4, -0.3], lB: [-0.1, -0.1], mood: "hurt" };
    case "air": {
      const spin = (f.ko ? 11 : 7) * t * (f.vx >= 0 ? 1 : -1) * f.face;
      return { ...base, rot: -spin, aF: [2.2, 0.3], aB: [-1.9, 0.4], lF: [0.9, -0.7], lB: [-0.6, -0.5], mood: f.ko ? "ko" : "hurt" };
    }
    case "down":
    case "ko":
      return { ...base, rot: -Math.PI / 2, aF: [2.6, 0.3], aB: [1.6, 0.6], lF: [0.25, -0.4], lB: [-0.1, -0.1], mood: f.act === "ko" ? "ko" : "dizzy" };
    case "getup": {
      const p = Math.min(1, t / 0.4);
      return { ...base, rot: lerp(-Math.PI / 2, 0, p), crouch: lerp(3, 0.4, p), mood: "dizzy" };
    }
    case "cheer": {
      const b = Math.abs(Math.sin(time * 8 + f.id));
      return { ...base, lift: b * 1.6, aF: [2.9, 0.25], aB: [2.75, 0.35], lF: [0.15, -0.2], lB: [-0.15, -0.2], mood: "happy" };
    }
    default:
      return base;
  }
}

interface Body {
  thigh: number;
  shin: number;
  torso: number;
  upper: number;
  fore: number;
  head: number;
  legW: number;
  armW: number;
  torsoW: number;
}

const BODIES: Record<Kind, Body> = {
  hero: { thigh: 3.8, shin: 3.6, torso: 5.4, upper: 3.0, fore: 2.8, head: 2.35, legW: 1.9, armW: 1.5, torsoW: 4.4 },
  runt: { thigh: 3.6, shin: 3.4, torso: 5.0, upper: 2.8, fore: 2.6, head: 2.5, legW: 1.6, armW: 1.3, torsoW: 3.8 },
  brute: { thigh: 3.6, shin: 3.4, torso: 5.4, upper: 3.0, fore: 2.8, head: 2.1, legW: 2.4, armW: 2.0, torsoW: 5.8 },
  drummer: { thigh: 3.7, shin: 3.5, torso: 5.3, upper: 2.9, fore: 2.7, head: 2.35, legW: 1.8, armW: 1.5, torsoW: 4.6 },
  loud: { thigh: 3.8, shin: 3.6, torso: 5.3, upper: 3.0, fore: 2.8, head: 2.35, legW: 1.7, armW: 1.4, torsoW: 4.2 },
  boss: { thigh: 3.4, shin: 3.2, torso: 5.6, upper: 3.0, fore: 2.8, head: 2.2, legW: 2.4, armW: 2.0, torsoW: 6.6 },
  kuzmich: { thigh: 3.6, shin: 3.4, torso: 5.6, upper: 2.9, fore: 2.7, head: 2.3, legW: 1.7, armW: 1.5, torsoW: 4.6 },
  chair: { thigh: 3.7, shin: 3.5, torso: 5.4, upper: 3.0, fore: 2.8, head: 2.3, legW: 2.0, armW: 1.7, torsoW: 5.0 },
  sinyak: { thigh: 3.5, shin: 3.3, torso: 5.4, upper: 3.0, fore: 2.8, head: 2.3, legW: 2.0, armW: 1.7, torsoW: 5.8 },
};

const OUTLINE = "#0d0f16";
const PANTS = "#2c3550";

function shade(hex: string, k: number): string {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.max(0, Math.min(255, Math.round(((n >> 16) & 255) * k)));
  const g = Math.max(0, Math.min(255, Math.round(((n >> 8) & 255) * k)));
  const b = Math.max(0, Math.min(255, Math.round((n & 255) * k)));
  return `rgb(${r},${g},${b})`;
}

function seg(ctx: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number, w: number, color: string): void {
  ctx.lineCap = "round";
  ctx.strokeStyle = OUTLINE;
  ctx.lineWidth = w + 3;
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
  ctx.strokeStyle = color;
  ctx.lineWidth = w;
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
}

function dot(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, color: string): void {
  ctx.fillStyle = OUTLINE;
  ctx.beginPath();
  ctx.arc(x, y, r + 1.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
}

/** A limb from (x, y): upper angle a (0 = down, + = forward), lower bent by b. */
function limb(
  ctx: CanvasRenderingContext2D, x: number, y: number, j: Joint, l1: number, l2: number, w: number,
  upper: string, lower: string, end: { r: number; color: string } | null, shoe = false,
): void {
  const x1 = x + Math.sin(j[0]) * l1;
  const y1 = y + Math.cos(j[0]) * l1;
  const a2 = j[0] + j[1];
  const x2 = x1 + Math.sin(a2) * l2;
  const y2 = y1 + Math.cos(a2) * l2;
  seg(ctx, x, y, x1, y1, w, upper);
  seg(ctx, x1, y1, x2, y2, w * 0.9, lower);
  if (shoe) {
    ctx.save();
    ctx.translate(x2, y2);
    ctx.rotate(-a2 + Math.PI / 2 * 0);
    ctx.fillStyle = OUTLINE;
    ctx.beginPath();
    ctx.ellipse(w * 0.35, 0, w * 0.95, w * 0.62, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#f3f3f3";
    ctx.beginPath();
    ctx.ellipse(w * 0.35, 0, w * 0.75, w * 0.45, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
  if (end) dot(ctx, x2, y2, end.r, end.color);
}

export function drawShadow(ctx: CanvasRenderingContext2D, v: View, f: Fighter): void {
  const p = project(v, f.x, f.z);
  const k = p.k * f.scale;
  const r = Math.max(0.35, 1 - f.y / 30);
  ctx.fillStyle = `rgba(0,0,0,${0.35 * r})`;
  ctx.beginPath();
  ctx.ellipse(p.sx, p.sy, 4.2 * k * r, 1.3 * k * r, 0, 0, Math.PI * 2);
  ctx.fill();
}

export function drawTelegraph(ctx: CanvasRenderingContext2D, v: View, f: Fighter, time: number): void {
  if (f.act !== "windup" || f.ko) return;
  const p = project(v, f.x, f.z);
  const k = p.k * f.scale;
  if (f.kind === "boss" && f.next !== "charge") {
    const r = 12 * project(v, f.x, f.z).k;
    ctx.strokeStyle = `rgba(255,70,60,${0.4 + 0.3 * Math.sin(time * 20)})`;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.ellipse(p.sx, p.sy, r, r * 0.32, 0, 0, Math.PI * 2);
    ctx.stroke();
  }
  if (f.kind === "loud" || (f.kind === "boss" && f.next === "charge")) {
    const len = (f.kind === "loud" ? 30 : 45) * p.k;
    const g = ctx.createLinearGradient(p.sx, 0, p.sx + f.face * len, 0);
    g.addColorStop(0, "rgba(255,120,60,0.45)");
    g.addColorStop(1, "rgba(255,120,60,0)");
    ctx.fillStyle = g;
    ctx.fillRect(Math.min(p.sx, p.sx + f.face * len), p.sy - 2.5 * p.k * 0.4, len, 5 * p.k * 0.4);
  }
  // the «!» over the head
  const hy = p.sy - (20 * k) - f.y * p.k;
  const pulse = 1 + 0.15 * Math.sin(time * 24);
  ctx.save();
  ctx.translate(p.sx, hy);
  ctx.scale(pulse, pulse);
  ctx.fillStyle = "#ff3b30";
  ctx.strokeStyle = OUTLINE;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.arc(0, 0, 10, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#fff";
  ctx.font = "900 15px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("!", 0, 1);
  ctx.restore();
}

export function drawFighter(ctx: CanvasRenderingContext2D, v: View, f: Fighter, time: number, s: State): void {
  const p = project(v, f.x, f.z, f.y);
  const k = p.k * f.scale;
  const pose = poseOf(f, time);
  const b = BODIES[f.kind];
  const white = f.flash > 0;
  const c = (col: string) => (white ? "#ffffff" : col);
  const look = f.look;
  const face = f.face;
  const fade = f.act === "ko" ? Math.max(0, 1 - Math.max(0, f.t - 0.7) / 0.4) : 1;

  if (!drawSprite(ctx, f, p.sx, p.sy, p.k, time)) {
  ctx.save();
  ctx.globalAlpha = fade;
  ctx.translate(p.sx, p.sy);
  const hipH = (b.thigh + b.shin - pose.crouch + pose.lift) * k;
  if (pose.rot !== 0) {
    const cy = f.act === "down" || f.act === "ko" ? -1.2 * k : -hipH;
    ctx.translate(0, cy);
    ctx.rotate(pose.rot * face);
    ctx.translate(0, -cy + (f.act === "down" || f.act === "ko" ? -hipH + 1.2 * k : 0));
  }
  ctx.scale(face * (Math.abs(pose.squash) < 0.2 ? 0.2 * Math.sign(pose.squash || 1) : pose.squash), 1);
  // local frame: x forward, y down, origin = feet on the floor
  const hx = 0;
  const hy = -hipH;
  const sx = hx + Math.sin(pose.lean) * b.torso * k;
  const sy = hy - Math.cos(pose.lean) * b.torso * k;
  const legW = b.legW * k;
  const armW = b.armW * k;
  const skin = c(look.skin);
  const shirt = c(look.shirt);
  const shirtDark = white ? "#ffffff" : shade(look.shirt, 0.72);
  const pants = c(f.kind === "boss" ? "#26262e" : PANTS);
  const pantsDark = white ? "#ffffff" : shade(f.kind === "boss" ? "#26262e" : PANTS, 0.75);

  // back limbs
  limb(ctx, hx - 0.6 * k, hy, pose.lB, b.thigh * k, b.shin * k, legW, pantsDark, pantsDark, null, true);
  limb(ctx, sx - 0.8 * k, sy + 0.6 * k, pose.aB, b.upper * k, b.fore * k, armW, shirtDark, white ? "#fff" : shade(look.skin, 0.85), { r: armW * 0.75, color: white ? "#fff" : shade(look.skin, 0.85) });
  // front leg
  limb(ctx, hx + 0.5 * k, hy, pose.lF, b.thigh * k, b.shin * k, legW, pants, pants, null, true);
  // torso
  const belly = f.kind === "boss" || f.kind === "brute" || f.kind === "sinyak";
  seg(ctx, hx, hy - 0.4 * k, sx, sy + 0.9 * k, b.torsoW * k, shirt);
  if (belly) {
    dot(ctx, (hx + sx) / 2 + 1.1 * k, (hy + sy) / 2 + 0.6 * k, b.torsoW * k * 0.48, shirt);
  }
  // shirt stripe
  ctx.strokeStyle = c(look.stripe);
  ctx.lineWidth = b.torsoW * k * 0.28;
  ctx.lineCap = "butt";
  ctx.beginPath();
  const mx = (hx + sx) / 2;
  const my = (hy + sy) / 2;
  ctx.moveTo(mx - b.torsoW * k * 0.35, my);
  ctx.lineTo(mx + b.torsoW * k * 0.35, my);
  ctx.stroke();
  // drum (in front of the belly)
  if (pose.prop === "drum") {
    ctx.fillStyle = OUTLINE;
    ctx.beginPath();
    ctx.ellipse(mx + 3 * k, my + 0.5 * k, 2.6 * k, 3.1 * k, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = c("#d9423b");
    ctx.beginPath();
    ctx.ellipse(mx + 3 * k, my + 0.5 * k, 2.2 * k, 2.7 * k, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = c("#f4f0e6");
    ctx.beginPath();
    ctx.ellipse(mx + 4.2 * k, my + 0.5 * k, 0.9 * k, 2.6 * k, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  // scarf
  const nx = sx;
  const ny = sy - 0.1 * k;
  seg(ctx, nx - 1.6 * k, ny, nx + 1.6 * k, ny, 1.4 * k, c(look.stripe));
  const tail = Math.sin(time * 9 + f.id) * 0.6 * k;
  seg(ctx, nx - 1.4 * k, ny, nx - 2.8 * k + tail, ny + 2.6 * k, 1.1 * k, c(look.stripe));

  // head
  const headR = b.head * k;
  const hdx = sx + Math.sin(pose.lean) * headR * 0.9 + (pose.mood === "hurt" ? -0.6 * k : 0);
  const hdy = sy - headR * 0.95;
  drawHead(ctx, hdx, hdy, headR, f, pose, c, white, time);

  // front arm (+ megaphone)
  const fist = { r: armW * 0.8, color: skin };
  limb(ctx, sx + 0.6 * k, sy + 0.6 * k, pose.aF, b.upper * k, b.fore * k, armW, shirt, skin, fist);
  if (pose.prop === "megaphone") {
    const a = pose.aF[0] + pose.aF[1];
    const x1 = sx + 0.6 * k + Math.sin(pose.aF[0]) * b.upper * k + Math.sin(a) * b.fore * k;
    const y1 = sy + 0.6 * k + Math.cos(pose.aF[0]) * b.upper * k + Math.cos(a) * b.fore * k;
    ctx.save();
    ctx.translate(x1, y1);
    ctx.rotate(Math.PI / 2 - a);
    ctx.fillStyle = OUTLINE;
    ctx.beginPath();
    ctx.moveTo(-0.5 * k, -1.3 * k);
    ctx.lineTo(4.2 * k, -2.6 * k);
    ctx.lineTo(4.2 * k, 2.6 * k);
    ctx.lineTo(-0.5 * k, 1.3 * k);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = c("#f4f0e6");
    ctx.beginPath();
    ctx.moveTo(0, -0.8 * k);
    ctx.lineTo(3.8 * k, -2.1 * k);
    ctx.lineTo(3.8 * k, 2.1 * k);
    ctx.lineTo(0, 0.8 * k);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = c("#e0702a");
    ctx.fillRect(3.2 * k, -2.1 * k, 0.6 * k, 4.2 * k);
    ctx.restore();
  }
  ctx.restore();
  }

  // spin / kick trails (unmirrored, screen space)
  if (f.kind === "hero" && (f.act === "spin" || f.act === "rage")) {
    const r = (f.act === "rage" ? 14 : 12) * p.k;
    const cy = p.sy - 7 * p.k;
    ctx.strokeStyle = f.act === "rage" ? "rgba(255,120,60,0.75)" : "rgba(198,230,58,0.75)";
    ctx.lineWidth = 4;
    const start = time * 18;
    ctx.beginPath();
    ctx.ellipse(p.sx, cy, r, r * 0.35, 0, start, start + Math.PI * 1.3);
    ctx.stroke();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "rgba(255,255,255,0.6)";
    ctx.beginPath();
    ctx.ellipse(p.sx, cy, r * 0.8, r * 0.28, 0, start + 1, start + 1 + Math.PI);
    ctx.stroke();
  }
  // buffed rivals glow
  if (f.buff > 0 && !f.ko && f.kind !== "hero") {
    ctx.fillStyle = "rgba(255,179,71,0.9)";
    ctx.font = `700 ${Math.round(10 + p.k)}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.fillText("♪", p.sx + 4 * k, p.sy - 18 * k + Math.sin(time * 6) * 3);
  }
  // dizzy stars
  if (f.act === "down" || f.act === "getup") {
    for (let i = 0; i < 3; i++) {
      const a = time * 6 + (i * Math.PI * 2) / 3;
      ctx.fillStyle = "#ffe14a";
      star(ctx, p.sx + Math.cos(a) * 3 * k - face * 4 * k, p.sy - 4 * k + Math.sin(a) * 1 * k, 3.5, a);
    }
  }
  // enemy HP pip
  if (f.kind !== "hero" && !f.ko && f.hp < f.maxHp && !isBoss(f.kind)) {
    const w = 8 * k;
    const y = p.sy - 18.5 * k - f.y * 0;
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(p.sx - w / 2, y, w, 3);
    ctx.fillStyle = "#ff5a4a";
    ctx.fillRect(p.sx - w / 2, y, (w * f.hp) / f.maxHp, 3);
  }
  void s;
}

function drawHead(
  ctx: CanvasRenderingContext2D, x: number, y: number, r: number, f: Fighter, pose: Pose,
  c: (col: string) => string, white: boolean, time: number,
): void {
  const look = f.look;
  if (look.hat === "hood") dot(ctx, x - r * 0.25, y + r * 0.1, r * 1.18, c(shade(look.shirt, 0.8)));
  dot(ctx, x, y, r, c(look.skin));
  // hair / hats
  ctx.lineWidth = 2;
  if (look.hat === "beanie") {
    ctx.fillStyle = OUTLINE;
    ctx.beginPath();
    ctx.arc(x, y - r * 0.15, r * 1.08, Math.PI, 0);
    ctx.fill();
    ctx.fillStyle = c(look.hatColor);
    ctx.beginPath();
    ctx.arc(x, y - r * 0.15, r * 0.96, Math.PI, 0);
    ctx.fill();
    ctx.fillStyle = c(shade(look.hatColor, 0.75));
    ctx.fillRect(x - r * 1.02, y - r * 0.32, r * 2.04, r * 0.36);
    dot(ctx, x, y - r * 1.2, r * 0.3, c("#ffffff"));
  } else if (look.hat === "cap") {
    ctx.fillStyle = OUTLINE;
    ctx.beginPath();
    ctx.arc(x, y - r * 0.2, r * 1.05, Math.PI, 0);
    ctx.fill();
    ctx.fillStyle = c(look.hatColor);
    ctx.beginPath();
    ctx.arc(x, y - r * 0.2, r * 0.93, Math.PI, 0);
    ctx.fill();
    ctx.fillStyle = OUTLINE;
    ctx.fillRect(x, y - r * 0.34, r * 1.7, r * 0.32);
    ctx.fillStyle = c(shade(look.hatColor, 0.8));
    ctx.fillRect(x + r * 0.1, y - r * 0.28, r * 1.5, r * 0.2);
  } else if (look.hat === "bandana") {
    ctx.fillStyle = c(look.hair);
    ctx.beginPath();
    ctx.arc(x, y - r * 0.1, r * 0.98, Math.PI * 1.05, -0.05);
    ctx.fill();
    ctx.fillStyle = c(look.hatColor);
    ctx.fillRect(x - r, y - r * 0.55, r * 2, r * 0.38);
    ctx.beginPath();
    ctx.moveTo(x - r, y - r * 0.45);
    ctx.lineTo(x - r * 1.7, y - r * 0.1 + Math.sin(time * 10) * r * 0.15);
    ctx.lineTo(x - r * 1.6, y - r * 0.7);
    ctx.fill();
  } else if (look.hat === "bald") {
    ctx.fillStyle = "rgba(255,255,255,0.45)";
    ctx.beginPath();
    ctx.ellipse(x - r * 0.25, y - r * 0.55, r * 0.35, r * 0.18, -0.4, 0, Math.PI * 2);
    ctx.fill();
  } else if (look.hat === "hood") {
    ctx.fillStyle = c(look.hair);
    ctx.beginPath();
    ctx.arc(x, y - r * 0.2, r * 0.95, Math.PI * 1.1, -0.1);
    ctx.fill();
  }
  // boss beard
  if (f.kind === "boss" || f.kind === "brute") {
    ctx.fillStyle = c(f.kind === "boss" ? "#2b1d14" : look.hair);
    ctx.beginPath();
    if (f.kind === "boss") ctx.arc(x + r * 0.15, y + r * 0.35, r * 0.85, 0.1, Math.PI - 0.1);
    else ctx.ellipse(x + r * 0.45, y + r * 0.22, r * 0.45, r * 0.14, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  if (white) return;
  // face (looks forward = +x)
  const ex = x + r * 0.42;
  const ey = y - r * 0.05;
  ctx.fillStyle = OUTLINE;
  ctx.strokeStyle = OUTLINE;
  ctx.lineWidth = Math.max(1.5, r * 0.16);
  ctx.lineCap = "round";
  if (pose.mood === "ko" || pose.mood === "dizzy") {
    for (const dx of [-0.35, 0.35]) {
      const cx = ex + dx * r;
      if (pose.mood === "ko") {
        ctx.beginPath();
        ctx.moveTo(cx - r * 0.15, ey - r * 0.15);
        ctx.lineTo(cx + r * 0.15, ey + r * 0.15);
        ctx.moveTo(cx + r * 0.15, ey - r * 0.15);
        ctx.lineTo(cx - r * 0.15, ey + r * 0.15);
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.arc(cx, ey, r * 0.15, time * 8, time * 8 + Math.PI * 1.5);
        ctx.stroke();
      }
    }
  } else {
    const eyeR = Math.max(1.4, r * 0.13);
    for (const dx of [-0.32, 0.32]) {
      ctx.beginPath();
      ctx.arc(ex + dx * r, ey, eyeR, 0, Math.PI * 2);
      ctx.fill();
    }
    if (pose.mood === "angry" || pose.mood === "yell") {
      ctx.beginPath();
      ctx.moveTo(ex - r * 0.55, ey - r * 0.38);
      ctx.lineTo(ex - r * 0.12, ey - r * 0.22);
      ctx.moveTo(ex + r * 0.55, ey - r * 0.38);
      ctx.lineTo(ex + r * 0.12, ey - r * 0.22);
      ctx.stroke();
    }
  }
  // mouth
  const mx = x + r * 0.45;
  const my = y + r * 0.45;
  if (pose.mood === "yell" || pose.mood === "hurt" || pose.mood === "ko") {
    ctx.fillStyle = "#5a1d1d";
    ctx.beginPath();
    ctx.ellipse(mx, my, r * 0.22, r * (pose.mood === "yell" ? 0.26 : 0.18), 0, 0, Math.PI * 2);
    ctx.fill();
  } else if (pose.mood === "happy" || f.kind === "hero") {
    ctx.beginPath();
    ctx.arc(mx, my - r * 0.12, r * 0.25, 0.2, Math.PI - 0.2);
    ctx.stroke();
  } else {
    ctx.beginPath();
    ctx.moveTo(mx - r * 0.22, my);
    ctx.lineTo(mx + r * 0.22, my - r * 0.05);
    ctx.stroke();
  }
}

function star(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, rot: number): void {
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const a = rot + (i * Math.PI) / 5;
    const rr = i % 2 ? r * 0.45 : r;
    ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
  }
  ctx.closePath();
  ctx.fill();
}

// ---------------------------------------------------------------------------
// Pickups, particles, HUD
// ---------------------------------------------------------------------------

const PROP_URLS: Record<"bottle" | "chair", string> = { bottle: bottleUrl, chair: chairUrl };
const propCache = new Map<string, HTMLImageElement>();

function propImage(kind: "bottle" | "chair"): HTMLImageElement | null {
  let img = propCache.get(kind);
  if (!img) {
    img = new Image();
    img.src = PROP_URLS[kind];
    propCache.set(kind, img);
  }
  return img.complete && img.naturalWidth > 0 ? img : null;
}

/** A bottle / a stadium seat / a spit, centred at (x, y), `u` px per world unit, turned by `rot`. */
function drawThing(ctx: CanvasRenderingContext2D, kind: ShotKind, x: number, y: number, u: number, rot: number): void {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(rot);
  const art = kind === "spit" ? null : propImage(kind);
  if (art) {
    // drawn props: a bottle 6.2 units tall, a seat 7.5 units wide
    const h = kind === "bottle" ? 6.2 * u : (7.5 * u * art.naturalHeight) / art.naturalWidth;
    const w = (h * art.naturalWidth) / art.naturalHeight;
    ctx.drawImage(art, -w / 2, -h / 2, w, h);
    ctx.restore();
    return;
  }
  ctx.lineJoin = "round";
  if (kind === "bottle") {
    ctx.fillStyle = OUTLINE;
    ctx.beginPath();
    ctx.roundRect(-1.3 * u, -1.4 * u, 2.6 * u, 4.4 * u, 0.9 * u);
    ctx.fill();
    ctx.fillRect(-0.6 * u, -3.1 * u, 1.2 * u, 2 * u);
    ctx.fillStyle = "#3f9a52";
    ctx.beginPath();
    ctx.roundRect(-1 * u, -1.1 * u, 2 * u, 3.8 * u, 0.7 * u);
    ctx.fill();
    ctx.fillRect(-0.35 * u, -2.9 * u, 0.7 * u, 1.9 * u);
    ctx.fillStyle = "rgba(255,255,255,0.55)";
    ctx.fillRect(-0.6 * u, -0.6 * u, 0.35 * u, 2.6 * u);
  } else if (kind === "chair") {
    ctx.fillStyle = OUTLINE;
    ctx.beginPath();
    ctx.roundRect(-3.4 * u, -0.9 * u, 6.8 * u, 2 * u, 0.8 * u);
    ctx.roundRect(1.6 * u, -5 * u, 2.2 * u, 5.4 * u, 0.9 * u);
    ctx.fill();
    ctx.fillStyle = "#2f6fe0";
    ctx.beginPath();
    ctx.roundRect(-3 * u, -0.55 * u, 6 * u, 1.3 * u, 0.6 * u);
    ctx.roundRect(1.95 * u, -4.6 * u, 1.5 * u, 4.6 * u, 0.6 * u);
    ctx.fill();
    ctx.fillStyle = "#9aa3b5";
    ctx.fillRect(-2.6 * u, 1.1 * u, 0.6 * u, 1.6 * u);
    ctx.fillRect(1.8 * u, 1.1 * u, 0.6 * u, 1.6 * u);
  } else {
    ctx.fillStyle = "rgba(215,245,200,0.9)";
    ctx.beginPath();
    ctx.ellipse(0, 0, 1.3 * u, 0.9 * u, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "rgba(215,245,200,0.45)";
    ctx.beginPath();
    ctx.ellipse(-2 * u, 0, 1.6 * u, 0.5 * u, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

/** What the throwers hold: Креслолом lifts a seat over his head, Синяк waves a bottle. */
export function drawHeld(ctx: CanvasRenderingContext2D, v: View, f: Fighter, time: number): void {
  if (f.ko || f.act === "air" || f.act === "down" || f.act === "getup" || f.act === "hurt") return;
  const p = project(v, f.x, f.z, f.y);
  const k = p.k * f.scale;
  if (f.kind === "chair" && f.act === "windup") {
    drawThing(ctx, "chair", p.sx, p.sy - 21 * k + Math.sin(time * 30) * 0.4 * k, p.k * 1.1, Math.sin(time * 14) * 0.1);
  } else if (f.kind === "sinyak" && f.act !== "strike") {
    const up = f.act === "windup";
    drawThing(ctx, "bottle", p.sx + f.face * (up ? -2 : 5) * k, p.sy - (up ? 20 : 9) * k, p.k * 0.9, f.face * (up ? -0.6 : 0.4) + Math.sin(time * 5 + f.id) * 0.15);
  }
}

export function drawShots(ctx: CanvasRenderingContext2D, v: View, s: State, time: number): void {
  for (const sh of s.shots) {
    const g = project(v, sh.x, sh.z);
    ctx.fillStyle = "rgba(0,0,0,0.28)";
    ctx.beginPath();
    ctx.ellipse(g.sx, g.sy, (sh.kind === "chair" ? 4 : 2) * g.k, 0.9 * g.k, 0, 0, Math.PI * 2);
    ctx.fill();
    const p = project(v, sh.x, sh.z, sh.y);
    const spin = sh.kind === "spit" ? (sh.vx < 0 ? Math.PI : 0) : time * (sh.kind === "chair" ? 9 : 14) + sh.id;
    if (sh.mine) {
      ctx.fillStyle = "rgba(198,230,58,0.35)";
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, 4.5 * p.k, 0, Math.PI * 2);
      ctx.fill();
    }
    drawThing(ctx, sh.kind, p.sx, p.sy, p.k * (sh.kind === "chair" ? 1.1 : 0.9), spin);
  }
}

export function drawPickups(ctx: CanvasRenderingContext2D, v: View, s: State, time: number): void {
  for (const pk of s.pickups) {
    const p = project(v, pk.x, pk.z);
    const bob = Math.sin(time * 5 + pk.id) * 3;
    const blink = pk.t < 2 && Math.floor(time * 8) % 2 === 0;
    if (blink) continue;
    ctx.fillStyle = "rgba(0,0,0,0.3)";
    ctx.beginPath();
    ctx.ellipse(p.sx, p.sy, 10, 3.5, 0, 0, Math.PI * 2);
    ctx.fill();
    // a bottle of kvass
    const y = p.sy - 18 + bob;
    ctx.fillStyle = OUTLINE;
    ctx.beginPath();
    ctx.roundRect(p.sx - 7, y - 4, 14, 22, 5);
    ctx.fill();
    ctx.fillRect(p.sx - 3.5, y - 11, 7, 9);
    ctx.fillStyle = "#c27a2c";
    ctx.beginPath();
    ctx.roundRect(p.sx - 5, y - 2, 10, 18, 4);
    ctx.fill();
    ctx.fillStyle = "#c6e63a";
    ctx.fillRect(p.sx - 5, y + 4, 10, 6);
    ctx.fillStyle = "#e9e9e9";
    ctx.fillRect(p.sx - 2, y - 10, 4, 6);
  }
}

export function drawParticles(ctx: CanvasRenderingContext2D, fx: Fx): void {
  for (const p of fx.particles) {
    if (p.life < 0) continue;
    const a = 1 - p.life / p.max;
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, a * 1.4));
    ctx.translate(p.x, p.y);
    ctx.rotate(p.rot);
    switch (p.kind) {
      case "star":
        ctx.fillStyle = p.color;
        star(ctx, 0, 0, 6 * p.size, 0);
        break;
      case "ring":
        ctx.strokeStyle = p.color;
        ctx.lineWidth = 3 * a;
        ctx.beginPath();
        ctx.arc(0, 0, (10 + 34 * (1 - a)) * p.size, 0, Math.PI * 2);
        ctx.stroke();
        break;
      case "word":
      case "num":
      case "heal":
      case "note": {
        const pop = p.kind === "word" ? Math.min(1.25, 0.4 + p.life * 8) : 1;
        const size = p.kind === "word" ? 26 * p.size : p.kind === "note" ? 20 : 16;
        ctx.scale(pop, pop);
        ctx.font = `900 ${size}px system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.lineJoin = "round";
        ctx.strokeStyle = OUTLINE;
        ctx.lineWidth = p.kind === "word" ? 6 : 4;
        ctx.strokeText(p.text ?? "", 0, 0);
        ctx.fillStyle = p.color;
        ctx.fillText(p.text ?? "", 0, 0);
        break;
      }
      case "dust":
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(0, 0, (4 + 8 * (1 - a)) * p.size, 0, Math.PI * 2);
        ctx.fill();
        break;
      case "wave":
        ctx.strokeStyle = p.color;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(0, 0, 10 + 14 * p.size, -0.7, 0.7);
        if (p.face === -1) ctx.rotate(Math.PI);
        ctx.stroke();
        break;
      case "item":
        drawItem(ctx, p.item ?? 0, p.color);
        break;
    }
    ctx.restore();
  }
}

function drawItem(ctx: CanvasRenderingContext2D, item: number, color: string): void {
  ctx.fillStyle = OUTLINE;
  if (item === 0) {
    // sneaker
    ctx.beginPath();
    ctx.roundRect(-9, -5, 18, 10, 4);
    ctx.fill();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(-7.5, -3.5, 15, 6, 3);
    ctx.fill();
    ctx.fillStyle = "#d9423b";
    ctx.fillRect(-2, -3.5, 4, 6);
  } else if (item === 1) {
    // beanie
    ctx.beginPath();
    ctx.arc(0, 2, 9, Math.PI, 0);
    ctx.fill();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(0, 2, 7.5, Math.PI, 0);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.arc(0, -7, 2.6, 0, Math.PI * 2);
    ctx.fill();
  } else {
    // scarf piece
    ctx.fillRect(-11, -4, 22, 8);
    for (let i = 0; i < 4; i++) {
      ctx.fillStyle = i % 2 ? color : "#1d1d24";
      ctx.fillRect(-10 + i * 5, -3, 5, 6);
    }
  }
}

function bar(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, frac: number, color: string, bg = "rgba(0,0,0,0.55)"): void {
  ctx.fillStyle = OUTLINE;
  ctx.beginPath();
  ctx.roundRect(x - 2, y - 2, w + 4, h + 4, (h + 4) / 2);
  ctx.fill();
  ctx.fillStyle = bg;
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, h / 2);
  ctx.fill();
  if (frac > 0) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(x, y, Math.max(h, w * Math.min(1, frac)), h, h / 2);
    ctx.fill();
  }
}

function outlinedText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, size: number, color: string, align: CanvasTextAlign = "center", weight = 900): void {
  ctx.font = `${weight} ${size}px system-ui, sans-serif`;
  ctx.textAlign = align;
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";
  ctx.strokeStyle = OUTLINE;
  ctx.lineWidth = Math.max(3, size * 0.22);
  ctx.strokeText(text, x, y);
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
}

export function drawHud(ctx: CanvasRenderingContext2D, v: View, s: State, fx: Fx, time: number, topInset: number): void {
  const pad = 14;
  const top = topInset + 12;
  const h = s.hero;
  // hero hp + rage
  const bw = Math.min(170, v.w * 0.42);
  outlinedText(ctx, "ТЫ", pad, top + 6, 13, "#c6e63a", "left");
  bar(ctx, pad + 26, top, bw, 12, h.hp / h.maxHp, h.hp / h.maxHp < 0.3 ? "#ff5a4a" : "#c6e63a");
  const rageFull = s.rage >= 100;
  const rageColor = rageFull ? (Math.floor(time * 6) % 2 ? "#ff8a3d" : "#ffe14a") : "#ff8a3d";
  bar(ctx, pad + 26, top + 19, bw * 0.8, 7, s.rage / 100, rageColor);
  outlinedText(ctx, "ЯРОСТЬ", pad + 26 + bw * 0.8 + 8, top + 22.5, 9, rageFull ? "#ffe14a" : "rgba(255,255,255,0.7)", "left", 800);
  // wave + knockouts
  const waves = s.mode === "derby" ? `ВОЛНА ${Math.max(1, s.wave)}/${DERBY_WAVES}` : `ВОЛНА ${Math.max(1, s.wave)}`;
  outlinedText(ctx, waves, v.w - pad, top + 6, 13, "#ffffff", "right");
  outlinedText(ctx, `🥊 ${s.knockouts}`, v.w - pad, top + 26, 16, "#ffe14a", "right");
  // combo
  if (s.combo >= 2) {
    const pop = fx.combo && fx.combo.t < 0.2 ? 1 + (0.2 - fx.combo.t) * 2.5 : 1;
    ctx.save();
    ctx.translate(v.w - pad - 4, top + 62);
    ctx.scale(pop, pop);
    outlinedText(ctx, `×${s.combo}`, 0, 0, 30, s.combo >= 10 ? "#ff8a3d" : "#ffffff", "right");
    outlinedText(ctx, "КОМБО", 0, 22, 11, "#ffe14a", "right", 800);
    ctx.restore();
  }
  if (fx.combo && COMBO_WORDS[fx.combo.n]) {
    const t = fx.combo.t;
    ctx.save();
    ctx.globalAlpha = Math.max(0, 1 - Math.max(0, t - 0.8) / 0.4);
    ctx.translate(v.w / 2, v.h * 0.3);
    ctx.rotate(-0.08);
    const sc = Math.min(1.1, 0.3 + t * 6);
    ctx.scale(sc, sc);
    outlinedText(ctx, COMBO_WORDS[fx.combo.n], 0, 0, 34, "#c6e63a");
    ctx.restore();
  }
  // boss bar
  const boss = s.enemies.find((e) => isBoss(e.kind) && !e.out);
  if (boss) {
    const w = v.w - pad * 2;
    const y = top + 92;
    outlinedText(ctx, ENEMY_NAMES[boss.kind as keyof typeof ENEMY_NAMES].toUpperCase(), v.w / 2, y - 8, 11, "#ff8a3d", "center", 800);
    bar(ctx, pad, y, w, 9, boss.hp / boss.maxHp, "#ff5a4a");
  }
  // wave banner
  if (s.banner) {
    const t = s.banner.t;
    const inA = Math.min(1, t * 5);
    const outA = Math.max(0, 1 - Math.max(0, t - 1.4) / 0.4);
    ctx.save();
    ctx.globalAlpha = inA * outA;
    ctx.fillStyle = "rgba(0,0,0,0.45)";
    ctx.fillRect(0, v.h * 0.33 - 38, v.w, 76);
    ctx.translate(v.w / 2 + (1 - inA) * -80, v.h * 0.33);
    outlinedText(ctx, s.banner.text, 0, -8, 40, s.banner.text === "БОСС!" ? "#ff5a4a" : "#c6e63a");
    outlinedText(ctx, s.banner.sub, 0, 24, 14, "#ffffff", "center", 800);
    ctx.restore();
  }
  // hurt vignette
  if (fx.flash > 0) {
    const g = ctx.createRadialGradient(v.w / 2, v.h / 2, v.h * 0.25, v.w / 2, v.h / 2, v.h * 0.75);
    g.addColorStop(0, "rgba(255,40,40,0)");
    g.addColorStop(1, `rgba(255,40,40,${fx.flash})`);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, v.w, v.h);
  }
  if (fx.rageFlash > 0) {
    ctx.fillStyle = `rgba(255,170,60,${fx.rageFlash * 0.5})`;
    ctx.fillRect(0, 0, v.w, v.h);
  }
}

/** Everything in one frame. */
export function drawFrame(
  ctx: CanvasRenderingContext2D, v: View, s: State, fx: Fx, bg: HTMLImageElement | null, time: number, topInset: number,
): void {
  ctx.save();
  if (s.shake > 0) ctx.translate((Math.random() - 0.5) * s.shake, (Math.random() - 0.5) * s.shake);
  drawBackground(ctx, v, bg, time);
  drawPickups(ctx, v, s, time);
  const all = [s.hero, ...s.enemies];
  for (const f of all) drawShadow(ctx, v, f);
  for (const f of all) drawTelegraph(ctx, v, f, time);
  all.sort((a, b) => b.z - a.z || a.id - b.id);
  for (const f of all) {
    drawFighter(ctx, v, f, time, s);
    drawHeld(ctx, v, f, time);
  }
  drawShots(ctx, v, s, time);
  drawParticles(ctx, fx);
  ctx.restore();
  drawHud(ctx, v, s, fx, time, topInset);
}
