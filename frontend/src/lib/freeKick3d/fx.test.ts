import { netBulge, netImpact, replayTimeScale } from "./fx";
import type { ShotTrajectory } from "./trajectory";

const traj = (outcome: ShotTrajectory["outcome"], end: Partial<ShotTrajectory["end"]> = {}): ShotTrajectory => ({
  outcome,
  samples: [],
  events: [],
  end: { t: 1, position: { x: 1, y: 1.5, z: -0.12 }, velocity: { x: 2, y: -1, z: -20 }, ...end },
});

describe("free kick 3D effects", () => {
  it("slows down only right before a goal or a save", () => {
    expect(replayTimeScale(traj("goal"), 0.2)).toBe(1);
    expect(replayTimeScale(traj("goal"), 0.99)).toBeLessThan(0.35);
    expect(replayTimeScale(traj("save"), 0.9)).toBeLessThan(1);
    expect(replayTimeScale(traj("goal"), 1.2)).toBe(1);
    expect(replayTimeScale(traj("wall"), 0.99)).toBe(1);
    expect(replayTimeScale(traj("miss"), 0.99)).toBe(1);
  });

  it("eases monotonically into the slow motion", () => {
    let prev = 1;
    for (let t = 0.7; t < 1; t += 0.02) {
      const s = replayTimeScale(traj("goal"), t);
      expect(s).toBeLessThanOrEqual(prev);
      prev = s;
    }
  });

  it("projects a goal onto the back net, inside the frame", () => {
    const hit = netImpact(traj("goal"))!;
    expect(hit.x).toBeGreaterThan(1);
    expect(hit.x).toBeLessThan(3.66);
    expect(hit.y).toBeGreaterThan(0);
    expect(hit.y).toBeLessThan(2.44);
    expect(netImpact(traj("save"))).toBeNull();
    // A ball flying into the top corner is clamped to the net.
    const corner = netImpact(traj("goal", { position: { x: 3.5, y: 2.3, z: -0.12 }, velocity: { x: 15, y: 8, z: -20 } }))!;
    expect(corner.x).toBeLessThan(3.66);
    expect(corner.y).toBeLessThan(2.44);
  });

  it("the net bulge peaks at the impact and dies out", () => {
    expect(Math.abs(netBulge(0, 0, 0))).toBeGreaterThan(Math.abs(netBulge(1, 0, 0)));
    expect(netBulge(0, 0, 2)).toBe(0);
    expect(netBulge(0, 0, -0.1)).toBe(0);
  });
});
