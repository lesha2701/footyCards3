/** Animated footballers (Mixamo "Soccer" pack, rebuilt into one meshopt
 * GLB with 8 clips — see public/free-kick-3d/footballer.glb). Purely
 * visual: they follow the deterministic shot timeline, never drive it. */
import { useGLTF } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

import { KEEPER_LINE_Z, type ShotSetup } from "@/lib/freeKick3d/trajectory";

export const FOOTBALLER_URL = "/free-kick-3d/footballer.glb";

export type Clip = "idle" | "wall_jump" | "kick" | "gk_idle" | "gk_dive_left" | "gk_dive_right" | "gk_catch" | "gk_fallen";

export type Kit = { shirt: string; shorts: string; socks: string };

export const KITS = {
  home: { shirt: "#2fbf71", shorts: "#f8fafc", socks: "#2fbf71" },
  away: { shirt: "#c0392b", shorts: "#f8fafc", socks: "#c0392b" },
  keeper: { shirt: "#facc15", shorts: "#111827", socks: "#facc15" },
} satisfies Record<string, Kit>;

/** In `kick`, the frame the right foot meets the ball (30 fps) and where
 * the toe is then, in the character's own frame (it faces +z, +x is its
 * left). Measured in Blender when the GLB was built. */
export const KICK_CONTACT_T = 22 / 30;
const KICK_TOE = new THREE.Vector3(-1.0, 0, 2.14);

/** Where the hips get to sideways in the dives (m) — the keeper's group is
 * nudged by the difference so the hands meet the computed save point. */
const DIVE_REACH: Record<"gk_dive_left" | "gk_dive_right" | "gk_catch", number> = {
  gk_dive_left: 2.56,
  gk_dive_right: 2.98,
  gk_catch: 0.3,
};

/** One animated copy of the footballer in a kit: its own skeleton, mixer
 * and tinted materials (the model's kit is white, so tinting = recolouring). */
function useFootballer(kit: Kit, castShadow: boolean) {
  const gltf = useGLTF(FOOTBALLER_URL);
  const model = useMemo(() => {
    const root = cloneSkinned(gltf.scene);
    root.traverse((o) => {
      const mesh = o as THREE.SkinnedMesh;
      if (!mesh.isMesh) return;
      mesh.frustumCulled = false;
      mesh.castShadow = castShadow;
      const tint = /Shirt/i.test(mesh.name) ? kit.shirt : /Shorts/i.test(mesh.name) ? kit.shorts : /Socks/i.test(mesh.name) ? kit.socks : null;
      if (tint) {
        const mat = (mesh.material as THREE.MeshStandardMaterial).clone();
        mat.color.set(tint);
        mesh.material = mat;
      }
    });
    return root;
  }, [gltf.scene, kit, castShadow]);
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
export function WallPlayerModel({ jumpAt, phase, clock, castShadow }: { jumpAt: number; phase: number; clock: PlayerClock; castShadow: boolean }) {
  const { model, mixer, actions } = useFootballer(KITS.away, castShadow);
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
 * catch when it's close — timed to arrive with the ball. */
export function KeeperModel({
  setup,
  targetX,
  arrival,
  clock,
  castShadow,
}: {
  setup: ShotSetup;
  /** Where the hands end up (from the trajectory), null while waiting. */
  targetX: number | null;
  /** Shot time when the ball reaches the keeper's line. */
  arrival: number;
  clock: PlayerClock;
  castShadow: boolean;
}) {
  const { model, mixer, actions, clips } = useFootballer(KITS.keeper, castShadow);
  const group = useRef<THREE.Group>(null);
  const state = useRef<{ clip: Clip | null }>({ clip: null });
  // Time of the widest point of each dive (hips furthest sideways).
  const peaks = useMemo(() => {
    const out: Partial<Record<Clip, number>> = {};
    for (const clip of clips) {
      const track = clip.tracks.find((tr) => tr.name.endsWith("Hips.position"));
      if (!track) continue;
      let best = 0;
      let at = 0;
      const first = track.values[0];
      for (let i = 0; i < track.times.length; i++) {
        const dx = Math.abs(track.values[i * 3] - first);
        if (dx > best) {
          best = dx;
          at = track.times[i];
        }
      }
      out[clip.name as Clip] = at;
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
    if (targetX === null || t < setup.keeper.reaction) {
      if (t < 0) play(state.current, actions, "gk_idle", { fade: 0.3 });
      g.position.x = setup.keeper.x;
    } else {
      const dx = targetX - setup.keeper.x;
      // The keeper faces +z: his left is world +x.
      const clip: keyof typeof DIVE_REACH = Math.abs(dx) < 0.7 ? "gk_catch" : dx > 0 ? "gk_dive_left" : "gk_dive_right";
      const peak = peaks[clip] ?? 1;
      const window = Math.max(0.2, arrival - setup.keeper.reaction);
      const speed = THREE.MathUtils.clamp(peak / window, 0.8, 3.5);
      const action = play(state.current, actions, clip, { once: true, speed, fade: 0.08 });
      // Nudge the body so the hands meet the computed point at the peak.
      const progress = THREE.MathUtils.clamp(action.time / peak, 0, 1);
      const extra = (Math.abs(dx) - DIVE_REACH[clip]) * Math.sign(dx || 1);
      g.position.x = setup.keeper.x + extra * THREE.MathUtils.smoothstep(progress, 0, 1);
      if (clip !== "gk_catch" && action.time >= action.getClip().duration - 0.05) {
        play(state.current, actions, "gk_fallen", { fade: 0.4 });
      }
    }
    mixer.update(clock.dt());
  });

  return (
    <group ref={group} position={[setup.keeper.x, 0, KEEPER_LINE_Z]}>
      <primitive object={model} />
    </group>
  );
}

/** The kicker: waits beside the ball, then runs in on the swipe; the ball
 * leaves at the clip's contact frame (shot time 0). */
export function KickerModel({ setup, clock, kicking, castShadow }: { setup: ShotSetup; clock: PlayerClock; kicking: boolean; castShadow: boolean }) {
  const { model, mixer, actions } = useFootballer(KITS.home, castShadow);
  const state = useRef<{ clip: Clip | null }>({ clip: null });
  const placement = useMemo(() => {
    const len = Math.hypot(setup.ball.x, setup.ball.z);
    const yaw = Math.atan2(-setup.ball.x / len, -setup.ball.z / len);
    // Origin such that the toe (plus half a ball ahead) is at the ball at contact.
    const toe = KICK_TOE.clone().add(new THREE.Vector3(0, 0, 0.12)).applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
    return { yaw, x: setup.ball.x - toe.x, z: setup.ball.z - toe.z };
  }, [setup]);

  useEffect(() => {
    state.current.clip = null;
    play(state.current, actions, "kick", { once: true, at: 0, speed: 0 });
  }, [actions, setup]);

  useFrame(() => {
    if (kicking) {
      const action = actions.kick;
      action.timeScale = 1;
      // Keep the clip locked to the shot clock (slow motion included).
      action.time = Math.min(action.getClip().duration, KICK_CONTACT_T + clock.t());
      mixer.update(0);
    } else {
      actions.kick.time = 0;
      mixer.update(0);
    }
  });

  return (
    <group position={[placement.x, 0, placement.z]} rotation-y={placement.yaw}>
      <primitive object={model} />
    </group>
  );
}

useGLTF.preload(FOOTBALLER_URL);
