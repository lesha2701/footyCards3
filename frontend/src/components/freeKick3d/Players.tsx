/** Animated footballers (Mixamo "Soccer" pack, rebuilt into one meshopt
 * GLB with 8 clips — see public/free-kick-3d/footballer.glb). Purely
 * visual: they follow the deterministic shot timeline, never drive it. */
import { useGLTF } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

import { KEEPER_LINE_Z, type ShotSetup } from "@/lib/freeKick3d/trajectory";

import { KICK } from "./kickStyles";
import { KEEPER_LOOK, KICKER_LOOK, LOOKS, type Look } from "./looks";

export const FOOTBALLER_URL = "/free-kick-3d/footballer.glb";

export type Clip = "idle" | "wall_jump" | "kick" | "gk_idle" | "gk_dive_left" | "gk_dive_right" | "gk_catch" | "gk_fallen";

export type Kit = { shirt: string; shorts: string; socks: string };

export const KITS = {
  home: { shirt: "#2fbf71", shorts: "#f8fafc", socks: "#2fbf71" },
  away: { shirt: "#c0392b", shorts: "#f8fafc", socks: "#c0392b" },
  keeper: { shirt: "#facc15", shorts: "#111827", socks: "#facc15" },
} satisfies Record<string, Kit>;


/** Where the hips get to sideways in the dives (m) — the keeper's group is
 * nudged by the difference so the hands meet the computed save point. */
const DIVE_REACH: Record<"gk_dive_left" | "gk_dive_right" | "gk_catch", number> = {
  gk_dive_left: 2.56,
  gk_dive_right: 2.98,
  gk_catch: 0.3,
};

/** One animated copy of the footballer in a kit: its own skeleton, mixer
 * and tinted materials (the model's kit is white, so tinting = recolouring). */
function useFootballer(kit: Kit, look: Look, castShadow: boolean) {
  const gltf = useGLTF(FOOTBALLER_URL);
  const model = useMemo(() => {
    const root = cloneSkinned(gltf.scene);
    root.scale.multiply(new THREE.Vector3(look.width, look.height, look.width));
    root.traverse((o) => {
      const mesh = o as THREE.SkinnedMesh;
      if (!mesh.isMesh) return;
      mesh.frustumCulled = false;
      mesh.castShadow = castShadow;
      if (/Hair/i.test(mesh.name) && look.hair === null) mesh.visible = false;
      const tint = /Shirt/i.test(mesh.name)
        ? kit.shirt
        : /Shorts/i.test(mesh.name)
          ? kit.shorts
          : /Socks/i.test(mesh.name)
            ? kit.socks
            : /Body/i.test(mesh.name)
              ? look.skin
              : /Hair/i.test(mesh.name)
                ? look.hair
                : null;
      if (tint) {
        const mat = (mesh.material as THREE.MeshStandardMaterial).clone();
        mat.color.set(tint);
        mesh.material = mat;
      }
    });
    return root;
  }, [gltf.scene, kit, look, castShadow]);
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
 * catch when it's close — timed to arrive with the ball. */
export function KeeperModel({
  setup,
  targetX,
  arrival,
  saved,
  clock,
  castShadow,
}: {
  setup: ShotSetup;
  /** Where the hands end up (from the trajectory), null while waiting. */
  targetX: number | null;
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
  // itself is him already lying on the grass).
  const timing = useMemo(() => {
    const out: Partial<Record<Clip, { start: number; reach: number }>> = {};
    for (const clip of clips) {
      const track = clip.tracks.find((tr) => tr.name.endsWith("Hips.position"));
      if (!track) continue;
      const first = track.values[0];
      const dx = (i: number) => Math.abs(track.values[i * 3] - first);
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
    // flying about after the goal. He's beaten where he stands.
    const tooLate = arrival - setup.keeper.reaction < 0.2;
    if (targetX === null || tooLate || t < setup.keeper.reaction) {
      if (t < 0) play(state.current, actions, "gk_idle", { fade: 0.3 });
      g.position.x = setup.keeper.x;
    } else {
      const dx = targetX - setup.keeper.x;
      // The keeper faces +z: his left is world +x.
      const clip: keyof typeof DIVE_REACH = Math.abs(dx) < 1.3 ? "gk_catch" : dx > 0 ? "gk_dive_left" : "gk_dive_right";
      const { start, reach } = timing[clip] ?? { start: 0, reach: 1 };
      // Arms out exactly when the ball gets there.
      const window = Math.max(0.15, arrival - setup.keeper.reaction);
      const speed = THREE.MathUtils.clamp((reach - start) / window, 0.7, 4.5);
      const action = play(state.current, actions, clip, { once: true, speed, fade: 0.06, at: start });
      if (saved && clip !== "gk_catch") {
        // The ball's in his hands: hold the stretch a moment, then the dive
        // plays out to its landing.
        action.timeScale = action.time >= reach && t < arrival + 0.3 ? 0 : 1;
      }
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

/** The kicker: waits at his run-up mark, runs in on the swipe; the ball
 * leaves at the clip's contact frame (shot time 0). */
export function KickerModel({
  setup,
  clock,
  kicking,
  kit = "home",
  castShadow,
}: {
  setup: ShotSetup;
  clock: PlayerClock;
  kicking: boolean;
  kit?: "home" | "away";
  castShadow: boolean;
}) {
  const { model, mixer, actions } = useFootballer(kit === "away" ? KITS.away : KITS.home, kit === "away" ? LOOKS[3] : KICKER_LOOK, castShadow);
  const placement = useMemo(() => {
    const len = Math.hypot(setup.ball.x, setup.ball.z);
    const yaw = Math.atan2(-setup.ball.x / len, -setup.ball.z / len);
    // Origin such that the toe (plus half a ball ahead) is at the ball at contact.
    const toe = KICK.toe.clone().add(new THREE.Vector3(0, 0, 0.12)).applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
    return { yaw, x: setup.ball.x - toe.x, z: setup.ball.z - toe.z };
  }, [setup]);

  useEffect(() => {
    const action = actions.kick;
    action.reset();
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.play();
  }, [actions, setup]);

  useFrame(() => {
    const action = actions.kick;
    // Locked to the shot clock (slow motion included); frame 0 while waiting.
    action.time = kicking ? THREE.MathUtils.clamp(KICK.contact + clock.t(), 0, action.getClip().duration) : 0;
    mixer.update(0);
  });

  return (
    <group position={[placement.x, 0, placement.z]} rotation-y={placement.yaw}>
      <primitive object={model} />
    </group>
  );
}

useGLTF.preload(FOOTBALLER_URL);
