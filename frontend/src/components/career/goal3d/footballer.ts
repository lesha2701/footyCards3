/** The skinned footballer of the 3D goal replay: the Mixamo model and clips
 * of the free-kick prototype (public/career-3d/footballer.glb, meshopt)
 * plus Mixamo's run, sprint, backpedal, header and celebrations on the same
 * rig (footballer-moves.glb, tools/career-replay-3d/build_moves.py),
 * prepared for 22 players whose positions come from the key frames: clips
 * play in place (no root motion but the keeper's dive), the loops' natural
 * speeds and the one-off clips' timing (kick contact, jump apex, dive
 * reach) are read from the clips. */
import * as THREE from "three";
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

import { DEFAULT_TIMING, type ClipName, type ClipTiming } from "@/lib/footballerMotion";

export const FOOTBALLER_URL = "/career-3d/footballer.glb";
export const MOVES_URL = "/career-3d/footballer-moves.glb";

export interface FootballerAsset {
  gltf: GLTF;
  clips: Record<ClipName, THREE.AnimationClip>;
  timing: ClipTiming;
  /** The striking (right) toe at the kick's contact, in the model's own
   * frame on the ground (it faces +z): where the ball must be then. */
  kickToe: { x: number; z: number };
}

/** Poses a copy of the model at the kick's contact and reads where the
 * right toe is (in place, so relative to the body). */
function kickToe(gltf: GLTF, kick: THREE.AnimationClip, contact: number): { x: number; z: number } {
  const model = cloneSkinned(gltf.scene);
  const mixer = new THREE.AnimationMixer(model);
  mixer.clipAction(kick).play();
  mixer.setTime(contact);
  model.updateMatrixWorld(true);
  const bones = bonesOf(model);
  const toe = bones.RightToeBase ?? bones.RightFoot;
  const p = toe ? toe.getWorldPosition(new THREE.Vector3()) : new THREE.Vector3(0.15, 0, 0.45);
  mixer.stopAllAction();
  return { x: p.x, z: p.z };
}

const HIPS = /Hips\.position$/;

/** Index (0-2) of the up axis in the hips position track: hips height is
 * by far the largest component of a standing pose. */
function upAxis(track: THREE.KeyframeTrack): number {
  const sums = [0, 0, 0];
  for (let i = 0; i < track.values.length; i += 3) for (let k = 0; k < 3; k++) sums[k] += Math.abs(track.values[i + k]);
  return sums.indexOf(Math.max(...sums));
}

/** The clip with its hips kept over the origin (sideways and forwards),
 * height left as animated — the key frames move the player, not the clip. */
function inPlace(clip: THREE.AnimationClip, up: number): THREE.AnimationClip {
  const out = clip.clone();
  for (const track of out.tracks) {
    if (!HIPS.test(track.name)) continue;
    for (let i = 0; i < track.values.length; i += 3) for (let k = 0; k < 3; k++) if (k !== up) track.values[i + k] = 0;
  }
  return out;
}

/** The dive keeps its sideways travel (that is the dive), from the origin. */
function fromOrigin(clip: THREE.AnimationClip, up: number): THREE.AnimationClip {
  const out = clip.clone();
  for (const track of out.tracks) {
    if (!HIPS.test(track.name)) continue;
    const first = [track.values[0], track.values[1], track.values[2]];
    for (let i = 0; i < track.values.length; i += 3) for (let k = 0; k < 3; k++) if (k !== up) track.values[i + k] -= first[k];
  }
  return out;
}

/** The top of a jump: when the hips are highest. */
function apexOf(clip: THREE.AnimationClip | undefined, up: number): number | null {
  const hips = clip?.tracks.find((tr) => HIPS.test(tr.name));
  if (!hips) return null;
  let best = -Infinity;
  let at = 0;
  for (let i = 0; i < hips.times.length; i++) {
    if (hips.values[i * 3 + up] > best) {
      best = hips.values[i * 3 + up];
      at = hips.times[i];
    }
  }
  return at;
}

/** How fast a clip travels as recorded (m/s): the hips' way over the ground
 * from its first to its last frame. `metres` = metres per unit of the track. */
function travelSpeed(clip: THREE.AnimationClip | undefined, up: number, metres: number): number | null {
  const hips = clip?.tracks.find((tr) => HIPS.test(tr.name));
  if (!clip || !hips || clip.duration <= 0) return null;
  const last = hips.values.length - 3;
  let d = 0;
  for (let k = 0; k < 3; k++) if (k !== up) d += (hips.values[last + k] - hips.values[k]) ** 2;
  const v = (Math.sqrt(d) * metres) / clip.duration;
  return v > 0.5 ? v : null;
}

function timingOf(clips: Record<string, THREE.AnimationClip>, up: number, metres: number): ClipTiming {
  const timing = { ...DEFAULT_TIMING };
  timing.runSpeed = travelSpeed(clips.run, up, metres) ?? timing.runSpeed;
  timing.sprintSpeed = travelSpeed(clips.sprint, up, metres) ?? timing.sprintSpeed;
  timing.backSpeed = travelSpeed(clips.run_back, up, metres) ?? timing.backSpeed;
  if (clips.header) {
    timing.headerApex = apexOf(clips.header, up) ?? timing.headerApex;
    timing.headerDuration = clips.header.duration;
  }
  if (clips.celebrate) timing.celebrateDuration = clips.celebrate.duration;
  if (clips.victory) timing.victoryDuration = clips.victory.duration;
  const jump = clips.wall_jump?.tracks.find((tr) => HIPS.test(tr.name));
  if (jump) {
    let best = -Infinity;
    for (let i = 0; i < jump.times.length; i++) {
      const h = jump.values[i * 3 + up];
      if (h > best) {
        best = h;
        timing.jumpApex = jump.times[i];
      }
    }
    timing.jumpDuration = clips.wall_jump.duration;
  }
  const dive = clips.gk_dive_left?.tracks.find((tr) => HIPS.test(tr.name));
  if (dive) {
    // When the hips start going sideways and when they are at 85 % of
    // their widest (arms out; the widest is him already on the grass).
    const side = (i: number) => {
      let s = 0;
      for (let k = 0; k < 3; k++) if (k !== up) s += (dive.values[i * 3 + k] - dive.values[k]) ** 2;
      return Math.sqrt(s);
    };
    let widest = 0;
    for (let i = 0; i < dive.times.length; i++) widest = Math.max(widest, side(i));
    let start = 0;
    let reach = clips.gk_dive_left.duration;
    for (let i = dive.times.length - 1; i >= 0; i--) {
      if (side(i) >= widest * 0.85) reach = dive.times[i];
      if (side(i) >= widest * 0.12) start = dive.times[i];
    }
    timing.diveStart = Math.min(start, reach);
    timing.diveReach = reach;
    timing.diveDuration = clips.gk_dive_left.duration;
  }
  if (clips.kick) timing.kickDuration = clips.kick.duration;
  if (clips.gk_catch) timing.catchDuration = clips.gk_catch.duration;
  return timing;
}

/** Bones of the Mixamo rig by their name without the "mixamorigN:" prefix
 * (the GLTF loader drops the colon: "mixamorig5Hips"). */
function bonesOf(root: THREE.Object3D): Record<string, THREE.Bone> {
  const out: Record<string, THREE.Bone> = {};
  root.traverse((o) => {
    if ((o as THREE.Bone).isBone) out[o.name.replace(/^mixamorig\d*:?/, "")] = o as THREE.Bone;
  });
  return out;
}

/** When a clip first has a hand above the head (the victory pose's arms
 * up), sampled on a posed copy of the model; 0 when it never does. */
function armsUpAt(gltf: GLTF, clip: THREE.AnimationClip | undefined): number {
  if (!clip) return 0;
  const model = cloneSkinned(gltf.scene);
  const mixer = new THREE.AnimationMixer(model);
  mixer.clipAction(clip).play();
  const bones = bonesOf(model);
  const head = bones.Head;
  const hands = [bones.LeftHand, bones.RightHand].filter(Boolean);
  const v = new THREE.Vector3();
  let at = 0;
  if (head && hands.length) {
    for (let time = 0; time < clip.duration; time += 0.1) {
      mixer.setTime(time);
      model.updateMatrixWorld(true);
      const top = head.getWorldPosition(v).y;
      if (hands.some((h) => h.getWorldPosition(v).y > top)) {
        at = time;
        break;
      }
    }
  }
  mixer.stopAllAction();
  return at;
}

/** Metres per unit of the hips track: the scale of the rig above them. */
function hipsMetres(gltf: GLTF): number {
  gltf.scene.updateMatrixWorld(true);
  const hips = bonesOf(gltf.scene).Hips;
  return hips?.parent ? hips.parent.getWorldScale(new THREE.Vector3()).y : 1;
}

/** The model's clips and the extra moves (same rig, played by bone name). */
export function prepareFootballer(gltf: GLTF, moves?: GLTF): FootballerAsset {
  const byName: Record<string, THREE.AnimationClip> = {};
  for (const clip of [...gltf.animations, ...(moves?.animations ?? [])]) byName[clip.name] = clip;
  const hips = byName.idle?.tracks.find((tr) => HIPS.test(tr.name));
  const up = hips ? upAxis(hips) : 1;
  const clips = {
    idle: inPlace(byName.idle, up),
    gk_idle: inPlace(byName.gk_idle, up),
    kick: inPlace(byName.kick, up),
    wall_jump: inPlace(byName.wall_jump, up),
    gk_dive_left: fromOrigin(byName.gk_dive_left, up),
    gk_dive_right: fromOrigin(byName.gk_dive_right, up),
    gk_catch: inPlace(byName.gk_catch, up),
  } as Record<ClipName, THREE.AnimationClip>;
  // Moves missing from an older file fall back to the closest clip there.
  const extra: [ClipName, ClipName][] = [
    ["run", "idle"], ["sprint", "run"], ["run_back", "run"], ["header", "wall_jump"], ["celebrate", "wall_jump"], ["victory", "celebrate"],
  ];
  for (const [name, fallback] of extra) clips[name] = byName[name] ? inPlace(byName[name], up) : clips[fallback];
  const timing = timingOf(byName, up, hipsMetres(gltf));
  timing.victoryFrom = armsUpAt(gltf, clips.victory);
  return { gltf, clips, timing, kickToe: kickToe(gltf, clips.kick, timing.kickContact) };
}

export interface PlayerLook { shirt: string; shorts: string; socks: string; skin: string; hair: string | null }

/** One player: its own skeleton and mixer, sharing geometry and (per
 * colour) materials with the others. */
export interface SkinnedPlayer {
  root: THREE.Group;
  mixer: THREE.AnimationMixer;
  actions: Record<ClipName, THREE.AnimationAction>;
  current: ClipName | null;
}

/** Materials cached by part and colour: one per kit colour, not per player
 * (Lambert: cheaper than the model's standard material on a phone). */
export class MaterialCache {
  private cache = new Map<string, THREE.Material>();
  get(base: THREE.Material, colour: string): THREE.Material {
    const key = `${base.uuid}:${colour}`;
    let mat = this.cache.get(key);
    if (!mat) {
      const src = base as THREE.MeshStandardMaterial;
      mat = new THREE.MeshLambertMaterial({ map: src.map ?? null, color: colour });
      this.cache.set(key, mat);
    }
    return mat;
  }
  dispose() {
    this.cache.forEach((m) => m.dispose());
    this.cache.clear();
  }
}

export function makePlayer(asset: FootballerAsset, look: PlayerLook, materials: MaterialCache): SkinnedPlayer {
  const model = cloneSkinned(asset.gltf.scene);
  model.traverse((o) => {
    const mesh = o as THREE.SkinnedMesh;
    if (!mesh.isMesh) return;
    mesh.frustumCulled = false;
    const colour = /Shirt/i.test(mesh.name) ? look.shirt
      : /Shorts/i.test(mesh.name) ? look.shorts
        : /Socks/i.test(mesh.name) ? look.socks
          : /Body/i.test(mesh.name) ? look.skin
            : /Hair/i.test(mesh.name) ? look.hair
              : "#ffffff";
    if (colour === null) {
      mesh.visible = false;
      return;
    }
    mesh.material = materials.get(mesh.material as THREE.Material, colour);
  });
  const root = new THREE.Group();
  root.add(model);
  const mixer = new THREE.AnimationMixer(model);
  const actions = {} as Record<ClipName, THREE.AnimationAction>;
  for (const [name, clip] of Object.entries(asset.clips) as [ClipName, THREE.AnimationClip][]) {
    actions[name] = mixer.clipAction(clip);
  }
  return { root, mixer, actions, current: null };
}

/** Switches a player to `next` (cross-fade) unless it already plays it;
 * one-off clips are then placed at `time` by the caller every frame. */
export function setClip(p: SkinnedPlayer, next: ClipName, oneOff: boolean, fade = 0.15): THREE.AnimationAction {
  const action = p.actions[next];
  if (p.current === next) return action;
  action.reset();
  action.setLoop(oneOff ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
  action.clampWhenFinished = oneOff;
  action.play();
  const prev = p.current ? p.actions[p.current] : null;
  if (prev) action.crossFadeFrom(prev, fade, false);
  p.current = next;
  return action;
}
