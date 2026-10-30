/** The three.js scene of a goal replay: pitch and stands, both goals,
 * 22 low-poly footballers (instanced: one draw call per body part), the
 * ball and a camera that follows it. Everything is placed from the
 * episode's key frames (lib/goalReplay3d) once per rendered frame; React
 * never re-renders during playback. */
import { useFrame, useThree } from "@react-three/fiber";
import { Component, Suspense, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import * as THREE from "three";

import {
  BALL_R,
  CROSSBAR,
  FPS_JUDGE,
  GOAL_HALF,
  NET_DEPTH,
  advance,
  ballState,
  cameraPose,
  judgeFps,
  toWorld,
  type CameraMode,
  type GoalEpisode,
} from "@/lib/goalReplay3d";
import type { CareerReplay } from "@/api/career";
import { poseTime } from "@/lib/footballerMotion";
import { PITCH_L, PITCH_W, SLOTS, interpolatePlayer, type Timeline } from "@/lib/matchReplay";

import { SkinnedPlayers } from "./SkinnedPlayers";
import { crowdTexture, netTexture, numberTexture, pitchTexture } from "./textures";

export interface ReplayClock { t: number; playing: boolean; ended: boolean }

export interface Kit { fill: string; text: string; gk: string; shorts: string }

export interface SlotLook { kit: Kit; n: number; keeper: boolean }

/** Game seconds per key frame (career_replay_service.STEP). */
const STEP_S = 0.5;
const HIP_Y = 0.9;
const SHOULDER_Y = 1.47;
const BALL_DRAW_R = BALL_R * 1.2; // a touch bigger than life, next to life-size players
const SKIN = ["#f1c7a1", "#c98e62", "#8a5a3b"];

/** "skinned": animated Mixamo footballers; "simple": the instanced low-poly
 * figures (while the model loads, if it can't, or on a slow phone). */
export type Figures = "skinned" | "simple";

export interface SceneProps {
  tl: Timeline;
  replay: CareerReplay;
  ep: GoalEpisode;
  flip: boolean;
  looks: SlotLook[];
  mode: CameraMode;
  clock: MutableRefObject<ReplayClock>;
  /** 0-1 progress of the episode, every frame (writes the DOM directly). */
  onProgress: (u: number) => void;
  onEnded: () => void;
  fpsRef?: MutableRefObject<HTMLSpanElement | null>;
  /** Start with these figures (?figures=simple to compare). */
  figures?: Figures;
}

/** Falls back to the simple figures if the model can't load or build. */
class FigureBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error) {
    console.warn("3D footballer model failed, simple figures instead:", error);
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function GoalScene(props: SceneProps) {
  const { tl, replay, ep, flip, looks, mode, clock, onProgress, onEnded, fpsRef } = props;
  const [figures, setFigures] = useState<Figures>(props.figures ?? "skinned");
  // The animated models are on screen (fps is judged from then on).
  const ready = useRef(figures === "simple");
  const simple = <Players tl={tl} ep={ep} flip={flip} looks={looks} clock={clock} />;
  const goalX = toWorld({ x: PITCH_W / 2, y: ep.side === "a" ? PITCH_L : 0 }, flip).x;
  return (
    <>
      <ClockDriver ep={ep} clock={clock} onProgress={onProgress} onEnded={onEnded} />
      <color attach="background" args={["#0b1424"]} />
      <fog attach="fog" args={["#0b1424", 90, 190]} />
      <hemisphereLight args={["#e8f0ff", "#24452c", 1.6]} />
      <directionalLight position={[25, 60, 30]} intensity={1.9} />
      <Stadium />
      <Goal x={PITCH_L / 2} ep={ep} clock={clock} scored={goalX > 0} />
      <Goal x={-PITCH_L / 2} ep={ep} clock={clock} scored={goalX < 0} />
      {figures === "skinned" ? (
        <FigureBoundary fallback={simple}>
          <Suspense fallback={simple}>
            <SkinnedPlayers tl={tl} replay={replay} ep={ep} flip={flip} looks={looks} clock={clock} onReady={() => { ready.current = true; }} />
          </Suspense>
        </FigureBoundary>
      ) : simple}
      <Ball tl={tl} ep={ep} flip={flip} clock={clock} />
      <CameraRig tl={tl} ep={ep} flip={flip} mode={mode} clock={clock} goalX={goalX} />
      <AdaptiveDpr fpsRef={fpsRef} onSlow={() => setFigures("simple")} ready={ready} />
    </>
  );
}

function ClockDriver({ ep, clock, onProgress, onEnded }: Pick<SceneProps, "ep" | "clock" | "onProgress" | "onEnded">) {
  useFrame((_, dt) => {
    const c = clock.current;
    if (c.playing && !c.ended) {
      c.t = advance(ep, c.t, Math.min(dt, 0.1) * 1000);
      if (c.t >= ep.f1) {
        c.ended = true;
        c.playing = false;
        onEnded();
      }
    }
    onProgress((c.t - ep.f0) / Math.max(1, ep.f1 - ep.f0));
  });
  return null;
}

/** On a phone that can't hold ~50 fps: first the pixel ratio goes down to
 * 1, then (below ~40 fps still) the animated models give way to the simple
 * figures — for good, no flip-flopping. */
function AdaptiveDpr({ fpsRef, onSlow, ready }: {
  fpsRef?: MutableRefObject<HTMLSpanElement | null>; onSlow: () => void; ready: MutableRefObject<boolean>;
}) {
  const setDpr = useThree((s) => s.setDpr);
  const acc = useRef({ n: 0, sum: 0, judge: FPS_JUDGE });
  useFrame((state, dt) => {
    const a = acc.current;
    a.n += 1;
    a.sum += dt;
    if (a.n < 60) return;
    const fps = a.n / a.sum;
    a.n = 0;
    a.sum = 0;
    if (fpsRef?.current) {
      fpsRef.current.textContent = `${Math.round(fps)} fps`;
      fpsRef.current.dataset.fps = String(Math.round(fps));
    }
    const verdict = judgeFps(a.judge, fps, {
      dpr: state.viewport.dpr, ready: ready.current, visible: document.visibilityState === "visible",
    });
    a.judge = verdict.state;
    if (verdict.action === "dpr") setDpr(1);
    if (verdict.action === "simple") onSlow();
  });
  return null;
}

// --- stadium ------------------------------------------------------------------------------

function Stadium() {
  const pitch = useMemo(() => pitchTexture(), []);
  const crowd = useMemo(() => crowdTexture(), []);
  useEffect(() => () => { pitch.dispose(); crowd.dispose(); }, [pitch, crowd]);
  const boards: [number, number, number, number][] = [
    [0, -PITCH_W / 2 - 4, PITCH_L + 10, 0], [0, PITCH_W / 2 + 4, PITCH_L + 10, 0],
    [-PITCH_L / 2 - 7, 0, PITCH_W + 8, Math.PI / 2], [PITCH_L / 2 + 7, 0, PITCH_W + 8, Math.PI / 2],
  ];
  // Stands: long sides and both ends, tilted towards the pitch.
  const stands: { pos: [number, number, number]; rotY: number; w: number }[] = [
    { pos: [0, 9, -PITCH_W / 2 - 17], rotY: 0, w: PITCH_L + 40 },
    { pos: [0, 9, PITCH_W / 2 + 17], rotY: Math.PI, w: PITCH_L + 40 },
    { pos: [-PITCH_L / 2 - 18, 9, 0], rotY: Math.PI / 2, w: PITCH_W + 40 },
    { pos: [PITCH_L / 2 + 18, 9, 0], rotY: -Math.PI / 2, w: PITCH_W + 40 },
  ];
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position-y={-0.02}>
        <planeGeometry args={[PITCH_L + 22, PITCH_W + 18]} />
        <meshLambertMaterial color="#2b7337" />
      </mesh>
      <mesh rotation-x={-Math.PI / 2}>
        <planeGeometry args={[PITCH_L, PITCH_W]} />
        <meshLambertMaterial map={pitch} />
      </mesh>
      {boards.map(([x, z, w, r], i) => (
        <mesh key={i} position={[x, 0.45, z]} rotation-y={r}>
          <boxGeometry args={[w, 0.9, 0.15]} />
          <meshBasicMaterial color={i % 2 ? "#123a5c" : "#0f2f4a"} />
        </mesh>
      ))}
      {stands.map((s, i) => (
        <group key={i} position={s.pos} rotation={[0, s.rotY, 0]}>
          <mesh rotation-x={-0.6}>
            <planeGeometry args={[s.w, 24]} />
            <meshBasicMaterial map={crowd} color="#c9d3e6" />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function netGeometry(w: number, h: number): THREE.PlaneGeometry {
  const g = new THREE.PlaneGeometry(w, h);
  const uv = g.attributes.uv as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, (uv.getX(i) * w) / 0.16, (uv.getY(i) * h) / 0.16);
  return g;
}

/** Posts, bar and net of the goal on scene X = x; the back of the net of
 * the goal just scored in bulges as the ball hits it. */
function Goal({ x, ep, clock, scored }: { x: number; ep: GoalEpisode; clock: MutableRefObject<ReplayClock>; scored: boolean }) {
  const dir = Math.sign(x);
  const tex = useMemo(() => netTexture(), []);
  const geo = useMemo(() => ({
    back: netGeometry(GOAL_HALF * 2, CROSSBAR),
    side: netGeometry(NET_DEPTH, CROSSBAR),
    top: netGeometry(NET_DEPTH, GOAL_HALF * 2),
  }), []);
  useEffect(() => () => { tex.dispose(); Object.values(geo).forEach((g) => g.dispose()); }, [tex, geo]);
  const back = useRef<THREE.Mesh>(null);
  useFrame(() => {
    if (!back.current) return;
    const since = clock.current.t - ep.goal;
    const bulge = scored && since > 0 ? Math.min(1, since * 3) * (0.25 + 0.3 * Math.exp(-since * 2.5)) : 0;
    back.current.position.x = x + dir * (NET_DEPTH + bulge);
  });
  return (
    <group>
      <mesh position={[x, CROSSBAR / 2, -GOAL_HALF]}>
        <cylinderGeometry args={[0.06, 0.06, CROSSBAR, 8]} />
        <meshLambertMaterial color="#ffffff" />
      </mesh>
      <mesh position={[x, CROSSBAR / 2, GOAL_HALF]}>
        <cylinderGeometry args={[0.06, 0.06, CROSSBAR, 8]} />
        <meshLambertMaterial color="#ffffff" />
      </mesh>
      <mesh position={[x, CROSSBAR, 0]} rotation-x={Math.PI / 2}>
        <cylinderGeometry args={[0.06, 0.06, GOAL_HALF * 2 + 0.12, 8]} />
        <meshLambertMaterial color="#ffffff" />
      </mesh>
      <mesh ref={back} geometry={geo.back} position={[x + dir * NET_DEPTH, CROSSBAR / 2, 0]} rotation-y={Math.PI / 2}>
        <meshBasicMaterial map={tex} transparent depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      {[-GOAL_HALF, GOAL_HALF].map((z) => (
        <mesh key={z} geometry={geo.side} position={[x + (dir * NET_DEPTH) / 2, CROSSBAR / 2, z]}>
          <meshBasicMaterial map={tex} transparent depthWrite={false} side={THREE.DoubleSide} />
        </mesh>
      ))}
      <mesh geometry={geo.top} position={[x + (dir * NET_DEPTH) / 2, CROSSBAR, 0]} rotation-x={Math.PI / 2}>
        <meshBasicMaterial map={tex} transparent depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

// --- players ------------------------------------------------------------------------------

const tmpRoot = new THREE.Matrix4();
const tmpPart = new THREE.Matrix4();
const tmpOut = new THREE.Matrix4();
const tmpQ = new THREE.Quaternion();
const tmpEuler = new THREE.Euler();
const tmpRoll = new THREE.Quaternion();
const tmpPos = new THREE.Vector3();
const ONE = new THREE.Vector3(1, 1, 1);
const AXIS_X = new THREE.Vector3(1, 0, 0);
const AXIS_Y = new THREE.Vector3(0, 1, 0);

function wrapAngle(a: number): number {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
}

function smoothstep(a: number, b: number, v: number): number {
  const u = Math.max(0, Math.min(1, (v - a) / (b - a)));
  return u * u * (3 - 2 * u);
}

function Players({ tl, ep, flip, looks, clock }: Pick<SceneProps, "tl" | "ep" | "flip" | "looks" | "clock">) {
  const geo = useMemo(() => ({
    torso: new THREE.CylinderGeometry(0.25, 0.19, 0.64, 7),
    head: new THREE.IcosahedronGeometry(0.13, 1),
    leg: new THREE.BoxGeometry(0.16, 0.86, 0.18).translate(0, -0.43, 0),
    arm: new THREE.BoxGeometry(0.11, 0.62, 0.12).translate(0, -0.31, 0),
    shadow: new THREE.CircleGeometry(0.45, 12).rotateX(-Math.PI / 2),
    ring: new THREE.RingGeometry(0.62, 0.82, 28).rotateX(-Math.PI / 2),
  }), []);
  const mats = useMemo(() => ({
    body: new THREE.MeshLambertMaterial(),
    shadow: new THREE.MeshBasicMaterial({ color: "#000000", transparent: true, opacity: 0.32, depthWrite: false }),
  }), []);
  const numbers = useMemo(
    () => looks.map((l) => numberTexture(l.n, l.keeper ? l.kit.gk : l.kit.fill, l.kit.text)),
    [looks],
  );
  useEffect(() => () => {
    Object.values(geo).forEach((g) => g.dispose());
    Object.values(mats).forEach((m) => m.dispose());
  }, [geo, mats]);
  useEffect(() => () => numbers.forEach((t) => t.dispose()), [numbers]);

  const torso = useRef<THREE.InstancedMesh>(null);
  const head = useRef<THREE.InstancedMesh>(null);
  const legs = useRef<THREE.InstancedMesh>(null);
  const arms = useRef<THREE.InstancedMesh>(null);
  const shadows = useRef<THREE.InstancedMesh>(null);
  const ring = useRef<THREE.Mesh>(null);
  const sprites = useRef<(THREE.Sprite | null)[]>([]);
  const state = useRef({
    heading: new Float32Array(SLOTS),
    phase: new Float32Array(SLOTS),
    lastT: Number.NaN,
  });

  // Kit colours per instance, set once.
  useEffect(() => {
    const c = new THREE.Color();
    for (let i = 0; i < SLOTS; i++) {
      const l = looks[i];
      torso.current?.setColorAt(i, c.set(l.keeper ? l.kit.gk : l.kit.fill));
      head.current?.setColorAt(i, c.set(SKIN[(i * 7) % SKIN.length]));
      for (const k of [0, 1]) {
        legs.current?.setColorAt(i * 2 + k, c.set(l.kit.shorts));
        arms.current?.setColorAt(i * 2 + k, c.set(l.keeper ? l.kit.gk : l.kit.fill));
      }
    }
    for (const m of [torso, head, legs, arms]) if (m.current?.instanceColor) m.current.instanceColor.needsUpdate = true;
    mats.body.needsUpdate = true;
  }, [looks, mats]);

  const keeper = ep.side === "a" ? looks.findIndex((l, i) => i >= 11 && l.keeper) : looks.findIndex((l, i) => i < 11 && l.keeper);
  const goalBall = useMemo(() => toWorld(ballState(tl, ep, ep.goal), flip), [tl, ep, flip]);

  useFrame((_, dtReal) => {
    const t = clock.current.t;
    const s = state.current;
    const dtGame = (t - s.lastT) * STEP_S;
    const jump = !(dtGame >= 0 && dtGame < 2);
    s.lastT = t;
    const f = Math.floor(t);
    const t2 = Math.min(tl.count - 1, t + 0.4);
    const f2 = Math.floor(t2);
    const ball = toWorld(ballState(tl, ep, t), flip);
    const celebrate = smoothstep(ep.goal + 0.3, ep.goal + 1.5, t);
    const dive = smoothstep(ep.shot + 0.6, ep.goal, t) * (1 - smoothstep(ep.goal + 2.5, ep.goal + 4.5, t));
    const turn = 1 - Math.exp(-10 * Math.min(dtReal, 0.1));

    for (let i = 0; i < SLOTS; i++) {
      // The scorer's side stand to celebrate (footballerMotion.poseTime).
      const at = poseTime(ep, i, t);
      const p = at < t ? toWorld(interpolatePlayer(tl, Math.floor(at), at - Math.floor(at), i), flip) : toWorld(interpolatePlayer(tl, f, t - f, i), flip);
      const q = at < t ? p : toWorld(interpolatePlayer(tl, f2, t2 - f2, i), flip);
      const span = Math.max(1e-3, (t2 - t) * STEP_S);
      const vx = (q.x - p.x) / span;
      const vz = (q.z - p.z) / span;
      const speed = Math.hypot(vx, vz);
      const target = speed > 0.8 ? Math.atan2(vx, vz) : Math.atan2(ball.x - p.x, ball.z - p.z);
      s.heading[i] = jump ? target : s.heading[i] + wrapAngle(target - s.heading[i]) * turn;
      if (jump) s.phase[i] = i;
      else s.phase[i] += speed * dtGame * 2.3;

      const scorerSide = (i < 11 ? "a" : "b") === ep.side;
      const party = scorerSide && !looks[i].keeper ? celebrate : 0;
      const hop = party * Math.abs(Math.sin(t * 3.5 + i)) * 0.35;
      let lift = hop;
      let roll = 0;
      let shift = 0;
      if (i === keeper && dive > 0) {
        const sgn = Math.sign(goalBall.z - p.z) || 1;
        roll = sgn * 1.25 * dive;
        shift = sgn * 0.9 * dive;
        lift += Math.sin(dive * Math.PI) * 0.35;
      }
      tmpQ.setFromAxisAngle(AXIS_Y, s.heading[i]);
      if (roll !== 0) tmpQ.premultiply(tmpRoll.setFromAxisAngle(AXIS_X, roll));
      tmpRoot.compose(tmpPos.set(p.x, lift, p.z + shift), tmpQ, ONE);

      const amp = Math.min(0.75, speed * 0.11) * (1 - party);
      const swing = Math.sin(s.phase[i]) * amp;
      const set = (mesh: THREE.InstancedMesh | null, idx: number, x: number, y: number, z: number, rx: number, rz = 0) => {
        if (!mesh) return;
        tmpPart.makeRotationFromEuler(tmpEuler.set(rx, 0, rz));
        tmpPart.setPosition(x, y, z);
        mesh.setMatrixAt(idx, tmpOut.multiplyMatrices(tmpRoot, tmpPart));
      };
      set(torso.current, i, 0, HIP_Y + 0.32, 0, 0);
      set(head.current, i, 0, 1.7, 0, 0);
      set(legs.current, i * 2, -0.1, HIP_Y, 0, swing);
      set(legs.current, i * 2 + 1, 0.1, HIP_Y, 0, -swing);
      const up = party * (-2.7 + Math.sin(t * 5 + i) * 0.25);
      const keeperArms = i === keeper ? dive * 2.6 : 0;
      set(arms.current, i * 2, -0.31, SHOULDER_Y, 0, -swing * 0.8 + up, -0.12 - keeperArms);
      set(arms.current, i * 2 + 1, 0.31, SHOULDER_Y, 0, swing * 0.8 + up, 0.12 + keeperArms);

      if (shadows.current) {
        tmpOut.makeTranslation(p.x, 0.02, p.z + shift);
        shadows.current.setMatrixAt(i, tmpOut);
      }
      const sp = sprites.current[i];
      if (sp) sp.position.set(p.x, 2.3 + lift, p.z + shift);
      if (i === ep.scorer && ring.current) ring.current.position.set(p.x, 0.03, p.z);
    }
    for (const m of [torso, head, legs, arms, shadows]) if (m.current) m.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <group>
      <instancedMesh ref={torso} args={[geo.torso, mats.body, SLOTS]} frustumCulled={false} />
      <instancedMesh ref={head} args={[geo.head, mats.body, SLOTS]} frustumCulled={false} />
      <instancedMesh ref={legs} args={[geo.leg, mats.body, SLOTS * 2]} frustumCulled={false} />
      <instancedMesh ref={arms} args={[geo.arm, mats.body, SLOTS * 2]} frustumCulled={false} />
      <instancedMesh ref={shadows} args={[geo.shadow, mats.shadow, SLOTS]} frustumCulled={false} />
      {ep.scorer !== null && (
        <mesh ref={ring} geometry={geo.ring}>
          <meshBasicMaterial color="#facc15" transparent opacity={0.9} depthWrite={false} />
        </mesh>
      )}
      {numbers.map((tex, i) => (
        <sprite key={i} ref={(el) => { sprites.current[i] = el; }} scale={[0.8, 0.8, 0.8]}>
          <spriteMaterial map={tex} depthWrite={false} />
        </sprite>
      ))}
    </group>
  );
}

// --- ball ---------------------------------------------------------------------------------

function Ball({ tl, ep, flip, clock }: Pick<SceneProps, "tl" | "ep" | "flip" | "clock">) {
  const mesh = useRef<THREE.Mesh>(null);
  const shadow = useRef<THREE.Mesh>(null);
  const last = useRef<{ x: number; z: number } | null>(null);
  useFrame(() => {
    const b = ballState(tl, ep, clock.current.t);
    const w = toWorld(b, flip);
    const m = mesh.current;
    if (m) {
      m.position.set(w.x, b.h - BALL_R + BALL_DRAW_R, w.z);
      const prev = last.current;
      if (prev) {
        const dx = w.x - prev.x;
        const dz = w.z - prev.z;
        if (Math.hypot(dx, dz) < 5) {
          m.rotation.x += dz / BALL_DRAW_R;
          m.rotation.z -= dx / BALL_DRAW_R;
        }
      }
      last.current = w;
    }
    if (shadow.current) {
      shadow.current.position.set(w.x, 0.025, w.z);
      const k = 1 / (1 + b.h * 0.35);
      shadow.current.scale.setScalar(k);
      (shadow.current.material as THREE.MeshBasicMaterial).opacity = 0.4 * k;
    }
  });
  return (
    <group>
      <mesh ref={mesh}>
        <icosahedronGeometry args={[BALL_DRAW_R, 1]} />
        <meshLambertMaterial color="#ffffff" emissive="#3a3a3a" flatShading />
      </mesh>
      <mesh ref={shadow} rotation-x={-Math.PI / 2}>
        <circleGeometry args={[BALL_DRAW_R * 1.3, 12]} />
        <meshBasicMaterial color="#000000" transparent opacity={0.4} depthWrite={false} />
      </mesh>
    </group>
  );
}

// --- camera -------------------------------------------------------------------------------

const FOV: Record<CameraMode, [number, number]> = { tv: [30, 52], goal: [46, 66], top: [42, 56], player: [38, 58] };

function CameraRig({ tl, ep, flip, mode, clock, goalX }: Pick<SceneProps, "tl" | "ep" | "flip" | "mode" | "clock"> & { goalX: number }) {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const size = useThree((s) => s.size);
  const pos = useRef(new THREE.Vector3());
  const look = useRef(new THREE.Vector3());
  const focus = useRef(new THREE.Vector2());
  const ready = useRef(false);
  const tmp = useMemo(() => ({ v2: new THREE.Vector2(), pos: new THREE.Vector3(), look: new THREE.Vector3() }), []);
  useFrame((_, dt) => {
    const t = clock.current.t;
    const portrait = size.height > size.width;
    let target = toWorld(ballState(tl, ep, t), flip);
    if (ep.scorer !== null && (mode === "player" || t > ep.goal + 1)) {
      // He stops to celebrate (footballerMotion.poseTime): so does the camera.
      const at = poseTime(ep, ep.scorer, t);
      const f = Math.floor(at);
      target = toWorld(interpolatePlayer(tl, f, at - f, ep.scorer), flip);
    }
    const k = ready.current ? 1 - Math.exp(-Math.min(dt, 0.1) * 3) : 1;
    focus.current.lerp(tmp.v2.set(target.x, target.z), ready.current ? 1 - Math.exp(-Math.min(dt, 0.1) * 6) : 1);
    const pose = cameraPose(mode, focus.current.x, focus.current.y, goalX, portrait);
    pos.current.lerp(tmp.pos.set(...pose.pos), k);
    look.current.lerp(tmp.look.set(...pose.look), k);
    ready.current = true;
    camera.position.copy(pos.current);
    camera.lookAt(look.current);
    const fov = FOV[mode][portrait ? 1 : 0];
    if (Math.abs(camera.fov - fov) > 0.05) {
      camera.fov += (fov - camera.fov) * k;
      camera.updateProjectionMatrix();
    }
  });
  return null;
}
