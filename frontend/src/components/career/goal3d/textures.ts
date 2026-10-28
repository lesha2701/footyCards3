/** Canvas textures of the 3D goal replay: drawn once, no image downloads. */
import * as THREE from "three";

import { PITCH_L, PITCH_W } from "@/lib/matchReplay";

function canvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return [c, c.getContext("2d")!];
}

function finish(c: HTMLCanvasElement, opts: { repeat?: [number, number]; anisotropy?: number } = {}): THREE.CanvasTexture {
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = opts.anisotropy ?? 1;
  if (opts.repeat) {
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(...opts.repeat);
  }
  return tex;
}

/** Mown stripes and the markings; canvas X along the pitch, Y across. */
export function pitchTexture(): THREE.CanvasTexture {
  const W = 2048;
  const s = W / PITCH_L;
  const H = Math.round(PITCH_W * s);
  const [c, g] = canvas(W, H);
  const stripes = 14;
  for (let i = 0; i < stripes; i++) {
    g.fillStyle = i % 2 ? "#2f7d3c" : "#348a42";
    g.fillRect((W / stripes) * i, 0, W / stripes + 1, H);
  }
  g.strokeStyle = "rgba(255,255,255,0.88)";
  g.fillStyle = "rgba(255,255,255,0.88)";
  g.lineWidth = Math.max(2, 0.12 * s);
  const m = (v: number) => v * s;
  const inset = g.lineWidth / 2;
  g.strokeRect(inset, inset, W - 2 * inset, H - 2 * inset);
  g.beginPath();
  g.moveTo(W / 2, 0);
  g.lineTo(W / 2, H);
  g.stroke();
  g.beginPath();
  g.arc(W / 2, H / 2, m(9.15), 0, Math.PI * 2);
  g.stroke();
  const dot = (x: number, y: number, r: number) => {
    g.beginPath();
    g.arc(x, y, r, 0, Math.PI * 2);
    g.fill();
  };
  dot(W / 2, H / 2, m(0.25));
  for (const end of [0, 1]) {
    const x = (v: number) => (end === 0 ? m(v) : W - m(v));
    const box = (depth: number, width: number) => {
      const y0 = H / 2 - m(width / 2);
      g.strokeRect(Math.min(x(0), x(depth)), y0, m(depth), m(width));
    };
    box(16.5, 40.3);
    box(5.5, 18.3);
    dot(x(11), H / 2, m(0.2));
    // The arc of the D outside the box.
    const a = Math.acos(5.5 / 9.15);
    g.beginPath();
    if (end === 0) g.arc(x(11), H / 2, m(9.15), -a, a);
    else g.arc(x(11), H / 2, m(9.15), Math.PI - a, Math.PI + a);
    g.stroke();
    for (const y of [0, H]) {
      g.beginPath();
      g.arc(x(0), y, m(1), 0, Math.PI * 2);
      g.stroke();
    }
  }
  return finish(c, { anisotropy: 4 });
}

/** A square mesh of the goal net (repeated). */
export function netTexture(): THREE.CanvasTexture {
  const [c, g] = canvas(64, 64);
  g.strokeStyle = "rgba(255,255,255,0.75)";
  g.lineWidth = 3;
  g.strokeRect(0, 0, 64, 64);
  return finish(c, { repeat: [1, 1] });
}

/** Crowd in the stands: dots of shirts on a dark background (seeded). */
export function crowdTexture(): THREE.CanvasTexture {
  const [c, g] = canvas(256, 128);
  g.fillStyle = "#121a2b";
  g.fillRect(0, 0, 256, 128);
  const colours = ["#c6e63a", "#f87171", "#e5e7eb", "#60a5fa", "#fbbf24", "#94a3b8"];
  let seed = 7;
  const rnd = () => {
    seed = (Math.imul(seed, 1103515245) + 12345) >>> 0;
    return seed / 4294967296;
  };
  for (let row = 0; row < 16; row++) {
    for (let col = 0; col < 48; col++) {
      if (rnd() < 0.12) continue;
      g.fillStyle = colours[Math.floor(rnd() * colours.length)];
      g.globalAlpha = 0.45 + rnd() * 0.4;
      g.fillRect(col * 5.33 + rnd() * 2, row * 8 + rnd() * 2, 3, 4);
    }
  }
  g.globalAlpha = 1;
  return finish(c, { repeat: [10, 1] });
}

/** A shirt-number badge floating over a player. */
export function numberTexture(n: number, fill: string, text: string): THREE.CanvasTexture {
  const [c, g] = canvas(64, 64);
  g.beginPath();
  g.arc(32, 32, 29, 0, Math.PI * 2);
  g.fillStyle = fill;
  g.fill();
  g.lineWidth = 4;
  g.strokeStyle = "rgba(11,26,18,0.85)";
  g.stroke();
  g.fillStyle = text;
  g.font = "bold 34px ui-monospace, Menlo, monospace";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(String(n), 32, 34);
  return finish(c);
}
