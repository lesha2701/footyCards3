/** Procedural textures and geometry for the 3D free kick: each built once
 * from a canvas, nothing to download (the generated art lives in
 * public/free-kick-3d and is loaded by Stadium.tsx). */
import * as THREE from "three";

import { BALL_RADIUS } from "@/lib/freeKick3d/trajectory";

export const PITCH_WIDTH = 96;
export const PITCH_DEPTH = 72;
export const PITCH_Z0 = -14;
const PX_PER_M = 14;

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

/** Transparent layer over the grass photo: mowing stripes (both ways, a
 * light check) and the darker advert track behind the line. The markings
 * are geometry (Stadium.tsx `PitchLines`): a texture this size blurs them. */
export function pitchOverlayTexture() {
  const [c, ctx] = canvas(PITCH_WIDTH * PX_PER_M, PITCH_DEPTH * PX_PER_M);
  // World z → canvas px: the plane is rotated −90° about x, so with the
  // default flipY the canvas's top row lands on the far (−z) edge.
  const Z = (z: number) => (z - PITCH_Z0) * PX_PER_M;

  const stripe = 5.5 * PX_PER_M;
  for (let i = 0; i * stripe < c.height; i += 2) {
    ctx.fillStyle = "rgba(255,255,255,0.08)";
    ctx.fillRect(0, i * stripe, c.width, stripe);
  }
  for (let i = 0; i * stripe < c.width; i += 2) {
    ctx.fillStyle = "rgba(0,0,0,0.05)";
    ctx.fillRect(i * stripe, 0, stripe, c.height);
  }

  const grd = ctx.createLinearGradient(0, Z(-3), 0, 0);
  grd.addColorStop(0, "rgba(0,0,0,0)");
  grd.addColorStop(1, "rgba(0,0,0,0.6)");
  ctx.fillStyle = grd;
  ctx.fillRect(0, 0, c.width, Z(-3));

  const tex = srgb(new THREE.CanvasTexture(c));
  tex.anisotropy = 8;
  return tex;
}

/** Across-the-line alpha for the pitch markings: the line fills the middle
 * half of the strip, soft at its edges. With mipmaps a far-off line fades
 * thinner instead of breaking into dashes (the canvas has no antialiasing,
 * and a 12 cm line at a grazing angle is under a pixel). */
export function lineProfileTexture() {
  const [c, ctx] = canvas(64, 4);
  const img = ctx.createImageData(c.width, c.height);
  for (let x = 0; x < c.width; x++) {
    const d = Math.abs((x + 0.5) / c.width - 0.5); // 0 centre … 0.5 strip edge
    const a = Math.min(1, Math.max(0, (0.25 - d) / 0.04 + 0.5));
    for (let y = 0; y < c.height; y++) {
      const i = (y * c.width + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = Math.round(255 * a);
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 16;
  return tex;
}

/** Flat strips on the ground (y = 0) along each polyline of world (x, z)
 * points, `width` wide, each segment run on by width/2 so corners close.
 * UV u goes across the strip (0..1), v along it in metres. */
export function groundStripsGeometry(polylines: [number, number][][], width: number) {
  const pos: number[] = [];
  const uv: number[] = [];
  const idx: number[] = [];
  for (const line of polylines) {
    let along = 0;
    for (let k = 0; k + 1 < line.length; k++) {
      const [ax, az] = line[k];
      const [bx, bz] = line[k + 1];
      const len = Math.hypot(bx - ax, bz - az);
      const dx = (bx - ax) / len;
      const dz = (bz - az) / len;
      const run = width / 4;
      const [sx, sz, ex, ez] = [ax - dx * run, az - dz * run, bx + dx * run, bz + dz * run];
      const nx = -dz * (width / 2);
      const nz = dx * (width / 2);
      const base = pos.length / 3;
      pos.push(sx - nx, 0, sz - nz, sx + nx, 0, sz + nz, ex + nx, 0, ez + nz, ex - nx, 0, ez - nz);
      uv.push(0, along, 1, along, 1, along + len, 0, along + len);
      // Wound to face up (+y).
      idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
      along += len;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  return geo;
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
export function ballGeometry(light = "#f2f2f7", dark = "#101014") {
  const lightC = new THREE.Color(light);
  const darkC = new THREE.Color(dark);
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
    const c = centres.some((cv) => cv.dot(centroid) > threshold) ? darkC : lightC;
    for (let k = 0; k < 3; k++) colors.set([c.r, c.g, c.b], (f + k) * 3);
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
