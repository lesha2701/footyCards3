/** The extra moves of «Атака 1 на 1» on the career footballer's rig
 * (public/one-on-one-3d/moves.glb, tools/one-on-one-3d/build_moves.py):
 * strikes with either foot, a chip, sidesteps for the feint, goal
 * celebrations, and the keeper's set stance, scoop, catches, body blocks,
 * beaten and getting-up (the power strikes, the side-foot, the
 * celebrations and the stance are mocap — Anderson Rohr's soccer pack). Their timing (when the foot meets the ball, where the toe is
 * then, when the keeper's hands reach the ground) is read off the clips. */
import * as THREE from "three";
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

import { HIPS, bonesOf, inPlace, setClip, upAxis, type SkinnedPlayer } from "@/components/career/goal3d/footballer";
import type { ClipName } from "@/lib/footballerMotion";
import type { Foot, ShotKind } from "@/lib/oneOnOne/technique";

export const ONE_ON_ONE_MOVES_URL = "/one-on-one-3d/moves.glb";

const STRIKES = ["shot_r", "shot_l", "power_r", "power_l", "pass_r", "pass_l", "chip_r", "chip_l"] as const;
const OTHERS = [
  "strafe_l", "strafe_r", "trip", "cheer_knees", "cheer_arms", "cheer_leap", "gk_set",
  "gk_scoop", "gk_catch_high", "gk_catch_low", "gk_block_l", "gk_block_r", "gk_miss", "gk_getup",
] as const;
export type Strike = (typeof STRIKES)[number];
export type Move = Strike | (typeof OTHERS)[number];

export type StrikeTiming = {
  /** When the foot meets the ball (s into the clip). */
  contact: number;
  /** The striking toe then, in the model's own frame on the ground (it
   * faces +z): where the ball must be. */
  toe: { x: number; z: number };
  /** When the other foot comes down beside the ball and stays (s into the
   * clip), and where it is at the contact (the model's frame): from then
   * to the contact it is planted — it must not slide. */
  plant: number;
  plantAt: { x: number; z: number };
};

/** The striking toe meets the ball below this (m; the ball is 0.22 high). */
const CONTACT_HEIGHT = 0.2;
/** The plant foot has come down when within this of its lowest (m). */
const PLANT_DOWN = 0.02;
/** The plant is looked for this long before the contact (s). */
const PLANT_WINDOW = 0.5;

export type Moves = {
  clips: Record<Move, THREE.AnimationClip>;
  strikes: Record<Strike, StrikeTiming>;
  /** When the keeper's hands are lowest in the scoop: the ball is his. */
  scoopPickup: number;
};

const SAMPLE = 1 / 60;

/** Samples a posed copy of the model through a clip. */
function sample(gltf: GLTF, clip: THREE.AnimationClip, read: (bones: Record<string, THREE.Bone>, t: number) => void) {
  const model = cloneSkinned(gltf.scene);
  const mixer = new THREE.AnimationMixer(model);
  // Once, held at the end: looped, its last sample would jump back to the
  // first (the fastest "move" of all).
  const action = mixer.clipAction(clip);
  action.setLoop(THREE.LoopOnce, 1);
  action.clampWhenFinished = true;
  action.play();
  const bones = bonesOf(model);
  for (let t = 0; t <= clip.duration + 1e-6; t += SAMPLE) {
    mixer.setTime(t);
    model.updateMatrixWorld(true);
    read(bones, t);
  }
  mixer.stopAllAction();
}

/** The contact is when the striking toe moves fastest low over the grass
 * (through the ball, not up in the follow-through); the plant, the
 * other foot coming down to its lowest before it (the toe: the heel lifts
 * as he goes over it). */
function strikeTiming(gltf: GLTF, clip: THREE.AnimationClip, foot: Foot): StrikeTiming {
  const name = foot === "left" ? "LeftToeBase" : "RightToeBase";
  const other = foot === "left" ? "RightToeBase" : "LeftToeBase";
  const prev = new THREE.Vector3();
  const p = new THREE.Vector3();
  const q = new THREE.Vector3();
  let best = -1;
  let contact = clip.duration / 2;
  let toe = { x: foot === "left" ? 0.15 : -0.15, z: 0.45 };
  const plantFoot: { t: number; x: number; y: number; z: number }[] = [];
  sample(gltf, clip, (bones, t) => {
    const b = bones[name];
    if (!b) return;
    b.getWorldPosition(p);
    if (t > 0 && p.y < CONTACT_HEIGHT) {
      const speed = p.distanceTo(prev);
      if (speed > best) {
        best = speed;
        contact = t;
        toe = { x: p.x, z: p.z };
      }
    }
    prev.copy(p);
    if (bones[other]) {
      bones[other].getWorldPosition(q);
      plantFoot.push({ t, x: q.x, y: q.y, z: q.z });
    }
  });
  const window = plantFoot.filter((f) => f.t >= contact - PLANT_WINDOW && f.t <= contact + 1e-6);
  const at = window[window.length - 1];
  if (!at) return { contact, toe, plant: contact, plantAt: { x: -toe.x, z: toe.z - 0.2 } };
  // Down at its lowest; it came down when it first got that low.
  let lowest = 0;
  for (let i = 1; i < window.length; i++) if (window[i].y < window[lowest].y) lowest = i;
  let plant = window[lowest].t;
  for (let i = lowest; i >= 0 && window[i].y < window[lowest].y + PLANT_DOWN; i--) plant = window[i].t;
  return { contact, toe, plant, plantAt: { x: at.x, z: at.z } };
}

function lowestHands(gltf: GLTF, clip: THREE.AnimationClip): number {
  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  let low = Infinity;
  let at = clip.duration / 2;
  sample(gltf, clip, (bones, t) => {
    if (!bones.LeftHand || !bones.RightHand) return;
    const y = (bones.LeftHand.getWorldPosition(a).y + bones.RightHand.getWorldPosition(b).y) / 2;
    if (y < low) {
      low = y;
      at = t;
    }
  });
  return at;
}

export function prepareMoves(model: GLTF, moves: GLTF): Moves {
  const byName: Record<string, THREE.AnimationClip> = {};
  for (const clip of moves.animations) byName[clip.name] = clip;
  // The up axis from a clip that stands still (the strikes run forward
  // further than the hips are high).
  const hips = model.animations.find((c) => c.name === "idle")?.tracks.find((tr) => HIPS.test(tr.name));
  const up = hips ? upAxis(hips) : 1;
  const clips = {} as Record<Move, THREE.AnimationClip>;
  for (const name of [...STRIKES, ...OTHERS]) {
    const src = byName[name];
    if (src) clips[name] = inPlace(src, up);
  }
  const strikes = {} as Record<Strike, StrikeTiming>;
  for (const name of STRIKES) {
    if (clips[name]) strikes[name] = strikeTiming(model, clips[name], name.endsWith("_l") ? "left" : "right");
  }
  return { clips, strikes, scoopPickup: clips.gk_scoop ? lowestHands(model, clips.gk_scoop) : 0.8 };
}

/** Puts the moves on a player's mixer next to its own clips. */
export function addMoves(p: SkinnedPlayer, moves: Moves) {
  const actions = p.actions as Record<string, THREE.AnimationAction>;
  for (const [name, clip] of Object.entries(moves.clips)) actions[name] = p.mixer.clipAction(clip);
}

/** setClip for the player's own clips and the moves alike. */
export function play(p: SkinnedPlayer, name: ClipName | Move, oneOff: boolean, fade = 0.15): THREE.AnimationAction {
  return setClip(p, (p.actions[name as ClipName] ? name : "idle") as ClipName, oneOff, fade);
}

/** His goal celebrations: one of them per attack (by its seed). */
export const CELEBRATIONS = ["celebrate", "cheer_knees", "cheer_arms", "cheer_leap"] as const;

/** The strike that shows a technique, and how it is played. */
export type StrikePlan = {
  clip: Strike;
  /** How long before the ball leaves the clip starts (s, at timeScale). */
  lead: number;
  timeScale: number;
  /** The body turned off the line of the shot (rad, + to his left): the
   * inside of the foot opens the hips, the outside closes them. */
  yaw: number;
  /** Leaning back (rad): a chip gets under the ball. */
  lean: number;
};

export function strikePlan(kind: ShotKind, foot: Foot): StrikePlan {
  const side = foot === "right" ? 1 : -1;
  const f = foot === "right" ? "r" : "l";
  switch (kind) {
    case "instep":
      return { clip: `shot_${f}`, lead: 0.3, timeScale: 1.15, yaw: 0, lean: 0 };
    case "power":
      // The full swing: the last stride, the plant and the whole leg through it.
      return { clip: `power_${f}`, lead: 0.42, timeScale: 1.1, yaw: 0, lean: 0.02 };
    case "curl":
      // Wrapped round with the inside: the side-foot, the body opened more.
      return { clip: `pass_${f}`, lead: 0.3, timeScale: 0.9, yaw: -0.65 * side, lean: 0.04 };
    case "outside":
      return { clip: `shot_${f}`, lead: 0.26, timeScale: 1.2, yaw: 0.35 * side, lean: 0 };
    case "side":
      return { clip: `pass_${f}`, lead: 0.26, timeScale: 1, yaw: -0.5 * side, lean: 0 };
    case "chip":
      return { clip: `chip_${f}`, lead: 0.3, timeScale: 1.1, yaw: 0, lean: 0.12 };
    case "toe":
      return { clip: `pass_${f}`, lead: 0.1, timeScale: 1.5, yaw: 0, lean: -0.06 };
  }
}
