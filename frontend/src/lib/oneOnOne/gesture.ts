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

export type FingerIntent = { feint: number; shot: QuantizedSwipe | null };

export class Finger {
  private points: SwipePoint[] = [];
  private anchorX = 0;
  private feintFrom = 0;
  down = false;

  constructor(private width: number, private height: number) {}

  resize(width: number, height: number) {
    this.width = width;
    this.height = height;
  }

  start(p: SwipePoint) {
    this.down = true;
    this.points = [p];
    this.anchorX = p.x;
    this.feintFrom = 0;
  }

  /** A move while holding; returns ±1 when it was a feint flick. */
  move(p: SwipePoint): number {
    if (!this.down) return 0;
    this.points.push(p);
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
    const swipe = swipeFromPoints(pts.slice(i), this.height);
    if (!swipe) return null;
    const q = quantizeSwipe(swipe);
    if (q.dy >= 0) return null;
    // Within what the server accepts (the engine plays the same integers).
    const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
    return { dx: clamp(q.dx, -1500, 1500), dy: clamp(q.dy, -1500, -1), curve: clamp(q.curve, -500, 500), durationMs: q.durationMs };
  }
}
