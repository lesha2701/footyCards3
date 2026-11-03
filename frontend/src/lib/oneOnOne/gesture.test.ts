import { Finger, Stick } from "./gesture";

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

describe("the left thumb's stick", () => {
  it("near the centre he stops, off it he runs, at the rim he sprints; the lean steers", () => {
    const s = new Stick(400, 800); // radius 52 px
    s.start({ x: 100, y: 600 });
    expect(s.read().hold).toBe(0);
    s.move({ x: 100, y: 570 });
    expect(s.read()).toMatchObject({ hold: 1, steer: 0 });
    s.move({ x: 100, y: 545 });
    expect(s.read().hold).toBe(2);
    s.move({ x: 140, y: 580 });
    expect(s.read().steer).toBeGreaterThan(500);
    s.end();
    expect(s.read()).toMatchObject({ hold: 0, steer: 0 });
  });

  it("dragged past the rim the stick follows the thumb", () => {
    const s = new Stick(400, 800);
    s.start({ x: 100, y: 600 });
    s.move({ x: 300, y: 600 });
    expect(s.read().anchor.x).toBeCloseTo(248);
    expect(s.read().steer).toBe(1000);
  });
});

describe("the right thumb's tap", () => {
  it("a short still press is a tap; held, or moved, it is not", () => {
    const f = new Finger(W, H);
    f.start({ x: 300, y: 600, t: 0 });
    f.move({ x: 303, y: 602, t: 80 });
    expect(f.end({ x: 302, y: 601, t: 150 })).toEqual({ feint: 0, shot: null, tap: true });
    f.start({ x: 300, y: 600, t: 0 });
    expect(f.end({ x: 300, y: 600, t: 500 }).tap).toBeUndefined();
    f.start({ x: 300, y: 600, t: 0 });
    f.move({ x: 340, y: 600, t: 100 });
    expect(f.end({ x: 300, y: 600, t: 200 }).tap).toBeUndefined();
  });
});
