/** Procedural textures and geometry for the 3D free kick: each built once
 * from a canvas, nothing to download (the generated art lives in
 * public/free-kick-3d and is loaded by Stadium.tsx). */
import * as THREE from "three";

import { BALL_RADIUS } from "@/lib/freeKick3d/trajectory";

export const PITCH_WIDTH = 96;
export const PITCH_DEPTH = 72;
export const PITCH_Z0 = -14;

function canvas(w: number, h: number) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return [c, c.getContext("2d")!] as const;
}

function srgb(tex: THREE.Texture) {
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** An alpha map, opaque in the middle and fading out along every edge (a
 * picture laid on the grass blends into what's around it). */
export function edgeFadeTexture() {
  const [c, ctx] = canvas(256, 256);
  const img = ctx.createImageData(c.width, c.height);
  const edge = (u: number) => Math.min(1, Math.max(0, u / 0.12));
  for (let y = 0; y < c.height; y++) {
    for (let x = 0; x < c.width; x++) {
      const u = x / (c.width - 1);
      const v = y / (c.height - 1);
      // The top edge (behind the goal line) fades over less: the line stays.
      const top = Math.min(1, Math.max(0, v / 0.025));
      const a = Math.min(edge(u), edge(1 - u), edge(1 - v), top);
      const i = (y * c.width + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = Math.round(255 * a * a * (3 - 2 * a));
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return new THREE.CanvasTexture(c);
}

/** Metres of net one copy of `netTexture` covers (so every net surface can
 * repeat it to the same cell size). */
export const NET_TILE = { w: 3.2, h: 1.6 };

export function netTexture() {
  const [c, ctx] = canvas(256, 128);
  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.lineWidth = 1.3;
  const cell = 9;
  ctx.beginPath();
  // Diamond mesh, like a real goal net.
  for (let x = -c.height; x <= c.width + c.height; x += cell) {
    ctx.moveTo(x, 0);
    ctx.lineTo(x + c.height, c.height);
    ctx.moveTo(x, 0);
    ctx.lineTo(x - c.height, c.height);
  }
  ctx.stroke();
  return srgb(new THREE.CanvasTexture(c));
}

/** Night sky: deep navy overhead, a warm floodlit haze at the horizon. */
export function skyTexture() {
  const [c, ctx] = canvas(4, 256);
  const g = ctx.createLinearGradient(0, 0, 0, 256);
  g.addColorStop(0, "#03070f");
  g.addColorStop(0.42, "#0b1830");
  g.addColorStop(0.5, "#1d3557");
  g.addColorStop(0.53, "#2a3f5f");
  g.addColorStop(1, "#05080f");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 4, 256);
  return srgb(new THREE.CanvasTexture(c));
}

/** Scrolling LED board strip. */
export function ledTexture(text: string, accent: string) {
  const [c, ctx] = canvas(1024, 64);
  ctx.fillStyle = "#04140b";
  ctx.fillRect(0, 0, c.width, c.height);
  ctx.font = "bold 40px Manrope, system-ui, sans-serif";
  ctx.textBaseline = "middle";
  let x = 16;
  while (x < c.width) {
    ctx.fillStyle = accent;
    ctx.fillText(text, x, 34);
    x += ctx.measureText(text).width + 24;
    ctx.fillStyle = "#c6e63a";
    ctx.fillText("●", x, 34);
    x += 48;
  }
  // LED pixel grid.
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  for (let gx = 0; gx < c.width; gx += 4) ctx.fillRect(gx, 0, 1, c.height);
  for (let gy = 0; gy < c.height; gy += 4) ctx.fillRect(0, gy, c.width, 1);
  const tex = srgb(new THREE.CanvasTexture(c));
  tex.wrapS = THREE.RepeatWrapping;
  return tex;
}

/** A football: a subdivided sphere whose faces near the 12 icosahedron
 * vertices are black — they read as the classic pentagon panels. */
export function ballGeometry() {
  const geo = new THREE.IcosahedronGeometry(BALL_RADIUS, 4);
  const phi = (1 + Math.sqrt(5)) / 2;
  const centres = [
    [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
    [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
    [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1],
  ].map(([x, y, z]) => new THREE.Vector3(x, y, z).normalize());
  const pos = geo.getAttribute("position");
  const colors = new Float32Array(pos.count * 3);
  const centroid = new THREE.Vector3();
  const a = new THREE.Vector3();
  const threshold = Math.cos(0.36);
  for (let f = 0; f < pos.count; f += 3) {
    centroid.set(0, 0, 0);
    for (let k = 0; k < 3; k++) centroid.add(a.fromBufferAttribute(pos, f + k));
    centroid.normalize();
    const dark = centres.some((cv) => cv.dot(centroid) > threshold);
    const shade = dark ? 0.06 : 0.95;
    for (let k = 0; k < 3; k++) colors.set([shade, shade, dark ? 0.08 : 0.97], (f + k) * 3);
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  // Smooth normals on a sphere: the direction from the centre.
  const normals = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    a.fromBufferAttribute(pos, i).normalize();
    normals.set([a.x, a.y, a.z], i * 3);
  }
  geo.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
  return geo;
}
