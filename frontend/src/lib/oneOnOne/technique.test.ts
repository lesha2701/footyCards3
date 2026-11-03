import type { ShotFlight } from "./engine";
import { keeperTake, shotTechnique, type RunAtShot } from "./technique";

/** A flight with just what the technique reads. Facing the goal (−z). */
function flight(v: { x: number; y: number; z: number }, spinY = 0, extra: Partial<ShotFlight> = {}): ShotFlight {
  return {
    outcome: "goal",
    kick: { velocity: v, spin: { x: 0, y: spinY, z: 0 } },
    from: { x: 0, z: 12 },
    keeper: { x: 0, z: 4, lyingFor: 0, reaction: 0.1, spread: false },
    overY: null,
    samples: [{ t: 0, ball: { x: 0, y: 0.11, z: 12 }, handX: 0, handY: 1.1, bodyX: 0, lying: false }],
    events: [],
    end: { t: 0.5, position: { x: 0, y: 1, z: 0 }, velocity: { x: 0, y: 0, z: 0 } },
    ...extra,
  };
}
const RUN: RunAtShot = { hx: 0, hz: -1, side: 0, keeperDist: 6 };

describe("how the shot looks", () => {
  it("cutting to one side he strikes with that foot", () => {
    expect(shotTechnique(flight({ x: 2, y: 2, z: -20 }), { ...RUN, side: 3 }, false).foot).toBe("left");
    expect(shotTechnique(flight({ x: -2, y: 2, z: -20 }), { ...RUN, side: -3 }, false).foot).toBe("right");
  });

  it("running straight he opens the body to the corner: the inside across it", () => {
    // Facing −z his left is −x.
    expect(shotTechnique(flight({ x: -5, y: 2, z: -20 }), RUN, false).foot).toBe("right");
    expect(shotTechnique(flight({ x: 5, y: 2, z: -20 }), RUN, false).foot).toBe("left");
  });

  it("struck clean with the laces, side-footed only soft, scooped, poked", () => {
    expect(shotTechnique(flight({ x: -4, y: 2, z: -20 }), RUN, false).kind).toBe("instep");
    expect(shotTechnique(flight({ x: -3, y: 1.5, z: -14 }), RUN, false).kind).toBe("side");
    expect(shotTechnique(flight({ x: -4, y: 4, z: -30 }), RUN, false).kind).toBe("power");
    expect(shotTechnique(flight({ x: 0, y: 9, z: -12 }), RUN, false).kind).toBe("chip");
    expect(shotTechnique(flight({ x: 0, y: 2, z: -20 }), RUN, true).kind).toBe("chip");
    expect(shotTechnique(flight({ x: -4, y: 2, z: -20 }), { ...RUN, keeperDist: 1.5 }, false).kind).toBe("toe");
  });

  it("sidespin: wrapped with the inside, bent away with the outside", () => {
    // Spin up (ω_y > 0) bends a ball flying to −z left — the right instep's wrap.
    const curled = shotTechnique(flight({ x: -4, y: 2, z: -20 }, 75), RUN, false);
    const bent = shotTechnique(flight({ x: -4, y: 2, z: -20 }, -75), RUN, false);
    expect(curled).toEqual({ foot: "right", kind: "curl" });
    expect(bent).toEqual({ foot: "right", kind: "outside" });
  });
});

describe("how the keeper takes a saved shot", () => {
  const save = (ball: { x: number; y: number; z: number }, prevZ: number, hand = { x: 0, y: 1.1 }, extra: Partial<ShotFlight> = {}) =>
    keeperTake(
      flight({ x: 0, y: 0, z: -20 }, 0, {
        outcome: "save",
        samples: [
          { t: 0.4, ball: { ...ball, z: prevZ }, handX: hand.x, handY: hand.y, bodyX: 0, lying: false },
          { t: 0.45, ball, handX: hand.x, handY: hand.y, bodyX: 0, lying: false },
        ],
        end: { t: 0.45, position: ball, velocity: { x: 0, y: 0, z: 0 } },
        ...extra,
      }),
    );

  it("holds a ball that comes at him; parries a hard one; blocks lying down", () => {
    expect(save({ x: 0.1, y: 1.1, z: 4 }, 4.6)).toBe("catch");
    expect(save({ x: 0.1, y: 1.1, z: 4 }, 5.5)).toBe("parry");
    expect(save({ x: 2.2, y: 1.1, z: 4 }, 4.6, { x: 2.2, y: 1.1 })).toBe("parry");
    expect(save({ x: 0.5, y: 0.2, z: 4 }, 4.6, { x: 0, y: 1.1 }, { keeper: { x: 0, z: 4, lyingFor: 1, reaction: 1, spread: false } })).toBe("block");
  });

  it("a goal or a miss is no save", () => {
    expect(keeperTake(flight({ x: 0, y: 2, z: -20 }))).toBeNull();
  });
});
