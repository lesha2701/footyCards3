/**
 * «Замес» drawn fighters: each fan is cut into parts (scratchpad tool, see
 * assets/zames/rig/rig.json) — torso, near / far arm, front / back leg and
 * four heads (calm, angry, dizzy, knocked out). Parts are posed by angles
 * around their pivots, all in half-size body-image pixels; the feet sit at
 * `rig.feet`. Until the pictures load, render.ts draws the code-drawn dolls.
 */
import rigData from "@/assets/zames/rig/rig.json";
import type { Fighter, Kind } from "@/lib/zames/engine";
import { HERO_MOVES } from "@/lib/zames/engine";

interface Part {
  x: number;
  y: number;
  w: number;
  h: number;
  px: number;
  py: number;
}

interface Rig {
  feet: [number, number];
  neck: [number, number];
  parts: Record<string, Part>;
}

const RIGS = rigData as unknown as Record<string, Rig>;

/** The hero skin worn in this brawl (style key of a "zames_hero" cosmetic; rig "skin-<key>"). */
let heroSkin: string | null = null;

export function setHeroSkin(key: string | null | undefined): void {
  heroSkin = key && RIGS[`skin-${key}`] ? key : null;
}

function rigKey(kind: Kind): string {
  return kind === "hero" && heroSkin ? `skin-${heroSkin}` : kind;
}

const URLS = import.meta.glob<string>("@/assets/zames/rig/*.webp", { eager: true, import: "default" });

const cache = new Map<string, HTMLImageElement>();

function image(rig: string, part: string): HTMLImageElement | null {
  const key = `${rig}-${part}`;
  let img = cache.get(key);
  if (!img) {
    const url = URLS[`/src/assets/zames/rig/${key}.webp`];
    if (!url) return null;
    img = new Image();
    img.src = url;
    cache.set(key, img);
  }
  return img.complete && img.naturalWidth > 0 ? img : null;
}

const PARTS = ["torso", "nearArm", "farArm", "frontLeg", "backLeg", "head0", "head1", "head2", "head3"];

/** Starts loading the fighters' parts (and the worn hero skin's). */
export function preloadSprites(): void {
  const rigs = Object.keys(RIGS).filter((k) => !k.startsWith("skin-"));
  if (heroSkin) rigs.push(`skin-${heroSkin}`);
  for (const rig of rigs) for (const p of PARTS) image(rig, p);
}

export function spritesReady(rig: string): boolean {
  return PARTS.every((p) => image(rig, p) !== null);
}

/** Pose in degrees, forward-positive (a raised arm / a kicking leg), plus px offsets. */
interface SpritePose {
  near: number;
  far: number;
  front: number;
  back: number;
  lean: number;
  lift: number;
  crouch: number;
  farX: number;
  squash: number;
  rot: number; // radians, whole body (air / down)
  lying: boolean;
  head: 0 | 1 | 2 | 3;
}

function ext(t: number, from: number, to: number, dur: number): number {
  if (t < from) return Math.min(1, t / Math.max(0.001, from)) * 0.3;
  if (t < to) return 0.3 + 0.7 * Math.min(1, (t - from) / Math.max(0.001, (to - from) * 0.5));
  return Math.max(0, 1 - (t - to) / Math.max(0.001, dur - to));
}

function poseOf(f: Fighter, time: number): SpritePose {
  const breathe = Math.sin(time * 4 + f.id);
  const p: SpritePose = {
    near: 6 + breathe * 3, far: breathe * 2, front: 0, back: 0, lean: 0, lift: breathe * 2, crouch: 0, farX: 0,
    squash: 1, rot: 0, lying: false, head: 0,
  };
  const t = f.t;
  switch (f.act) {
    case "walk": {
      const speed = f.kind === "brute" || f.kind === "boss" || f.kind === "sinyak" ? 8 : 12;
      const sw = Math.sin((time + f.id) * speed);
      return { ...p, front: 20 * sw, back: -20 * sw, near: 6 - 12 * sw, far: 10 * sw, lift: Math.abs(Math.cos((time + f.id) * speed)) * 7, lean: 4 };
    }
    case "p1": {
      const m = HERO_MOVES.p1;
      const e = ext(t, m.from, m.to, m.dur);
      return { ...p, near: 6 + 70 * e, lean: 7 * e, head: 1 };
    }
    case "p2": {
      const m = HERO_MOVES.p2;
      const e = ext(t, m.from, m.to, m.dur);
      return { ...p, far: 22 * e, farX: 45 * e, near: -12 * e, lean: 9 * e, head: 1 };
    }
    case "p3": {
      const m = HERO_MOVES.p3;
      const e = ext(t, m.from, m.to, m.dur);
      return { ...p, near: -35 + 175 * e, lift: 18 * e, lean: -4 * e, crouch: 20 * (1 - e), head: 1 };
    }
    case "kick": {
      const m = HERO_MOVES.kick;
      const e = ext(t, m.from, m.to, m.dur);
      return { ...p, front: 88 * e, back: -12 * e, lean: -14 * e, near: -25 * e, far: 18 * e, head: 1 };
    }
    case "spin": {
      const m = HERO_MOVES.spin;
      const k = Math.min(1, t / m.dur);
      const e = ext(t, m.from, m.to, m.dur);
      return { ...p, squash: Math.cos(k * Math.PI * 2), front: 85 * e, back: -10 * e, lean: -10 * e, near: 70, far: 40, lift: 25 * e, head: 1 };
    }
    case "sweep": {
      const m = HERO_MOVES.sweep;
      const e = ext(t, m.from, m.to, m.dur);
      return { ...p, crouch: 110 * Math.min(1, e * 1.4), front: 80 * e, back: -60 * e, lean: 22 * e, near: 40 * e, far: -20 * e, head: 1 };
    }
    case "block":
      return { ...p, near: 115, far: 70, lean: -4, crouch: 14, head: 1 };
    case "rage": {
      const w = Math.sin(time * 40);
      return { ...p, squash: Math.cos(time * 26), near: 70 + 45 * w, far: 70 - 45 * w, front: 45 * w, back: -45 * w, lift: 22, head: 1 };
    }
    case "windup":
      if (f.kind === "boss" || f.kind === "chair") return { ...p, near: 165, far: 130, lean: -8, head: 1 };
      if (f.kind === "loud") return { ...p, far: 15, lean: -8, head: 1 };
      if (f.kind === "kuzmich") return { ...p, lean: -12 + Math.sin(time * 40) * 1.5, near: 15, far: 10, head: 1 };
      return { ...p, near: -45, lean: -10 + Math.sin(time * 50) * 2, head: 1 };
    case "strike":
      if (f.kind === "kuzmich") return { ...p, lean: 14, near: 10, head: 1 }; // the spit: the head goes forward
      if (f.kind === "chair") return { ...p, near: 120, far: 100, lean: 16, front: 10, head: 1 }; // the seat goes off overhead
      return { ...p, near: 78, lean: 12, front: 10, head: 1 };
    case "slam":
      return { ...p, near: 35, far: 35, lean: 25, crouch: 45, head: 1 };
    case "charge": {
      const sw = Math.sin(time * 20);
      return { ...p, front: 25 * sw, back: -25 * sw, lean: 24, near: -30, far: -20, head: 1 };
    }
    case "shout":
      return { ...p, far: 18, lean: 10, head: 1 };
    case "drum": {
      const w = Math.sin(time * 22);
      return { ...p, near: 12 + 14 * w, far: -14 * w, head: 1 };
    }
    case "hurt":
      return { ...p, lean: -18, near: -25, far: 35, front: 15, back: -10, head: 2 };
    case "air": {
      const spin = (f.ko ? 11 : 7) * t * (f.vx >= 0 ? 1 : -1) * f.face;
      return { ...p, rot: spin, near: 130, far: -40, front: 45, back: -35, head: f.ko ? 3 : 2 };
    }
    case "down":
    case "ko":
      return { ...p, lying: true, near: 60, far: 20, front: 10, back: -5, head: f.act === "ko" ? 3 : 2, lift: 0 };
    case "getup": {
      const k = Math.min(1, t / 0.4);
      return { ...p, rot: (1 - k) * (Math.PI / 2), crouch: 60 * (1 - k), head: 2 };
    }
    case "cheer": {
      const b = Math.abs(Math.sin(time * 8 + f.id));
      return { ...p, near: 165, far: 150, lift: b * 22, head: 0 };
    }
    default:
      if (f.kind !== "hero" && f.cool < 0.3 && f.token) p.head = 1;
      return p;
  }
}

/** Screen height of a fighter, in world units × the fighter's scale. */
export const SPRITE_HEIGHT = 22;

function drawPart(ctx: CanvasRenderingContext2D, key: string, rig: Rig, name: string, deg: number, dx = 0): void {
  const img = image(key, name);
  const part = rig.parts[name];
  if (!img || !part) return;
  if (deg !== 0) {
    ctx.save();
    ctx.translate(part.px + dx, part.py);
    ctx.rotate((-deg * Math.PI) / 180);
    ctx.translate(-part.px - dx, -part.py);
    ctx.drawImage(img, part.x + dx, part.y, part.w, part.h);
    ctx.restore();
  } else ctx.drawImage(img, part.x + dx, part.y, part.w, part.h);
}

let filterOk: boolean | null = null;

/** Draws the fighter with its feet at (sx, sy); `k` = px per world unit there. */
export function drawSprite(ctx: CanvasRenderingContext2D, f: Fighter, sx: number, sy: number, k: number, time: number): boolean {
  const key = rigKey(f.kind);
  if (!spritesReady(key)) return false;
  const rig = RIGS[key];
  const pose = poseOf(f, time);
  const top = Math.min(...[0, 1, 2, 3].map((i) => rig.parts[`head${i}`]?.y ?? rig.parts.torso.y));
  const bodyH = rig.feet[1] - top;
  const s = (SPRITE_HEIGHT * k * f.scale) / bodyH;
  const [fx, fy] = rig.feet;
  const hip: [number, number] = [
    (rig.parts.frontLeg.px + rig.parts.backLeg.px) / 2, (rig.parts.frontLeg.py + rig.parts.backLeg.py) / 2,
  ];
  const fade = f.act === "ko" ? Math.max(0, 1 - Math.max(0, f.t - 0.7) / 0.4) : 1;

  ctx.save();
  ctx.globalAlpha = fade;
  if (f.flash > 0) {
    if (filterOk === null) filterOk = typeof ctx.filter === "string";
    if (filterOk) ctx.filter = "brightness(2.2) saturate(0.4)";
  }
  ctx.translate(sx, sy);
  if (pose.lying) {
    // on the back along the floor, head behind
    ctx.translate(0, -bodyH * 0.11 * s);
    ctx.scale(f.face * s, s);
    ctx.rotate(-Math.PI / 2);
    ctx.translate(-fx, -(fy - bodyH * 0.45));
    ctx.translate(0, 0);
  } else {
    const sq = Math.abs(pose.squash) < 0.18 ? 0.18 * Math.sign(pose.squash || 1) : pose.squash;
    ctx.translate(0, -pose.lift * s);
    if (pose.rot !== 0) {
      ctx.translate(0, -bodyH * 0.5 * s);
      ctx.rotate(pose.rot * -f.face);
      ctx.translate(0, bodyH * 0.5 * s);
    }
    ctx.scale(f.face * sq * s, s);
    ctx.translate(-fx, -fy);
  }

  drawPart(ctx, key, rig, "backLeg", pose.back);
  drawPart(ctx, key, rig, "frontLeg", pose.front);
  // upper body: crouch + lean around the hips
  ctx.save();
  ctx.translate(0, pose.crouch);
  ctx.translate(hip[0], hip[1]);
  ctx.rotate((pose.lean * Math.PI) / 180);
  ctx.translate(-hip[0], -hip[1]);
  drawPart(ctx, key, rig, "farArm", pose.far, pose.farX);
  // the head nods a little with the blows
  const headName = `head${pose.head}`;
  const nod = pose.head === 2 ? -8 : pose.head === 1 ? 4 : Math.sin(time * 3 + f.id) * 2;
  drawPart(ctx, key, rig, headName, nod);
  drawPart(ctx, key, rig, "torso", 0);
  drawPart(ctx, key, rig, "nearArm", pose.near);
  ctx.restore();
  ctx.restore();
  return true;
}
