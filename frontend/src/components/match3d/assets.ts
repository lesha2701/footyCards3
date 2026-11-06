/** Everything «Матч 3D» downloads and prepares once, before the kick-off. */
import * as THREE from "three";
import { GLTFLoader, type GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";

import { FOOTBALLER_URL, HIPS, MOVES_URL, inPlace, prepareFootballer, upAxis } from "@/components/career/goal3d/footballer";
import { ONE_ON_ONE_MOVES_URL, prepareMoves, type Moves } from "@/components/oneOnOne/moves";

import { bakeClips, mergeModel, simplify, type Baked, type Merged } from "./baked";
import type { Paces } from "./motion";

export const MATCH_MOVES_URL = "/match-3d/moves.glb";
/** The light model everybody far from the camera wears. */
const FAR_TRIS = 3200;

export type MatchAssets = {
  near: Merged;
  far: Merged;
  baked: Baked;
  moves: Moves;
  paces: Paces;
  map: THREE.Texture | null;
  hairMap: THREE.Texture | null;
  grass: THREE.Texture;
  fans: THREE.Texture;
  led: THREE.Texture;
};

const breathe = () => new Promise((r) => setTimeout(r, 0));

const texture = (url: string) => new THREE.TextureLoader().loadAsync(url).then((t) => {
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
});

let cache: Promise<MatchAssets> | null = null;

async function load(onProgress: (share: number) => void): Promise<MatchAssets> {
  const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  let done = 0;
  const tick = <T,>(p: Promise<T>) => p.then((v) => { done += 1; onProgress((done / 8) * 0.8); return v; });
  const [gltf, base, oneOnOne, own, grass, fans, led] = await Promise.all([
    tick(loader.loadAsync(FOOTBALLER_URL)),
    tick(loader.loadAsync(MOVES_URL)),
    tick(loader.loadAsync(ONE_ON_ONE_MOVES_URL)),
    tick(loader.loadAsync(MATCH_MOVES_URL).catch((): GLTF | null => null)),
    tick(texture("/free-kick-3d/grass.webp")),
    tick(texture("/free-kick-3d/fans.webp")),
    tick(texture("/free-kick-3d/led.webp")),
  ]);
  await breathe();
  const asset = prepareFootballer(gltf, base);
  const moves = prepareMoves(gltf, oneOnOne);
  const hips = gltf.animations.find((c) => c.name === "idle")?.tracks.find((tr) => HIPS.test(tr.name));
  const up = hips ? upAxis(hips) : 1;
  const clips: Record<string, THREE.AnimationClip> = { ...asset.clips, ...moves.clips };
  // The engine moves the keeper through his dive; the career's clips carry
  // him themselves, and would take him twice as far.
  for (const name of ["gk_dive_left", "gk_dive_right"]) {
    const raw = gltf.animations.concat(base.animations).find((c) => c.name === name);
    if (raw) clips[name] = inPlace(raw, up);
  }
  for (const clip of own?.animations ?? []) clips[clip.name] = inPlace(clip, up);
  onProgress(0.85);
  await breathe();
  const { merged, boneNames } = mergeModel(gltf);
  const far = simplify(merged, FAR_TRIS);
  onProgress(0.92);
  await breathe();
  const baked = bakeClips(gltf, clips, boneNames);
  let map: THREE.Texture | null = null, hairMap: THREE.Texture | null = null;
  gltf.scene.traverse((o) => {
    const mesh = o as THREE.Mesh;
    const mat = mesh.material as THREE.MeshStandardMaterial | undefined;
    if (!mat?.map) return;
    if (/Hair/i.test(mesh.name)) hairMap ??= mat.map;
    else map ??= mat.map;
  });
  onProgress(1);
  return {
    near: merged, far, baked, moves, map, hairMap, grass, fans, led,
    paces: {
      run: asset.timing.runSpeed, sprint: asset.timing.sprintSpeed, back: asset.timing.backSpeed,
      dribble: 1.13,
    },
  };
}

/** Once a session; a failed attempt can be retried. */
export function loadMatchAssets(onProgress: (share: number) => void): Promise<MatchAssets> {
  cache ??= load(onProgress).catch((e) => {
    cache = null;
    throw e;
  });
  return cache;
}
