/** The skinned footballer of the 3D goal replay: the Mixamo model and clips
 * of the free-kick prototype (public/career-3d/footballer.glb, meshopt),
 * prepared for 22 players whose positions come from the key frames:
 * clips play in place (no root motion but the keeper's dive), a run cycle
 * is built from the idle pose on the same bones, and the one-off clips'
 * timing (kick contact, jump apex, dive reach) is read from the clips. */
import * as THREE from "three";
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

import { DEFAULT_TIMING, RUN_AT, type ClipName, type ClipTiming } from "@/lib/footballerMotion";

export const FOOTBALLER_URL = "/career-3d/footballer.glb";

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

function timingOf(clips: Record<string, THREE.AnimationClip>, up: number): ClipTiming {
  const timing = { ...DEFAULT_TIMING };
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

/** A run cycle on the model's own skeleton, from its idle pose: thighs,
 * knees, arms and elbows swing about axes worked out from the bones
 * themselves (the axis that turns the bone's child towards the body's
 * front), so no hand-tuned rig conventions. One stride pair per period at
 * RUN_AT m/s; the mixer's time scale follows the player's speed. */
function runClip(gltf: GLTF, idle: THREE.AnimationClip, up: number): THREE.AnimationClip {
  const model = cloneSkinned(gltf.scene);
  const mixer = new THREE.AnimationMixer(model);
  mixer.clipAction(idle).play();
  mixer.setTime(0);
  model.updateMatrixWorld(true);
  const bones = bonesOf(model);
  const front = new THREE.Vector3(0, 0, 1); // the model faces +z

  // Rest of the pose: every bone the idle clip moves, at its first frame.
  const base: Record<string, THREE.Quaternion> = {};
  for (const tr of idle.tracks) {
    if (!tr.name.endsWith(".quaternion")) continue;
    const name = tr.name.slice(0, -".quaternion".length);
    base[name] = new THREE.Quaternion(tr.values[0], tr.values[1], tr.values[2], tr.values[3]);
  }
  const axisOf = (bone: THREE.Bone, child: THREE.Bone): THREE.Vector3 => {
    const toLocal = bone.getWorldQuaternion(new THREE.Quaternion()).invert();
    const f = front.clone().applyQuaternion(toLocal);
    const d = child.position.clone().normalize();
    const axis = new THREE.Vector3().crossVectors(d, f);
    return axis.lengthSq() > 1e-8 ? axis.normalize() : new THREE.Vector3(1, 0, 0);
  };
  type Swing = (w: number) => number;
  const swings: [string, string, Swing][] = [
    ["RightUpLeg", "RightLeg", (w) => 0.62 * Math.sin(w)],
    ["LeftUpLeg", "LeftLeg", (w) => -0.62 * Math.sin(w)],
    ["RightLeg", "RightFoot", (w) => -(0.3 + 1.0 * Math.max(0, Math.cos(w)))],
    ["LeftLeg", "LeftFoot", (w) => -(0.3 + 1.0 * Math.max(0, -Math.cos(w)))],
    ["RightArm", "RightForeArm", (w) => -0.55 * Math.sin(w)],
    ["LeftArm", "LeftForeArm", (w) => 0.55 * Math.sin(w)],
    ["RightForeArm", "RightHand", (w) => 1.15 - 0.2 * Math.sin(w)],
    ["LeftForeArm", "LeftHand", (w) => 1.15 + 0.2 * Math.sin(w)],
    ["Spine", "Spine1", () => 0.14],
    ["Spine1", "Spine2", () => 0.05],
  ];
  const period = 0.68 * (7 / RUN_AT);
  const samples = 16;
  const times = Array.from({ length: samples + 1 }, (_, i) => (i / samples) * period);
  const tracks: THREE.KeyframeTrack[] = [];
  const moved = new Set<string>();
  for (const [boneName, childName, swing] of swings) {
    const bone = bones[boneName];
    const child = bones[childName];
    if (!bone || !child || !base[bone.name]) continue;
    const axis = axisOf(bone, child);
    const values: number[] = [];
    const q = new THREE.Quaternion();
    for (const time of times) {
      q.copy(base[bone.name]).multiply(new THREE.Quaternion().setFromAxisAngle(axis, swing((time / period) * Math.PI * 2)));
      values.push(q.x, q.y, q.z, q.w);
    }
    tracks.push(new THREE.QuaternionKeyframeTrack(`${bone.name}.quaternion`, times, values));
    moved.add(bone.name);
  }
  for (const [name, q] of Object.entries(base)) {
    if (moved.has(name)) continue;
    tracks.push(new THREE.QuaternionKeyframeTrack(`${name}.quaternion`, [0], [q.x, q.y, q.z, q.w]));
  }
  // Hips: over the origin, a little lower than standing, bobbing twice a cycle.
  const hips = idle.tracks.find((tr) => HIPS.test(tr.name));
  if (hips) {
    const h0 = hips.values[up];
    const values: number[] = [];
    for (const time of times) {
      const v = [0, 0, 0];
      v[up] = h0 * (0.95 + 0.025 * Math.abs(Math.sin((time / period) * Math.PI * 2)));
      values.push(...v);
    }
    tracks.push(new THREE.VectorKeyframeTrack(hips.name, times, values));
  }
  mixer.stopAllAction();
  return new THREE.AnimationClip("run", period, tracks);
}

export function prepareFootballer(gltf: GLTF): FootballerAsset {
  const byName: Record<string, THREE.AnimationClip> = {};
  for (const clip of gltf.animations) byName[clip.name] = clip;
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
    run: runClip(gltf, inPlace(byName.idle, up), up),
  } as Record<ClipName, THREE.AnimationClip>;
  const timing = timingOf(byName, up);
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
