import { Environment, Lightformer, PerformanceMonitor, Trail } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Suspense, useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import * as THREE from "three";

import { aftermathAt, simulateAftermath } from "@/lib/freeKick3d/aftermath";
import { NET_DEPTH, NET_TOP_DEPTH, keeperGoesFor, netBulge, netImpact, reactionTime, replayTimeScale } from "@/lib/freeKick3d/fx";
import { playFreeKickSfx } from "@/lib/freeKick3d/sfx";
import { BOOTS, ballSkin, glovesColor } from "@/lib/gameGear";
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
} from "@/lib/freeKick3d/trajectory";
import type { FreeKickTarget } from "@/types";

import Confetti from "./Confetti";
import { KICK } from "./kickStyles";
import { LOOKS } from "./looks";
import { KeeperModel, KickerModel, WallPlayerModel, type Celebration, type PlayerClock } from "./Players";
import { Stadium, type Hype, type Quality } from "./Stadium";
import { NET_TILE, ballGeometry, netTexture } from "./textures";

export type SceneGear = { ball?: string | null; kickerBoots?: string | null; keeperGloves?: string | null };
const NO_GEAR: SceneGear = {};

export type LiveShot = { id: number; kick: KickParams; trajectory: ShotTrajectory };

type Props = {
  setup: ShotSetup;
  shot: LiveShot | null;
  /** Fired once per shot, when the replay reaches the outcome — the
   * decision, or the woodwork for a miss off it (`reactionTime`). */
  onDecided: (shotId: number) => void;
  /** The shot world is mounted (swipes are accepted from then on). */
  onReady: () => void;
  /** The FPS readout element (written from the render loop, no re-renders). */
  fpsRef: MutableRefObject<HTMLSpanElement | null>;
  /** A goal sets the stands off (confetti, «ГОЛ!» boards) — not when it's
   * the bot scoring past the player in goal. */
  cheerGoals?: boolean;
  /** Whose shirt the kicker wears. */
  kickerKit?: "home" | "away";
  /** How the kicker celebrates a goal. */
  kickerCelebration?: Celebration;
  /** The player's «Мой игрок» gear (lib/gameGear.ts codes): the ball, the
   * kicker's boots, the keeper's gloves — null/absent for the defaults. */
  gear?: SceneGear;
  /** «Испытание дня»: the ring to aim for on the goal plane, and whether
   * the shot went in it (null until the server says). */
  target?: FreeKickTarget | null;
  targetHit?: boolean | null;
  /** Current shot time, written every frame (−1 while waiting): the page
   * times the player's dive against the strike with it. */
  shotClockRef?: MutableRefObject<number>;
};


/** Shot time runs on its own clock so the replay can slow down near the
 * goal (−1 = waiting for a kick). */
type ShotClock = { shotId: number; t: number; decided: boolean; decidedAt: number; announced: boolean };

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

export default function FreeKickScene3D({
  setup,
  shot,
  onDecided,
  onReady,
  fpsRef,
  cheerGoals = true,
  kickerKit = "home",
  kickerCelebration = "celebrate",
  gear = NO_GEAR,
  target = null,
  targetHit = null,
  shotClockRef,
}: Props) {
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
      <ShotWorld
        setup={setup}
        shot={shot}
        onDecided={onDecided}
        onReady={onReady}
        quality={quality}
        hype={hype}
        cheerGoals={cheerGoals}
        kickerKit={kickerKit}
        kickerCelebration={kickerCelebration}
        gear={gear}
        target={target}
        targetHit={targetHit}
        shotClockRef={shotClockRef}
      />
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
      {/* Rim: the floodlights behind the goal outline the players (the kicker
          is seen from behind) against the dark stands. */}
      <directionalLight position={[-6, 14, -40]} intensity={1.1} color="#dfe8ff" />
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
  cheerGoals = true,
  kickerKit = "home",
  kickerCelebration = "celebrate",
  gear = NO_GEAR,
  target = null,
  targetHit = null,
  shotClockRef,
}: Omit<Props, "fpsRef"> & { quality: Quality; hype: Hype }) {
  const stage = useRef<Stage>({
    clock: { shotId: -1, t: -1, decided: false, decidedAt: 0, announced: false },
    dt: 0,
    ball: new THREE.Vector3(setup.ball.x, setup.ball.y, setup.ball.z),
    shake: 0,
    ripple: null,
  });
  const [confetti, setConfetti] = useState(0);

  // Restarts per shot id, not per object: a penalty's trajectory is swapped
  // mid-flight when the player dives, without restarting the clock.
  const shotId = shot?.id ?? null;
  useEffect(() => {
    // A shot starts with the kicker's run-up: the ball leaves at t = 0.
    // The kick clip is cued so its contact frame lands on shot time 0.
    stage.current.clock = {
      shotId: shotId ?? -1, t: shotId !== null ? -KICK.lead : -1, decided: false, decidedAt: 0, announced: false,
    };
    stage.current.ripple = null;
  }, [shotId]);
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
    if (shotClockRef) shotClockRef.current = shot && c.shotId === shot.id ? c.t : -1;
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
        // The stands go wild only for the player's own goal — not when the
        // bot scores past them in goal.
        if (cheerGoals) {
          hype.current = 1;
          setConfetti((n) => n + 1);
        }
        setTimeout(() => playFreeKickSfx("net"), travel * 1000);
      }
    }
    if (!c.announced && c.t >= reactionTime(traj)) {
      c.announced = true;
      onDecided(shot.id);
    }
  }, -1);

  return (
    <>
      <GoalFrame stage={stage} />
      <Wall setup={setup} shot={shot} stage={stage} quality={quality} />
      <Suspense fallback={<Keeper setup={setup} shot={shot} stage={stage} />}>
        <AnimatedKeeper setup={setup} shot={shot} stage={stage} quality={quality} gloves={glovesColor(gear.keeperGloves)} />
      </Suspense>
      <Suspense fallback={null}>
        <KickerModel
          setup={setup}
          clock={playerClock(stage, shot)}
          kicking={shot !== null}
          celebrateAt={shot?.trajectory.outcome === "goal" ? shot.trajectory.end.t + 0.6 : null}
          kit={kickerKit}
          celebration={kickerCelebration}
          boots={(gear.kickerBoots && BOOTS[gear.kickerBoots]) || null}
          castShadow={quality === "high"}
        />
      </Suspense>
      <Ball setup={setup} shot={shot} stage={stage} quality={quality} skin={gear.ball} />
      {target && <TargetRing target={target} hit={targetHit} />}
      <CameraRig setup={setup} shot={shot} stage={stage} />
      <Confetti burstId={confetti} />
    </>
  );
}

/** «Испытание дня»: a glowing ring on the goal plane (just in front of
 * the line) that pulses while you aim — it's small from 25 m — gold once
 * the shot has gone in it. */
function TargetRing({ target, hit }: { target: FreeKickTarget; hit: boolean | null }) {
  const color = hit ? "#facc15" : hit === false ? "#94a3b8" : "#c6e63a";
  const pulse = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    const m = pulse.current;
    if (!m) return;
    const k = (state.clock.getElapsedTime() % 1.2) / 1.2;
    m.scale.setScalar(1 + k * 0.6);
    (m.material as THREE.MeshBasicMaterial).opacity = hit === null ? 0.7 * (1 - k) : 0;
  });
  return (
    <group position={[target.x, target.y, 0.02]}>
      <mesh ref={pulse}>
        <ringGeometry args={[target.r - 0.06, target.r, 48]} />
        <meshBasicMaterial color={color} transparent opacity={0.7} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh>
        <ringGeometry args={[target.r - 0.14, target.r, 48]} />
        <meshBasicMaterial color={color} transparent opacity={0.95} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh>
        <ringGeometry args={[target.r * 0.45 - 0.05, target.r * 0.45, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.8} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh>
        <circleGeometry args={[target.r, 48]} />
        <meshBasicMaterial color={color} transparent opacity={0.14} depthWrite={false} toneMapped={false} />
      </mesh>
    </group>
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
// trail showing the curl), then the deterministic aftermath — into the
// net, off the wall, rolling out. No physics engine: Rapier panicked
// inside its WASM step on phones, and it was only ever cosmetic here.
// ---------------------------------------------------------------------------

function Ball({ setup, shot, stage, quality, skin: skinCode }: StageProps & { quality: Quality; skin?: string | null }) {
  const mesh = useRef<THREE.Mesh>(null);
  const shadow = useRef<THREE.Mesh>(null);
  const skin = ballSkin(skinCode);
  const geometry = useMemo(() => ballGeometry(skin.light, skin.dark), [skin]);
  const aftermath = useMemo(() => (shot ? simulateAftermath(setup, shot.trajectory) : null), [setup, shot]);
  const [decided, setDecided] = useState<number | null>(null);

  useFrame((_, delta) => {
    const ball = mesh.current;
    if (!ball) return;
    const s = stage.current;
    const t = shotTime(s, shot);
    if (!shot || !aftermath || t < 0) {
      ball.position.set(setup.ball.x, setup.ball.y, setup.ball.z);
      ball.rotation.set(0, 0, 0);
    } else {
      const traj = shot.trajectory;
      const p = t <= traj.end.t ? sampleAt(traj, t).ball : aftermathAt(aftermath, t);
      const moved = Math.hypot(p.x - ball.position.x, p.z - ball.position.z);
      ball.position.set(p.x, p.y, p.z);
      // Visual spin: around the spin axis plus a roll as fast as it moves.
      ball.rotation.y += shot.kick.spin.y * delta * (t <= traj.end.t ? 0.25 : 0.05);
      ball.rotation.x -= moved / BALL_RADIUS;
      if (s.clock.decided && decided !== shot.id) setDecided(shot.id);
    }
    s.ball.copy(ball.position);
    if (shadow.current) {
      shadow.current.position.set(ball.position.x, 0.012, ball.position.z);
      shadow.current.scale.setScalar(Math.max(0.35, 1 - ball.position.y * 0.12));
    }
  });

  // The light trail only while the shot flies.
  const flying = shot !== null && decided !== shot.id;

  return (
    <>
      <mesh ref={mesh} geometry={geometry} castShadow>
        <meshStandardMaterial vertexColors roughness={skin.roughness} metalness={skin.metalness} envMapIntensity={0.8} />
      </mesh>
      {flying && (
        <Trail key={shot.id} target={mesh as MutableRefObject<THREE.Object3D>} width={0.9} length={5} color="#c6e63a" attenuation={(w) => w * w} decay={1.2} />
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

// ---------------------------------------------------------------------------
// Wall and keeper follow the same deterministic timeline (`wallLift`,
// keeper hands) as the trajectory function.
// ---------------------------------------------------------------------------

function Wall({ setup, shot, stage, quality }: StageProps & { quality: Quality }) {
  const bodies = useRef<(THREE.Group | null)[]>([]);
  const half = (WALL_PLAYER_HEIGHT - 2 * WALL_PLAYER_RADIUS) / 2;

  useFrame(() => {
    const t = shotTime(stage.current, shot);
    const end = shot?.trajectory.end.t ?? 0;
    const lift = shot && t >= 0 ? sampleAt(shot.trajectory, Math.min(t, end)).wallLift : 0;
    // After the decision the wall keeps landing on its own.
    const landing = shot && t > end ? Math.max(0, lift - (t - end) * 1.5) : lift;
    setup.wall.forEach((w, i) => {
      bodies.current[i]?.position.set(w.x, landing + WALL_PLAYER_HEIGHT / 2, w.z);
    });
  });

  // Players turn to face the ball (a penalty has no wall).
  const first = setup.wall[0];
  const yaw = first ? Math.atan2(setup.ball.x - first.x, setup.ball.z - first.z) : 0;

  return (
    <>
      {setup.wall.map((w, i) => (
        <group key={`${setup.seed}-${i}`}>
          <group
            ref={(g) => {
              bodies.current[i] = g;
            }}
            position={[w.x, WALL_PLAYER_HEIGHT / 2, w.z]}
            rotation={[0, yaw, 0]}
          >
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
          </group>
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
function AnimatedKeeper({ setup, shot, stage, quality, gloves }: StageProps & { quality: Quality; gloves: string }) {
  const traj = shot?.trajectory;
  const last = traj?.samples[traj.samples.length - 1];
  const targetX = traj && last && keeperGoesFor(traj) ? last.keeperHand.x : null;
  return (
    <KeeperModel
      setup={setup}
      targetX={targetX}
      targetY={last?.keeperHand.y ?? KEEPER_STAND_HAND_Y}
      arrival={traj?.end.t ?? 1}
      saved={traj?.outcome === "save"}
      clock={playerClock(stage, shot)}
      castShadow={quality === "high"}
      gloves={gloves}
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

const NET_SEG_X = 36;
const NET_SEG_Y = 12;

/** The back net's slope: from the roof's rear edge down to the grass. */
const NET_SLOPE_RISE = NET_DEPTH - NET_TOP_DEPTH;
const NET_SLOPE_LEN = Math.hypot(GOAL_HEIGHT, NET_SLOPE_RISE);
const NET_SLOPE_ANGLE = Math.atan2(NET_SLOPE_RISE, GOAL_HEIGHT);

/** A net texture repeated so its cells come out the same size on a surface
 * `uSpan` × `vSpan` metres (UVs 0..1), or with UVs in metres (spans 1). */
function useNet(uSpan: number, vSpan: number) {
  return useMemo(() => {
    const tex = netTexture();
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(uSpan / NET_TILE.w, vSpan / NET_TILE.h);
    return tex;
  }, [uSpan, vSpan]);
}

/** A thin tube from `a` to `b` (the goal's rear supports). */
function Tube({ a, b, r = 0.028 }: { a: [number, number, number]; b: [number, number, number]; r?: number }) {
  const { position, quaternion, length } = useMemo(() => {
    const va = new THREE.Vector3(...a);
    const vb = new THREE.Vector3(...b);
    const dir = vb.clone().sub(va);
    return {
      position: va.clone().add(vb).multiplyScalar(0.5),
      quaternion: new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize()),
      length: dir.length(),
    };
    // The points are literals per call site; their values are the identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a.join(), b.join()]);
  return (
    <mesh position={position} quaternion={quaternion} castShadow>
      <cylinderGeometry args={[r, r, length, 8]} />
      <meshStandardMaterial color="#dfe3ea" roughness={0.4} metalness={0.2} />
    </mesh>
  );
}

function GoalFrame({ stage }: { stage: MutableRefObject<Stage> }) {
  const w = GOAL_HALF_WIDTH * 2;
  const backNet = useNet(w, NET_SLOPE_LEN);
  const roofNet = useNet(w, NET_TOP_DEPTH);
  const sideNet = useNet(1, 1); // the side shapes carry UVs in metres
  const back = useRef<THREE.Mesh>(null);
  const resting = useRef<Float32Array | null>(null);
  const postH = GOAL_HEIGHT + POST_RADIUS;
  // A side net: the goal's profile — post, roof, slope, grass.
  const side = useMemo(() => {
    const shape = new THREE.Shape();
    shape.moveTo(0, 0);
    shape.lineTo(0, GOAL_HEIGHT);
    shape.lineTo(NET_TOP_DEPTH, GOAL_HEIGHT);
    shape.lineTo(NET_DEPTH, 0);
    shape.closePath();
    return new THREE.ShapeGeometry(shape);
  }, []);

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
    // Plane local (x, along the slope) ↔ goal (x, height); the bulge pushes
    // the net outwards (local −z).
    for (let i = 0; i < pos.count; i++) {
      const x = rest[i * 3];
      const y = ((rest[i * 3 + 1] + NET_SLOPE_LEN / 2) / NET_SLOPE_LEN) * GOAL_HEIGHT;
      pos.setZ(i, -Math.max(0, netBulge(x - ripple.x, y - ripple.y, age)));
    }
    pos.needsUpdate = true;
  });

  const netMaterial = (tex: THREE.Texture) => (
    <meshBasicMaterial map={tex} transparent alphaTest={0.25} side={THREE.DoubleSide} color="#eef1f5" />
  );

  return (
    <>

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
      {/* Back net: sloping from the roof's rear edge down to the grass. */}
      <mesh
        ref={back}
        position={[0, GOAL_HEIGHT / 2, -(NET_DEPTH + NET_TOP_DEPTH) / 2]}
        rotation-x={NET_SLOPE_ANGLE}
      >
        <planeGeometry args={[w, NET_SLOPE_LEN, NET_SEG_X, NET_SEG_Y]} />
        {netMaterial(backNet)}
      </mesh>
      <mesh position={[0, GOAL_HEIGHT, -NET_TOP_DEPTH / 2]} rotation-x={Math.PI / 2}>
        <planeGeometry args={[w, NET_TOP_DEPTH]} />
        {netMaterial(roofNet)}
      </mesh>
      {[-GOAL_HALF_WIDTH, GOAL_HALF_WIDTH].map((x) => (
        <mesh key={x} geometry={side} position={[x, 0, 0]} rotation-y={Math.PI / 2}>
          {netMaterial(sideNet)}
        </mesh>
      ))}
      {/* The rear frame the net hangs on. */}
      {[-GOAL_HALF_WIDTH, GOAL_HALF_WIDTH].map((x) => (
        <group key={x}>
          <Tube a={[x, GOAL_HEIGHT, 0]} b={[x, GOAL_HEIGHT, -NET_TOP_DEPTH]} />
          <Tube a={[x, GOAL_HEIGHT, -NET_TOP_DEPTH]} b={[x, 0.03, -NET_DEPTH]} />
        </group>
      ))}
      <Tube a={[-GOAL_HALF_WIDTH, GOAL_HEIGHT, -NET_TOP_DEPTH]} b={[GOAL_HALF_WIDTH, GOAL_HEIGHT, -NET_TOP_DEPTH]} r={0.022} />
      <Tube a={[-GOAL_HALF_WIDTH, 0.03, -NET_DEPTH]} b={[GOAL_HALF_WIDTH, 0.03, -NET_DEPTH]} r={0.03} />
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
