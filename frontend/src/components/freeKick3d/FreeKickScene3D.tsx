import { PerformanceMonitor } from "@react-three/drei";
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
import { Suspense, useEffect, useMemo, useRef, useState, type MutableRefObject, type Ref } from "react";
import * as THREE from "three";

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

const NET_DEPTH = 2;
const PITCH_COLORS = ["#2f8f4e", "#37a35a"];

/** Shared clock: seconds since the current shot was kicked (−1 = waiting). */
type ShotClock = { shotId: number; startedAt: number; decided: boolean };

export default function FreeKickScene3D({ setup, shot, onDecided, onReady, fpsRef }: Props) {
  const [dpr, setDpr] = useState(1.5);
  return (
    <Canvas
      dpr={dpr}
      gl={{ antialias: false, powerPreference: "high-performance", stencil: false }}
      camera={{ fov: 50, near: 0.1, far: 200 }}
      style={{ touchAction: "none" }}
    >
      {/* Mid Android: start at 1.5× and step down to 1× if the frame rate sags. */}
      <PerformanceMonitor onDecline={() => setDpr(1)} onIncline={() => setDpr(1.5)} />
      <color attach="background" args={["#0d1b2a"]} />
      <fog attach="fog" args={["#0d1b2a", 45, 110]} />
      <hemisphereLight args={["#dbeafe", "#1f4d2c", 1.1]} />
      <directionalLight position={[8, 20, 12]} intensity={1.4} />
      <Pitch />
      <Stands />
      <CameraRig setup={setup} />
      {/* Rapier's WASM loads asynchronously: the scenery shows meanwhile. */}
      <Suspense fallback={null}>
        <Physics gravity={[0, -9.81, 0]} timeStep={1 / 60}>
          <ShotWorld setup={setup} shot={shot} onDecided={onDecided} onReady={onReady} />
        </Physics>
      </Suspense>
      <FpsMeter fpsRef={fpsRef} />
    </Canvas>
  );
}

function ShotWorld({ setup, shot, onDecided, onReady }: Omit<Props, "fpsRef">) {
  const clock = useRef<ShotClock>({ shotId: -1, startedAt: 0, decided: false });
  const elapsed = useThree((s) => s.clock);
  useEffect(() => {
    clock.current = { shotId: shot?.id ?? -1, startedAt: elapsed.getElapsedTime(), decided: false };
  }, [shot, elapsed]);
  useEffect(onReady, [onReady]);

  return (
    <>
      <GoalFrame />
      <Wall setup={setup} shot={shot} clock={clock} />
      <Keeper setup={setup} shot={shot} clock={clock} />
      <Ball setup={setup} shot={shot} clock={clock} onDecided={onDecided} />
      {/* Ground for the post-outcome physics. */}
      <RigidBody type="fixed" colliders={false}>
        <CuboidCollider args={[60, 0.5, 60]} position={[0, -0.5, 20]} restitution={0.5} friction={0.8} />
      </RigidBody>
    </>
  );
}

function shotTime(clock: ShotClock, now: number) {
  return clock.shotId < 0 ? -1 : now - clock.startedAt;
}

// ---------------------------------------------------------------------------
// Ball: a plain mesh replaying the deterministic samples; at the decided
// moment a fresh dynamic Rapier body takes over (so the ball drops into the
// net or bounces off the wall naturally — purely cosmetic, the outcome is
// already set). Remounting per shot avoids flipping one body's type.
// ---------------------------------------------------------------------------

type Released = { shotId: number; position: Vec3; velocity: Vec3; spin: Vec3 };

function Ball({ setup, shot, clock, onDecided }: Omit<Props, "fpsRef" | "onReady"> & { clock: MutableRefObject<ShotClock> }) {
  const flight = useRef<THREE.Mesh>(null);
  const body = useRef<RapierRigidBody>(null);
  const shadow = useRef<THREE.Mesh>(null);
  const texture = useMemo(ballTexture, []);
  const [released, setReleased] = useState<Released | null>(null);
  const live = released !== null && released.shotId === shot?.id ? released : null;

  useFrame((state, delta) => {
    const mesh = flight.current;
    if (!mesh) return;
    const c = clock.current;
    const t = shotTime(c, state.clock.getElapsedTime());
    if (!shot || t < 0) {
      mesh.position.set(setup.ball.x, setup.ball.y, setup.ball.z);
      mesh.rotation.set(0, 0, 0);
    } else if (!c.decided) {
      const traj = shot.trajectory;
      const s = sampleAt(traj, Math.min(t, traj.end.t));
      mesh.position.set(s.ball.x, s.ball.y, s.ball.z);
      // Visual spin: around the spin axis plus a forward roll.
      mesh.rotation.y += shot.kick.spin.y * delta * 0.25;
      mesh.rotation.x -= delta * 18;
      if (t >= traj.end.t) {
        c.decided = true;
        const v = traj.end.velocity;
        setReleased({
          shotId: shot.id,
          position: traj.end.position,
          velocity: v,
          spin: { x: -v.z / BALL_RADIUS / 4, y: shot.kick.spin.y, z: 0 },
        });
        onDecided(shot.id);
      }
    }
    if (shadow.current) {
      const p = live && body.current ? body.current.translation() : mesh.position;
      shadow.current.position.set(p.x, 0.012, p.z);
      shadow.current.scale.setScalar(Math.max(0.35, 1 - p.y * 0.12));
    }
  });

  const ballMesh = (ref?: Ref<THREE.Mesh>) => (
    <mesh ref={ref}>
      <icosahedronGeometry args={[BALL_RADIUS, 1]} />
      <meshLambertMaterial map={texture} flatShading />
    </mesh>
  );

  return (
    <>
      <group visible={!live}>{ballMesh(flight)}</group>
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
          {ballMesh()}
        </RigidBody>
      )}
      <mesh ref={shadow} rotation-x={-Math.PI / 2}>
        <circleGeometry args={[BALL_RADIUS * 1.2, 12]} />
        <meshBasicMaterial color="#000" transparent opacity={0.35} depthWrite={false} />
      </mesh>
    </>
  );
}

/** 0.43 kg in a 0.11 m sphere. */
const BALL_DENSITY = 0.43 / ((4 / 3) * Math.PI * BALL_RADIUS ** 3);

// ---------------------------------------------------------------------------
// Wall and keeper: kinematic bodies that follow the same deterministic
// timeline (`wallLift`, keeper hands) as the trajectory function.
// ---------------------------------------------------------------------------

function Wall({ setup, shot, clock }: { setup: ShotSetup; shot: LiveShot | null; clock: MutableRefObject<ShotClock> }) {
  const bodies = useRef<(RapierRigidBody | null)[]>([]);
  const half = (WALL_PLAYER_HEIGHT - 2 * WALL_PLAYER_RADIUS) / 2;

  useFrame((state) => {
    const t = shotTime(clock.current, state.clock.getElapsedTime());
    const lift = shot && t >= 0 ? sampleAt(shot.trajectory, Math.min(t, shot.trajectory.end.t)).wallLift : 0;
    // After the decision the wall keeps landing on its own timeline.
    const landing = shot && t > shot.trajectory.end.t ? Math.max(0, lift - (t - shot.trajectory.end.t) * 1.5) : lift;
    setup.wall.forEach((w, i) => {
      bodies.current[i]?.setNextKinematicTranslation({ x: w.x, y: landing + WALL_PLAYER_HEIGHT / 2, z: w.z });
    });
  });

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
          >
            <CapsuleCollider args={[half, WALL_PLAYER_RADIUS]} restitution={0.3} />
            <Footballer radius={WALL_PLAYER_RADIUS} half={half} kit="#d64545" shorts="#f8fafc" />
          </RigidBody>
          <mesh position={[w.x, 0.012, w.z]} rotation-x={-Math.PI / 2}>
            <circleGeometry args={[0.32, 12]} />
            <meshBasicMaterial color="#000" transparent opacity={0.3} depthWrite={false} />
          </mesh>
        </group>
      ))}
    </>
  );
}

/** No colliders: the save is already decided (and its rebound velocity set)
 * by the trajectory, and a keeper standing next to the line would otherwise
 * knock a ball that beat him back out of the net. */
function Keeper({ setup, shot, clock }: { setup: ShotSetup; shot: LiveShot | null; clock: MutableRefObject<ShotClock> }) {
  const body = useRef<RapierRigidBody>(null);
  const hands = useRef<RapierRigidBody>(null);
  const half = 0.55;
  const tilt = useMemo(() => ({ euler: new THREE.Euler(), quat: new THREE.Quaternion() }), []);

  useFrame((state) => {
    const t = shotTime(clock.current, state.clock.getElapsedTime());
    const s = shot && t >= 0 ? sampleAt(shot.trajectory, Math.min(t, shot.trajectory.end.t)) : null;
    const handX = s ? s.keeperHand.x : setup.keeper.x;
    const handY = s ? s.keeperHand.y : KEEPER_STAND_HAND_Y;
    const bodyX = s ? s.keeperX : setup.keeper.x;
    // A dive: the torso leans from the feet towards the hands.
    const lean = Math.atan2(handX - bodyX, Math.max(0.2, handY));
    body.current?.setNextKinematicTranslation({ x: bodyX, y: KEEPER_BODY_RADIUS + half, z: KEEPER_LINE_Z });
    body.current?.setNextKinematicRotation(tilt.quat.setFromEuler(tilt.euler.set(0, 0, -lean)));
    hands.current?.setNextKinematicTranslation({ x: handX, y: handY, z: KEEPER_LINE_Z });
  });

  return (
    <>
      <RigidBody ref={body} type="kinematicPosition" colliders={false} position={[setup.keeper.x, KEEPER_BODY_RADIUS + half, KEEPER_LINE_Z]}>
        <Footballer radius={KEEPER_BODY_RADIUS} half={half} kit="#facc15" shorts="#111827" />
      </RigidBody>
      <RigidBody ref={hands} type="kinematicPosition" colliders={false} position={[setup.keeper.x, KEEPER_STAND_HAND_Y, KEEPER_LINE_Z]}>
        <mesh position={[-0.18, 0, 0]}>
          <icosahedronGeometry args={[0.11, 0]} />
          <meshLambertMaterial color="#22d3c4" flatShading />
        </mesh>
        <mesh position={[0.18, 0, 0]}>
          <icosahedronGeometry args={[0.11, 0]} />
          <meshLambertMaterial color="#22d3c4" flatShading />
        </mesh>
      </RigidBody>
    </>
  );
}

/** Low-poly figure on a capsule: body, shorts and a head. */
function Footballer({ radius, half, kit, shorts }: { radius: number; half: number; kit: string; shorts: string }) {
  return (
    <>
      <mesh position={[0, 0.12, 0]}>
        <capsuleGeometry args={[radius, half * 2 - 0.5, 2, 8]} />
        <meshLambertMaterial color={kit} flatShading />
      </mesh>
      <mesh position={[0, -half + 0.05, 0]}>
        <capsuleGeometry args={[radius * 0.85, 0.3, 2, 8]} />
        <meshLambertMaterial color={shorts} flatShading />
      </mesh>
      <mesh position={[0, half + radius * 0.55, 0]}>
        <icosahedronGeometry args={[radius * 0.62, 1]} />
        <meshLambertMaterial color="#e0b48c" flatShading />
      </mesh>
    </>
  );
}

// ---------------------------------------------------------------------------
// Static scenery
// ---------------------------------------------------------------------------

const NET = {
  restitution: 0,
  restitutionCombineRule: CoefficientCombineRule.Min,
  friction: 2,
  frictionCombineRule: CoefficientCombineRule.Max,
};

function GoalFrame() {
  const net = useMemo(netTexture, []);
  const postH = GOAL_HEIGHT + POST_RADIUS;
  const w = GOAL_HALF_WIDTH * 2;
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
        <mesh key={x} position={[x, postH / 2, 0]}>
          <cylinderGeometry args={[POST_RADIUS, POST_RADIUS, postH, 8]} />
          <meshLambertMaterial color="#f8fafc" />
        </mesh>
      ))}
      <mesh position={[0, GOAL_HEIGHT, 0]} rotation-z={Math.PI / 2}>
        <cylinderGeometry args={[POST_RADIUS, POST_RADIUS, w + POST_RADIUS * 2, 8]} />
        <meshLambertMaterial color="#f8fafc" />
      </mesh>
      <group>
        <mesh position={[0, GOAL_HEIGHT / 2, -NET_DEPTH]}>
          <planeGeometry args={[w, GOAL_HEIGHT]} />
          <meshBasicMaterial map={net} transparent alphaTest={0.3} side={THREE.DoubleSide} />
        </mesh>
        <mesh position={[0, GOAL_HEIGHT, -NET_DEPTH / 2]} rotation-x={Math.PI / 2}>
          <planeGeometry args={[w, NET_DEPTH]} />
          <meshBasicMaterial map={net} transparent alphaTest={0.3} side={THREE.DoubleSide} />
        </mesh>
        {[-GOAL_HALF_WIDTH, GOAL_HALF_WIDTH].map((x) => (
          <mesh key={x} position={[x, GOAL_HEIGHT / 2, -NET_DEPTH / 2]} rotation-y={Math.PI / 2}>
            <planeGeometry args={[NET_DEPTH, GOAL_HEIGHT]} />
            <meshBasicMaterial map={net} transparent alphaTest={0.3} side={THREE.DoubleSide} />
          </mesh>
        ))}
      </group>
    </>
  );
}

function Pitch() {
  const texture = useMemo(pitchTexture, []);
  return (
    <mesh rotation-x={-Math.PI / 2} position={[0, 0, PITCH_Z0 + PITCH_DEPTH / 2]}>
      <planeGeometry args={[PITCH_WIDTH, PITCH_DEPTH]} />
      <meshLambertMaterial map={texture} />
    </mesh>
  );
}

function Stands() {
  return (
    <>
      {/* LED boards behind the goal and two tiers of stands. */}
      <mesh position={[0, 0.45, -6]}>
        <boxGeometry args={[44, 0.9, 0.2]} />
        <meshBasicMaterial color="#3ed17e" />
      </mesh>
      <mesh position={[0, 4, -12]} rotation-x={-0.5}>
        <boxGeometry args={[70, 10, 1]} />
        <meshLambertMaterial color="#1e293b" flatShading />
      </mesh>
      <mesh position={[0, 11, -18]} rotation-x={-0.35}>
        <boxGeometry args={[80, 8, 1]} />
        <meshLambertMaterial color="#334155" flatShading />
      </mesh>
      {[-1, 1].map((side) => (
        <mesh key={side} position={[side * 34, 4, 12]} rotation-z={side * 0.5}>
          <boxGeometry args={[1, 10, 50]} />
          <meshLambertMaterial color="#1e293b" flatShading />
        </mesh>
      ))}
    </>
  );
}

/** Behind the ball, looking at the goal. A portrait phone gets a wider
 * vertical field of view so the whole goal still fits across. */
function CameraRig({ setup }: { setup: ShotSetup }) {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const aspect = useThree((s) => s.size.width / s.size.height);
  const goal = useMemo(() => new THREE.Vector3(0, 1.1, 0), []);
  const home = useMemo(() => {
    const len = Math.hypot(setup.ball.x, setup.ball.z);
    const fx = -setup.ball.x / len;
    const fz = -setup.ball.z / len;
    return new THREE.Vector3(setup.ball.x - fx * 3.4, 1.7, setup.ball.z - fz * 3.4);
  }, [setup]);

  useEffect(() => {
    camera.fov = aspect < 0.8 ? 62 : 48;
    camera.updateProjectionMatrix();
  }, [camera, aspect]);

  useFrame(() => {
    camera.position.lerp(home, 0.1);
    camera.lookAt(goal);
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

// ---------------------------------------------------------------------------
// Procedural textures (one canvas each, built once — no image downloads).
// ---------------------------------------------------------------------------

const PITCH_WIDTH = 80;
const PITCH_DEPTH = 64;
const PITCH_Z0 = -12;
const PX_PER_M = 12;

function pitchTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = PITCH_WIDTH * PX_PER_M;
  canvas.height = PITCH_DEPTH * PX_PER_M;
  const ctx = canvas.getContext("2d")!;
  // World (x, z) → canvas px: the plane is rotated −90° about x, so with the
  // default flipY the canvas's top row lands on the far (−z) edge.
  const X = (x: number) => (x + PITCH_WIDTH / 2) * PX_PER_M;
  const Z = (z: number) => (z - PITCH_Z0) * PX_PER_M;
  const stripe = 5.5;
  for (let i = 0; i * stripe < PITCH_DEPTH; i++) {
    ctx.fillStyle = PITCH_COLORS[i % 2];
    ctx.fillRect(0, i * stripe * PX_PER_M, canvas.width, stripe * PX_PER_M + 1);
  }
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.lineWidth = 0.12 * PX_PER_M;
  ctx.beginPath();
  // Goal line, penalty box, goal area, penalty spot, arc.
  ctx.moveTo(0, Z(0));
  ctx.lineTo(canvas.width, Z(0));
  ctx.rect(X(-20.16), Z(0), 40.32 * PX_PER_M, 16.5 * PX_PER_M);
  ctx.rect(X(-9.16), Z(0), 18.32 * PX_PER_M, 5.5 * PX_PER_M);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(X(0), Z(11), 9.15 * PX_PER_M, 0.2 * Math.PI, 0.8 * Math.PI);
  ctx.stroke();
  ctx.fillStyle = "#fff";
  ctx.beginPath();
  ctx.arc(X(0), Z(11), 0.15 * PX_PER_M, 0, Math.PI * 2);
  ctx.fill();
  const tex = new THREE.CanvasTexture(canvas);
  tex.anisotropy = 4;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function netTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 128;
  const ctx = canvas.getContext("2d")!;
  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.lineWidth = 2;
  const cell = 10;
  for (let x = 0; x <= canvas.width; x += cell) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.stroke();
  }
  for (let y = 0; y <= canvas.height; y += cell) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(canvas.width, y);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function ballTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#f8fafc";
  ctx.fillRect(0, 0, 128, 64);
  ctx.fillStyle = "#111827";
  for (const [x, y] of [[16, 16], [56, 40], [96, 16], [36, 56], [76, 8], [116, 48]]) {
    ctx.beginPath();
    ctx.arc(x, y, 9, 0, Math.PI * 2);
    ctx.fill();
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
