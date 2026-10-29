import {
  BALL_RADIUS,
  createSetup,
  magnusAccel,
  mulberry32,
  penaltyBotShot,
  playShot,
  playerKeeperSetup,
  quantizeSwipe,
  sampleAt,
  simulateShot,
  swipeToKick,
  type ShotOutcome,
  type SwipeInput,
} from "./trajectory";

const swipe = (dx: number, dy: number, curve = 0, durationMs = 160): SwipeInput => ({ dx, dy, curve, durationMs });

/** Scan a grid of swipes for a seed and return the first one with `outcome`. */
function findSwipe(seed: number, outcome: ShotOutcome): SwipeInput {
  for (let dy = -0.2; dy >= -0.62; dy -= 0.02) {
    for (let dx = -0.2; dx <= 0.2; dx += 0.01) {
      for (const curve of [0, -0.1, 0.1, -0.25, 0.25]) {
        const s = swipe(dx, dy, curve);
        if (playShot(seed, s).outcome === outcome) return s;
      }
    }
  }
  throw new Error(`no ${outcome} for seed ${seed}`);
}

describe("free kick 3D trajectory", () => {
  it("is deterministic: same seed and swipe give an identical trajectory", () => {
    const a = playShot(1234, swipe(0.05, -0.38, 0.12, 170));
    const b = playShot(1234, swipe(0.05, -0.38, 0.12, 170));
    expect(b).toEqual(a);
    // Bit-exact, not just close.
    expect(Object.is(a.end.position.x, b.end.position.x)).toBe(true);
  });

  it("depends only on the quantized swipe", () => {
    const a = playShot(77, swipe(0.0501, -0.3802, 0.1199, 170.2));
    const b = playShot(77, quantizeSwipe(swipe(0.05, -0.38, 0.12, 170)), true);
    expect(b).toEqual(a);
  });

  it("produces the same setup for a seed and different setups for different seeds", () => {
    expect(createSetup(9)).toEqual(createSetup(9));
    expect(createSetup(9)).not.toEqual(createSetup(10));
    const rnd = mulberry32(5);
    for (let i = 0; i < 100; i++) {
      const v = rnd();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it("places the wall 9.15 m from the ball, 3â€“4 players", () => {
    for (let seed = 1; seed <= 20; seed++) {
      const s = createSetup(seed);
      expect([3, 4]).toContain(s.wall.length);
      const cx = s.wall.reduce((acc, w) => acc + w.x, 0) / s.wall.length;
      const cz = s.wall.reduce((acc, w) => acc + w.z, 0) / s.wall.length;
      const d = Math.hypot(cx - s.ball.x, cz - s.ball.z);
      expect(d).toBeGreaterThan(9.1);
      expect(d).toBeLessThan(9.4);
    }
  });

  it("Magnus force is perpendicular to the velocity and the spin axis", () => {
    const v = { x: 3, y: 5, z: -24 };
    const spin = { x: 4, y: -30, z: 1 };
    const m = magnusAccel(spin, v);
    expect(m.x * v.x + m.y * v.y + m.z * v.z).toBeCloseTo(0, 9);
    expect(m.x * spin.x + m.y * spin.y + m.z * spin.z).toBeCloseTo(0, 9);
  });

  it("the ball copies the swipe's bow: out to that side, then back onto the aim", () => {
    const setup = createSetup(3);
    // Let the ball fly without the wall/keeper in the way.
    const open = { ...setup, wall: [], keeper: { ...setup.keeper, reaction: 99 } };
    const fly = (curve: number) => simulateShot(open, swipeToKick(open, quantizeSwipe(swipe(0, -0.4, curve))));
    // Sideways offset from the straight line ball → goal centre, mid-flight.
    const bowAtMid = (curve: number) => {
      const traj = fly(curve);
      const mid = sampleAt(traj, traj.end.t / 2).ball;
      const straight = sampleAt(fly(0), traj.end.t / 2).ball;
      return mid.x - straight.x;
    };
    expect(bowAtMid(0.25)).toBeGreaterThan(0.5);
    expect(bowAtMid(-0.25)).toBeLessThan(-0.5);
    // …and it still arrives roughly where the swipe pointed.
    const straightEnd = fly(0).end.position.x;
    expect(Math.abs(fly(0.25).end.position.x - straightEnd)).toBeLessThan(1.2);
    expect(Math.abs(fly(-0.25).end.position.x - straightEnd)).toBeLessThan(1.2);
  });

  it("a low driven shot keeps its pace", () => {
    const setup = createSetup(1);
    const open = { ...setup, wall: [], keeper: { ...setup.keeper, reaction: 99 } };
    const traj = simulateShot(open, swipeToKick(open, quantizeSwipe(swipe(0, -0.12, 0, 160))));
    expect(traj.outcome).not.toBe("wall");
    expect(traj.end.position.z).toBeLessThanOrEqual(-BALL_RADIUS);
    expect(Math.hypot(traj.end.velocity.x, traj.end.velocity.z)).toBeGreaterThan(12);
  });

  it("a faster swipe hits harder", () => {
    const setup = createSetup(1);
    const speed = (ms: number) => {
      const v = swipeToKick(setup, quantizeSwipe(swipe(0, -0.4, 0, ms))).velocity;
      return Math.hypot(v.x, v.y, v.z);
    };
    expect(speed(100)).toBeGreaterThan(speed(400));
  });

  it("reaches every outcome: goal, save, wall and miss", () => {
    const seed = 5;
    for (const outcome of ["goal", "save", "wall", "miss"] as const) {
      const traj = playShot(seed, findSwipe(seed, outcome));
      expect(traj.outcome).toBe(outcome);
      expect(traj.events.some((e) => e.type === outcome)).toBe(true);
    }
  });

  it("a goal crosses the line inside the frame", () => {
    const traj = playShot(5, findSwipe(5, "goal"));
    expect(traj.end.position.z).toBeLessThanOrEqual(-BALL_RADIUS);
    expect(Math.abs(traj.end.position.x)).toBeLessThan(3.66);
    expect(traj.end.position.y).toBeLessThan(2.44);
  });

  it("a low swipe straight into the wall is blocked, a lofted one clears it", () => {
    const base = createSetup(1);
    // One wall player right on the line ball â†’ goal centre, 9.15 m out.
    const len = Math.hypot(base.ball.x, base.ball.z);
    const k = 9.15 / len;
    const setup = { ...base, wall: [{ x: base.ball.x * (1 - k), z: base.ball.z * (1 - k) }], wallJumpAt: 99 };
    const fly = (dy: number) => simulateShot(setup, swipeToKick(setup, quantizeSwipe(swipe(0, dy)))).outcome;
    expect(fly(-0.22)).toBe("wall");
    expect(fly(-0.5)).not.toBe("wall");
  });

  it("samples are time-ordered, start at the spot and end at the decision", () => {
    const traj = playShot(11, swipe(0.04, -0.4, 0.1));
    const setup = createSetup(11);
    expect(traj.samples[0].ball).toEqual(setup.ball);
    for (let i = 1; i < traj.samples.length; i++) {
      expect(traj.samples[i].t).toBeGreaterThan(traj.samples[i - 1].t);
    }
    expect(traj.samples[traj.samples.length - 1].t).toBe(traj.end.t);
    expect(traj.end.t).toBeGreaterThan(0.3);
    expect(traj.end.t).toBeLessThan(4.01);
  });

  it("sampleAt interpolates between samples and clamps at the ends", () => {
    const traj = playShot(11, swipe(0.04, -0.4, 0.1));
    const [a, b] = traj.samples;
    const mid = sampleAt(traj, (a.t + b.t) / 2);
    expect(mid.ball.z).toBeCloseTo((a.ball.z + b.ball.z) / 2, 9);
    expect(sampleAt(traj, -1).ball).toEqual(a.ball);
    expect(sampleAt(traj, 99).ball).toEqual(traj.samples[traj.samples.length - 1].ball);
  });
});

describe("the player's own keeper", () => {
  it("with no swipe stays in the middle: saves a strike down the middle, not a corner", () => {
    const seen = new Set<string>();
    for (let seed = 1; seed < 400; seed++) {
      const { kind, swipe: q } = penaltyBotShot(seed, null);
      if (kind !== "power" && kind !== "low_corner") continue;
      const setup = playerKeeperSetup(seed, null);
      expect(simulateShot(setup, swipeToKick(setup, q)).outcome).toBe(kind === "power" ? "save" : "goal");
      seen.add(kind);
    }
    expect(seen).toEqual(new Set(["power", "low_corner"]));
  });
});
