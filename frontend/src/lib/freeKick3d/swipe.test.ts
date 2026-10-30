import { swipeFromPoints, type SwipePoint } from "./swipe";

const H = 800;

describe("swipeFromPoints", () => {
  it("measures a straight upward flick", () => {
    const pts: SwipePoint[] = [
      { x: 200, y: 700, t: 0 },
      { x: 210, y: 550, t: 80 },
      { x: 220, y: 400, t: 160 },
    ];
    const s = swipeFromPoints(pts, H)!;
    expect(s.dx).toBeCloseTo(20 / H);
    expect(s.dy).toBeCloseTo(-300 / H);
    expect(Math.abs(s.curve)).toBeLessThan(0.01);
    expect(s.durationMs).toBe(160);
  });

  it("signs the curve by which way the path bows", () => {
    const bow = (midX: number) =>
      swipeFromPoints(
        [
          { x: 200, y: 700, t: 0 },
          { x: midX, y: 550, t: 80 },
          { x: 200, y: 400, t: 160 },
        ],
        H,
      )!.curve;
    expect(bow(260)).toBeCloseTo(60 / 300);
    expect(bow(140)).toBeCloseTo(-60 / 300);
  });

  it("ignores taps and downward swipes", () => {
    expect(swipeFromPoints([{ x: 0, y: 0, t: 0 }], H)).toBeNull();
    expect(swipeFromPoints([{ x: 200, y: 700, t: 0 }, { x: 205, y: 690, t: 50 }], H)).toBeNull();
    expect(swipeFromPoints([{ x: 200, y: 300, t: 0 }, { x: 200, y: 600, t: 150 }], H)).toBeNull();
  });

  it("does not count the hold before the flick into its duration", () => {
    const s = swipeFromPoints(
      [
        { x: 200, y: 700, t: 0 },
        { x: 201, y: 700, t: 400 },
        { x: 202, y: 699, t: 600 },
        { x: 205, y: 550, t: 680 },
        { x: 210, y: 400, t: 760 },
      ],
      H,
    )!;
    expect(s.durationMs).toBe(160);
  });
});
