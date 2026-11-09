/** The people in the stands, for a phone: no objects at all. At load the cut-out
 * supporters are drawn once on to a sheet of four bays of seats, twice (sitting, and
 * with their arms up), and the sheet is laid on the slope of each tier. They move in
 * the fragment shader: each person's patch of the sheet slides up and down, and in a
 * cheer that patch is read from the arms-up sheet. The cost is the tier's few
 * triangles and two texture reads. */
import * as THREE from "three";

/** The supporters' sheet is 4 by 4. These have their arms up. */
const ARMS_UP = [0, 1, 5, 7, 9, 12, 15];
const ARMS_DOWN = [2, 3, 4, 6, 8, 10, 11, 13, 14];
const SHEET_W = 2048, SHEET_H = 1024;
/** What one sheet holds. The sheet is the tier's whole depth. */
export const BAYS = 4;
export const ROWS = 28;
const SEATS = 15;
/** The share of a bay the aisle takes. */
const AISLE = 0.07;
/** The slope foreshortens them seen from the broadcast camera: drawn this much taller. */
const TALL = 1.6;
const FULL = 0.94;

const rng = (seed: number) => () => (seed = (seed * 16807) % 2147483647) / 2147483647;

/** The same people in grey and navy: not everyone came in the shirt. */
function plainClothes(cut: CanvasImageSource, w: number, h: number) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const x = c.getContext("2d", { willReadFrequently: true })!;
  x.drawImage(cut, 0, 0, w, h);
  const im = x.getImageData(0, 0, w, h), d = im.data;
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i], g = d[i + 1], b = d[i + 2];
    if (g > r * 1.15 && g > b * 1.15) { d[i] = g * 0.28; d[i + 1] = g * 0.32; d[i + 2] = g * 0.42; }
  }
  x.putImageData(im, 0, 0);
  return c;
}

function bake(sheet: CanvasImageSource, plain: CanvasImageSource, cellW: number, cellH: number) {
  const r = rng(40711);
  type Fan = { x: number; y: number; cell: number; up: number; plain: boolean; size: number };
  const fans: Fan[] = [];
  const bay = SHEET_W / BAYS, rowH = SHEET_H / ROWS;
  const seat = (bay * (1 - AISLE)) / SEATS;
  // Back rows first: the row in front covers their legs.
  for (let row = ROWS - 1; row >= 0; row--) {
    for (let b = 0; b < BAYS; b++) {
      for (let i = 0; i < SEATS; i++) {
        if (r() > FULL) continue;
        const up = ARMS_UP[Math.floor(r() * ARMS_UP.length)];
        fans.push({
          x: b * bay + bay * AISLE + (i + 0.5 + (r() - 0.5) * 0.3) * seat,
          y: SHEET_H - row * rowH,
          cell: r() < 0.3 ? up : ARMS_DOWN[Math.floor(r() * ARMS_DOWN.length)],
          up, plain: r() < 0.14, size: seat * (1.32 + r() * 0.24),
        });
      }
    }
  }
  const page = (arms: boolean) => {
    const c = document.createElement("canvas");
    c.width = SHEET_W; c.height = SHEET_H;
    const x = c.getContext("2d")!;
    for (let row = 0; row < ROWS; row++) {
      x.fillStyle = "#26364d"; x.fillRect(0, row * rowH, SHEET_W, rowH * 0.7);
      x.fillStyle = "#161f2d"; x.fillRect(0, row * rowH + rowH * 0.7, SHEET_W, rowH * 0.3);
    }
    for (let b = 0; b < BAYS; b++) {
      x.fillStyle = "#4b5461"; x.fillRect(b * bay, 0, bay * AISLE, SHEET_H);
      x.fillStyle = "#3a424e";
      for (let row = 0; row < ROWS; row++) x.fillRect(b * bay, row * rowH + rowH * 0.7, bay * AISLE, rowH * 0.3);
    }
    for (const f of fans) {
      const cell = arms ? f.up : f.cell;
      const w = f.size, h = f.size * TALL;
      x.drawImage(f.plain ? plain : sheet, (cell % 4) * cellW, Math.floor(cell / 4) * cellH, cellW, cellH, f.x - w / 2, f.y - h, w, h);
    }
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    t.wrapS = THREE.RepeatWrapping;
    t.anisotropy = 4;
    return t;
  };
  return [page(false), page(true)] as const;
}

const VERTEX = /* glsl */ `
varying vec2 vUv;
varying vec2 vAt;
void main() {
  vUv = uv;
  vAt = position.xz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.);
}
`;

const FRAGMENT = /* glsl */ `
uniform sampler2D uSit;
uniform sampler2D uUp;
uniform float uTime;
uniform vec2 uCheer;
uniform vec3 uHome;
uniform vec3 uAway;
uniform vec2 uShade;
varying vec2 vUv;
varying vec2 vAt;

void main() {
  float away = step(vAt.x, -38.) * step(vAt.y, -8.) * step(-46., vAt.y);
  float cheer = away > .5 ? uCheer.y : uCheer.x;
  // Whose patch of the sheet is this.
  vec2 id = floor(vec2(vUv.x * ${(SEATS * BAYS).toFixed(1)} / ${BAYS.toFixed(1)}, vUv.y * ${ROWS.toFixed(1)}));
  float me = fract(sin(dot(id, vec2(12.9898, 78.233))) * 43758.5453);
  float idle = sin(uTime * (1.5 + me) + me * 40.) * .012;
  float hop = abs(sin(uTime * (6. + me * 3.) + me * 30.)) * cheer * .05;
  vec2 uv = vec2(vUv.x, vUv.y - idle - hop);
  // The patches jump apart: the mip comes from the unbroken coordinates, a little
  // sharper than the distance asks for.
  vec2 dx = dFdx(vUv) * .7, dy = dFdy(vUv) * .7;
  vec3 c = textureGrad(uSit, uv, dx, dy).rgb;
  if (cheer > .01 && me < cheer * 1.3) c = textureGrad(uUp, uv, dx, dy).rgb;
  // The sheet's clothes are green: that part takes the side's colour. Measured against
  // the pixel's own brightness, because a far mip is green mixed with skin.
  float green = clamp((c.g - max(c.r, c.b)) / max(c.g, .04) * 4.5, 0., 1.);
  vec3 tint = away > .5 ? uAway : uHome;
  c = mix(c, tint * (.5 + c.g * 1.1), green);
  gl_FragColor = vec4(c * mix(uShade.x, uShade.y, vUv.y), 1.);
  #include <colorspace_fragment>
}
`;

export type Crowd = {
  /** The material of a tier: `lo` and `hi`, how much light its front and back get. */
  tier: (lo: number, hi: number) => THREE.ShaderMaterial;
  cheer: (team: 0 | 1) => void;
  update: (dt: number) => void;
  dispose: () => void;
};

export function makeCrowd(map: THREE.Texture, colours: readonly [string, string]): Crowd {
  const image = map.image as HTMLImageElement | ImageBitmap;
  const plain = plainClothes(image, image.width, image.height);
  const [sit, up] = bake(image, plain, image.width / 4, image.height / 4);
  const time = { value: 0 };
  const cheerUp = new THREE.Vector2(0, 0);
  const home = { value: new THREE.Color(colours[0]) }, away = { value: new THREE.Color(colours[1]) };
  const mats: THREE.ShaderMaterial[] = [];
  let clock = 0;
  return {
    tier: (lo, hi) => {
      const m = new THREE.ShaderMaterial({
        vertexShader: VERTEX,
        fragmentShader: FRAGMENT,
        uniforms: {
          uSit: { value: sit }, uUp: { value: up }, uTime: time, uCheer: { value: cheerUp },
          uHome: home, uAway: away, uShade: { value: new THREE.Vector2(lo, hi) },
        },
      });
      mats.push(m);
      return m;
    },
    cheer: (team) => { cheerUp.setComponent(team, 1); },
    update: (dt) => {
      clock = (clock + dt) % 628.3;
      time.value = clock;
      // A ground stays up for its goal for several seconds, then sits down again.
      const fall = dt / 8;
      cheerUp.set(Math.max(0, cheerUp.x - fall), Math.max(0, cheerUp.y - fall));
    },
    dispose: () => { sit.dispose(); up.dispose(); mats.forEach((m) => m.dispose()); },
  };
}
