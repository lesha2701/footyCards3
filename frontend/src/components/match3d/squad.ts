/** Everyone on the pitch as instanced meshes: the full model for who's near
 * the camera, the light one for the rest, the light one again flattened on
 * the grass for the sun's shadows. A pose is two rows of the bake and a blend. */
import * as THREE from "three";

import type { Baked, Merged } from "./baked";
import { SUN } from "./stadium";

/** 22 footballers, the referee, two assistants. */
export const PEOPLE = 25;
export const REFEREE = 22;

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

/** Per-instance data of one mesh (its own copy: an instance slot can hold anyone). */
type Layer = { mesh: THREE.InstancedMesh; pose: THREE.InstancedBufferAttribute; shirt: THREE.InstancedBufferAttribute; shorts: THREE.InstancedBufferAttribute; socks: THREE.InstancedBufferAttribute; skin: THREE.InstancedBufferAttribute; hair: THREE.InstancedBufferAttribute };

function layer(merged: Merged, baked: Baked, map: THREE.Texture | null, hairMap: THREE.Texture | null): Layer {
  const geo = geometryOf(merged);
  const attr = (size: number, dynamic = false) => {
    const a = new THREE.InstancedBufferAttribute(new Float32Array(PEOPLE * size), size);
    if (dynamic) a.setUsage(THREE.DynamicDrawUsage);
    return a;
  };
  const pose = attr(3, true), shirt = attr(3, true), shorts = attr(3, true), socks = attr(3, true), skin = attr(3, true), hair = attr(3, true);
  geo.setAttribute("aPose", pose);
  geo.setAttribute("aShirt", shirt);
  geo.setAttribute("aShorts", shorts);
  geo.setAttribute("aSocks", socks);
  geo.setAttribute("aSkin", skin);
  geo.setAttribute("aHair", hair);

  const mat = new THREE.MeshLambertMaterial({ map });
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uBake = { value: baked.texture };
    sh.uniforms.uHairMap = { value: hairMap };
    sh.vertexShader = (`${HEAD}attribute vec3 aShirt; attribute vec3 aShorts; attribute vec3 aSocks; attribute vec3 aSkin; attribute vec3 aHair;
varying vec3 vMcTint; varying float vMcHair;
` + sh.vertexShader)
      .replace("#include <beginnormal_vertex>", "mat4 mcS = mcSkin();\nvec3 objectNormal = normalize(mat3(mcS) * vec3(normal));")
      .replace("#include <begin_vertex>", `vec3 transformed = (mcS * vec4(position, 1.)).xyz;
        vMcTint = aPart < .5 ? aSkin : aPart < 1.5 ? aShirt : aPart < 2.5 ? aShorts : aPart < 3.5 ? aSocks : aPart < 4.5 ? aHair : vec3(1.);
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
  return { mesh, pose, shirt, shorts, socks, skin, hair };
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
  const full = layer(near, baked, map, hairMap);
  const light = layer(far, baked, map, hairMap);
  const shadowMat = new THREE.MeshBasicMaterial({ color: "#071a0c", transparent: true, opacity: 0.34, depthFunc: THREE.LessDepth });
  shadowMat.onBeforeCompile = (sh) => {
    sh.uniforms.uBake = { value: baked.texture };
    sh.uniforms.uSun = { value: SUN };
    sh.vertexShader = (`${HEAD}uniform vec3 uSun;\n` + sh.vertexShader)
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
  const setColor = (a: THREE.InstancedBufferAttribute, at: number, c: THREE.Color) => a.setXYZ(at, c.r, c.g, c.b);
  const colours = looks.map((l) => ({
    shirt: tint(l.kit.shirt, 1.18), shorts: tint(l.kit.shorts, 1.18), socks: tint(l.kit.socks, 1.18), skin: skinTone(l.skin), hair: tint(l.hair),
  }));
  return {
    group, shadow,
    set: (i, x, y, z, yaw, rowA, rowB, w, close) => {
      q.setFromAxisAngle(up, yaw);
      m.compose(p.set(x, y, z), q, one);
      const l = close ? full : light;
      const at = close ? nFull++ : nLight++;
      l.mesh.setMatrixAt(at, m);
      l.pose.setXYZ(at, rowA, rowB, w);
      const c = colours[i];
      setColor(l.shirt, at, c.shirt); setColor(l.shorts, at, c.shorts); setColor(l.socks, at, c.socks); setColor(l.skin, at, c.skin); setColor(l.hair, at, c.hair);
      m.toArray(shadow.instanceMatrix.array, i * 16);
      shadowPose.setXYZ(i, rowA, rowB, w);
    },
    commit: () => {
      for (const [l, n] of [[full, nFull], [light, nLight]] as const) {
        l.mesh.count = n;
        l.mesh.instanceMatrix.needsUpdate = true;
        for (const a of [l.pose, l.shirt, l.shorts, l.socks, l.skin, l.hair]) a.needsUpdate = true;
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
    },
  };
}
