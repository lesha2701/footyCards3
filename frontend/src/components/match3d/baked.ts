/** The footballers of «Матч 3D» as data for the GPU: the career model merged
 * into one geometry, a lighter copy of it for the far side of the pitch (a
 * half-edge collapse by quadric error, so what's left keeps its skin weights),
 * and every clip baked into a float texture of bone matrices. No skeletons or
 * mixers at run time: 25 people cost one or two draw calls. */
import * as THREE from "three";
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

export const BAKE_FPS = 30;

export type Merged = {
  pos: Float32Array;
  uv: Float32Array;
  bones: Uint8Array;
  weights: Float32Array;
  part: Float32Array;
  index: Uint32Array;
};

export type ClipRow = { first: number; count: number; duration: number };
export type Baked = { texture: THREE.DataTexture; rows: Record<string, ClipRow>; height: number };

/** skin, shirt, shorts, socks, hair, the rest (boots). */
export const partOf = (name: string) =>
  /Shirt/i.test(name) ? 1 : /Shorts/i.test(name) ? 2 : /Socks/i.test(name) ? 3 : /Body/i.test(name) ? 0 : /Hair/i.test(name) ? 4 : 5;

/** The whole model in its bind pose, on one bone list. */
export function mergeModel(gltf: GLTF): { merged: Merged; boneNames: string[] } {
  const scene = cloneSkinned(gltf.scene);
  const meshes: THREE.SkinnedMesh[] = [];
  scene.traverse((o) => {
    if ((o as THREE.SkinnedMesh).isSkinnedMesh) meshes.push(o as THREE.SkinnedMesh);
  });
  const boneNames = meshes[0].skeleton.bones.map((b) => b.name);
  const pos: number[] = [], uv: number[] = [], bones: number[] = [], weights: number[] = [], part: number[] = [], index: number[] = [];
  const v = new THREE.Vector3();
  for (const m of meshes) {
    const g = m.geometry;
    const base = pos.length / 3;
    const position = g.getAttribute("position");
    // The file is quantized mesh by mesh, each scale hidden in that mesh's
    // inverse bind matrices: one common space means undoing the difference.
    const ref = meshes[0].skeleton;
    const at = m.skeleton.bones.findIndex((b) => ref.bones.some((r) => r.name === b.name));
    const refAt = ref.bones.findIndex((b) => b.name === m.skeleton.bones[at].name);
    const toCommon = ref.boneInverses[refAt].clone().invert().multiply(m.skeleton.boneInverses[at]);
    const si = g.getAttribute("skinIndex"), sw = g.getAttribute("skinWeight"), tu = g.getAttribute("uv");
    const remap = m.skeleton.bones.map((b) => Math.max(0, boneNames.indexOf(b.name)));
    const p = partOf(m.name);
    for (let i = 0; i < position.count; i++) {
      v.fromBufferAttribute(position, i).applyMatrix4(toCommon);
      pos.push(v.x, v.y, v.z);
      uv.push(tu.getX(i), tu.getY(i));
      for (let k = 0; k < 4; k++) {
        bones.push(remap[si.getComponent(i, k)]);
        weights.push(sw.getComponent(i, k));
      }
      part.push(p);
    }
    const idx = g.getIndex()!;
    for (let i = 0; i < idx.count; i++) index.push(base + idx.getX(i));
  }
  return {
    boneNames,
    merged: {
      pos: new Float32Array(pos), uv: new Float32Array(uv), bones: new Uint8Array(bones),
      weights: new Float32Array(weights), part: new Float32Array(part), index: new Uint32Array(index),
    },
  };
}

/** Symmetric 4×4 quadric, 10 numbers. */
const addPlane = (q: Float64Array, at: number, a: number, b: number, c: number, d: number, w: number) => {
  q[at] += w * a * a; q[at + 1] += w * a * b; q[at + 2] += w * a * c; q[at + 3] += w * a * d;
  q[at + 4] += w * b * b; q[at + 5] += w * b * c; q[at + 6] += w * b * d;
  q[at + 7] += w * c * c; q[at + 8] += w * c * d; q[at + 9] += w * d * d;
};
const errorAt = (q: Float64Array, a: number, r: number, x: number, y: number, z: number) =>
  (q[a] + q[r]) * x * x + 2 * (q[a + 1] + q[r + 1]) * x * y + 2 * (q[a + 2] + q[r + 2]) * x * z + 2 * (q[a + 3] + q[r + 3]) * x
  + (q[a + 4] + q[r + 4]) * y * y + 2 * (q[a + 5] + q[r + 5]) * y * z + 2 * (q[a + 6] + q[r + 6]) * y
  + (q[a + 7] + q[r + 7]) * z * z + 2 * (q[a + 8] + q[r + 8]) * z + (q[a + 9] + q[r + 9]);

/** Decimates to about `target` triangles. Vertices seamed in the source (the
 * same place, the same part) move as one, so no cracks open along them. */
export function simplify(m: Merged, target: number): Merged {
  const n = m.pos.length / 3;
  const scale = 1e5;
  const weld = new Map<string, number>();
  const root = new Int32Array(n);
  for (let i = 0; i < n; i++) {
    const k = `${m.part[i]}:${Math.round(m.pos[i * 3] * scale)}:${Math.round(m.pos[i * 3 + 1] * scale)}:${Math.round(m.pos[i * 3 + 2] * scale)}`;
    const at = weld.get(k);
    if (at === undefined) { weld.set(k, i); root[i] = i; } else root[i] = at;
  }
  const tris = Int32Array.from(m.index, (i) => root[i]);
  const parent = Int32Array.from({ length: n }, (_, i) => i);
  const find = (i: number) => {
    while (parent[i] !== i) { parent[i] = parent[parent[i]]; i = parent[i]; }
    return i;
  };
  let alive = tris.length / 3;
  const quad = new Float64Array(n * 10);
  const edgeCount = new Map<number, number>();
  const key = (a: number, b: number) => (a < b ? a * n + b : b * n + a);
  const accumulate = () => {
    quad.fill(0);
    edgeCount.clear();
    for (let t = 0; t < tris.length; t += 3) {
      const a = find(tris[t]), b = find(tris[t + 1]), c = find(tris[t + 2]);
      if (a === b || b === c || a === c) continue;
      const ax = m.pos[a * 3], ay = m.pos[a * 3 + 1], az = m.pos[a * 3 + 2];
      const ux = m.pos[b * 3] - ax, uy = m.pos[b * 3 + 1] - ay, uz = m.pos[b * 3 + 2] - az;
      const vx = m.pos[c * 3] - ax, vy = m.pos[c * 3 + 1] - ay, vz = m.pos[c * 3 + 2] - az;
      let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      const l = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1e-12;
      const area = l * 0.5;
      nx /= l; ny /= l; nz /= l;
      const d = -(nx * ax + ny * ay + nz * az);
      for (const v of [a, b, c]) addPlane(quad, v * 10, nx, ny, nz, d, area);
      for (const [p, q] of [[a, b], [b, c], [c, a]]) {
        const k = key(p, q);
        edgeCount.set(k, (edgeCount.get(k) ?? 0) + 1);
      }
    }
    // Open edges (sleeves, collars) hold their outline.
    edgeCount.forEach((count, k) => {
      if (count !== 1) return;
      const a = Math.floor(k / n), b = k % n;
      const dx = m.pos[b * 3] - m.pos[a * 3], dy = m.pos[b * 3 + 1] - m.pos[a * 3 + 1], dz = m.pos[b * 3 + 2] - m.pos[a * 3 + 2];
      const w = (dx * dx + dy * dy + dz * dz) * 40;
      for (const v of [a, b]) {
        addPlane(quad, v * 10, 1, 0, 0, -m.pos[v * 3], w);
        addPlane(quad, v * 10, 0, 1, 0, -m.pos[v * 3 + 1], w);
        addPlane(quad, v * 10, 0, 0, 1, -m.pos[v * 3 + 2], w);
      }
    });
  };
  for (let pass = 0; pass < 40 && alive > target; pass++) {
    accumulate();
    const edges: { k: number; to: number; from: number; cost: number }[] = [];
    edgeCount.forEach((_, k) => {
      const a = Math.floor(k / n), b = k % n;
      if (m.part[a] !== m.part[b]) return;
      const ea = errorAt(quad, a * 10, b * 10, m.pos[a * 3], m.pos[a * 3 + 1], m.pos[a * 3 + 2]);
      const eb = errorAt(quad, a * 10, b * 10, m.pos[b * 3], m.pos[b * 3 + 1], m.pos[b * 3 + 2]);
      edges.push(ea < eb ? { k, to: a, from: b, cost: ea } : { k, to: b, from: a, cost: eb });
    });
    edges.sort((p, q) => p.cost - q.cost);
    const touched = new Uint8Array(n);
    const quota = Math.max(1, Math.min(Math.ceil((alive - target) / 3), Math.ceil(edges.length * 0.06)));
    let done = 0;
    for (const e of edges) {
      if (done >= quota) break;
      if (touched[e.to] || touched[e.from]) continue;
      touched[e.to] = 1; touched[e.from] = 1;
      parent[e.from] = e.to;
      done += 1;
    }
    if (!done) break;
    alive = 0;
    for (let t = 0; t < tris.length; t += 3) {
      const a = find(tris[t]), b = find(tris[t + 1]), c = find(tris[t + 2]);
      if (a !== b && b !== c && a !== c) alive += 1;
    }
  }
  // What's left, on the first copy of each surviving vertex.
  const newAt = new Int32Array(n).fill(-1);
  const keep: number[] = [];
  const index: number[] = [];
  const out = (original: number) => {
    const r = find(root[original]);
    if (newAt[r] < 0) { newAt[r] = keep.length; keep.push(r); }
    return newAt[r];
  };
  for (let t = 0; t < m.index.length; t += 3) {
    const a = out(m.index[t]), b = out(m.index[t + 1]), c = out(m.index[t + 2]);
    if (a !== b && b !== c && a !== c) index.push(a, b, c);
  }
  const pick = <T extends Float32Array | Uint8Array>(src: T, size: number, dst: T) => {
    keep.forEach((i, at) => {
      for (let k = 0; k < size; k++) dst[at * size + k] = src[i * size + k];
    });
    return dst;
  };
  const c = keep.length;
  return {
    pos: pick(m.pos, 3, new Float32Array(c * 3)), uv: pick(m.uv, 2, new Float32Array(c * 2)),
    bones: pick(m.bones, 4, new Uint8Array(c * 4)), weights: pick(m.weights, 4, new Float32Array(c * 4)),
    part: pick(m.part, 1, new Float32Array(c)), index: new Uint32Array(index),
  };
}

/** The bone palettes of every clip, row by row (a 3×4 matrix = 3 texels). */
export function bakeClips(gltf: GLTF, clips: Record<string, THREE.AnimationClip>, boneNames: string[]): Baked {
  const model = cloneSkinned(gltf.scene);
  const mixer = new THREE.AnimationMixer(model);
  const byName = new Map<string, THREE.Bone>();
  let mesh: THREE.SkinnedMesh | null = null;
  model.traverse((o) => {
    if ((o as THREE.Bone).isBone) byName.set(o.name, o as THREE.Bone);
    if ((o as THREE.SkinnedMesh).isSkinnedMesh) mesh ??= o as THREE.SkinnedMesh;
  });
  const bones = boneNames.map((n) => byName.get(n)!);
  // Straight from the file: skeleton.pose() would rewrite the bones' local
  // scale, and the clips, which key only rotations and positions, keep it.
  const skeleton = (mesh as unknown as THREE.SkinnedMesh).skeleton;
  const restInv = boneNames.map((n) => skeleton.boneInverses[skeleton.bones.findIndex((b) => b.name === n)]);

  const rows: Baked["rows"] = {};
  let height = 0;
  for (const [name, clip] of Object.entries(clips)) {
    const count = Math.max(2, Math.ceil(clip.duration * BAKE_FPS) + 1);
    rows[name] = { first: height, count, duration: clip.duration };
    height += count;
  }
  const width = bones.length * 3;
  const data = new Float32Array(width * height * 4);
  const m = new THREE.Matrix4();
  for (const [name, clip] of Object.entries(clips)) {
    const action = mixer.clipAction(clip);
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.play();
    const { first, count } = rows[name];
    for (let r = 0; r < count; r++) {
      mixer.setTime(Math.min(clip.duration - 1e-4, r / BAKE_FPS));
      model.updateMatrixWorld(true);
      let at = (first + r) * width * 4;
      for (let b = 0; b < bones.length; b++) {
        m.multiplyMatrices(bones[b].matrixWorld, restInv[b]);
        const e = m.elements;
        for (let row = 0; row < 3; row++) {
          data[at++] = e[row]; data[at++] = e[row + 4]; data[at++] = e[row + 8]; data[at++] = e[row + 12];
        }
      }
    }
    action.stop();
  }
  const texture = new THREE.DataTexture(data, width, height, THREE.RGBAFormat, THREE.FloatType);
  texture.minFilter = texture.magFilter = THREE.NearestFilter;
  texture.needsUpdate = true;
  return { texture, rows, height };
}
