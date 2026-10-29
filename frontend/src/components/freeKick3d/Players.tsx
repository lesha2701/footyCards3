/** Animated footballers (generated characters with the Mixamo "Soccer"
 * pack's clips, one meshopt GLB each — see characters.ts). Purely visual:
 * they follow the deterministic shot timeline, never drive it. */
import { useGLTF } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

import { KEEPER_LINE_Z, type ShotSetup } from "@/lib/freeKick3d/trajectory";

import { CHARACTERS, type Character } from "./characters";
import { KICK } from "./kickStyles";
import { KEEPER_LOOK, KICKER_LOOK, LOOKS, type Look } from "./looks";

export type Clip =
  | "idle"
  | "wall_jump"
  | "kick"
  | "gk_idle"
  | "gk_dive_left"
  | "gk_dive_right"
  | "gk_catch"
  | "gk_jump"
  | "gk_block_left"
  | "gk_block_right"
  | "gk_fallen"
  | "celebrate"
  | "silly_dance";

/** A goal celebration clip: the free one, or the «Смешной танец» bought
 * as a «Мой игрок» cosmetic (cel_silly). */
export type Celebration = "celebrate" | "silly_dance";

type KeeperClip = "gk_dive_left" | "gk_dive_right" | "gk_catch" | "gk_jump" | "gk_block_left" | "gk_block_right";

export type Kit = { shirt: string; shorts: string; socks: string };

export const KITS = {
  home: { shirt: "#2fbf71", shorts: "#f8fafc", socks: "#2fbf71" },
  away: { shirt: "#c0392b", shorts: "#f8fafc", socks: "#c0392b" },
  keeper: { shirt: "#facc15", shorts: "#111827", socks: "#facc15" },
} satisfies Record<string, Kit>;


/** Where the hips get to sideways in the dives (m) — the keeper's group is
 * nudged by the difference so the hands meet the computed save point. */
const DIVE_REACH: Record<KeeperClip, number> = {
  gk_dive_left: 2.56,
  gk_dive_right: 2.98,
  gk_catch: 0.3,
  gk_jump: 0,
  gk_block_left: 1.0,
  gk_block_right: 1.0,
};

/** A ball near him: a leap for a high one, down at the feet for a low one
 * off to a side, otherwise the chest catch; further out, the dive. The
 * keeper faces +z: his left is world +x. */
function keeperClip(dx: number, handY: number): KeeperClip {
  if (Math.abs(dx) >= 1.3) return dx > 0 ? "gk_dive_left" : "gk_dive_right";
  if (handY >= 1.7) return "gk_jump";
  if (handY <= 0.6 && Math.abs(dx) >= 0.35) return dx > 0 ? "gk_block_left" : "gk_block_right";
  return "gk_catch";
}

/** Where a skinned mesh's bind-pose vertex sits, as a fraction of the
 * body's height: the row of its matrix (relative to the model root) that
 * gives the height, and the height range. The vertices can be stored lying
 * down — the bones stand them up — so the matrix goes through the skin's
 * rest transform (the same for every bone in the bind pose). */
function heightFrame(scene: THREE.Object3D, mesh: THREE.SkinnedMesh) {
  scene.updateMatrixWorld(true);
  const rest = mesh.skeleton
    ? new THREE.Matrix4()
        .copy(mesh.bindMatrixInverse)
        .multiply(mesh.skeleton.bones[0].matrixWorld)
        .multiply(mesh.skeleton.boneInverses[0])
        .multiply(mesh.bindMatrix)
    : new THREE.Matrix4();
  const m = new THREE.Matrix4().copy(scene.matrixWorld).invert().multiply(mesh.matrixWorld).multiply(rest).elements;
  const row = new THREE.Vector4(m[1], m[5], m[9], m[13]);
  const pos = mesh.geometry.getAttribute("position");
  let lo = Infinity;
  let hi = -Infinity;
  for (let i = 0; i < pos.count; i++) {
    const y = row.x * pos.getX(i) + row.y * pos.getY(i) + row.z * pos.getZ(i) + row.w;
    lo = Math.min(lo, y);
    hi = Math.max(hi, y);
  }
  return { row, range: new THREE.Vector2(lo, hi) };
}

/** The model's white kit takes the team's colours — shirt, shorts and
 * socks by bind-pose height, keeping the fabric's shading — and the skin
 * and hair are multiplied by the look's colours. */
function tintMaterial(
  base: THREE.MeshStandardMaterial,
  frame: ReturnType<typeof heightFrame>,
  character: Character,
  kit: Kit,
  look: Look,
) {
  const mat = base.clone();
  const uniforms = {
    uKitRow: { value: frame.row },
    uKitRange: { value: frame.range },
    uBands: { value: new THREE.Vector3(character.socksTop, character.shirtHem, character.hairline) },
    uShirt: { value: new THREE.Color(kit.shirt) },
    uShorts: { value: new THREE.Color(kit.shorts) },
    uSocks: { value: new THREE.Color(kit.socks) },
    uSkin: { value: new THREE.Color(look.skin) },
    uHair: { value: new THREE.Color(look.hair) },
  };
  mat.customProgramCacheKey = () => "fk3d-kit";
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nuniform vec4 uKitRow;\nuniform vec2 uKitRange;\nvarying float vKitH;")
      .replace(
        "#include <begin_vertex>",
        "#include <begin_vertex>\nvKitH = (dot(uKitRow.xyz, position) + uKitRow.w - uKitRange.x) / (uKitRange.y - uKitRange.x);",
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        "#include <common>\nuniform vec3 uBands, uShirt, uShorts, uSocks, uSkin, uHair;\nvarying float vKitH;",
      )
      .replace(
        "#include <map_fragment>",
        `#include <map_fragment>
        {
          vec3 c = diffuseColor.rgb;
          float hi = max(c.r, max(c.g, c.b));
          float lo = min(c.r, min(c.g, c.b));
          float white = smoothstep(0.1, 0.2, lo) * (1.0 - smoothstep(0.12, 0.22, (hi - lo) / max(hi, 1e-3)));
          vec3 kit = vKitH < uBands.x ? uSocks : vKitH < uBands.y ? uShorts : uShirt;
          vec3 body = c * (vKitH > uBands.z ? uHair : uSkin);
          diffuseColor.rgb = mix(body, kit * min(1.0, hi / 0.65), white);
        }`,
      );
  };
  return mat;
}

/** One animated copy of a footballer in a kit: its own skeleton, mixer
 * and tinted material. */
function useFootballer(kit: Kit, look: Look, castShadow: boolean) {
  const character = CHARACTERS[look.character];
  const gltf = useGLTF(character.url);
  const frame = useMemo(() => {
    let mesh: THREE.SkinnedMesh | null = null;
    gltf.scene.traverse((o) => {
      if ((o as THREE.SkinnedMesh).isSkinnedMesh && !mesh) mesh = o as THREE.SkinnedMesh;
    });
    return heightFrame(gltf.scene, mesh!);
  }, [gltf.scene]);
  const model = useMemo(() => {
    const root = cloneSkinned(gltf.scene);
    root.scale.multiply(new THREE.Vector3(look.width, look.height, look.width));
    root.traverse((o) => {
      const mesh = o as THREE.SkinnedMesh;
      if (!mesh.isMesh) return;
      mesh.frustumCulled = false;
      mesh.castShadow = castShadow;
      mesh.material = tintMaterial(mesh.material as THREE.MeshStandardMaterial, frame, character, kit, look);
    });
    return root;
  }, [gltf.scene, frame, character, kit, look, castShadow]);
  const mixer = useMemo(() => new THREE.AnimationMixer(model), [model]);
  const actions = useMemo(() => {
    const out = {} as Record<Clip, THREE.AnimationAction>;
    for (const clip of gltf.animations) out[clip.name as Clip] = mixer.clipAction(clip);
    return out;
  }, [gltf.animations, mixer]);
  useEffect(() => () => void mixer.stopAllAction(), [mixer]);
  return { model, mixer, actions, clips: gltf.animations };
}

/** Cross-fades to `next` unless it's already the playing clip. */
function play(current: { clip: Clip | null }, actions: Record<Clip, THREE.AnimationAction>, next: Clip, opts: { once?: boolean; fade?: number; at?: number; speed?: number } = {}) {
  if (current.clip === next) return actions[next];
  const action = actions[next];
  action.reset();
  action.setLoop(opts.once ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
  action.clampWhenFinished = !!opts.once;
  action.timeScale = opts.speed ?? 1;
  if (opts.at !== undefined) action.time = opts.at;
  action.play();
  const prev = current.clip ? actions[current.clip] : null;
  if (prev) action.crossFadeFrom(prev, opts.fade ?? 0.15, false);
  current.clip = next;
  return action;
}

/** Shared per-frame inputs from the scene's shot clock. */
export type PlayerClock = { t: () => number; dt: () => number };

// ---------------------------------------------------------------------------

/** A wall player: idles, then jumps (the group height itself is the
 * deterministic `wallLift`, set by the parent). Faces the ball. */
export function WallPlayerModel({
  jumpAt,
  phase,
  look,
  clock,
  castShadow,
}: {
  jumpAt: number;
  phase: number;
  look: Look;
  clock: PlayerClock;
  castShadow: boolean;
}) {
  const { model, mixer, actions } = useFootballer(KITS.away, look, castShadow);
  const state = useRef<{ clip: Clip | null }>({ clip: null });
  useEffect(() => {
    play(state.current, actions, "idle", { at: phase });
  }, [actions, phase]);
  useFrame(() => {
    const t = clock.t();
    if (t >= jumpAt - 0.25 && t < jumpAt + 1.4) play(state.current, actions, "wall_jump", { once: true, at: 0.35, speed: 1.3 });
    else if (t < 0 || t >= jumpAt + 1.4) play(state.current, actions, "idle", { at: phase, fade: 0.3 });
    mixer.update(clock.dt());
  });
  // Model's origin is between the feet; the parent places it at body centre.
  return <primitive object={model} />;
}

/** The keeper: ready stance; at the (seeded) reaction time he goes for the
 * point the trajectory says his hands go to — a dive to the side, or a
 * catch, leap or block when it's close — timed to arrive with the ball. */
export function KeeperModel({
  setup,
  targetX,
  targetY,
  arrival,
  saved,
  clock,
  castShadow,
}: {
  setup: ShotSetup;
  /** Where the hands end up (from the trajectory), null while waiting. */
  targetX: number | null;
  targetY: number;
  /** Shot time when the ball reaches the keeper's line. */
  arrival: number;
  /** He gets to it: the dive holds at full stretch (instead of carrying
   * him on past the ball), then he goes down where he is. */
  saved: boolean;
  clock: PlayerClock;
  castShadow: boolean;
}) {
  const { model, mixer, actions, clips } = useFootballer(KITS.keeper, KEEPER_LOOK, castShadow);
  const group = useRef<THREE.Group>(null);
  const state = useRef<{ clip: Clip | null }>({ clip: null });
  // Per clip: when the hips start moving sideways (the dives open with
  // half a second of swaying — skipped) and when they're at 85 % of their
  // widest, which is when the arms are out at the ball (the widest point
  // itself is him already lying on the grass). The leap goes by height.
  const timing = useMemo(() => {
    const out: Partial<Record<Clip, { start: number; reach: number }>> = {};
    for (const clip of clips) {
      const track = clip.tracks.find((tr) => tr.name.endsWith("Hips.position"));
      if (!track) continue;
      const axis = clip.name === "gk_jump" ? 1 : 0;
      const first = track.values[axis];
      const dx = (i: number) => Math.abs(track.values[i * 3 + axis] - first);
      let best = 0;
      for (let i = 0; i < track.times.length; i++) best = Math.max(best, dx(i));
      let start = 0;
      let reach = clip.duration;
      for (let i = track.times.length - 1; i >= 0; i--) {
        if (dx(i) >= best * 0.85) reach = track.times[i];
        if (dx(i) >= best * 0.12) start = track.times[i];
      }
      out[clip.name as Clip] = { start: Math.min(start, reach), reach };
    }
    return out;
  }, [clips]);

  useEffect(() => {
    play(state.current, actions, "gk_idle");
  }, [actions, setup]);

  useFrame(() => {
    const t = clock.t();
    const g = group.current;
    if (!g) return;
    // A dive that would only start as the ball arrives isn't played: he'd be
    // flying about after the goal. He's beaten where he stands. (A catch is
    // short enough to still play.)
    const close = targetX !== null && Math.abs(targetX - setup.keeper.x) < 1.3;
    const tooLate = arrival - setup.keeper.reaction < (close ? 0.08 : 0.2);
    if (targetX === null || tooLate || t < setup.keeper.reaction) {
      if (t < 0) play(state.current, actions, "gk_idle", { fade: 0.3 });
      g.position.x = setup.keeper.x;
    } else {
      const dx = targetX - setup.keeper.x;
      const clip = keeperClip(dx, targetY);
      const { start, reach } = timing[clip] ?? { start: 0, reach: 1 };
      // Arms out exactly when the ball gets there.
      const window = Math.max(0.15, arrival - setup.keeper.reaction);
      const speed = THREE.MathUtils.clamp((reach - start) / window, 0.7, 4.5);
      const action = play(state.current, actions, clip, { once: true, speed, fade: 0.06, at: start });
      // Sped up to reach the ball in time; past the reach the clip plays at
      // its own pace — the landing and getting back up aren't hurried. The
      // ball's in his hands: hold the stretch a moment first.
      if (action.time >= reach) action.timeScale = saved && clip !== "gk_catch" && t < arrival + 0.3 ? 0 : 1;
      // Nudge the body so the hands meet the computed point at the reach.
      const progress = THREE.MathUtils.clamp((action.time - start) / (reach - start || 1), 0, 1);
      // Bounded: a bigger correction would read as sliding, not diving.
      const extra = THREE.MathUtils.clamp(Math.abs(dx) - DIVE_REACH[clip], -1.2, 1.2) * Math.sign(dx || 1);
      g.position.x = setup.keeper.x + extra * THREE.MathUtils.smoothstep(progress, 0, 1);
      // The dive ends with him on the grass and stays there (the clip clamps
      // on its last frame) — no second fall from a standing start.
    }
    mixer.update(clock.dt());
  });

  return (
    <group ref={group} position={[setup.keeper.x, 0, KEEPER_LINE_Z]}>
      <primitive object={model} />
    </group>
  );
}

/** Where the celebration picks up: the arms go up about a second in. */
const CELEBRATE_FROM = 1.0;
const CELEBRATE_FADE = 0.4;

/** The kicker: waits at his run-up mark, runs in on the swipe; the ball
 * leaves at the clip's contact frame (shot time 0). After a goal he
 * celebrates where the run-up left him. */
export function KickerModel({
  setup,
  clock,
  kicking,
  celebrateAt,
  celebration = "celebrate",
  kit = "home",
  castShadow,
}: {
  setup: ShotSetup;
  clock: PlayerClock;
  kicking: boolean;
  /** Shot time to start celebrating at — null when it's no goal. */
  celebrateAt: number | null;
  celebration?: Celebration;
  kit?: "home" | "away";
  castShadow: boolean;
}) {
  const look = kit === "away" ? LOOKS[3] : KICKER_LOOK;
  const { model, mixer, actions, clips } = useFootballer(kit === "away" ? KITS.away : KITS.home, look, castShadow);
  const group = useRef<THREE.Group>(null);
  // The kick ends a couple of metres on from where the celebration clip
  // starts: the hips' gap (in the hips' parent space), made up by moving
  // the model as the celebration fades in.
  const gap = useMemo(() => {
    const hips = (name: Clip) =>
      clips.find((c) => c.name === name)?.tracks.find((tr) => tr.name.endsWith("Hips.position"))?.values;
    const kick = hips("kick");
    const party = hips(celebration);
    if (!kick || !party) return null;
    const n = kick.length;
    return new THREE.Vector3(kick[n - 3] - party[0], kick[n - 2] - party[1], kick[n - 1] - party[2]);
  }, [clips, celebration]);
  const gapLocal = useRef<THREE.Vector3 | null>(null);
  useEffect(() => {
    gapLocal.current = null;
  }, [gap]);
  const placement = useMemo(() => {
    const len = Math.hypot(setup.ball.x, setup.ball.z);
    const yaw = Math.atan2(-setup.ball.x / len, -setup.ball.z / len);
    // Origin such that the toe (plus half a ball ahead) is at the ball at contact.
    const toe = CHARACTERS[look.character].toe.clone().add(new THREE.Vector3(0, 0, 0.12)).applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
    return { yaw, x: setup.ball.x - toe.x, z: setup.ball.z - toe.z };
  }, [setup, look]);

  useEffect(() => {
    const action = actions.kick;
    action.reset();
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.play();
  }, [actions, setup]);

  useFrame(() => {
    const action = actions.kick;
    const t = clock.t();
    // Locked to the shot clock (slow motion included); frame 0 while waiting.
    action.time = kicking ? THREE.MathUtils.clamp(KICK.contact + t, 0, action.getClip().duration) : 0;
    const party = actions[celebration];
    const w = party && kicking && celebrateAt !== null ? THREE.MathUtils.clamp((t - celebrateAt) / CELEBRATE_FADE, 0, 1) : 0;
    if (party) {
      if (w > 0 && !party.isRunning()) {
        party.reset();
        party.setLoop(THREE.LoopOnce, 1);
        party.clampWhenFinished = true;
        party.play();
      } else if (w === 0 && party.isRunning()) party.stop();
      // The victory clip opens with a second of standing; the dance loops.
      const into = t - (celebrateAt ?? 0);
      const length = party.getClip().duration;
      party.time = celebration === "silly_dance" ? into % length : THREE.MathUtils.clamp(CELEBRATE_FROM + into, 0, length);
      party.setEffectiveWeight(w);
      action.setEffectiveWeight(1 - w);
    }
    const g = group.current;
    if (g && gap) {
      if (!gapLocal.current) {
        const hips = model.getObjectByProperty("type", "Bone");
        if (hips?.parent) {
          g.updateMatrixWorld(true);
          const m = new THREE.Matrix4().copy(g.matrixWorld).invert().multiply(hips.parent.matrixWorld);
          gapLocal.current = gap.clone().applyMatrix3(new THREE.Matrix3().setFromMatrix4(m));
        }
      }
      if (gapLocal.current) model.position.set(gapLocal.current.x * w, 0, gapLocal.current.z * w);
    }
    mixer.update(0);
  });

  return (
    <group ref={group} position={[placement.x, 0, placement.z]} rotation-y={placement.yaw}>
      <primitive object={model} />
    </group>
  );
}

for (const c of Object.values(CHARACTERS)) useGLTF.preload(c.url);
