/** A cost proxy for the 11-a-side match's simulation (the benchmark only,
 * not the game): 22 agents steered at a fixed tick, the ball, a carrier that
 * weighs every pass against every opponent. Only + − × ÷ √ and a seeded
 * generator, so it runs the same anywhere. */
export const N = 22;
export const HZ = 30;
const DT = 1 / HZ;
const ANCHORS: [number, number][] = [[-48, 0], [-32, -24], [-34, -8], [-34, 8], [-32, 24], [-12, -22], [-14, -7], [-14, 7], [-12, 22], [8, -8], [8, 8]];
const TOP = 7.6;
const ACCEL = 9;

export type Proto = {
  x: Float64Array; z: Float64Array; vx: Float64Array; vz: Float64Array;
  bx: number; bz: number; bvx: number; bvz: number; owner: number; tick: number; rng: number; possession: number;
};

export function createProto(seed: number): Proto {
  const s: Proto = { x: new Float64Array(N), z: new Float64Array(N), vx: new Float64Array(N), vz: new Float64Array(N), bx: 0, bz: 0, bvx: 0, bvz: 0, owner: 9, tick: 0, rng: seed | 0, possession: 0 };
  for (let i = 0; i < N; i++) {
    const a = ANCHORS[i % 11];
    s.x[i] = i < 11 ? a[0] : -a[0];
    s.z[i] = i < 11 ? a[1] : -a[1];
  }
  return s;
}

function rnd(s: Proto): number {
  s.rng = (s.rng + 0x6d2b79f5) | 0;
  let t = s.rng;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

const tx = new Float64Array(N);
const tz = new Float64Array(N);

function segDist2(ax: number, az: number, bx: number, bz: number, px: number, pz: number): number {
  const dx = bx - ax, dz = bz - az;
  const l = dx * dx + dz * dz || 1;
  let u = ((px - ax) * dx + (pz - az) * dz) / l;
  u = u < 0 ? 0 : u > 1 ? 1 : u;
  const ex = ax + dx * u - px, ez = az + dz * u - pz;
  return ex * ex + ez * ez;
}

function decide(s: Proto) {
  const o = s.owner;
  const us = o < 11 ? 0 : 11;
  const them = o < 11 ? 11 : 0;
  const dir = o < 11 ? 1 : -1;
  let best = -1;
  let score = 6 + rnd(s) * 8;
  for (let j = us; j < us + 11; j++) {
    if (j === o) continue;
    const dx = s.x[j] - s.x[o], dz = s.z[j] - s.z[o];
    const d = Math.sqrt(dx * dx + dz * dz);
    if (d < 5 || d > 42) continue;
    let lane = 1e9;
    for (let k = them; k < them + 11; k++) {
      const q = segDist2(s.x[o], s.z[o], s.x[j], s.z[j], s.x[k], s.z[k]);
      if (q < lane) lane = q;
    }
    const v = (Math.sqrt(lane) * 2 + (dx * dir) / 6) - d / 18;
    if (v > score) { score = v; best = j; }
  }
  // Where to carry it: eight ways against all eleven.
  let bestX = dir, bestZ = 0, bestV = -1e9;
  for (let w = 0; w < 8; w++) {
    const ax = w === 0 || w === 1 || w === 7 ? 0.8 : w === 3 || w === 4 || w === 5 ? -0.8 : 0;
    const az = w >= 1 && w <= 3 ? 0.8 : w >= 5 ? -0.8 : 0;
    const px = s.x[o] + ax * 6, pz = s.z[o] + az * 6;
    let near = 1e9;
    for (let k = them; k < them + 11; k++) {
      const ex = s.x[k] - px, ez = s.z[k] - pz;
      const q = ex * ex + ez * ez;
      if (q < near) near = q;
    }
    const v = Math.sqrt(near) + ax * dir * 2;
    if (v > bestV) { bestV = v; bestX = ax; bestZ = az; }
  }
  tx[o] = s.x[o] + bestX * 8;
  tz[o] = s.z[o] + bestZ * 8;
  if (best >= 0) {
    const dx = s.x[best] + s.vx[best] * 0.5 - s.x[o], dz = s.z[best] + s.vz[best] * 0.5 - s.z[o];
    const d = Math.sqrt(dx * dx + dz * dz) || 1;
    const pace = 11 + d / 3;
    s.bvx = (dx / d) * pace;
    s.bvz = (dz / d) * pace;
    s.owner = -1;
  }
}

/** One tick of the proxy. */
export function stepProto(s: Proto) {
  s.tick += 1;
  const { x, z, vx, vz } = s;
  if (s.owner >= 0) {
    s.bx = x[s.owner] + vx[s.owner] * 0.08;
    s.bz = z[s.owner] + vz[s.owner] * 0.08;
    s.bvx = vx[s.owner];
    s.bvz = vz[s.owner];
    s.possession = s.owner < 11 ? 0 : 1;
  } else {
    s.bx += s.bvx * DT;
    s.bz += s.bvz * DT;
    s.bvx *= 0.986;
    s.bvz *= 0.986;
  }
  if (s.bx > 52 || s.bx < -52 || s.bz > 33.5 || s.bz < -33.5) {
    s.bx = s.bx > 52 ? 48 : s.bx < -52 ? -48 : s.bx;
    s.bz = s.bz > 33.5 ? 32 : s.bz < -33.5 ? -32 : s.bz;
    s.bvx = -s.bvx * 0.3;
    s.bvz = -s.bvz * 0.3;
  }
  const shift = s.bx * 0.55;
  const atk = s.possession === 0 ? 0 : 11;
  const def = 11 - atk;
  // The block moves with the ball; the attackers run off it.
  for (let i = 0; i < N; i++) {
    const a = ANCHORS[i % 11];
    const side = i < 11 ? 1 : -1;
    const up = (i < 11) === (atk === 0) ? 10 : -4;
    tx[i] = i % 11 === 0 ? side * a[0] + s.bx * 0.06 : side * (a[0] + up) + shift;
    tz[i] = i % 11 === 0 ? s.bz * 0.08 : side * a[1] + (s.bz - side * a[1]) * 0.25;
  }
  // The two nearest defenders go to the ball, the others mark.
  let n1 = -1, n2 = -1, d1 = 1e9, d2 = 1e9;
  for (let i = def; i < def + 11; i++) {
    if (i % 11 === 0) continue;
    const dx = x[i] - s.bx, dz = z[i] - s.bz;
    const q = dx * dx + dz * dz;
    if (q < d1) { d2 = d1; n2 = n1; d1 = q; n1 = i; } else if (q < d2) { d2 = q; n2 = i; }
  }
  for (let i = def; i < def + 11; i++) {
    if (i === n1 || i === n2 || i % 11 === 0) continue;
    let near = -1, nd = 1e9;
    for (let k = atk; k < atk + 11; k++) {
      const dx = x[k] - x[i], dz = z[k] - z[i];
      const q = dx * dx + dz * dz;
      if (q < nd) { nd = q; near = k; }
    }
    if (nd < 400) {
      const gx = (i < 11 ? -52 : 52) - x[near], gz = -z[near];
      const gl = Math.sqrt(gx * gx + gz * gz) || 1;
      tx[i] = x[near] + (gx / gl) * 2.2;
      tz[i] = z[near] + (gz / gl) * 2.2;
    }
  }
  if (n1 >= 0) { tx[n1] = s.bx; tz[n1] = s.bz; }
  if (n2 >= 0) { tx[n2] = s.bx + (n2 < 11 ? -6 : 6); tz[n2] = s.bz * 0.9; }
  if (s.owner >= 0 && s.tick % 5 === s.owner % 5) decide(s);
  if (s.owner < 0) {
    let near = -1, nd = 1e9;
    for (let i = 0; i < N; i++) {
      const dx = x[i] - s.bx, dz = z[i] - s.bz;
      const q = dx * dx + dz * dz;
      if (q < nd) { nd = q; near = i; }
    }
    tx[near] = s.bx + s.bvx * 0.3;
    tz[near] = s.bz + s.bvz * 0.3;
    if (nd < 1) s.owner = near;
  } else if (n1 >= 0 && d1 < 1 && rnd(s) < 0.07) {
    s.owner = n1;
  }
  // Steering, and keeping apart.
  for (let i = 0; i < N; i++) {
    let dx = tx[i] - x[i], dz = tz[i] - z[i];
    for (let j = 0; j < N; j++) {
      if (j === i) continue;
      const ex = x[i] - x[j], ez = z[i] - z[j];
      const q = ex * ex + ez * ez;
      if (q < 4 && q > 1e-6) { dx += (ex / q) * 3; dz += (ez / q) * 3; }
    }
    const d = Math.sqrt(dx * dx + dz * dz);
    const want = d < 0.05 ? 0 : (d < 6 ? (d / 6) * TOP : TOP) / d;
    let ax = dx * want - vx[i], az = dz * want - vz[i];
    const al = Math.sqrt(ax * ax + az * az);
    const lim = ACCEL * DT;
    if (al > lim) { ax *= lim / al; az *= lim / al; }
    vx[i] += ax;
    vz[i] += az;
    x[i] += vx[i] * DT;
    z[i] += vz[i] * DT;
  }
}

export function hashProto(s: Proto): number {
  let h = 0;
  for (let i = 0; i < N; i++) h += s.x[i] * (i + 1) - s.z[i] * (i + 2);
  return h + s.bx + s.owner;
}
