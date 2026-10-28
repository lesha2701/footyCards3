import { Environment, Lightformer, PerformanceMonitor, Trail } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  BallCollider,
  CapsuleCollider,
  CoefficientCombineRule,
  CuboidCollider,
  CylinderCollider,
  Physics,
  RigidBody,
  type RapierRigidBody,
} from "@react-three/rapier";
import { Suspense, useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import * as THREE from "three";

import { NET_DEPTH, keeperGoesFor, netBulge, netImpact, replayTimeScale } from "@/lib/freeKick3d/fx";
import { playFreeKickSfx } from "@/lib/freeKick3d/sfx";
import {
  BALL_RADIUS,
  GOAL_HALF_WIDTH,
  GOAL_HEIGHT,
  KEEPER_BODY_RADIUS,
  KEEPER_LINE_Z,
  KEEPER_STAND_HAND_Y,
  POST_RADIUS,
  WALL_PLAYER_HEIGHT,
  WALL_PLAYER_RADIUS,
  sampleAt,
  type KickParams,
  type ShotSetup,
  type ShotTrajectory,
  type Vec3,
} from "@/lib/freeKick3d/trajectory";

import Confetti from "./Confetti";
import { KICK } from "./kickStyles";
import { LOOKS } from "./looks";
import { KeeperModel, KickerModel, WallPlayerModel, type PlayerClock } from "./Players";
import { Stadium, type Hype, type Quality } from "./Stadium";
import { ballGeometry, netTexture } from "./textures";

export type LiveShot = { id: number; kick: KickParams; trajectory: ShotTrajectory };

type Props = {
  setup: ShotSetup;
  shot: LiveShot | null;
  /** Fired once per shot, when the replay reaches the decided outcome. */
  onDecided: (shotId: number) => void;
  /** Rapier's WASM is loaded and the shot world is mounted. */
  onReady: () => void;
  /** The FPS readout element (written from the render loop, no re-renders). */
  fpsRef: MutableRefObject<HTMLSpanElement | null>;
};

/** Shot time runs on its own clock so the replay can slow down near the
 * goal (−1 = waiting for a kick). */
type ShotClock = { shotId: number; t: number; decided: boolean; decidedAt: number };

/** Everything the presentation layer shares across components per frame. */
type Stage = {
  clock: ShotClock;
  /** Animation step this frame: real time while waiting, shot time (slow
   * motion included) during a shot. */
  dt: number;
  ball: THREE.Vector3;
  shake: number;
  /** Back-net impact (x, y) and when it lands, in scene seconds. */
  ripple: { x: number; y: number; at: number } | null;
};

export default function FreeKickScene3D({ setup, shot, onDecided, onReady, fpsRef }: Props) {
  // Start pretty; the first sustained frame drop switches to the light
  // profile for good (no flip-flopping shadows on a struggling phone).
  const [quality, setQuality] = useState<Quality>("high");
  const hype = useRef(0);
  return (
    <Canvas
      dpr={quality === "high" ? 1.5 : 1}
      shadows={quality === "high"}
      gl={{ antialias: false, powerPreference: "high-performance", stencil: false }}
      camera={{ fov: 50, near: 0.1, far: 400 }}
      style={{ touchAction: "none" }}
    >
      <PerformanceMonitor onDecline={() => setQuality("low")} />
      <fog attach="fog" args={["#0b1830", 70, 170]} />
      <Lights quality={quality} />
      {/* Reflections for the ball and posts: a tiny cube map rendered once
          from a few light panels — no HDR download. */}
      <Environment resolution={64} frames={1}>
        <Lightformer intensity={3} position={[0, 12, -20]} scale={[40, 6, 1]} />
        <Lightformer intensity={2} position={[-25, 10, 10]} rotation-y={Math.PI / 2} scale={[30, 4, 1]} />
        <Lightformer intensity={2} position={[25, 10, 10]} rotation-y={-Math.PI / 2} scale={[30, 4, 1]} />
        <Lightformer intensity={0.6} color="#2c8a47" position={[0, -5, 0]} rotation-x={Math.PI / 2} scale={[60, 60, 1]} />
      </Environment>
      <Stadium quality={quality} hype={hype} />
      {/* Rapier's WASM loads asynchronously: the stadium shows meanwhile. */}
      <Suspense fallback={null}>
        <Physics gravity={[0, -9.81, 0]} timeStep={1 / 60}>
          <ShotWorld setup={setup} shot={shot} onDecided={onDecided} onReady={onReady} quality={quality} hype={hype} />
        </Physics>
      </Suspense>
      <FpsMeter fpsRef={fpsRef} />
    </Canvas>
  );
}

/** Night match: a cool sky fill plus a floodlight key that casts the only
 * shadows (high quality only, fitted to the ball → goal area). */
function Lights({ quality }: { quality: Quality }) {
  const key = useRef<THREE.DirectionalLight>(null);
  useEffect(() => {
    const l = key.current;
    if (!l) return;
    l.target.position.set(0, 0, 10);
    l.target.updateMatrixWorld();
    const cam = l.shadow.camera;
    cam.left = -22;
    cam.right = 22;
    cam.top = 22;
    cam.bottom = -22;
    cam.near = 1;
    cam.far = 90;
    cam.updateProjectionMatrix();
  }, [quality]);
  return (
    <>
      <hemisphereLight args={["#9fb7d9", "#0f2a18", 0.7]} />
      <directionalLight
        ref={key}
        position={[-18, 30, 30]}
        intensity={2.2}
        color="#fff6e0"
        castShadow={quality === "high"}
        shadow-mapSize={[1024, 1024]}
        shadow-bias={-0.0004}
        shadow-normalBias={0.02}
      />
      <directionalLight position={[22, 18, -20]} intensity={0.8} color="#cfe0ff" />
    </>
  );
}

function ShotWorld({
  setup,
  shot,
  onDecided,
  onReady,
  quality,
  hype,
}: Omit<Props, "fpsRef"> & { quality: Quality; hype: Hype }) {
  const stage = useRef<Stage>({
    clock: { shotId: -1, t: -1, decided: false, decidedAt: 0 },
    dt: 0,
    ball: new THREE.Vector3(setup.ball.x, setup.ball.y, setup.ball.z),
    shake: 0,
    ripple: null,
  });
  const [confetti, setConfetti] = useState(0);

  useEffect(() => {
    // A shot starts with the kicker's run-up: the ball leaves at t = 0.
    // The kick clip is cued so its contact frame lands on shot time 0.
    stage.current.clock = { shotId: shot?.id ?? -1, t: shot ? -KICK.lead : -1, decided: false, decidedAt: 0 };
    stage.current.ripple = null;
  }, [shot]);
  useEffect(onReady, [onReady]);

  // Runs before everything else each frame (negative priority keeps the
  // automatic render): advances shot time, fires impacts and the decision.
  useFrame((state, delta) => {
    const s = stage.current;
    const c = s.clock;
    const now = state.clock.getElapsedTime();
    hype.current = Math.max(0, hype.current - delta * 0.22);
    s.shake = Math.max(0, s.shake - delta * 2.5);
    const dt = Math.min(delta, 0.05);
    s.dt = dt;
    if (!shot || c.shotId !== shot.id) return;

    const traj = shot.trajectory;
    const prev = c.t;
    c.t += dt * (c.decided || c.t < 0 ? 1 : replayTimeScale(traj, c.t));
    s.dt = c.t - prev;
    if (prev < 0 && c.t >= 0) playFreeKickSfx("kick");
    for (const e of traj.events) {
      if (e.t <= prev || e.t > c.t) continue;
      if (e.type === "post") {
        playFreeKickSfx("post");
        s.shake = 0.6;
      } else if (e.type === "wall") {
        playFreeKickSfx("wall");
        s.shake = 0.5;
      } else if (e.type === "save") {
        playFreeKickSfx("wall");
        s.shake = 0.3;
      }
    }
    if (!c.decided && c.t >= traj.end.t) {
      c.decided = true;
      c.decidedAt = now;
      const hit = netImpact(traj);
      if (hit) {
        const v = traj.end.velocity;
        const travel = v.z < -0.1 ? (-NET_DEPTH - traj.end.position.z) / v.z : 0;
        s.ripple = { ...hit, at: now + travel };
        hype.current = 1;
        setConfetti((n) => n + 1);
        setTimeout(() => playFreeKickSfx("net"), travel * 1000);
      }
      onDecided(shot.id);
    }
  }, -1);

  return (
    <>
      <GoalFrame stage={stage} />
      <Wall setup={setup} shot={shot} stage={stage} quality={quality} />
      <Suspense fallback={<Keeper setup={setup} shot={shot} stage={stage} />}>
        <AnimatedKeeper setup={setup} shot={shot} stage={stage} quality={quality} />
      </Suspense>
      <Suspense fallback={null}>
        <KickerModel setup={setup} clock={playerClock(stage, shot)} kicking={shot !== null} castShadow={quality === "high"} />
      </Suspense>
      <Ball setup={setup} shot={shot} stage={stage} quality={quality} />
      <CameraRig setup={setup} shot={shot} stage={stage} />
      <Confetti burstId={confetti} />
      {/* Ground for the post-outcome physics. */}
      <RigidBody type="fixed" colliders={false}>
        <CuboidCollider args={[60, 0.5, 60]} position={[0, -0.5, 20]} restitution={0.5} friction={0.8} />
      </RigidBody>
    </>
  );
}

type StageProps = { setup: ShotSetup; shot: LiveShot | null; stage: MutableRefObject<Stage> };

/** The animated players read the shot clock through this. */
function playerClock(stage: MutableRefObject<Stage>, shot: LiveShot | null): PlayerClock {
  return { t: () => shotTime(stage.current, shot), dt: () => stage.current.dt };
}

function shotTime(stage: Stage, shot: LiveShot | null) {
  return shot && stage.clock.shotId === shot.id ? stage.clock.t : -1;
}

// ---------------------------------------------------------------------------
// Ball: a plain mesh replaying the deterministic samples (with a light
// trail showing the curl); at the decided moment a fresh dynamic Rapier
// body takes over so it drops into the net or bounces off the wall —
// purely cosmetic, the outcome is already set.
// ---------------------------------------------------------------------------

type Released = { shotId: number; position: Vec3; velocity: Vec3; spin: Vec3 };

function Ball({ setup, shot, stage, quality }: StageProps & { quality: Quality }) {
  const flight = useRef<THREE.Mesh>(null);
  const body = useRef<RapierRigidBody>(null);
  const shadow = useRef<THREE.Mesh>(null);
  const geometry = useMemo(ballGeometry, []);
  const [released, setReleased] = useState<Released | null>(null);
  const live = released !== null && released.shotId === shot?.id ? released : null;

  useFrame((_, delta) => {
    const mesh = flight.current;
    if (!mesh) return;
    const s = stage.current;
    const t = shotTime(s, shot);
    if (!shot || t < 0) {
      mesh.position.set(setup.ball.x, setup.ball.y, setup.ball.z);
      mesh.rotation.set(0, 0, 0);
    } else if (!live) {
      const traj = shot.trajectory;
      const smp = sampleAt(traj, Math.min(t, traj.end.t));
      mesh.position.set(smp.ball.x, smp.ball.y, smp.ball.z);
      // Visual spin: around the spin axis plus a forward roll.
      mesh.rotation.y += shot.kick.spin.y * delta * 0.25;
      mesh.rotation.x -= delta * 18;
      if (s.clock.decided) {
        const v = traj.end.velocity;
        setReleased({
          shotId: shot.id,
          position: traj.end.position,
          velocity: v,
          spin: { x: -v.z / BALL_RADIUS / 4, y: shot.kick.spin.y, z: 0 },
        });
      }
    }
    const p = live && body.current ? body.current.translation() : mesh.position;
    s.ball.set(p.x, p.y, p.z);
    if (shadow.current) {
      shadow.current.position.set(p.x, 0.012, p.z);
      shadow.current.scale.setScalar(Math.max(0.35, 1 - p.y * 0.12));
    }
  });

  const material = (
    <meshStandardMaterial vertexColors roughness={0.42} metalness={0} envMapIntensity={0.8} />
  );
  const flying = shot !== null && !live;

  return (
    <>
      <mesh ref={flight} geometry={geometry} visible={!live} castShadow>
        {material}
      </mesh>
      {flying && (
        <Trail key={shot.id} target={flight as MutableRefObject<THREE.Object3D>} width={0.9} length={5} color="#c6e63a" attenuation={(w) => w * w} decay={1.2} />
      )}
      {live && (
        <RigidBody
          key={live.shotId}
          ref={body}
          colliders={false}
          position={[live.position.x, live.position.y, live.position.z]}
          linearVelocity={[live.velocity.x, live.velocity.y, live.velocity.z]}
          angularVelocity={[live.spin.x, live.spin.y, live.spin.z]}
          ccd
          linearDamping={0.3}
          angularDamping={0.6}
        >
          <BallCollider args={[BALL_RADIUS]} restitution={0.55} friction={0.6} density={BALL_DENSITY} />
          <mesh geometry={geometry} castShadow>
            {material}
          </mesh>
        </RigidBody>
      )}
      {/* Contact shadow: soft blob under the ball (the real shadow is too
          small to read on a phone). */}
      <mesh ref={shadow} rotation-x={-Math.PI / 2}>
        <circleGeometry args={[BALL_RADIUS * 1.3, 16]} />
        <meshBasicMaterial color="#000" transparent opacity={quality === "high" ? 0.25 : 0.4} depthWrite={false} />
      </mesh>
    </>
  );
}

/** 0.43 kg in a 0.11 m sphere. */
const BALL_DENSITY = 0.43 / ((4 / 3) * Math.PI * BALL_RADIUS ** 3);

// ---------------------------------------------------------------------------
// Wall and keeper follow the same deterministic timeline (`wallLift`,
// keeper hands) as the trajectory function.
// ---------------------------------------------------------------------------

function Wall({ setup, shot, stage, quality }: StageProps & { quality: Quality }) {
  const bodies = useRef<(RapierRigidBody | null)[]>([]);
  const half = (WALL_PLAYER_HEIGHT - 2 * WALL_PLAYER_RADIUS) / 2;

  useFrame(() => {
    const t = shotTime(stage.current, shot);
    const end = shot?.trajectory.end.t ?? 0;
    const lift = shot && t >= 0 ? sampleAt(shot.trajectory, Math.min(t, end)).wallLift : 0;
    // After the decision the wall keeps landing on its own.
    const landing = shot && t > end ? Math.max(0, lift - (t - end) * 1.5) : lift;
    setup.wall.forEach((w, i) => {
      bodies.current[i]?.setNextKinematicTranslation({ x: w.x, y: landing + WALL_PLAYER_HEIGHT / 2, z: w.z });
    });
  });

  // Players turn to face the ball.
  const yaw = Math.atan2(setup.ball.x - setup.wall[0].x, setup.ball.z - setup.wall[0].z);

  return (
    <>
      {setup.wall.map((w, i) => (
        <group key={`${setup.seed}-${i}`}>
          <RigidBody
            ref={(rb) => {
              bodies.current[i] = rb;
            }}
            type="kinematicPosition"
            colliders={false}
            position={[w.x, WALL_PLAYER_HEIGHT / 2, w.z]}
            rotation={[0, yaw, 0]}
          >
            <CapsuleCollider args={[half, WALL_PLAYER_RADIUS]} restitution={0.3} />
            <Suspense
              fallback={
                <Footballer radius={WALL_PLAYER_RADIUS} half={half} kit="#c0392b" trim="#f8fafc" shorts="#f8fafc" socks="#c0392b" hair={WALL_HAIR[i % WALL_HAIR.length]} handsFront />
              }
            >
              {/* The model stands on its feet; the body is centred. */}
              <group position-y={-WALL_PLAYER_HEIGHT / 2}>
                <WallPlayerModel
                  jumpAt={setup.wallJumpAt}
                  phase={i * 1.3}
                  // A different line-up of faces for each position.
                  look={LOOKS[(setup.seed + i * 3) % LOOKS.length]}
                  clock={playerClock(stage, shot)} castShadow={quality === "high"} />
              </group>
            </Suspense>
          </RigidBody>
          {quality === "low" && (
            <mesh position={[w.x, 0.012, w.z]} rotation-x={-Math.PI / 2}>
              <circleGeometry args={[0.32, 12]} />
              <meshBasicMaterial color="#000" transparent opacity={0.3} depthWrite={false} />
            </mesh>
          )}
        </group>
      ))}
    </>
  );
}

const WALL_HAIR = ["#3b2a1e", "#111111", "#7a4a24", "#c9a26b"];

/** No colliders: the save is already decided (and its rebound velocity set)
 * by the trajectory, and a keeper standing next to the line would otherwise
 * knock a ball that beat him back out of the net. */
function Keeper({ setup, shot, stage }: StageProps) {
  const body = useRef<THREE.Group>(null);
  const hands = useRef<THREE.Group>(null);
  const half = 0.55;

  useFrame(() => {
    const t = shotTime(stage.current, shot);
    const s = shot && t >= 0 ? sampleAt(shot.trajectory, Math.min(t, shot.trajectory.end.t)) : null;
    const handX = s ? s.keeperHand.x : setup.keeper.x;
    const handY = s ? s.keeperHand.y : KEEPER_STAND_HAND_Y;
    const bodyX = s ? s.keeperX : setup.keeper.x;
    // A dive: the torso leans from the feet towards the hands.
    const lean = Math.atan2(handX - bodyX, Math.max(0.2, handY));
    body.current?.position.set(bodyX, KEEPER_BODY_RADIUS + half, KEEPER_LINE_Z);
    body.current?.rotation.set(0, 0, -lean);
    hands.current?.position.set(handX, handY, KEEPER_LINE_Z);
  });

  return (
    <>
      <group ref={body} position={[setup.keeper.x, KEEPER_BODY_RADIUS + half, KEEPER_LINE_Z]}>
        <Footballer radius={KEEPER_BODY_RADIUS} half={half} kit="#facc15" trim="#111827" shorts="#111827" socks="#facc15" />
      </group>
      <group ref={hands} position={[setup.keeper.x, KEEPER_STAND_HAND_Y, KEEPER_LINE_Z]}>
        {[-0.2, 0.2].map((x) => (
          <mesh key={x} position={[x, 0, 0.05]} castShadow>
            <boxGeometry args={[0.13, 0.16, 0.06]} />
            <meshStandardMaterial color="#22d3c4" roughness={0.6} />
          </mesh>
        ))}
      </group>
    </>
  );
}

/** The keeper, animated: where his hands end up comes from the trajectory
 * (he stays put for a shot the wall stops or one flying well wide/over). */
function AnimatedKeeper({ setup, shot, stage, quality }: StageProps & { quality: Quality }) {
  const traj = shot?.trajectory;
  const last = traj?.samples[traj.samples.length - 1];
  const targetX = traj && last && keeperGoesFor(traj) ? last.keeperHand.x : null;
  return (
    <KeeperModel
      setup={setup}
      targetX={targetX}
      arrival={traj?.end.t ?? 1}
      clock={playerClock(stage, shot)}
      castShadow={quality === "high"}
    />
  );
}

/** Stylised figure: shirt with trim, shorts, socks, a head; wall players
 * keep their hands in front. */
function Footballer({
  radius,
  half,
  kit,
  trim,
  shorts,
  socks,
  hair = "#3b2a1e",
  handsFront = false,
}: {
  radius: number;
  half: number;
  kit: string;
  trim: string;
  shorts: string;
  socks: string;
  hair?: string;
  handsFront?: boolean;
}) {
  const skin = "#d9a37c";
  // Legs run from under the shorts down to the ground (the capsule's bottom).
  const legTop = -half * 0.35 - 0.16;
  const legBottom = -(half + radius);
  return (
    <group>
      <mesh position={[0, 0.2, 0]} castShadow>
        <capsuleGeometry args={[radius, half * 2 - 0.65, 3, 10]} />
        <meshStandardMaterial color={kit} roughness={0.75} />
      </mesh>
      <mesh position={[0, half - 0.02, 0]}>
        <torusGeometry args={[radius * 0.55, 0.025, 6, 14]} />
        <meshStandardMaterial color={trim} roughness={0.7} />
      </mesh>
      <mesh position={[0, -half * 0.35, 0]} castShadow>
        <cylinderGeometry args={[radius * 1.02, radius * 0.95, 0.32, 10]} />
        <meshStandardMaterial color={shorts} roughness={0.8} />
      </mesh>
      {[-1, 1].map((side) => (
        <mesh key={side} position={[side * radius * 0.45, (legTop + legBottom) / 2, 0]} castShadow>
          <cylinderGeometry args={[0.075, 0.06, legTop - legBottom, 8]} />
          <meshStandardMaterial color={socks} roughness={0.8} />
        </mesh>
      ))}
      <mesh position={[0, half + radius * 0.65, 0]} castShadow>
        <sphereGeometry args={[radius * 0.6, 14, 10]} />
        <meshStandardMaterial color={skin} roughness={0.7} />
      </mesh>
      {/* Hair: the top of a slightly bigger sphere, tilted back. */}
      <mesh position={[0, half + radius * 0.68, -0.012]} rotation-x={-0.35}>
        <sphereGeometry args={[radius * 0.64, 14, 8, 0, Math.PI * 2, 0, Math.PI * 0.42]} />
        <meshStandardMaterial color={hair} roughness={0.9} />
      </mesh>
      {handsFront &&
        [-1, 1].map((side) => (
          <mesh key={side} position={[side * 0.07, -half * 0.3, radius * 0.95]}>
            <sphereGeometry args={[0.065, 8, 6]} />
            <meshStandardMaterial color={skin} roughness={0.7} />
          </mesh>
        ))}
    </group>
  );
}

// ---------------------------------------------------------------------------
// Goal: posts, a diamond net and a back panel that bulges where the ball hits.
// ---------------------------------------------------------------------------

const NET = {
  restitution: 0,
  restitutionCombineRule: CoefficientCombineRule.Min,
  friction: 2,
  frictionCombineRule: CoefficientCombineRule.Max,
};

const NET_SEG_X = 36;
const NET_SEG_Y = 12;

function GoalFrame({ stage }: { stage: MutableRefObject<Stage> }) {
  const net = useMemo(netTexture, []);
  const back = useRef<THREE.Mesh>(null);
  const resting = useRef<Float32Array | null>(null);
  const postH = GOAL_HEIGHT + POST_RADIUS;
  const w = GOAL_HALF_WIDTH * 2;

  useFrame((state) => {
    const mesh = back.current;
    const ripple = stage.current.ripple;
    if (!mesh) return;
    const pos = mesh.geometry.getAttribute("position") as THREE.BufferAttribute;
    if (!resting.current) resting.current = Float32Array.from(pos.array as Float32Array);
    const rest = resting.current;
    const age = ripple ? state.clock.getElapsedTime() - ripple.at : -1;
    if (!ripple || age > 1.7) {
      if (pos.getZ(0) !== rest[2]) {
        (pos.array as Float32Array).set(rest);
        pos.needsUpdate = true;
      }
      return;
    }
    // Plane local (x, y) ↔ goal (x, y − h/2); bulge pushes the net back (−z).
    for (let i = 0; i < pos.count; i++) {
      const x = rest[i * 3];
      const y = rest[i * 3 + 1] + GOAL_HEIGHT / 2;
      pos.setZ(i, -Math.max(0, netBulge(x - ripple.x, y - ripple.y, age)));
    }
    pos.needsUpdate = true;
  });

  const netMaterial = (
    <meshBasicMaterial map={net} transparent alphaTest={0.3} side={THREE.DoubleSide} color="#e5e7eb" />
  );

  return (
    <>
      <RigidBody type="fixed" colliders={false}>
        {[-GOAL_HALF_WIDTH, GOAL_HALF_WIDTH].map((x) => (
          <CylinderCollider key={x} args={[postH / 2, POST_RADIUS]} position={[x, postH / 2, 0]} restitution={0.65} />
        ))}
        <CylinderCollider args={[GOAL_HALF_WIDTH, POST_RADIUS]} position={[0, GOAL_HEIGHT, 0]} rotation={[0, 0, Math.PI / 2]} restitution={0.65} />
        {/* Net: back, sides and roof — dead (Min combine), so the ball drops into it. */}
        <CuboidCollider args={[GOAL_HALF_WIDTH, GOAL_HEIGHT / 2, 0.05]} position={[0, GOAL_HEIGHT / 2, -NET_DEPTH]} {...NET} />
        <CuboidCollider args={[0.05, GOAL_HEIGHT / 2, NET_DEPTH / 2]} position={[-GOAL_HALF_WIDTH - 0.05, GOAL_HEIGHT / 2, -NET_DEPTH / 2]} {...NET} />
        <CuboidCollider args={[0.05, GOAL_HEIGHT / 2, NET_DEPTH / 2]} position={[GOAL_HALF_WIDTH + 0.05, GOAL_HEIGHT / 2, -NET_DEPTH / 2]} {...NET} />
        <CuboidCollider args={[GOAL_HALF_WIDTH, 0.05, NET_DEPTH / 2]} position={[0, GOAL_HEIGHT + 0.05, -NET_DEPTH / 2]} {...NET} />
      </RigidBody>

      {[-GOAL_HALF_WIDTH, GOAL_HALF_WIDTH].map((x) => (
        <mesh key={x} position={[x, postH / 2, 0]} castShadow>
          <cylinderGeometry args={[POST_RADIUS, POST_RADIUS, postH, 12]} />
          <meshStandardMaterial color="#f8fafc" roughness={0.25} metalness={0.1} />
        </mesh>
      ))}
      <mesh position={[0, GOAL_HEIGHT, 0]} rotation-z={Math.PI / 2} castShadow>
        <cylinderGeometry args={[POST_RADIUS, POST_RADIUS, w + POST_RADIUS * 2, 12]} />
        <meshStandardMaterial color="#f8fafc" roughness={0.25} metalness={0.1} />
      </mesh>
      <mesh ref={back} position={[0, GOAL_HEIGHT / 2, -NET_DEPTH]}>
        <planeGeometry args={[w, GOAL_HEIGHT, NET_SEG_X, NET_SEG_Y]} />
        {netMaterial}
      </mesh>
      <mesh position={[0, GOAL_HEIGHT, -NET_DEPTH / 2]} rotation-x={Math.PI / 2}>
        <planeGeometry args={[w, NET_DEPTH]} />
        {netMaterial}
      </mesh>
      {[-GOAL_HALF_WIDTH, GOAL_HALF_WIDTH].map((x) => (
        <mesh key={x} position={[x, GOAL_HEIGHT / 2, -NET_DEPTH / 2]} rotation-y={Math.PI / 2}>
          <planeGeometry args={[NET_DEPTH, GOAL_HEIGHT]} />
          {netMaterial}
        </mesh>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Camera: behind the ball, then it chases the flight a little (never into
// the goal), with a short shake on wall/post hits. A portrait phone gets a
// wider vertical field of view so the whole goal still fits across.
// ---------------------------------------------------------------------------

function CameraRig({ setup, shot, stage }: StageProps) {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const aspect = useThree((s) => s.size.width / s.size.height);
  const tmp = useMemo(
    () => ({ want: new THREE.Vector3(), look: new THREE.Vector3(), lookNow: new THREE.Vector3(0, 1.1, 0) }),
    [],
  );
  const frame = useMemo(() => {
    const len = Math.hypot(setup.ball.x, setup.ball.z);
    const f = new THREE.Vector3(-setup.ball.x / len, 0, -setup.ball.z / len);
    // Behind the ball and a little to the left: over the kicker's shoulder.
    const left = new THREE.Vector3(f.z, 0, -f.x);
    const home = new THREE.Vector3(setup.ball.x, 2.0, setup.ball.z).addScaledVector(f, -4.9).addScaledVector(left, 0.8);
    return { f, home, goal: new THREE.Vector3(0, 1.1, 0) };
  }, [setup]);

  useEffect(() => {
    camera.fov = aspect < 0.8 ? 62 : 48;
    camera.updateProjectionMatrix();
  }, [camera, aspect]);

  useFrame(() => {
    const s = stage.current;
    const t = shotTime(s, shot);
    const follow = t < 0 ? 0 : Math.min(1, t / 0.9) * 0.55;
    // Chase point: a few metres behind and above the ball, kept out of the box.
    tmp.want.copy(s.ball).addScaledVector(frame.f, -4).setY(Math.max(1.4, s.ball.y + 0.9));
    tmp.want.z = Math.max(tmp.want.z, 7);
    tmp.want.lerpVectors(frame.home, tmp.want, follow);
    camera.position.lerp(tmp.want, t < 0 ? 0.12 : 0.08);
    tmp.look.lerpVectors(frame.goal, s.ball, follow * 0.6);
    tmp.lookNow.lerp(tmp.look, 0.15);
    if (s.shake > 0) {
      const a = s.shake * 0.06;
      camera.position.x += (Math.random() - 0.5) * a;
      camera.position.y += (Math.random() - 0.5) * a;
    }
    camera.lookAt(tmp.lookNow);
  });
  return null;
}

function FpsMeter({ fpsRef }: { fpsRef: MutableRefObject<HTMLSpanElement | null> }) {
  const acc = useRef({ frames: 0, time: 0 });
  useFrame((_, delta) => {
    acc.current.frames += 1;
    acc.current.time += delta;
    if (acc.current.time >= 0.5) {
      if (fpsRef.current) fpsRef.current.textContent = `${Math.round(acc.current.frames / acc.current.time)} fps`;
      acc.current = { frames: 0, time: 0 };
    }
  });
  return null;
}
