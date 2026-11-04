/** 22 footballers in one instanced draw: the model merged into one geometry,
 * every clip baked into a float texture of bone matrices, a pose per instance
 * (two rows and a blend) read in the vertex shader. No skeletons or mixers on
 * the CPU — the benchmark's candidate for the match. */
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

export type Baked = {
  texture: THREE.DataTexture;
  /** Row of a clip's first frame, and how many frames it has. */
  rows: Record<string, { first: number; count: number; duration: number }>;
  height: number;
};

const partOf = (name: string) =>
  /Shirt/i.test(name) ? 1 : /Shorts/i.test(name) ? 2 : /Socks/i.test(name) ? 3 : /Body/i.test(name) ? 0 : /Hair/i.test(name) ? 4 : 5;

/** The whole model in its bind pose, in the scene's space, on one bone list. */
export function mergeModel(gltf: GLTF): { merged: Merged; boneNames: string[] } {
  const scene = cloneSkinned(gltf.scene);
  const meshes: THREE.SkinnedMesh[] = [];
  scene.traverse((o) => {
    if ((o as THREE.SkinnedMesh).isSkinnedMesh) meshes.push(o as THREE.SkinnedMesh);
  });
  const boneNames = meshes[0].skeleton.bones.map((b) => b.name);
  for (const m of meshes) m.skeleton.pose();
  scene.updateMatrixWorld(true);
  const pos: number[] = [];
  const uv: number[] = [];
  const bones: number[] = [];
  const weights: number[] = [];
  const part: number[] = [];
  const index: number[] = [];
  const v = new THREE.Vector3();
  for (const m of meshes) {
    const g = m.geometry;
    const base = pos.length / 3;
    const si = g.getAttribute("skinIndex");
    const sw = g.getAttribute("skinWeight");
    const tu = g.getAttribute("uv");
    const remap = m.skeleton.bones.map((b) => Math.max(0, boneNames.indexOf(b.name)));
    const p = partOf(m.name);
    for (let i = 0; i < g.getAttribute("position").count; i++) {
      m.getVertexPosition(i, v);
      v.applyMatrix4(m.matrixWorld);
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

/** A crude vertex-clustering LOD (a stand-in for a proper decimation: only
 * its triangle count matters for the numbers). */
export function clusterLod(m: Merged, cell: number): Merged {
  const key = new Map<string, number>();
  const remap = new Int32Array(m.pos.length / 3);
  const keep: number[] = [];
  for (let i = 0; i < remap.length; i++) {
    const k = `${m.part[i]}:${Math.round(m.pos[i * 3] / cell)}:${Math.round(m.pos[i * 3 + 1] / cell)}:${Math.round(m.pos[i * 3 + 2] / cell)}`;
    let at = key.get(k);
    if (at === undefined) {
      at = keep.length;
      key.set(k, at);
      keep.push(i);
    }
    remap[i] = at;
  }
  const index: number[] = [];
  for (let i = 0; i < m.index.length; i += 3) {
    const a = remap[m.index[i]], b = remap[m.index[i + 1]], c = remap[m.index[i + 2]];
    if (a !== b && b !== c && a !== c) index.push(a, b, c);
  }
  const pick = <T extends Float32Array | Uint8Array>(src: T, n: number, out: T) => {
    keep.forEach((i, at) => {
      for (let k = 0; k < n; k++) out[at * n + k] = src[i * n + k];
    });
    return out;
  };
  const n = keep.length;
  return {
    pos: pick(m.pos, 3, new Float32Array(n * 3)),
    uv: pick(m.uv, 2, new Float32Array(n * 2)),
    bones: pick(m.bones, 4, new Uint8Array(n * 4)),
    weights: pick(m.weights, 4, new Float32Array(n * 4)),
    part: pick(m.part, 1, new Float32Array(n)),
    index: new Uint32Array(index),
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
  (mesh as unknown as THREE.SkinnedMesh).skeleton.pose();
  model.updateMatrixWorld(true);
  const restInv = bones.map((b) => b.matrixWorld.clone().invert());

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
          data[at++] = e[row];
          data[at++] = e[row + 4];
          data[at++] = e[row + 8];
          data[at++] = e[row + 12];
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

const HEAD = /* glsl */ `
uniform highp sampler2D uBake;
attribute vec4 aBones;
attribute vec4 aWeights;
attribute float aPart;
attribute vec3 aPose;
mat4 mcBone(int row, int b) {
  vec4 a = texelFetch(uBake, ivec2(b * 3, row), 0);
  vec4 c = texelFetch(uBake, ivec2(b * 3 + 1, row), 0);
  vec4 d = texelFetch(uBake, ivec2(b * 3 + 2, row), 0);
  return mat4(a.x, c.x, d.x, 0., a.y, c.y, d.y, 0., a.z, c.z, d.z, 0., a.w, c.w, d.w, 1.);
}
mat4 mcPose(int b) {
  return mcBone(int(aPose.x), b) * (1. - aPose.z) + mcBone(int(aPose.y), b) * aPose.z;
}
mat4 mcSkin() {
  mat4 s = mat4(0.);
  for (int k = 0; k < 4; k++) if (aWeights[k] > 0.) s += mcPose(int(aBones[k])) * aWeights[k];
  return s;
}
`;

function geometryOf(m: Merged, shared?: THREE.BufferGeometry): THREE.InstancedBufferGeometry {
  const g = new THREE.InstancedBufferGeometry();
  if (shared) {
    g.copy(shared as THREE.InstancedBufferGeometry);
    return g;
  }
  g.setAttribute("position", new THREE.BufferAttribute(m.pos, 3));
  g.setAttribute("uv", new THREE.BufferAttribute(m.uv, 2));
  g.setAttribute("aBones", new THREE.BufferAttribute(m.bones, 4));
  g.setAttribute("aWeights", new THREE.BufferAttribute(m.weights, 4));
  g.setAttribute("aPart", new THREE.BufferAttribute(m.part, 1));
  g.setIndex(new THREE.BufferAttribute(m.index, 1));
  g.computeVertexNormals();
  return g;
}

export type Crowd = {
  group: THREE.Group;
  mesh: THREE.InstancedMesh;
  pose: THREE.InstancedBufferAttribute;
  set: (i: number, x: number, z: number, yaw: number) => void;
  commit: () => void;
  dispose: () => void;
};

const KITS = [["#d7263d", "#ffffff"], ["#1e88e5", "#10243d"]];
const SKINS = ["#ffffff", "#c98f68", "#7a4a32", "#e6b896", "#f1d2bd", "#9c6646"];
const SUN = new THREE.Vector3(-0.45, 1, 0.35);

export function makeCrowd(merged: Merged, baked: Baked, map: THREE.Texture | null, n: number, planar: boolean): Crowd {
  const geo = geometryOf(merged);
  const shirt = new Float32Array(n * 3);
  const shorts = new Float32Array(n * 3);
  const skin = new Float32Array(n * 3);
  const c = new THREE.Color();
  for (let i = 0; i < n; i++) {
    const kit = KITS[i < n / 2 ? 0 : 1];
    const keeper = i % 11 === 0;
    c.set(keeper ? "#f4d03f" : kit[0]).toArray(shirt, i * 3);
    c.set(kit[1]).toArray(shorts, i * 3);
    c.set(SKINS[(i * 5) % SKINS.length]).toArray(skin, i * 3);
  }
  const pose = new THREE.InstancedBufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage);
  geo.setAttribute("aPose", pose);
  geo.setAttribute("aShirt", new THREE.InstancedBufferAttribute(shirt, 3));
  geo.setAttribute("aShorts", new THREE.InstancedBufferAttribute(shorts, 3));
  geo.setAttribute("aSkin", new THREE.InstancedBufferAttribute(skin, 3));

  const mat = new THREE.MeshLambertMaterial({ map });
  mat.onBeforeCompile = (s) => {
    s.uniforms.uBake = { value: baked.texture };
    s.vertexShader = (HEAD + "attribute vec3 aShirt; attribute vec3 aShorts; attribute vec3 aSkin; varying vec3 vMcTint; varying float vMcFlat;\n" + s.vertexShader)
      .replace("#include <beginnormal_vertex>", "mat4 mcS = mcSkin();\nvec3 objectNormal = mat3(mcS) * vec3(normal);")
      .replace("#include <begin_vertex>", `vec3 transformed = (mcS * vec4(position, 1.)).xyz;
        vMcTint = aPart < .5 ? aSkin : aPart < 1.5 ? aShirt * 1.18 : aPart < 2.5 ? aShorts * 1.18 : aPart < 3.5 ? aShirt * 1.18 : aPart < 4.5 ? vec3(.12, .09, .07) : vec3(1.);
        vMcFlat = aPart > 3.5 && aPart < 4.5 ? 1. : 0.;`);
    s.fragmentShader = ("varying vec3 vMcTint; varying float vMcFlat;\n" + s.fragmentShader).replace(
      "#include <map_fragment>",
      "#include <map_fragment>\ndiffuseColor.rgb = mix(diffuseColor.rgb, vec3(1.), vMcFlat) * vMcTint;",
    );
  };
  const mesh = new THREE.InstancedMesh(geo, mat, n);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.frustumCulled = false;
  const group = new THREE.Group();
  group.add(mesh);

  let shadowMat: THREE.MeshBasicMaterial | null = null;
  let shadow: THREE.InstancedMesh | null = null;
  if (planar) {
    shadowMat = new THREE.MeshBasicMaterial({ color: "#000000", transparent: true, opacity: 0.3, depthFunc: THREE.LessDepth });
    shadowMat.onBeforeCompile = (s) => {
      s.uniforms.uBake = { value: baked.texture };
      s.uniforms.uSun = { value: SUN };
      s.vertexShader = (HEAD + "uniform vec3 uSun;\n" + s.vertexShader)
        .replace("#include <begin_vertex>", "vec3 transformed = (mcSkin() * vec4(position, 1.)).xyz;")
        .replace("#include <project_vertex>", `vec4 mvPosition = instanceMatrix * vec4(transformed, 1.);
          mvPosition.xz -= uSun.xz / uSun.y * mvPosition.y;
          mvPosition.y = .02;
          mvPosition = viewMatrix * mvPosition;
          gl_Position = projectionMatrix * mvPosition;`);
    };
    shadow = new THREE.InstancedMesh(geo, shadowMat, n);
    shadow.instanceMatrix = mesh.instanceMatrix;
    shadow.frustumCulled = false;
    shadow.renderOrder = 1;
    group.add(shadow);
  }

  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  const p = new THREE.Vector3();
  const one = new THREE.Vector3(1, 1, 1);
  return {
    group, mesh, pose,
    set: (i, x, z, yaw) => {
      q.setFromAxisAngle(up, yaw);
      m.compose(p.set(x, 0, z), q, one);
      mesh.setMatrixAt(i, m);
    },
    commit: () => {
      mesh.instanceMatrix.needsUpdate = true;
      pose.needsUpdate = true;
    },
    dispose: () => {
      geo.dispose();
      mat.dispose();
      shadowMat?.dispose();
    },
  };
}
