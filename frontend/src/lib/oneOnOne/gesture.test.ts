import { Finger } from "./gesture";

const W = 400;
const H = 800;

describe("one finger for the whole attack", () => {
  it("drag from where the finger came down steers, in quantized steps up to full", () => {
    const f = new Finger(W, H);
    f.start({ x: 200, y: 600, t: 0 });
    expect(f.steer()).toBe(0);
    for (let i = 1; i <= 10; i++) f.move({ x: 200 + i * 4, y: 600, t: i * 40 });
    expect(f.steer()).toBe(450); // 40 px of a 88 px span
    // Slowly — a sharp jump sideways would be the feint.
    for (let i = 1; i <= 20; i++) f.move({ x: 240 + i * 6, y: 600, t: 400 + i * 40 });
    expect(f.steer()).toBe(1000);
    for (let i = 1; i <= 40; i++) f.move({ x: 360 - i * 6, y: 600, t: 1200 + i * 40 });
    expect(f.steer()).toBeLessThan(0);
  });

  it("a quick sideways flick while holding is the feint, and steering starts again from there", () => {
    const f = new Finger(W, H);
    f.start({ x: 200, y: 600, t: 0 });
    f.move({ x: 205, y: 600, t: 300 });
    let dir = 0;
    for (let i = 1; i <= 4; i++) dir ||= f.move({ x: 205 - i * 14, y: 602, t: 300 + i * 25 });
    expect(dir).toBe(-1);
    expect(f.steer()).toBe(0);
  });

  it("letting go with an upward flick is the shot; a calm release is just a stop", () => {
    const f = new Finger(W, H);
    f.start({ x: 200, y: 600, t: 0 });
    f.move({ x: 210, y: 600, t: 400 });
    for (let i = 1; i <= 6; i++) f.move({ x: 210 + i * 3, y: 600 - i * 30, t: 400 + i * 20 });
    const shot = f.end({ x: 230, y: 410, t: 540 });
    expect(shot.shot).not.toBeNull();
    expect(shot.shot!.dy).toBeLessThan(0);
    expect(shot.shot!.dx).toBeGreaterThan(0);

    const g = new Finger(W, H);
    g.start({ x: 200, y: 600, t: 0 });
    g.move({ x: 230, y: 600, t: 400 });
    expect(g.end({ x: 231, y: 601, t: 800 })).toEqual({ feint: 0, shot: null });
  });
});
