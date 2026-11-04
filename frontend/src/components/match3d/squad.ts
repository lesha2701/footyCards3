/** Everyone on the pitch as instanced meshes: the full model for who's near
 * the camera, the light one for the rest, the light one again flattened on
 * the grass for the sun's shadows. A pose is two rows of the bake and a blend. */
import * as THREE from "three";

import type { Baked, Merged } from "./baked";
import { SUN } from "./stadium";

/** 22 footballers, the referee, two assistants. */
export const PEOPLE = 25;
export const REFEREE = 22;

const head = (b: Baked) => /* glsl */ `
uniform highp sampler2D uBake;
attribute vec4 aBones;
attribute vec4 aWeights;
attribute float aPart;
attribute vec3 aPose;
const int MC_COLUMNS = ${b.columns};
const int MC_FRAME = ${b.texture.image.width / b.columns};
mat4 mcBone(int row, int b) {
  ivec2 at = ivec2((row % MC_COLUMNS) * MC_FRAME + b * 3, row / MC_COLUMNS);
  vec4 a = texelFetch(uBake, at, 0);
  vec4 c = texelFetch(uBake, at + ivec2(1, 0), 0);
  vec4 d = texelFetch(uBake, at + ivec2(2, 0), 0);
  return mat4(a.x, c.x, d.x, 0., a.y, c.y, d.y, 0., a.z, c.z, d.z, 0., a.w, c.w, d.w, 1.);
}
mat4 mcPose(int b) {
  return mcBone(int(aPose.x + .5), b) * (1. - aPose.z) + mcBone(int(aPose.y + .5), b) * aPose.z;
}
mat4 mcSkin() {
  mat4 s = mat4(0.);
  for (int k = 0; k < 4; k++) if (aWeights[k] > 0.) s += mcPose(int(aBones[k] + .5)) * aWeights[k];
  return s;
}
`;

function geometryOf(m: Merged): THREE.BufferGeometry {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(m.pos, 3));
  g.setAttribute("uv", new THREE.BufferAttribute(m.uv, 2));
  g.setAttribute("aBones", new THREE.BufferAttribute(m.bones, 4));
  g.setAttribute("aWeights", new THREE.BufferAttribute(m.weights, 4));
  g.setAttribute("aPart", new THREE.BufferAttribute(m.part, 1));
  g.setIndex(new THREE.BufferAttribute(m.index, 1));
  g.computeVertexNormals();
  return g;
}

export type Kit = { shirt: string; shorts: string; socks: string };
export type Look = { kit: Kit; skin: string; hair: string; bald?: boolean };

/** Per-instance data of one mesh (an instance slot can hold anyone). */
type Layer = { mesh: THREE.InstancedMesh; pose: THREE.InstancedBufferAttribute; look: THREE.InstancedBufferAttribute };

/** Colours per person: skin, shirt, shorts, socks, hair. In a texture, not in
 * attributes: phones allow 16 of those, and a matrix alone takes four. */
function lookTexture(looks: Look[]) {
  const data = new Float32Array(looks.length * 5 * 4);
  looks.forEach((l, i) => {
    [skinTone(l.skin), tint(l.kit.shirt, 1.18), tint(l.kit.shorts, 1.18), tint(l.kit.socks, 1.18), tint(l.hair)].forEach((c, k) => {
      data.set([c.r, c.g, c.b, 1], (i * 5 + k) * 4);
    });
  });
  const t = new THREE.DataTexture(data, 5, looks.length, THREE.RGBAFormat, THREE.FloatType);
  t.minFilter = t.magFilter = THREE.NearestFilter;
  t.needsUpdate = true;
  return t;
}

function layer(merged: Merged, baked: Baked, map: THREE.Texture | null, hairMap: THREE.Texture | null, looks: THREE.Texture): Layer {
  const geo = geometryOf(merged);
  const pose = new THREE.InstancedBufferAttribute(new Float32Array(PEOPLE * 3), 3).setUsage(THREE.DynamicDrawUsage);
  const look = new THREE.InstancedBufferAttribute(new Float32Array(PEOPLE), 1).setUsage(THREE.DynamicDrawUsage);
  geo.setAttribute("aPose", pose);
  geo.setAttribute("aLook", look);

  const mat = new THREE.MeshLambertMaterial({ map });
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uBake = { value: baked.texture };
    sh.uniforms.uLooks = { value: looks };
    sh.uniforms.uHairMap = { value: hairMap };
    sh.vertexShader = (`${head(baked)}uniform highp sampler2D uLooks; attribute float aLook;
varying vec3 vMcTint; varying float vMcHair;
` + sh.vertexShader)
      .replace("#include <beginnormal_vertex>", "mat4 mcS = mcSkin();\nvec3 objectNormal = normalize(mat3(mcS) * vec3(normal));")
      .replace("#include <begin_vertex>", `vec3 transformed = (mcS * vec4(position, 1.)).xyz;
        vMcTint = aPart < 4.5 ? texelFetch(uLooks, ivec2(int(aPart + .5), int(aLook + .5)), 0).rgb : vec3(1.);
        vMcHair = aPart > 3.5 && aPart < 4.5 ? 1. : 0.;`);
    sh.fragmentShader = (`uniform sampler2D uHairMap;
varying vec3 vMcTint; varying float vMcHair;
` + sh.fragmentShader).replace(
      "#include <map_fragment>",
      `#include <map_fragment>
       if (vMcHair > .5) diffuseColor.rgb = texture2D(uHairMap, vMapUv).rgb * 1.6;
       diffuseColor.rgb *= vMcTint;`,
    );
  };
  mat.customProgramCacheKey = () => "match3d-player";
  const mesh = new THREE.InstancedMesh(geo, mat, PEOPLE);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.frustumCulled = false;
  return { mesh, pose, look };
}

export type Squad = {
  group: THREE.Group;
  /** Place someone. `near`: draw him in full detail. */
  set: (i: number, x: number, y: number, z: number, yaw: number, rowA: number, rowB: number, w: number, near: boolean) => void;
  commit: () => void;
  dispose: () => void;
  shadow: THREE.InstancedMesh;
};

const tint = (s: string, k = 1) => new THREE.Color(s).multiplyScalar(k);
/** The skin's texture is already skin-coloured: only this much of a tone goes on. */
const skinTone = (s: string) => new THREE.Color(s).lerp(new THREE.Color("#ffffff"), 0.4);

export function makeSquad(near: Merged, far: Merged, baked: Baked, map: THREE.Texture | null, hairMap: THREE.Texture | null, looks: Look[]): Squad {
  const lookMap = lookTexture(looks);
  const full = layer(near, baked, map, hairMap, lookMap);
  const light = layer(far, baked, map, hairMap, lookMap);
  const shadowMat = new THREE.MeshBasicMaterial({ color: "#071a0c", transparent: true, opacity: 0.34, depthFunc: THREE.LessDepth });
  shadowMat.onBeforeCompile = (sh) => {
    sh.uniforms.uBake = { value: baked.texture };
    sh.uniforms.uSun = { value: SUN };
    sh.vertexShader = (`${head(baked)}uniform vec3 uSun;\n` + sh.vertexShader)
      .replace("#include <begin_vertex>", "vec3 transformed = (mcSkin() * vec4(position, 1.)).xyz;")
      .replace("#include <project_vertex>", `vec4 mvPosition = instanceMatrix * vec4(transformed, 1.);
        mvPosition.xz -= uSun.xz / uSun.y * mvPosition.y;
        mvPosition.y = .015;
        mvPosition = viewMatrix * mvPosition;
        gl_Position = projectionMatrix * mvPosition;`);
  };
  shadowMat.customProgramCacheKey = () => "match3d-shadow";
  // Everybody is here, in his own slot, whichever detail he's drawn in.
  const shadowPose = new THREE.InstancedBufferAttribute(new Float32Array(PEOPLE * 3), 3).setUsage(THREE.DynamicDrawUsage);
  const shadowGeo = light.mesh.geometry.clone();
  shadowGeo.setAttribute("aPose", shadowPose);
  const shadow = new THREE.InstancedMesh(shadowGeo, shadowMat, PEOPLE);
  shadow.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  shadow.frustumCulled = false;
  shadow.renderOrder = 1;
  const group = new THREE.Group();
  group.add(full.mesh, light.mesh, shadow);

  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  const p = new THREE.Vector3();
  const one = new THREE.Vector3(1, 1, 1);
  let nFull = 0, nLight = 0;
  return {
    group, shadow,
    set: (i, x, y, z, yaw, rowA, rowB, w, close) => {
      q.setFromAxisAngle(up, yaw);
      m.compose(p.set(x, y, z), q, one);
      const l = close ? full : light;
      const at = close ? nFull++ : nLight++;
      l.mesh.setMatrixAt(at, m);
      l.pose.setXYZ(at, rowA, rowB, w);
      l.look.setX(at, i);
      m.toArray(shadow.instanceMatrix.array, i * 16);
      shadowPose.setXYZ(i, rowA, rowB, w);
    },
    commit: () => {
      for (const [l, n] of [[full, nFull], [light, nLight]] as const) {
        l.mesh.count = n;
        l.mesh.instanceMatrix.needsUpdate = true;
        l.pose.needsUpdate = true;
        l.look.needsUpdate = true;
      }
      shadow.instanceMatrix.needsUpdate = true;
      shadowPose.needsUpdate = true;
      nFull = 0; nLight = 0;
    },
    dispose: () => {
      full.mesh.geometry.dispose();
      light.mesh.geometry.dispose();
      shadowGeo.dispose();
      (full.mesh.material as THREE.Material).dispose();
      (light.mesh.material as THREE.Material).dispose();
      shadowMat.dispose();
      lookMap.dispose();
    },
  };
}
