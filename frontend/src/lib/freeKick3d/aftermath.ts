/** What the ball does after the outcome is decided — dropping into the net,
 * bouncing off the wall or the keeper, rolling out wide. Purely cosmetic
 * (the outcome is already set), but a pure function too: no physics engine
 * at runtime, nothing that can crash or drift between devices. */
import { netBackZ } from "./fx";
import {
  BALL_RADIUS,
  GOAL_HALF_WIDTH,
  GOAL_HEIGHT,
  WALL_PLAYER_HEIGHT,
  WALL_PLAYER_RADIUS,
  type ShotSetup,
  type ShotTrajectory,
  type Vec3,
} from "./trajectory";

const DT = 1 / 120;
const GRAVITY = 9.81;
const DRAG_K = 0.0135;
const BOUNCE = 0.5;
const BOUNCE_FRICTION = 0.85;
const ROLL_DECAY_PER_S = 0.6;
/** The net swallows the ball: only this much of the speed into it is left. */
const NET_KEEP = 0.05;
/** Inside the goal the net lies on the grass: the ball dies quickly. */
const NET_ROLL_DECAY_PER_S = 3;
const NET_FRICTION = 0.5;
const WALL_BOUNCE = 0.35;

export type Aftermath = { t0: number; dt: number; positions: Vec3[] };

/** Ball positions from the decision (`traj.end`) for `duration` seconds. */
export function simulateAftermath(setup: ShotSetup, traj: ShotTrajectory, duration = 4): Aftermath {
  const p = { ...traj.end.position };
  const v = { ...traj.end.velocity };
  const inGoal = traj.outcome === "goal";
  const positions: Vec3[] = [{ ...p }];
  const steps = Math.round(duration / DT);
  let resting = false;

  for (let i = 0; i < steps; i++) {
    if (!resting) {
      const speed = Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
      v.x -= DRAG_K * speed * v.x * DT;
      v.y -= (GRAVITY + DRAG_K * speed * v.y) * DT;
      v.z -= DRAG_K * speed * v.z * DT;
      p.x += v.x * DT;
      p.y += v.y * DT;
      p.z += v.z * DT;

      if (inGoal) net(p, v);
      for (const w of setup.wall) wallPlayer(p, v, w.x, w.z);

      if (p.y < BALL_RADIUS) {
        p.y = BALL_RADIUS;
        if (v.y < -0.8) {
          v.y = -v.y * BOUNCE;
          v.x *= BOUNCE_FRICTION;
          v.z *= BOUNCE_FRICTION;
        } else {
          v.y = 0;
          const roll = 1 - (inGoal && p.z < 0 ? NET_ROLL_DECAY_PER_S : ROLL_DECAY_PER_S) * DT;
          v.x *= roll;
          v.z *= roll;
          if (v.x * v.x + v.z * v.z < 0.01) resting = true;
        }
      }
    }
    positions.push({ ...p });
  }
  return { t0: traj.end.t, dt: DT, positions };
}

/** Position at shot time `t` (clamped to the simulated span). */
export function aftermathAt(a: Aftermath, t: number): Vec3 {
  const k = Math.max(0, (t - a.t0) / a.dt);
  const i = Math.min(a.positions.length - 1, Math.floor(k));
  const j = Math.min(a.positions.length - 1, i + 1);
  const f = Math.min(1, k - i);
  const u = a.positions[i];
  const w = a.positions[j];
  return { x: u.x + (w.x - u.x) * f, y: u.y + (w.y - u.y) * f, z: u.z + (w.z - u.z) * f };
}

/** Inside the goal: back, sides and roof of the net catch the ball. */
function net(p: Vec3, v: Vec3) {
  const r = BALL_RADIUS;
  // The back net slopes: lower down it's further back.
  const back = netBackZ(p.y) + r;
  if (p.z < back) {
    p.z = back;
    // Dead: the slope would otherwise throw the ball forward, out of the
    // goal, as it drops — it sags into the net instead.
    if (v.z < 0) v.z = -0.15;
    v.x *= NET_FRICTION;
    v.y = Math.min(v.y, 0);
  }
  const side = GOAL_HALF_WIDTH - r;
  if (p.x > side || p.x < -side) {
    p.x = p.x > 0 ? side : -side;
    v.x = -v.x * NET_KEEP;
    v.z *= NET_FRICTION;
  }
  const roof = GOAL_HEIGHT - r;
  if (p.y > roof) {
    p.y = roof;
    if (v.y > 0) v.y = -v.y * NET_KEEP;
  }
}

/** A wall player as a vertical capsule standing on the ground. */
function wallPlayer(p: Vec3, v: Vec3, cx: number, cz: number) {
  if (p.y > WALL_PLAYER_HEIGHT + BALL_RADIUS) return;
  const dx = p.x - cx;
  const dz = p.z - cz;
  const rr = WALL_PLAYER_RADIUS + BALL_RADIUS;
  const d2 = dx * dx + dz * dz;
  if (d2 >= rr * rr) return;
  const d = Math.sqrt(d2) || 1;
  const nx = dx / d;
  const nz = dz / d;
  p.x = cx + nx * rr;
  p.z = cz + nz * rr;
  const vn = v.x * nx + v.z * nz;
  if (vn < 0) {
    v.x -= (1 + WALL_BOUNCE) * vn * nx;
    v.z -= (1 + WALL_BOUNCE) * vn * nz;
  }
}
