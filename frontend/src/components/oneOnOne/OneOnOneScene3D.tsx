/** «Атака 1 на 1» in 3D. The free kick's stadium, goal, lights, ball and
 * crowd; the footballers are the career replay's skinned model (it has the
 * run and the sprint). The scene steps the pure episode engine at its fixed
 * 60 Hz from the finger (`input`) through the recorder — so what is shown is
 * exactly what the server will replay — and then plays the shot's flight.
 * Everything else here is presentation and never feeds back. */
import { Environment, Lightformer, PerformanceMonitor, Trail } from "@react-three/drei";
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { Suspense, useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";

import {
  FOOTBALLER_URL,
  MOVES_URL,
  MaterialCache,
  makePlayer,
  prepareFootballer,
  type FootballerAsset,
  type SkinnedPlayer,
} from "@/components/career/goal3d/footballer";
import Confetti from "@/components/freeKick3d/Confetti";
import { FpsMeter, GoalFrame, Lights } from "@/components/freeKick3d/FreeKickScene3D";
import { Stadium, type Quality } from "@/components/freeKick3d/Stadium";
import { ballGeometry } from "@/components/freeKick3d/textures";
import { aftermathAt, simulateAftermath } from "@/lib/freeKick3d/aftermath";
import { NET_DEPTH, netImpact } from "@/lib/freeKick3d/fx";
import { playFreeKickSfx } from "@/lib/freeKick3d/sfx";
import { BALL_RADIUS, createPenaltySetup, type QuantizedSwipe, type ShotTrajectory } from "@/lib/freeKick3d/trajectory";
import { ballSkin } from "@/lib/gameGear";
import { keeperTake, techniqueOf, type KeeperTake, type Technique } from "@/lib/oneOnOne/technique";
import {
  BALL_LEAD,
  FEINT_TICKS,
  KEEPER_START_Z,
  TICK,
  flightAt,
  type EpisodeEnd,
  type EpisodeSetup,
  type EpisodeState,
  type KeeperMode,
  type ShotFlight,
} from "@/lib/oneOnOne/engine";
import type { EpisodeRecorder } from "@/lib/oneOnOne/recorder";

import { ONE_ON_ONE_MOVES_URL, addMoves, play, prepareMoves, strikePlan, type Moves, type StrikePlan } from "./moves";

/** What the finger does right now (the page writes it, the scene reads it
 * every tick). `feint` is consumed by the tick that takes it. */
export type LiveInput = { live: boolean; hold: boolean; steer: number; feint: number; shot: QuantizedSwipe | null };

/** Slow motion for the last moments of a shot that's a goal or a save. */
const SLOWMO_WINDOW = 0.25;
const SLOWMO_SCALE = 0.35;

type Props = {
  setup: EpisodeSetup;
  recorder: EpisodeRecorder;
  input: MutableRefObject<LiveInput>;
  /** The engine ended the episode (on the tick: the timeline is complete). */
  onEnded: (end: EpisodeEnd) => void;
  /** The outcome is on screen (the ball in, saved, the ball taken). */
  onDecided: () => void;
  onReady: () => void;
  fpsRef: MutableRefObject<HTMLSpanElement | null>;
  ball?: string | null;
};

type Snap = Pick<EpisodeState, "x" | "z" | "hx" | "hz" | "speed" | "kx" | "kz" | "kMode" | "feintTicks" | "feintDir" | "lungeDir">;

const snap = (s: EpisodeState): Snap => ({
  x: s.x, z: s.z, hx: s.hx, hz: s.hz, speed: s.speed, kx: s.kx, kz: s.kz,
  kMode: s.kMode, feintTicks: s.feintTicks, feintDir: s.feintDir, lungeDir: s.lungeDir,
});

/** Shared per frame between the parts of the scene. */
type Stage = {
  acc: number;
  prev: Snap;
  cur: Snap;
  end: EpisodeEnd | null;
  /** Shot time (negative while the kick winds up), or time since the end. */
  t: number;
  /** How the shot looks (foot, technique) and is played; how he takes it. */
  tech: Technique | null;
  plan: StrikePlan | null;
  take: KeeperTake | null;
  /** The keeper's hands (between the palms) this frame, and from when (s)
   * the ball is in them. */
  hands: THREE.Vector3;
  holdFrom: number;
  decided: boolean;
  dt: number;
  ball: THREE.Vector3;
  shake: number;
  ripple: { x: number; y: number; at: number } | null;
};

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

/** The flight as the free kick's helpers read a trajectory (outcome and end). */
function asTrajectory(f: ShotFlight): ShotTrajectory {
  return { outcome: f.outcome, samples: [], events: f.events, end: f.end };
}
const NO_WALL = createPenaltySetup(1);

export default function OneOnOneScene3D(props: Props) {
  const [quality, setQuality] = useState<Quality>("high");
  const hype = useRef(0);
  return (
    <Canvas
      dpr={quality === "high" ? 1.5 : 1}
      shadows={quality === "high"}
      gl={{ antialias: false, powerPreference: "high-performance", stencil: false }}
      camera={{ fov: 55, near: 0.1, far: 400 }}
      style={{ touchAction: "none" }}
    >
      <PerformanceMonitor onDecline={() => setQuality("low")} />
      <fog attach="fog" args={["#0b1830", 70, 170]} />
      <Lights quality={quality} />
      <Environment resolution={64} frames={1}>
        <Lightformer intensity={3} position={[0, 12, -20]} scale={[40, 6, 1]} />
        <Lightformer intensity={2} position={[-25, 10, 10]} rotation-y={Math.PI / 2} scale={[30, 4, 1]} />
        <Lightformer intensity={2} position={[25, 10, 10]} rotation-y={-Math.PI / 2} scale={[30, 4, 1]} />
        <Lightformer intensity={0.6} color="#2c8a47" position={[0, -5, 0]} rotation-x={Math.PI / 2} scale={[60, 60, 1]} />
      </Environment>
      <Stadium quality={quality} hype={hype} />
      <Episode {...props} quality={quality} hype={hype} />
      <FpsMeter fpsRef={props.fpsRef} />
    </Canvas>
  );
}

function Episode({
  setup,
  recorder,
  input,
  onEnded,
  onDecided,
  onReady,
  ball,
  quality,
  hype,
}: Omit<Props, "fpsRef"> & { quality: Quality; hype: MutableRefObject<number> }) {
  const stage = useRef<Stage>({
    acc: 0, prev: snap(recorder.state), cur: snap(recorder.state), end: null, t: 0, decided: false, dt: 0,
    tech: null, plan: null, take: null, hands: new THREE.Vector3(), holdFrom: Infinity,
    ball: new THREE.Vector3(), shake: 0, ripple: null,
  });
  const [confetti, setConfetti] = useState(0);
  const [flight, setFlight] = useState<ShotFlight | null>(null);

  // A new attack, a new recorder: start over.
  useEffect(() => {
    const s0 = snap(recorder.state);
    Object.assign(stage.current, {
      acc: 0, prev: s0, cur: s0, end: null, t: 0, decided: false, ripple: null, tech: null, plan: null, take: null, holdFrom: Infinity,
    });
    setFlight(null);
  }, [recorder]);

  useFrame((state, delta) => {
    const s = stage.current;
    const dt = Math.min(delta, 0.1);
    hype.current = Math.max(0, hype.current - delta * 0.22);
    s.shake = Math.max(0, s.shake - delta * 2.5);
    s.dt = dt;
    if (!s.end) {
      if (!input.current.live) return;
      s.acc += dt;
      let steps = 0;
      while (s.acc >= TICK && steps < 8 && !recorder.state.ended) {
        const inp = input.current;
        s.prev = s.cur;
        recorder.step(inp.hold, inp.steer, inp.feint, inp.shot);
        inp.feint = 0;
        s.cur = snap(recorder.state);
        s.acc -= TICK;
        steps += 1;
      }
      // A long stall (tab in the background): don't race to catch up.
      if (steps === 8) s.acc = 0;
      const ended = recorder.state.ended;
      if (ended) {
        s.end = ended;
        s.acc = TICK;
        s.tech = techniqueOf(recorder.state, recorder.timeline);
        s.plan = s.tech ? strikePlan(s.tech.kind, s.tech.foot) : null;
        s.take = ended.flight ? keeperTake(ended.flight) : null;
        s.t = s.plan ? -s.plan.lead : 0;
        if (ended.flight) setFlight(ended.flight);
        onEnded(ended);
      }
      return;
    }
    // After the end: the flight (with slow motion near a goal or a save).
    const f = s.end.flight;
    const prev = s.t;
    let scale = 1;
    if (f && !s.decided && (f.outcome === "goal" || f.outcome === "save")) {
      const left = f.end.t - s.t;
      if (left > 0 && left < SLOWMO_WINDOW) scale = SLOWMO_SCALE + (1 - SLOWMO_SCALE) * (left / SLOWMO_WINDOW) ** 2;
    }
    s.t += dt * scale;
    s.dt = s.t - prev;
    if (f) {
      if (prev < 0 && s.t >= 0) playFreeKickSfx("kick");
      for (const e of f.events) {
        if (e.t <= prev || e.t > s.t) continue;
        if (e.type === "post") {
          playFreeKickSfx("post");
          s.shake = 0.6;
        } else if (e.type === "save") {
          playFreeKickSfx("wall");
          s.shake = 0.3;
        }
      }
    }
    const decideAt = f ? f.end.t : 0.25;
    if (!s.decided && s.t >= decideAt) {
      s.decided = true;
      if (f) {
        const hit = netImpact(asTrajectory(f));
        if (hit) {
          const v = f.end.velocity;
          const travel = v.z < -0.1 ? (-NET_DEPTH - f.end.position.z) / v.z : 0;
          s.ripple = { ...hit, at: state.clock.getElapsedTime() + travel };
          hype.current = 1;
          setConfetti((n) => n + 1);
          setTimeout(() => playFreeKickSfx("net"), travel * 1000);
        }
      }
      onDecided();
    }
  }, -1);

  return (
    <>
      <GoalFrame stage={stage} />
      <Suspense fallback={null}>
        <Players setup={setup} stage={stage} flight={flight} quality={quality} onReady={onReady} />
      </Suspense>
      <Ball stage={stage} flight={flight} skin={ball} quality={quality} />
      <CameraRig stage={stage} flight={flight} />
      <Confetti burstId={confetti} />
    </>
  );
}

type StageRef = MutableRefObject<Stage>;

/** The attacker's position this frame (interpolated between ticks). */
function attackerAt(s: Stage) {
  const k = s.end ? 1 : Math.min(1, s.acc / TICK);
  return {
    x: lerp(s.prev.x, s.cur.x, k),
    z: lerp(s.prev.z, s.cur.z, k),
    hx: lerp(s.prev.hx, s.cur.hx, k),
    hz: lerp(s.prev.hz, s.cur.hz, k),
    speed: s.end ? 0 : s.cur.speed,
  };
}

function keeperAt(s: Stage) {
  const k = s.end ? 1 : Math.min(1, s.acc / TICK);
  const x = lerp(s.prev.kx, s.cur.kx, k);
  const z = lerp(s.prev.kz, s.cur.kz, k);
  const speed = Math.hypot(s.cur.kx - s.prev.kx, s.cur.kz - s.prev.kz) / TICK;
  return { x, z, speed, mode: s.cur.kMode as KeeperMode };
}

// ---------------------------------------------------------------------------
// The two footballers.
// ---------------------------------------------------------------------------

const ATTACKER_LOOK = { shirt: "#2fbf71", shorts: "#f8fafc", socks: "#2fbf71", skin: "#e6b896", hair: "#3a2a20" };
const KEEPER_LOOK = { shirt: "#facc15", shorts: "#111827", socks: "#facc15", skin: "#c98f68", hair: "#1c1612" };

function hipsOf(p: SkinnedPlayer): THREE.Object3D | null {
  let hips: THREE.Object3D | null = null;
  p.root.traverse((o) => {
    if (!hips && (o as THREE.Bone).isBone && /Hips$/.test(o.name)) hips = o;
  });
  return hips;
}

/** The keeper's two hands (the ball between them when he holds it). */
function handsOf(p: SkinnedPlayer): [THREE.Object3D, THREE.Object3D] | null {
  let l: THREE.Object3D | null = null;
  let r: THREE.Object3D | null = null;
  p.root.traverse((o) => {
    if (!(o as THREE.Bone).isBone) return;
    if (/LeftHand$/.test(o.name)) l = o;
    else if (/RightHand$/.test(o.name)) r = o;
  });
  return l && r ? [l, r] : null;
}

/** The run, then the sprint from a little above the run's own pace: each
 * played close to the speed it was recorded at (sped up much, the legs
 * whirl), the strides cross-faded rather than switched. */
const SPRINT_FROM = 0.95;
const STRIDE_MIN = 0.75;
const STRIDE_MAX = 1.1;
function runAt(p: SkinnedPlayer, speed: number, asset: FootballerAsset) {
  const sprint = speed > asset.timing.sprintSpeed * SPRINT_FROM;
  const clip = play(p, sprint ? "sprint" : "run", false, 0.35);
  clip.timeScale = THREE.MathUtils.clamp(speed / (sprint ? asset.timing.sprintSpeed : asset.timing.runSpeed), STRIDE_MIN, STRIDE_MAX);
}

/** The ball settles into the keeper's hands over this (s). */
const INTO_HANDS = 0.08;
const wrapAngle =(a: number) => Math.atan2(Math.sin(a), Math.cos(a));
/** The scoop played faster (he is already down at the ball). */
const SCOOP_SPEED = 1.5;
/** Getting up after the feint fooled him (s). */
const GETUP_S = 0.7;

/** Keeps the hips over (x, z) whatever the clip does (the dives travel
 * sideways on their own; here the engine says where his body is). */
function pinHips(p: SkinnedPlayer, hips: THREE.Object3D | null, x: number, z: number, tmp: THREE.Vector3) {
  p.root.position.set(x, 0, z);
  if (!hips) return;
  p.root.updateMatrixWorld(true);
  hips.getWorldPosition(tmp);
  p.root.position.x += x - tmp.x;
  p.root.position.z += z - tmp.z;
}

function Players({
  setup,
  stage,
  flight,
  quality,
  onReady,
}: {
  setup: EpisodeSetup;
  stage: StageRef;
  flight: ShotFlight | null;
  quality: Quality;
  onReady: () => void;
}) {
  const [gltf, extra, movesGltf] = useLoader(GLTFLoader, [FOOTBALLER_URL, MOVES_URL, ONE_ON_ONE_MOVES_URL], (loader) => {
    loader.setMeshoptDecoder(MeshoptDecoder);
  });
  const asset = useMemo<FootballerAsset>(() => prepareFootballer(gltf, extra), [gltf, extra]);
  const moves = useMemo<Moves>(() => prepareMoves(gltf, movesGltf), [gltf, movesGltf]);
  const materials = useMemo(() => new MaterialCache(), []);
  const attacker = useMemo(() => {
    const p = makePlayer(asset, ATTACKER_LOOK, materials);
    addMoves(p, moves);
    p.root.rotation.order = "YXZ";
    return p;
  }, [asset, moves, materials]);
  const keeper = useMemo(() => {
    const p = makePlayer(asset, KEEPER_LOOK, materials);
    addMoves(p, moves);
    return p;
  }, [asset, moves, materials]);
  const bones = useMemo(() => ({ keeper: hipsOf(keeper), hands: handsOf(keeper) }), [keeper]);
  const tmp = useMemo(() => ({ v: new THREE.Vector3(), a: new THREE.Vector3(), b: new THREE.Vector3() }), []);
  // The keeper getting up after he bit on the feint (s since, or null).
  const getup = useRef<{ mode: KeeperMode; since: number | null }>({ mode: "wait", since: null });
  useEffect(() => {
    for (const p of [attacker, keeper]) {
      p.root.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) o.castShadow = quality === "high";
      });
    }
  }, [attacker, keeper, quality]);
  useEffect(() => () => {
    attacker.mixer.stopAllAction();
    keeper.mixer.stopAllAction();
    materials.dispose();
  }, [attacker, keeper, materials]);
  useEffect(onReady, [onReady]);
  // The keeper's dive in the shot: where his hands go, which side, when.
  const dive = useMemo(() => {
    if (!flight || flight.keeper.lyingFor > 0) return null;
    const last = flight.samples[flight.samples.length - 1];
    const dx = last.handX - flight.keeper.x;
    return { dx, y: last.handY, arrival: flight.end.t, reaction: flight.keeper.reaction };
  }, [flight]);

  useFrame((_, delta) => {
    const s = stage.current;
    const a = attackerAt(s);
    const k = keeperAt(s);
    const t = s.t;
    const end = s.end;

    // --- Attacker ---
    const runYaw = Math.atan2(a.hx, a.hz);
    attacker.root.rotation.set(0, runYaw, 0);
    if (end?.flight && s.plan) {
      const f = end.flight;
      const plan = s.plan;
      const strike = moves.strikes[plan.clip];
      // He turns his body to the shot (open or closed for the technique)
      // through the wind-up; at the contact the toe is at the ball.
      const v = f.kick.velocity;
      const shotYaw = Math.atan2(v.x, v.z) + plan.yaw;
      const turn = Math.min(1, (t + plan.lead) / (plan.lead * 0.7));
      const yaw = runYaw + wrapAngle(shotYaw - runYaw) * turn;
      attacker.root.rotation.set(-plan.lean * turn, yaw, 0);
      const kick = play(attacker, plan.clip, true, 0.08);
      kick.time = THREE.MathUtils.clamp(strike.contact + t * plan.timeScale, 0, kick.getClip().duration);
      kick.paused = true;
      const toe = tmp.v.set(strike.toe.x, 0, strike.toe.z).applyAxisAngle(THREE.Object3D.DEFAULT_UP, yaw);
      attacker.root.position.set(f.from.x - toe.x, 0, f.from.z - toe.z);
      if (end.outcome === "goal" && t > f.end.t + 0.6) {
        attacker.root.rotation.x = 0;
        play(attacker, "celebrate", true, 0.3).paused = false;
      }
    } else if (end?.outcome === "tackle") {
      // Into the keeper at his feet: he goes over.
      play(attacker, "trip", true, 0.1).paused = false;
      attacker.root.position.set(a.x, 0, a.z);
    } else if (end) {
      play(attacker, "idle", false, 0.3);
      attacker.root.position.set(a.x, 0, a.z);
    } else if (s.cur.feintTicks > 0) {
      // The feint: a quick sidestep with the ball, leaning into it.
      const side = play(attacker, s.cur.feintDir > 0 ? "strafe_r" : "strafe_l", false, 0.08);
      side.timeScale = 1.6;
      attacker.root.position.set(a.x, 0, a.z);
      attacker.root.rotation.z = -s.cur.feintDir * Math.sin((1 - s.cur.feintTicks / FEINT_TICKS) * Math.PI) * 0.18;
    } else {
      if (a.speed < 0.4) play(attacker, "idle", false, 0.2);
      else runAt(attacker, a.speed, asset);
      attacker.root.position.set(a.x, 0, a.z);
    }
    attacker.mixer.update(s.dt);

    // --- Keeper (faces the ball) ---
    // The ball in his hands or at his feet is no direction to face: then he
    // faces the attacker (where the shot came from).
    const b = s.ball;
    const near = Math.hypot(b.x - k.x, b.z - k.z) < 0.8 || t >= s.holdFrom;
    const fx = end?.flight ? end.flight.from.x : near ? a.x : b.x;
    const fz = end?.flight ? end.flight.from.z : near ? a.z : b.z;
    keeper.root.rotation.set(0, Math.atan2(fx - k.x, fz - k.z), 0);
    const g = getup.current;
    if (g.mode === "fallen" && k.mode !== "fallen" && k.mode !== "lunge" && !end) g.since = 0;
    g.mode = k.mode;
    if (g.since !== null) g.since += delta;
    let pinX = k.x;
    const lying = end?.flight && end.flight.keeper.lyingFor > 0 && t < end.flight.keeper.lyingFor;
    if (k.mode === "lunge" || k.mode === "fallen" || lying) {
      // Bit on the feint: the dive the wrong way, held on the grass.
      const clip = play(keeper, s.cur.lungeDir > 0 ? "gk_dive_left" : "gk_dive_right", true, 0.08);
      clip.timeScale = 1.6;
      clip.paused = false;
    } else if (end?.outcome === "tackle") {
      // Down at the attacker's feet and the ball gathered in.
      const scoop = play(keeper, "gk_scoop", true, 0.08);
      scoop.timeScale = SCOOP_SPEED;
      scoop.paused = false;
      s.holdFrom = moves.scoopPickup / SCOOP_SPEED;
    } else if (end?.flight && dive && t >= dive.reaction) {
      const f = end.flight;
      const samp = flightAt(f, Math.min(Math.max(t, 0), f.end.t));
      pinX = samp.bodyX;
      if (s.take === "catch") s.holdFrom = f.end.t;
      if (Math.abs(dive.dx) >= 1) {
        const clip = play(keeper, dive.dx > 0 ? "gk_dive_left" : "gk_dive_right", true, 0.06);
        const { diveStart, diveReach } = asset.timing;
        if (clip.time < diveStart) clip.time = diveStart;
        clip.timeScale = THREE.MathUtils.clamp((diveReach - diveStart) / Math.max(0.15, dive.arrival - dive.reaction), 0.7, 4.5);
        if (clip.time >= diveReach && end.outcome === "save" && t < f.end.t + 0.3) clip.timeScale = 0;
      } else if (end.outcome === "goal" && t > f.end.t + 0.2) {
        // Beaten: hands on his head.
        play(keeper, "gk_miss", true, 0.3);
      } else if (s.take === "block" || (f.keeper.spread && dive.y < 0.7)) {
        // Spread at the attacker's feet.
        play(keeper, f.end.position.x - k.x > 0 ? "gk_block_l" : "gk_block_r", true, 0.06).timeScale = 1.8;
      } else {
        // Straight at him: up, at the chest, or down for it.
        play(keeper, dive.y > 1.35 ? "gk_catch_high" : dive.y < 0.75 ? "gk_catch_low" : "gk_catch", true, 0.08).timeScale = 1.6;
      }
    } else if (!end && g.since !== null && g.since < GETUP_S) {
      // Back on his feet after the feint fooled him.
      const up = play(keeper, "gk_getup", true, 0.1);
      up.timeScale = up.getClip().duration / GETUP_S;
    } else if (!end && k.speed > 0.6) {
      runAt(keeper, k.speed, asset);
    } else if (!end?.flight || t < (dive?.reaction ?? 0)) {
      play(keeper, "gk_idle", false, 0.25);
    }
    keeper.mixer.update(s.dt);
    pinHips(keeper, bones.keeper, pinX, k.z, tmp.v);
    // Where the ball sits when he has it: between his palms.
    if (bones.hands) {
      keeper.root.updateMatrixWorld(true);
      bones.hands[0].getWorldPosition(tmp.a);
      bones.hands[1].getWorldPosition(tmp.b);
      s.hands.addVectors(tmp.a, tmp.b).multiplyScalar(0.5);
    }
  }, -0.5);

  return (
    <>
      <primitive object={attacker.root} />
      <primitive object={keeper.root} position={[0, 0, KEEPER_START_Z]} />
      {/* The line the keeper starts from, for the scale of how far he came. */}
      <mesh rotation-x={-Math.PI / 2} position={[setup.start.x, 0.01, setup.start.z]}>
        <ringGeometry args={[0.5, 0.62, 28]} />
        <meshBasicMaterial color="#c6e63a" transparent opacity={0.35} depthWrite={false} />
      </mesh>
    </>
  );
}

// ---------------------------------------------------------------------------
// Ball: at the attacker's feet (touched forward with his stride), then the
// flight's samples, then the deterministic aftermath.
// ---------------------------------------------------------------------------

function Ball({ stage, flight, skin: skinCode, quality }: { stage: StageRef; flight: ShotFlight | null; skin?: string | null; quality: Quality }) {
  const group = useRef<THREE.Group>(null);
  const mesh = useRef<THREE.Mesh>(null);
  const shadow = useRef<THREE.Mesh>(null);
  const skin = ballSkin(skinCode);
  const geometry = useMemo(() => ballGeometry(skin.light, skin.dark), [skin]);
  const aftermath = useMemo(() => (flight ? simulateAftermath(NO_WALL, asTrajectory(flight)) : null), [flight]);
  const stride = useRef({ phase: 0, x: 0, z: 0 });
  const [flying, setFlying] = useState(false);

  useFrame(() => {
    const g = group.current;
    const m = mesh.current;
    if (!g || !m) return;
    const s = stage.current;
    const end = s.end;
    const f = end?.flight;
    let x: number;
    let y = BALL_RADIUS;
    let z: number;
    if (f && aftermath) {
      const t = s.t;
      const p = t < 0 ? { x: f.from.x, y: BALL_RADIUS, z: f.from.z } : t <= f.end.t ? flightAt(f, t).ball : aftermathAt(aftermath, t);
      ({ x, y, z } = p);
      if (t >= s.holdFrom) {
        // Caught: it goes into his gloves and stays there.
        const k = Math.min(1, (t - s.holdFrom) / INTO_HANDS);
        x = lerp(x, s.hands.x, k);
        y = lerp(y, s.hands.y, k);
        z = lerp(z, s.hands.z, k);
      }
      if (flying !== (t >= 0 && !s.decided)) setFlying(t >= 0 && !s.decided);
    } else if (end?.outcome === "tackle") {
      // Rolls on into the keeper at the attacker's feet, then he gathers it
      // into his hands as he comes up.
      const k = keeperAt(s);
      const roll = Math.min(1, s.dt * 10);
      x = lerp(g.position.x, k.x, roll * 0.5);
      z = lerp(g.position.z, k.z + 0.35, roll * 0.5);
      if (s.t >= s.holdFrom) {
        const kk = Math.min(1, (s.t - s.holdFrom) / INTO_HANDS);
        x = lerp(x, s.hands.x, kk);
        y = lerp(BALL_RADIUS, s.hands.y, kk);
        z = lerp(z, s.hands.z, kk);
      }
    } else {
      const a = attackerAt(s);
      // Dribbling: a touch every couple of strides runs it a little ahead.
      const moved = Math.hypot(a.x - stride.current.x, a.z - stride.current.z);
      stride.current.phase += moved / 1.1;
      const lead = BALL_LEAD + 0.16 * Math.sin(stride.current.phase * Math.PI);
      x = a.x + a.hx * lead;
      z = a.z + a.hz * lead;
    }
    stride.current.x = attackerAt(s).x;
    stride.current.z = attackerAt(s).z;
    const moved = Math.hypot(x - g.position.x, z - g.position.z);
    // Rolling turns it; in the keeper's hands it moves with them, unturned.
    if (s.t < s.holdFrom || !end) {
      if (moved > 1e-4) g.rotation.y = Math.atan2(x - g.position.x, z - g.position.z);
      m.rotation.x += moved / BALL_RADIUS;
    }
    g.position.set(x, y, z);
    s.ball.set(x, y, z);
    if (shadow.current) {
      shadow.current.position.set(x, 0.012, z);
      shadow.current.scale.setScalar(Math.max(0.35, 1 - y * 0.12));
    }
  });

  return (
    <>
      <group ref={group}>
        <mesh ref={mesh} geometry={geometry} castShadow>
          <meshStandardMaterial vertexColors roughness={skin.roughness} metalness={skin.metalness} envMapIntensity={0.8} />
        </mesh>
      </group>
      {flying && (
        <Trail target={mesh as MutableRefObject<THREE.Object3D>} width={0.9} length={5} color="#c6e63a" attenuation={(w) => w * w} decay={1.2} />
      )}
      <mesh ref={shadow} rotation-x={-Math.PI / 2}>
        <circleGeometry args={[BALL_RADIUS * 1.3, 16]} />
        <meshBasicMaterial color="#000" transparent opacity={quality === "high" ? 0.25 : 0.4} depthWrite={false} />
      </mesh>
    </>
  );
}

// ---------------------------------------------------------------------------
// Camera: behind the attacker, turned towards the goal; on the shot it
// holds and follows the ball a little. A portrait phone gets a wider view.
// ---------------------------------------------------------------------------

function CameraRig({ stage, flight }: { stage: StageRef; flight: ShotFlight | null }) {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const aspect = useThree((s) => s.size.width / s.size.height);
  const tmp = useMemo(
    () => ({ want: new THREE.Vector3(), look: new THREE.Vector3(), lookNow: new THREE.Vector3(0, 1.1, 0), goal: new THREE.Vector3(0, 1.1, 0), held: new THREE.Vector3() }),
    [],
  );
  const placed = useRef(false);

  useEffect(() => {
    camera.fov = aspect < 0.8 ? 64 : 50;
    camera.updateProjectionMatrix();
  }, [camera, aspect]);
  useEffect(() => {
    if (flight) tmp.held.copy(camera.position);
  }, [flight, camera, tmp]);

  useFrame(() => {
    const s = stage.current;
    const a = attackerAt(s);
    if (!flight) {
      // Behind him, mostly looking at the goal (so the keeper is in view).
      const len = Math.hypot(a.x, a.z) || 1;
      const bx = lerp(-a.x / len, a.hx, 0.35);
      const bz = lerp(-a.z / len, a.hz, 0.35);
      const bl = Math.hypot(bx, bz) || 1;
      const near = Math.min(1, Math.max(0, (a.z - 6) / 14));
      tmp.want.set(a.x - (bx / bl) * lerp(3.8, 5.6, near), lerp(2.0, 2.7, near), a.z - (bz / bl) * lerp(3.8, 5.6, near));
      tmp.look.set(a.x, 0.9, a.z).lerp(tmp.goal, 0.5);
      if (!placed.current) {
        camera.position.copy(tmp.want);
        tmp.lookNow.copy(tmp.look);
        placed.current = true;
      }
      camera.position.lerp(tmp.want, 0.1);
    } else {
      // The shot: hold position, drift a little after the ball.
      const follow = Math.min(1, Math.max(0, s.t) / 0.8) * 0.3;
      tmp.want.lerpVectors(tmp.held, s.ball, follow).setY(Math.max(1.4, tmp.want.y));
      camera.position.lerp(tmp.want, 0.08);
      tmp.look.lerpVectors(tmp.goal, s.ball, 0.55);
    }
    tmp.lookNow.lerp(tmp.look, 0.15);
    if (s.shake > 0) {
      const k = s.shake * 0.06;
      camera.position.x += (Math.random() - 0.5) * k;
      camera.position.y += (Math.random() - 0.5) * k;
    }
    camera.lookAt(tmp.lookNow);
  });
  return null;
}
