/** The model's texture has a «7» painted on the back of the shirt, the same on
 * everyone. In the shader it is covered with the cloth beside it and the man's
 * own number goes on in its place, from one atlas of digits. */
import * as THREE from "three";

const CELL_W = 64;
const CELL_H = 96;
let digits: THREE.CanvasTexture | null = null;

export function digitAtlas(): THREE.Texture {
  if (digits) return digits;
  const canvas = document.createElement("canvas");
  canvas.width = CELL_W * 10;
  canvas.height = CELL_H;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#fff";
  ctx.font = "bold 88px Arial, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let d = 0; d < 10; d++) ctx.fillText(String(d), CELL_W * (d + 0.5), CELL_H * 0.54);
  digits = new THREE.CanvasTexture(canvas);
  // Same way up as the model's UVs (glTF: v goes down).
  digits.flipY = false;
  digits.anisotropy = 4;
  return digits;
}

/** 1: white ink, 0: near-black, whichever reads on the shirt. */
export const inkOn = (shirt: string) => {
  const c = new THREE.Color(shirt);
  return c.r * 0.3 + c.g * 0.59 + c.b * 0.11 > 0.45 ? 0 : 1;
};

/** `shirtCloth`: the texture with the painted number covered; `shirtInk`: how
 * much of his number covers this point. A number below zero: not the shirt. Zero:
 * no number. Explicit gradients: a jump in the coordinates would otherwise pick
 * the wrong mip and draw a line round the patch. */
export const SHIRT_NUMBER_GLSL = /* glsl */ `
uniform sampler2D uDigits;
vec4 shirtCloth(sampler2D map, vec2 uv, float number) {
  bool over = number > -.5 && abs(uv.x - .553) < .034 && abs(uv.y - .76) < .06;
  return textureGrad(map, over ? uv + vec2(.08, 0.) : uv, dFdx(uv), dFdy(uv));
}
float shirtInk(vec2 uv, float number) {
  vec2 q = (uv - vec2(.553, .7)) / vec2(.074, .118);
  vec2 cell = q / vec2(10., 1.);
  float n = floor(number + .5), tens = floor(n / 10.), two = step(.5, tens);
  float x = q.x + 1. - .5 * (1. - two), f = fract(x);
  float digit = mix(n - tens * 10., tens, two * (1. - step(1., x)));
  float inside = step(.5, n) * step(0., x) * (1. - step(1. + two, x)) * step(0., q.y) * (1. - step(1., q.y));
  // Read everywhere, masked after: inside a branch the gradients go wrong at its edge.
  return inside * textureGrad(uDigits, vec2((digit + f) / 10., q.y), dFdx(cell), dFdy(cell)).r;
}
`;
export const SHIRT_INK_DARK = "vec3(.07, .09, .15)";
export const SHIRT_INK_LIGHT = "vec3(.95)";

/** Puts `number` (0: none) on a shirt material of the model. */
export function printNumber(mat: THREE.Material, number: number, shirt: string) {
  const ink = inkOn(shirt);
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uDigits = { value: digitAtlas() };
    sh.uniforms.uNumber = { value: number };
    sh.uniforms.uInk = { value: ink };
    sh.fragmentShader = (`uniform float uNumber, uInk;\n${SHIRT_NUMBER_GLSL}` + sh.fragmentShader).replace(
      "#include <map_fragment>",
      `diffuseColor *= shirtCloth(map, vMapUv, uNumber);
       diffuseColor.rgb = mix(diffuseColor.rgb, uInk > .5 ? ${SHIRT_INK_LIGHT} : ${SHIRT_INK_DARK}, shirtInk(vMapUv, uNumber));`,
    );
  };
  mat.customProgramCacheKey = () => "shirt-number";
}
