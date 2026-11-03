/** One finger runs the whole attack: hold = run, drag left/right of where
 * the finger came down = steer, a quick sideways flick = the feint, a
 * flick upwards as the finger leaves = the shot (measured like the free
 * kick's swipe), letting go otherwise = stop. Pure: the page feeds it
 * pointer samples and reads what the finger means now. */
import { swipeFromPoints, type SwipePoint } from "@/lib/freeKick3d/swipe";
import { quantizeSwipe, type QuantizedSwipe } from "@/lib/freeKick3d/trajectory";

import { quantizeSteer } from "./recorder";

/** Full steer at this share of the screen width from the anchor. */
const STEER_SPAN = 0.22;
/** A feint: this far sideways (share of the width) within FEINT_MS… */
const FEINT_DIST = 0.09;
const FEINT_MS = 160;
/** …and mostly sideways. */
const FEINT_SLOPE = 1.6;
/** A shot: the last upward stretch of the path, at least this tall (share
 * of the height) and no older than SHOT_MS. */
const SHOT_MIN = 0.07;
const SHOT_MS = 600;
/** A thumb resting still (px), and one frame (ms) — where its stroke began. */
const STILL_PX = 3;
const FRAME_MS = 16;
/** A tap: down and up within TAP_MS, moving less than TAP_DIST (share of
 * the height). */
const TAP_MS = 260;
const TAP_DIST = 0.025;

export type FingerIntent = { feint: number; shot: QuantizedSwipe | null; tap?: boolean };

export class Finger {
  private points: SwipePoint[] = [];
  private anchorX = 0;
  private feintFrom = 0;
  private downAt: SwipePoint = { x: 0, y: 0, t: 0 };
  private wander = 0;
  down = false;

  constructor(private width: number, private height: number) {}

  resize(width: number, height: number) {
    this.width = width;
    this.height = height;
  }

  start(p: SwipePoint) {
    this.down = true;
    this.points = [p];
    this.downAt = p;
    this.wander = 0;
    this.anchorX = p.x;
    this.feintFrom = 0;
  }

  /** A move while holding; returns ±1 when it was a feint flick. */
  move(p: SwipePoint): number {
    if (!this.down) return 0;
    this.points.push(p);
    this.wander = Math.max(this.wander, Math.hypot(p.x - this.downAt.x, p.y - this.downAt.y));
    // Keep about a second of path: the shot only looks at the last stretch.
    while (this.points.length > 2 && p.t - this.points[0].t > 1000) this.points.shift();
    const dir = this.flick(p);
    if (dir !== 0) {
      // Steering starts again from here, so the run doesn't swerve after it.
      this.anchorX = p.x;
      this.feintFrom = this.points.length - 1;
    }
    return dir;
  }

  /** Steer in thousandths (quantized for the timeline). */
  steer(): number {
    if (!this.down || this.points.length === 0) return 0;
    const last = this.points[this.points.length - 1];
    return quantizeSteer((last.x - this.anchorX) / (this.width * STEER_SPAN));
  }

  /** The finger leaves: a shot, a feint flick, or just a stop. */
  end(p: SwipePoint): FingerIntent {
    if (!this.down) return { feint: 0, shot: null };
    this.down = false;
    this.points.push(p);
    const shot = this.shot();
    if (shot) return { feint: 0, shot };
    const wander = Math.max(this.wander, Math.hypot(p.x - this.downAt.x, p.y - this.downAt.y));
    if (p.t - this.downAt.t <= TAP_MS && wander < this.height * TAP_DIST) return { feint: 0, shot: null, tap: true };
    return { feint: this.flick(p), shot: null };
  }

  cancel() {
    this.down = false;
    this.points = [];
  }

  /** Path for the trail on screen. */
  trail(): SwipePoint[] {
    return this.points;
  }

  private flick(p: SwipePoint): number {
    let i = this.points.length - 1;
    while (i > this.feintFrom && p.t - this.points[i - 1].t <= FEINT_MS) i -= 1;
    const from = this.points[i];
    const dx = p.x - from.x;
    const dy = p.y - from.y;
    if (Math.abs(dx) < this.width * FEINT_DIST || Math.abs(dx) < Math.abs(dy) * FEINT_SLOPE) return 0;
    return dx > 0 ? 1 : -1;
  }

  private shot(): QuantizedSwipe | null {
    const pts = this.points;
    const last = pts[pts.length - 1];
    // Back from the end while the finger was going up (a little jitter allowed).
    let i = pts.length - 1;
    while (i > 0 && pts[i - 1].y >= pts[i].y - 2 && last.t - pts[i - 1].t <= SHOT_MS) i -= 1;
    if ((pts[i].y - last.y) / this.height < SHOT_MIN) return null;
    // The thumb often rests on the button (while the left one aims) before
    // it swipes: the stroke starts when it moves, not when it came down —
    // else the rest counts as a slow swipe, and the shot comes out weak.
    const stroke = pts.slice(i);
    while (stroke.length > 2 && Math.hypot(stroke[1].x - stroke[0].x, stroke[1].y - stroke[0].y) < STILL_PX) stroke.shift();
    if (stroke[1].t - stroke[0].t > FRAME_MS * 2) stroke[0] = { ...stroke[0], t: stroke[1].t - FRAME_MS };
    const swipe = swipeFromPoints(stroke, this.height);
    if (!swipe) return null;
    const q = quantizeSwipe(swipe);
    if (q.dy >= 0) return null;
    // Within what the server accepts (the engine plays the same integers).
    const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
    return { dx: clamp(q.dx, -1500, 1500), dy: clamp(q.dy, -1500, -1), curve: clamp(q.curve, -500, 500), durationMs: q.durationMs };
  }
}

/** The left thumb: a floating stick where it came down. Off-centre by less
 * than DEAD of the radius — he stops; up to SPRINT — runs with the ball at
 * his feet; at the rim — sprints. Its sideways lean is the steer. */
const STICK_RADIUS = 0.13; // of the shorter screen side
const DEAD = 0.22;
const SPRINT = 0.88;

export type StickState = { hold: 0 | 1 | 2; steer: number; knob: { x: number; y: number }; anchor: { x: number; y: number } };

export class Stick {
  private anchor = { x: 0, y: 0 };
  private knob = { x: 0, y: 0 };
  down = false;

  constructor(private width: number, private height: number) {}

  resize(width: number, height: number) {
    this.width = width;
    this.height = height;
  }

  get radius() {
    return Math.min(this.width, this.height) * STICK_RADIUS;
  }

  start(p: { x: number; y: number }) {
    this.down = true;
    this.anchor = { x: p.x, y: p.y };
    this.knob = { ...this.anchor };
  }

  move(p: { x: number; y: number }) {
    if (!this.down) return;
    const r = this.radius;
    let dx = p.x - this.anchor.x;
    let dy = p.y - this.anchor.y;
    const d = Math.hypot(dx, dy);
    if (d > r) {
      // Dragged past the rim: the stick follows the thumb.
      this.anchor.x += (dx / d) * (d - r);
      this.anchor.y += (dy / d) * (d - r);
      dx = p.x - this.anchor.x;
      dy = p.y - this.anchor.y;
    }
    this.knob = { x: p.x, y: p.y };
  }

  end() {
    this.down = false;
  }

  read(): StickState {
    const r = this.radius;
    const dx = this.knob.x - this.anchor.x;
    const dy = this.knob.y - this.anchor.y;
    const k = Math.hypot(dx, dy) / r;
    const hold = !this.down || k < DEAD ? 0 : k >= SPRINT ? 2 : 1;
    return { hold, steer: hold ? quantizeSteer(dx / r) : 0, knob: this.knob, anchor: this.anchor };
  }
}
