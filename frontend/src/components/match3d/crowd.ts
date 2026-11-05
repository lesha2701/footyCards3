/** The people in the stands: one instanced draw of cut-out supporters on the
 * seats of the bowl, in their side's colours. Nothing runs per person on the CPU:
 * they bob in the vertex shader and jump when `cheer` is up. */
import * as THREE from "three";

import { HALF_L, HALF_W } from "@/lib/match3d/core";

/** The sheet is 4 by 4. These have their arms up, the rest clap or shout. */
const ARMS_UP = [0, 1, 5, 7, 9, 12, 15];
const ARMS_DOWN = [2, 3, 4, 6, 8, 10, 11, 13, 14];
/** A person takes this much room (m): along a row and between rows. */
const SEAT = 0.95;
const ROW = 1.05;
const SIZE = 1.35;
/** How full the ground is, and how full the stand behind the broadcast camera,
 * which only a replay ever looks at. */
const FULL = 0.93;
const BEHIND_CAMERA = 0.4;

export type Ring = { a: number; b: number; y: number };
/** A point of a stand: `t` round the bowl, `u` the share of the way round. */
export type Bowl = {
  point: (t: number, a: number, b: number) => readonly [number, number];
  /** Evenly spaced `t` round a ring (m apart), with their `u`. */
  walk: (a: number, b: number, step: number) => { t: number; u: number }[];
};

const rng = (seed: number) => () => (seed = (seed * 16807) % 2147483647) / 2147483647;

/** The seats of one tier: everyone sits on the slope from `lo` to `hi`. */
function seat(bowl: Bowl, lo: Ring, hi: Ring, tiles: number, aisle: number, shadeLo: number, shadeHi: number, r: () => number) {
  const out: number[] = [];
  const depth = Math.sqrt((hi.a - lo.a) ** 2 + (hi.y - lo.y) ** 2);
  const rows = Math.floor(depth / ROW);
  for (let row = 0; row < rows; row++) {
    const f = (row + 0.5) / rows;
    const a = lo.a + (hi.a - lo.a) * f, b = lo.b + (hi.b - lo.b) * f, y = lo.y + (hi.y - lo.y) * f;
    for (const { t, u } of bowl.walk(a, b, SEAT)) {
      const across = (u * tiles) % 1;
      if (across < aisle) continue;
      const [x, z] = bowl.point(t, a, b);
      if (r() > (z > HALF_W ? BEHIND_CAMERA : FULL)) continue;
      // Away fans are one block in the corner by their own end.
      const away = x < -38 && z < -8 && z > -46;
      const neutral = r() < 0.14;
      const up = ARMS_UP[Math.floor(r() * ARMS_UP.length)];
      const cell = r() < 0.3 ? up : ARMS_DOWN[Math.floor(r() * ARMS_DOWN.length)];
      const side = neutral ? 2 : away ? 1 : 0;
      out.push(x + (r() - 0.5) * 0.25, y, z, cell, up, side, r(), shadeLo + (shadeHi - shadeLo) * f);
    }
  }
  return out;
}

const VERTEX = /* glsl */ `
attribute vec3 aPos;
attribute vec4 aFan;
attribute float aShade;
uniform float uTime;
uniform vec2 uCheer;
uniform vec2 uHalf;
varying vec2 vUv;
varying vec3 vTint;
varying float vShade;
uniform vec3 uColor[3];

void main() {
  float side = aFan.z, ph = aFan.w;
  float cheer = side < 1.5 ? (side < .5 ? uCheer.x : uCheer.y) : max(uCheer.x, uCheer.y) * .5;
  // They face the pitch, not the camera: nobody turns round to watch a replay.
  vec2 out0 = aPos.xz - clamp(aPos.xz, -uHalf, uHalf);
  vec2 n = normalize(out0 + vec2(.001, 0.));
  vec3 right = vec3(-n.y, 0., n.x);
  float big = .9 + fract(ph * 17.) * .22;
  float beat = uTime * (1.5 + fract(ph * 7.) * 1.1) + ph * 40.;
  float hop = abs(sin(uTime * (6.5 + fract(ph * 3.) * 2.5) + ph * 30.)) * cheer * .62;
  vec3 at = aPos + right * (position.x * ${SIZE.toFixed(2)} * big);
  at.y += position.y * ${SIZE.toFixed(2)} * big + sin(beat) * .03 + hop;
  at += right * sin(beat * .6) * .05 * position.y;
  float cell = cheer > .3 ? aFan.y : aFan.x;
  // A hair inside the cell: the low mips would bleed the next person in.
  vUv = (uv * .97 + .015 + vec2(mod(cell, 4.), 3. - floor(cell / 4.))) / 4.;
  vTint = uColor[int(side)] * (.8 + fract(ph * 11.) * .35);
  vShade = aShade;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(at, 1.);
}
`;

const FRAGMENT = /* glsl */ `
uniform sampler2D uMap;
varying vec2 vUv;
varying vec3 vTint;
varying float vShade;

void main() {
  // A sharper mip than the distance asks for: at the proper one a person is mostly
  // see-through, and the alpha test eats him.
  vec4 c = texture2D(uMap, vUv, -1.2);
  if (c.a < .32) discard;
  // The sheet's clothes are green: that part takes his side's colour.
  // Measured against the pixel's own brightness: a far mip is green mixed with skin.
  float green = clamp((c.g - max(c.r, c.b)) / max(c.g, .04) * 4.5, 0., 1.);
  vec3 rgb = mix(c.rgb, vTint * (.5 + c.g * 1.1), green);
  gl_FragColor = vec4(rgb * vShade, 1.);
  #include <colorspace_fragment>
}
`;

export type Crowd = { mesh: THREE.Mesh; cheer: (team: 0 | 1) => void; update: (dt: number, time: number) => void; dispose: () => void };

export function makeCrowd(map: THREE.Texture, bowl: Bowl, tiers: { lo: Ring; hi: Ring; tiles: number; aisle: number; shade: readonly [number, number] }[], colours: readonly [string, string]): Crowd {
  const r = rng(40711);
  const data = tiers.flatMap((t) => seat(bowl, t.lo, t.hi, t.tiles, t.aisle, t.shade[0], t.shade[1], r));
  const n = data.length / 8;
  const pos = new Float32Array(n * 3), fan = new Float32Array(n * 4), shade = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const k = i * 8;
    pos.set(data.slice(k, k + 3), i * 3);
    fan.set(data.slice(k + 3, k + 7), i * 4);
    shade[i] = data[k + 7];
  }
  const geo = new THREE.InstancedBufferGeometry();
  const quad = new THREE.PlaneGeometry(1, 1);
  quad.translate(0, 0.5, 0);
  geo.index = quad.index;
  geo.setAttribute("position", quad.getAttribute("position"));
  geo.setAttribute("uv", quad.getAttribute("uv"));
  geo.setAttribute("aPos", new THREE.InstancedBufferAttribute(pos, 3));
  geo.setAttribute("aFan", new THREE.InstancedBufferAttribute(fan, 4));
  geo.setAttribute("aShade", new THREE.InstancedBufferAttribute(shade, 1));
  geo.instanceCount = n;
  const cheer = new THREE.Vector2(0, 0);
  const time = { value: 0 };
  const mat = new THREE.ShaderMaterial({
    vertexShader: VERTEX,
    fragmentShader: FRAGMENT,
    side: THREE.DoubleSide,
    uniforms: {
      uMap: { value: map },
      uTime: time,
      uCheer: { value: cheer },
      uHalf: { value: new THREE.Vector2(HALF_L, HALF_W) },
      uColor: { value: [new THREE.Color(colours[0]), new THREE.Color(colours[1]), new THREE.Color("#3a4152")] },
    },
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.frustumCulled = false;
  return {
    mesh,
    cheer: (team) => { cheer.setComponent(team, 1); },
    update: (dt, t) => {
      time.value = t;
      // A ground stays up for its goal for several seconds, then sits down again.
      const fall = dt / 8;
      cheer.set(Math.max(0, cheer.x - fall), Math.max(0, cheer.y - fall));
    },
    dispose: () => { geo.dispose(); quad.dispose(); mat.dispose(); },
  };
}
