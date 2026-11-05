/** What each person on the pitch looks like doing, from the engine's state:
 * a clip and how far into it, faded from the last one. Kicks are timed so the
 * foot meets the ball on the tick the engine releases it. Presentation only:
 * nothing here feeds back into the simulation. */
import { CELEBRATIONS, type Moves, type Strike } from "@/components/oneOnOne/moves";
import { SLIDE_LEN, windupOf } from "@/lib/match3d/actions";
import { Act, FROM_SLIDE, HZ, Kick, WALK_DRIBBLE, touchFoot, type MatchState, type Player } from "@/lib/match3d/core";

import { BAKE_FPS, type Baked } from "./baked";

const FADE = 0.2;
/** A run, a sprint or a sidestep lasts at least this long (s): a body doesn't
 * change gait every other step. */
const GAIT_MIN = 0.28;
const QUICK = 0.08;
/** The slide clip (s): the last strides of its run-up, and where it starts to get up. */
const SLIDE_IN = 0.62;
const SLIDE_UP = 1.9;
/** When the ball leaves the hands or the foot in the match's own clips (s). */
const CONTACT: Record<string, number> = { throw_in: 0.68, penalty: 0.73, gk_throw: 1.53, gk_roll: 1.13, gk_dropkick: 2.1 };

/** When each foot is furthest forward in the loops a man carries the ball in (s). */
const FOOT_AT: Record<string, { r: number; l: number }> = {
  run: { r: 0.55, l: 0.18 }, sprint: { r: 0.42, l: 0.15 }, dribble_jog: { r: 0.7, l: 0.18 },
};
/** How hard the loop is pulled on to the engine's touch count (1/s). */
const LOCK = 7;

/** Natural speed of the loops (m/s). */
export type Paces = { run: number; sprint: number; back: number; dribble: number };

type Pick = { name: string; loop: boolean; speed: number; fade: number; t0?: number };

export type Pose = { rowA: number; rowB: number; w: number };

export class Motion {
  /** Current clip per person. */
  private clip: string[];
  private t: Float32Array;
  private prev: string[];
  private prevT: Float32Array;
  private prevLoop: Uint8Array;
  private fade: Float32Array;
  private fadeLen: Float32Array;
  private loop: Uint8Array;
  private held: (Pick | null)[];
  private lastAct: Int8Array;
  private gait: Float32Array;
  readonly pose: Pose[];

  constructor(private readonly baked: Baked, private readonly moves: Moves, private readonly paces: Paces, n: number) {
    this.clip = new Array(n).fill("idle");
    this.prev = new Array(n).fill("idle");
    this.t = new Float32Array(n);
    this.prevT = new Float32Array(n);
    this.prevLoop = new Uint8Array(n).fill(1);
    this.loop = new Uint8Array(n).fill(1);
    this.fade = new Float32Array(n).fill(1);
    this.fadeLen = new Float32Array(n).fill(FADE);
    this.held = new Array(n).fill(null);
    this.lastAct = new Int8Array(n).fill(-1);
    this.gait = new Float32Array(n);
    this.pose = Array.from({ length: n }, () => ({ rowA: 0, rowB: 0, w: 0 }));
  }

  private has(name: string) {
    return this.baked.rows[name] !== undefined;
  }
  private or(name: string, other: string) {
    return this.has(name) ? name : other;
  }

  /** The strike a planned kick is shown with. */
  private strike(p: Player, s: MatchState): Pick {
    const plan = p.plan;
    const r = p.side >= 0;
    const f = r ? "r" : "l";
    let name: string = `pass_${f}`;
    let rate = 1.1;
    if (plan) {
      if (plan.kind === Kick.Throw) { name = this.or("throw_in", "idle"); rate = 1; }
      else if (plan.kind === Kick.Shot) {
        const chip = !plan.ground && plan.speed < 14.5;
        name = s.set?.kind === "penalty" ? this.or("penalty", `shot_${f}`) : chip ? `chip_${f}` : plan.speed > 25 ? `power_${f}` : `shot_${f}`;
        rate = name === "penalty" ? 1 : 1.1;
      } else if (plan.kind === Kick.Lob || plan.kind === Kick.Cross || plan.kind === Kick.Corner || plan.kind === Kick.Clear) {
        name = `shot_${f}`;
        rate = 1.05;
      }
    }
    const contact = this.moves.strikes[name as Strike]?.contact ?? CONTACT[name] ?? 0;
    const t0 = Math.max(0, contact - (windupOf(p) / HZ) * rate);
    return { name, loop: false, speed: rate, fade: QUICK, t0 };
  }

  /** Fits a clip to the ticks the engine gives the move. */
  private fit(name: string, p: Player, min = 0.8, max = 2.6) {
    const r = this.baked.rows[name];
    return r && p.actLen > 0 ? Math.max(min, Math.min(max, r.duration / (p.actLen / HZ))) : 1;
  }

  private slideUp(f: string, p: Player) {
    const r = this.baked.rows[`slide_${f}`];
    return r && p.actLen > 0 ? (r.duration - SLIDE_UP) / (p.actLen / HZ) : 1;
  }

  /** One-off moves are chosen once, as they start. */
  private oneOff(p: Player, s: MatchState): Pick | null {
    const f = p.side >= 0 ? "r" : "l";
    /** The foot that rolls the ball is the one away from where he goes. */
    const other = p.side >= 0 ? "l" : "r";
    switch (p.act) {
      case Act.Kick: return this.strike(p, s);
      case Act.Trap:
        if (s.ball.y > 0.95 && this.has("chest_trap")) return { name: "chest_trap", loop: false, speed: 1.3, fade: QUICK, t0: 0.42 };
        return { name: this.or(`trap_${f}`, "receive"), loop: false, speed: 1.2, fade: QUICK, t0: 0.1 };
      case Act.Tackle: return { name: this.or(`tackle_${f}`, `slide_${f}`), loop: false, speed: 1.15, fade: QUICK, t0: 0.12 };
      // The clip is a run-up, the slide and getting up: he is already running.
      case Act.Slide: return { name: `slide_${f}`, loop: false, speed: (SLIDE_UP - SLIDE_IN) / (SLIDE_LEN / HZ), fade: QUICK, t0: SLIDE_IN };
      case Act.Down: {
        const name = this.or("fall_side", "trip");
        return { name, loop: false, speed: this.fit(name, p), fade: QUICK };
      }
      case Act.Getup: {
        if (p.sub === FROM_SLIDE) return { name: `slide_${f}`, loop: false, speed: this.slideUp(f, p), fade: 0.03, t0: SLIDE_UP };
        const name = this.or("getup_front", "gk_getup");
        return { name, loop: false, speed: this.fit(name, p), fade: name === "getup_front" ? 0.03 : FADE };
      }
      case Act.Header: return { name: "header", loop: false, speed: 1.1, fade: QUICK, t0: Math.max(0, this.moves.headerAt - 0.2) };
      case Act.Volley: return { name: this.or(`shot_${f}`, "kick"), loop: false, speed: 1.3, fade: QUICK, t0: 0.15 };
      case Act.Feint: {
        const names = [`stepover_${f}`, "dragback", `ballroll_${other}`, `roulette_${f}`];
        const name = names[p.sub];
        return { name: this.has(name) ? name : p.sub === 3 || p.sub === 1 ? `roulette_${f}` : `strafe_${f}`, loop: false, speed: 1, fade: QUICK };
      }
      case Act.Dive: {
        // side is along z; which hand that is depends on the end he guards.
        const left = p.side * (p.hx > 0 ? 1 : -1) < 0;
        const low = p.sub === 0;
        const n = low ? (left ? "gk_block_l" : "gk_block_r") : left ? "gk_dive_left" : "gk_dive_right";
        return { name: n, loop: false, speed: 1.15, fade: QUICK, t0: 0.1 };
      }
      case Act.Catch:
        return { name: p.sub === 2 ? "gk_catch_high" : p.sub === 0 ? "gk_scoop" : "gk_catch_low", loop: false, speed: 1.2, fade: QUICK };
      case Act.Hold: return { name: "gk_idle", loop: true, speed: 1, fade: FADE };
      case Act.GkThrow: {
        const name = this.or(p.sub === 0 ? "gk_roll" : "gk_throw", "pass_r");
        return { name, loop: false, speed: 1.1, fade: QUICK, t0: Math.max(0, (CONTACT[name] ?? 0) - 0.3) };
      }
      case Act.GkKick: {
        const name = this.or("gk_dropkick", "power_r");
        return { name, loop: false, speed: 1.1, fade: QUICK, t0: Math.max(0, (CONTACT[name] ?? 0) - 0.4) };
      }
      case Act.Celebrate: return { name: CELEBRATIONS[p.i % CELEBRATIONS.length], loop: false, speed: 1, fade: 0.25 };
      case Act.Dejected: return { name: this.or("dejected", "idle"), loop: false, speed: 1, fade: 0.3 };
      default: return null;
    }
  }

  private locomotion(p: Player, s: MatchState): Pick {
    const v = Math.sqrt(p.vx * p.vx + p.vz * p.vz);
    const keeper = p.role === "GK";
    if (v < 0.5) {
      if (keeper && s.ball.owner !== p.i) return { name: s.ball.owner < 0 || Math.abs(s.ball.x - p.x) < 40 ? this.or("gk_set", "gk_idle") : "gk_idle", loop: true, speed: 1, fade: FADE };
      return { name: this.or("offensive_idle", "idle"), loop: true, speed: 1, fade: FADE };
    }
    const along = (p.vx * p.hx + p.vz * p.hz) / v;
    const across = (p.hx * p.vz - p.hz * p.vx) / v;
    const has = s.ball.owner === p.i;
    if (has) {
      // Walking it, the close-control take. At a pace he runs like anybody
      // else, or his feet would skate: the takes were played at under 2 m/s.
      if (v < (this.clip[p.i] === "dribble_jog" ? WALK_DRIBBLE : WALK_DRIBBLE - 0.3) && this.has("dribble_jog")) {
        return { name: "dribble_jog", loop: true, speed: Math.max(0.8, Math.min(2, v / this.paces.dribble)), fade: FADE };
      }
      if (v > (this.clip[p.i] === "sprint" ? 5.9 : 6.5)) return { name: "sprint", loop: true, speed: v / this.paces.sprint, fade: FADE };
      return { name: "run", loop: true, speed: Math.max(0.55, v / this.paces.run), fade: FADE };
    }
    if (along < -0.45 && v < 6.5) return { name: "run_back", loop: true, speed: v / this.paces.back, fade: FADE };
    if (Math.abs(across) > 0.72 && v < 5.5) {
      const side = across > 0 ? "r" : "l";
      if (p.faceBall && !keeper && this.has(`jockey_${side}`)) return { name: `jockey_${side}`, loop: true, speed: Math.max(0.8, v / 2), fade: FADE };
      const name = keeper ? this.or(`gk_sidestep_${side}`, `strafe_${side}`) : `strafe_${side}`;
      return { name, loop: true, speed: Math.max(0.8, v / 3.6), fade: FADE };
    }
    if (p.faceBall && v < 3.2 && p.duty === 1 && this.has("jockey")) return { name: "jockey", loop: true, speed: 1, fade: FADE };
    // Up into a sprint later than down out of it.
    if (v > (this.clip[p.i] === "sprint" ? 5.9 : 6.5)) return { name: "sprint", loop: true, speed: v / this.paces.sprint, fade: FADE };
    return { name: "run", loop: true, speed: Math.max(0.55, v / this.paces.run), fade: FADE };
  }

  private enter(i: number, pick: Pick) {
    if (this.clip[i] === pick.name && !(!pick.loop && pick.t0 !== undefined)) return;
    // The drag-back ends turned round, and the instance turns with it: a blend
    // across that would spin him through the wrong way.
    const cut = this.clip[i] === "dragback";
    this.prev[i] = this.clip[i];
    this.prevT[i] = this.t[i];
    this.prevLoop[i] = this.loop[i];
    this.clip[i] = pick.name;
    this.loop[i] = pick.loop ? 1 : 0;
    // Run into walk keeps its stride: the loops share a phase.
    const r0 = this.baked.rows[this.prev[i]], r1 = this.baked.rows[pick.name];
    this.t[i] = pick.t0 ?? (pick.loop && this.prevLoop[i] && r0 && r1 ? (this.t[i] / r0.duration) * r1.duration : 0);
    this.fade[i] = cut ? 1 : 0;
    this.fadeLen[i] = pick.fade;
  }

  /** The clip itself is turning him: the body's heading waits. */
  turning(i: number) {
    return this.clip[i] === "dragback";
  }

  private rowOf(name: string, t: number, loop: boolean): { a: number; b: number; w: number } {
    const r = this.baked.rows[name] ?? this.baked.rows.idle;
    if (loop) {
      const u = ((t % r.duration) + r.duration) % r.duration;
      const f = (u / r.duration) * (r.count - 1);
      const n = Math.floor(f);
      return { a: r.first + n, b: r.first + Math.min(n + 1, r.count - 1), w: f - n };
    }
    const f = Math.min(t * BAKE_FPS, r.count - 1.001);
    const n = Math.floor(f);
    return { a: r.first + n, b: r.first + n + 1, w: f - n };
  }

  /** Everyone stands at the kick-off, mid-stride or not. */
  snap(s: MatchState) {
    for (let i = 0; i < 22; i++) this.update(i, s.players[i], s, 0);
    for (let i = 22; i < this.pose.length; i++) this.updateSimple(i, 0, 0);
  }

  /** Advances person i by dt seconds of game time. */
  update(i: number, p: Player, s: MatchState, dt: number) {
    const act = p.act;
    if (act !== this.lastAct[i] || (act !== Act.None && p.actT <= 1)) {
      this.lastAct[i] = act;
      const pick = this.oneOff(p, s);
      this.held[i] = pick;
      if (pick) this.enter(i, pick);
    }
    const pick = this.held[i] ?? this.locomotion(p, s);
    this.gait[i] += dt;
    if (!this.held[i]) {
      const stopping = pick.name.endsWith("idle") || pick.name === "gk_set";
      if (pick.name !== this.clip[i] && (this.gait[i] >= GAIT_MIN || stopping || this.loop[i] === 0)) {
        this.enter(i, pick);
        this.gait[i] = 0;
      }
      if (pick.name !== this.clip[i]) { this.step(i, dt, Math.max(0.55, pick.speed)); return; }
    }
    this.step(i, dt, pick.speed);
    if (s.ball.owner === i) this.lockStride(i, p);
  }

  /** The stride follows the ball: his foot is at it on the engine's touch. */
  private lockStride(i: number, p: Player) {
    const name = this.clip[i], at = FOOT_AT[name];
    if (!at || p.act !== Act.None || this.fade[i] < 1) return;
    const r = this.baked.rows[name];
    if (!r) return;
    const u = 1 - p.touch / p.touchLen;
    const walking = name === "dribble_jog";
    const span = walking ? r.duration / 2 : r.duration;
    const want = (walking ? at.l : touchFoot(p) > 0 ? at.r : at.l) + u * span;
    let d = (want - this.t[i]) % span;
    if (d > span / 2) d -= span;
    if (d < -span / 2) d += span;
    this.t[i] += d * Math.min(1, LOCK / HZ);
  }

  /** The officials: only ever walking or running. */
  updateSimple(i: number, v: number, dt: number) {
    const pick: Pick = v < 0.5 ? { name: "idle", loop: true, speed: 1, fade: FADE }
      : v > 6.3 ? { name: "sprint", loop: true, speed: v / this.paces.sprint, fade: FADE }
        : { name: "run", loop: true, speed: Math.max(0.55, v / this.paces.run), fade: FADE };
    this.enter(i, pick);
    this.step(i, dt, pick.speed);
  }

  private step(i: number, dt: number, speed: number) {
    this.t[i] += dt * speed;
    this.prevT[i] += dt;
    this.fade[i] = Math.min(1, this.fade[i] + dt / this.fadeLen[i]);
    const now = this.rowOf(this.clip[i], this.t[i], this.loop[i] === 1);
    const out = this.pose[i];
    if (this.fade[i] < 1) {
      const old = this.rowOf(this.prev[i], this.prevT[i], this.prevLoop[i] === 1);
      out.rowA = old.a; out.rowB = now.a; out.w = this.fade[i];
    } else {
      out.rowA = now.a; out.rowB = now.b; out.w = now.w;
    }
  }
}
