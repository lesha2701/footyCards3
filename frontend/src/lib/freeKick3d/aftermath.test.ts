import { aftermathAt, simulateAftermath } from "./aftermath";
import { NET_DEPTH } from "./fx";
import { BALL_RADIUS, GOAL_HALF_WIDTH, GOAL_HEIGHT, createSetup, type ShotTrajectory, type Vec3 } from "./trajectory";

const traj = (outcome: ShotTrajectory["outcome"], position: Vec3, velocity: Vec3): ShotTrajectory => ({
  outcome,
  samples: [],
  events: [],
  end: { t: 1, position, velocity },
});

describe("free kick 3D aftermath", () => {
  const setup = { ...createSetup(1), wall: [] };

  it("a goal stays in the net and comes to rest on the ground", () => {
    const a = simulateAftermath(setup, traj("goal", { x: 2, y: 2, z: -0.12 }, { x: 6, y: 3, z: -30 }));
    for (const p of a.positions) {
      expect(p.z).toBeGreaterThanOrEqual(-NET_DEPTH);
      expect(Math.abs(p.x)).toBeLessThanOrEqual(GOAL_HALF_WIDTH);
      expect(p.y).toBeLessThanOrEqual(GOAL_HEIGHT);
      expect(p.y).toBeGreaterThanOrEqual(BALL_RADIUS);
      expect(Number.isFinite(p.x + p.y + p.z)).toBe(true);
    }
    const last = a.positions[a.positions.length - 1];
    expect(last.y).toBeCloseTo(BALL_RADIUS, 5);
    expect(last.z).toBeLessThan(0);
  });

  it("a ball bounces off a wall player instead of passing through", () => {
    const base = createSetup(1);
    const w = { x: 0, z: 10 };
    const a = simulateAftermath({ ...base, wall: [w] }, traj("miss", { x: 0, y: 1, z: 12 }, { x: 0, y: 0, z: -20 }));
    for (const p of a.positions) expect(Math.hypot(p.x - w.x, p.z - w.z) > 0.3 || p.y > 2).toBe(true);
  });

  it("starts at the decision and interpolates over time", () => {
    const a = simulateAftermath(setup, traj("miss", { x: 5, y: 1, z: -0.12 }, { x: 10, y: 2, z: -15 }));
    expect(aftermathAt(a, 1)).toEqual({ x: 5, y: 1, z: -0.12 });
    const later = aftermathAt(a, 1.5);
    expect(later.x).toBeGreaterThan(5);
    expect(later.z).toBeLessThan(-0.12);
    // Clamped past the end.
    expect(aftermathAt(a, 100)).toEqual(a.positions[a.positions.length - 1]);
  });
});
