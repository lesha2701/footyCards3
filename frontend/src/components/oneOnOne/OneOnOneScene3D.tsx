/** «Атака 1 на 1» in 3D. The free kick's stadium, goal, lights, ball and
 * crowd — in the afternoon sun, as a match on TV looks; the footballers are
 * the career replay's skinned model (it has the run and the sprint), with
 * the beaten defenders, a teammate and the referee around the breakaway. The scene steps the pure episode engine at its fixed
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
import { keeperTake, techniqueOf, type Foot, type KeeperTake, type Technique } from "@/lib/oneOnOne/technique";
import {
  FEINT_TICKS,
  HEADER_Y,
  KEEPER_START_Z,
  TICK,
  VOLLEY_Y,
  flightAt,
  type EpisodeEnd,
  type EpisodeSetup,
  type EpisodeState,
  type KeeperMode,
  type ShotFlight,
} from "@/lib/oneOnOne/engine";
import { AIM_POST, driveHeight, type ShotIntent } from "@/lib/oneOnOne/aim";
import type { EpisodeRecorder } from "@/lib/oneOnOne/recorder";
import { CLAIM_RADIUS, DEF_LUNGE_TICKS, PASS_CROSS, PASS_WINDUP, isOffside, offsideLine, pickMate, type DefMode, type TeamSetup } from "@/lib/oneOnOne/team";

import { FEINTS } from "@/lib/oneOnOne/feints";
import { CELEBRATIONS, ONE_ON_ONE_MOVES_URL, addMoves, play, prepareMoves, scissorFoot, strikePlan, type Moves, type Strike, type StrikePlan, type StrikeTiming } from "./moves";

/** What the finger does right now (the page writes it, the scene reads it
 * every tick). `feint` is consumed by the tick that takes it. */
/** hold: 0 stop, 1 run, 2 sprint. */
/** `aiming` — the right thumb is down: the stick's lean is `aim` (and
 * `steer` 0), and the goal shows where it aims — as high as the power bar
 * held (`power`) would put it, or up for the chip (`lob`). */
export type LiveInput = {
  live: boolean;
  hold: number;
  steer: number;
  feint: number;
  shot: QuantizedSwipe | ShotIntent | null;
  aiming: boolean;
  aim: number;
  power: number | null;
  lob: boolean;
  /** A pass button: how it's played (consumed by the tick that takes it). */
  pass: { mode: number; power: number } | null;
  /** The stick pulled back: the pass looks behind him too. */
  back: boolean;
  /** Written by the scene: the foot his stride brings through next (null
   * when he isn't running) — the one he strikes with (the page labels it). */
  stride: Foot | null;
};

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
  /** How his feint looks (lib/oneOnOne/feints.ts; null = the sidestep). */
  feint?: string | null;
  /** Arrows at the screen's edge to teammates out of the frame. */
  pointers?: MutableRefObject<(HTMLDivElement | null)[]>;
};

type Dot = { x: number; z: number; vx: number; vz: number };
type DefDot = Dot & { mode: DefMode; dirX: number; dirZ: number };
type Snap = Pick<EpisodeState, "x" | "z" | "hx" | "hz" | "speed" | "lead" | "kx" | "kz" | "kMode" | "feintTicks" | "feintDir" | "lungeDir"> & {
  /** The team episodes: the others, the pass being played, the ball off his feet. */
  men: Dot[];
  defs: DefDot[];
  windup: number;
  target: number;
  ball: { x: number; y: number; z: number } | null;
  /** Ticks until a cross meets him, negative past it (null: no cross on its way). */
  crossIn: number | null;
  /** Where it meets him, how high, whether he can get there. */
  air: { x: number; z: number; y: number; reach: boolean } | null;
  mode: number;
};

const snap = (s: EpisodeState): Snap => {
  const r = s.team;
  return {
    x: s.x, z: s.z, hx: s.hx, hz: s.hz, speed: s.speed, lead: s.lead, kx: s.kx, kz: s.kz,
    kMode: s.kMode, feintTicks: s.feintTicks, feintDir: s.feintDir, lungeDir: s.lungeDir,
    men: r ? r.men.map((m) => ({ x: m.x, z: m.z, vx: m.vx, vz: m.vz })) : [],
    defs: r ? r.defs.map((d) => ({ x: d.x, z: d.z, vx: d.vx, vz: d.vz, mode: d.mode, dirX: d.dirX, dirZ: d.dirZ })) : [],
    windup: r ? r.windup : 0,
    target: r ? r.target : 0,
    ball: s.free ? { x: s.free.x, y: s.fromY ?? BALL_RADIUS, z: s.free.z } : null,
    crossIn: r?.pass?.high ? r.pass.total - r.pass.at : null,
    air: r?.pass?.high ? { x: r.pass.toX, z: r.pass.toZ, y: r.pass.contactY, reach: r.pass.reach } : null,
    mode: r ? r.mode : 0,
  };
};

/** One of the team's men on the pitch: the model, its toes, and what is
 * left of the pass it has just played. */
type Actor = { p: SkinnedPlayer; feet: [THREE.Object3D, THREE.Object3D] | null; kick: { clip: Strike; t: number } | null };
/** Who plays whom: the man the player runs and the others. A pass swaps the
 * passer's and the receiver's models. */
type Cast = { active: Actor | null; mates: Actor[]; defs: SkinnedPlayer[] };

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
  /** How long he has been running (s) — the defenders fall behind with it. */
  run: number;
  /** When (s of `run`) the feint began. */
  feintAt: number | null;
  cast: Cast;
  /** The strike the pass under way is played with. */
  passClip: Strike;
  passes: number;
  /** How he meets a ball in the air, once he goes for it. */
  air: AirMove | null;
  /** Who dealt with the cross, and how the ball leaves if it isn't held. */
  claim: "catch" | "away" | null;
  away: THREE.Vector3;
};

type AirMove = "header" | "dive" | "volley";
/** Above HEADER_Y he heads it on his feet, a jump for what's over his head;
 * under it he goes in for it with the head; lower it's the foot, in the fall. */
const VOLLEY_FROM = 0.5;
const airMove = (y: number): AirMove | null => (y > HEADER_Y ? "header" : y > VOLLEY_Y ? "dive" : y > VOLLEY_FROM ? "volley" : null);
/** Head height (m), how far the head goes forward in the header, how long
 * before the contact he leaves the ground and turns to the shot. */
const HEAD_Y = 1.6;
const HEADER_REACH = 0.3;
const AIR_UP = 0.3;
/** He runs on until this close to the contact (s). */
const AIR_WINDOW = 0.4;
const AIR_TURN = 0.3;
/** The dive: how long, how far over at the contact, flat on the grass (rad),
 * his length to the head, how far he slides past the ball (m/s). */
const DIVE_S = 0.32;
const DIVE_PITCH = 1.2;
const DIVE_FLAT = 1.5;
const DIVE_BODY = 1.6;
const DIVE_SLIDE = 2;
/** The trap in the receive clip (s). */
const RECEIVE_TRAP = 1;
const airEuler = new THREE.Euler(0, 0, 0, "YXZ");

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

/** The flight as the free kick's helpers read a trajectory (outcome and end). */
function asTrajectory(f: ShotFlight): ShotTrajectory {
  return { outcome: f.outcome === "blocked" ? "wall" : f.outcome, samples: [], events: f.events, end: f.end };
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
      <fog attach="fog" args={["#c4d6e6", 90, 230]} />
      <Lights quality={quality} time="day" />
      <Environment resolution={64} frames={1}>
        <Lightformer intensity={2.2} color="#cfe3ff" position={[0, 30, 0]} rotation-x={Math.PI / 2} scale={[80, 80, 1]} />
        <Lightformer intensity={3} color="#fff1d6" position={[-30, 34, 18]} scale={[20, 20, 1]} />
        <Lightformer intensity={1.2} position={[25, 10, 10]} rotation-y={-Math.PI / 2} scale={[30, 4, 1]} />
        <Lightformer intensity={0.8} color="#3f8a3a" position={[0, -5, 0]} rotation-x={Math.PI / 2} scale={[60, 60, 1]} />
      </Environment>
      <Stadium quality={quality} hype={hype} time="day" />
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
  feint,
  pointers,
  quality,
  hype,
}: Omit<Props, "fpsRef"> & { quality: Quality; hype: MutableRefObject<number> }) {
  const stage = useRef<Stage>({
    acc: 0, prev: snap(recorder.state), cur: snap(recorder.state), end: null, t: 0, decided: false, dt: 0,
    tech: null, plan: null, take: null, hands: new THREE.Vector3(), holdFrom: Infinity,
    ball: new THREE.Vector3(), shake: 0, ripple: null, run: 0, feintAt: null,
    cast: { active: null, mates: [], defs: [] }, passClip: "pass_r", passes: 0, air: null, claim: null, away: new THREE.Vector3(),
  });
  const [confetti, setConfetti] = useState(0);
  const [flight, setFlight] = useState<ShotFlight | null>(null);

  // A new attack, a new recorder: start over.
  useEffect(() => {
    const s0 = snap(recorder.state);
    Object.assign(stage.current, {
      acc: 0, prev: s0, cur: s0, end: null, t: 0, decided: false, ripple: null, tech: null, plan: null, take: null, holdFrom: Infinity,
      run: 0, feintAt: null, passes: 0, air: null, claim: null,
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
      s.run += dt;
      let steps = 0;
      while (s.acc >= TICK && steps < 8 && !recorder.state.ended) {
        const inp = input.current;
        s.prev = s.cur;
        const team = recorder.state.team;
        recorder.step(inp.hold, inp.steer, inp.feint, inp.shot, inp.pass && team ? { target: pickMate(recorder.state, inp.aim, inp.back), ...inp.pass } : null);
        inp.feint = 0;
        inp.pass = null;
        s.cur = snap(recorder.state);
        // A shot waiting for the cross: he goes for it, by how high it comes.
        const air = s.cur.air;
        if (!air) s.air = null;
        else if (air.reach && recorder.shotWaiting) s.air = airMove((s.cur.crossIn ?? 0) > 0 ? air.y : s.cur.ball?.y ?? 0);
        if (s.cur.feintTicks > 0 && s.prev.feintTicks === 0) s.feintAt = s.run;
        if (team && team.passes !== s.passes) {
          // The ball has left: the player has the receiver now, the passer
          // carries on with the strike. Both jump slots here, no in-between.
          s.passes = team.passes;
          const c = s.cast;
          const passer = c.active;
          if (passer) {
            c.active = c.mates[team.target];
            c.mates[team.target] = passer;
            passer.kick = { clip: s.passClip, t: 0 };
          }
          s.prev = s.cur;
        }
        s.acc -= TICK;
        steps += 1;
      }
      // A long stall (tab in the background): don't race to catch up.
      if (steps === 8) s.acc = 0;
      const ended = recorder.state.ended;
      if (ended) {
        s.end = ended;
        s.acc = TICK;
        // Met in the air: no wind-up on the grass, he is already up there
        // (or, struck late, goes up now).
        const wentUp = s.air !== null;
        s.air = ended.flight ? airMove(recorder.state.fromY ?? 0) : null;
        s.tech = s.air ? null : techniqueOf(recorder.state, recorder.timeline, input.current.stride);
        s.plan = s.tech ? strikePlan(s.tech.kind, s.tech.foot) : null;
        // Struck first time off a pass the wind-up is only a touch.
        if (s.plan && (recorder.timeline.passes?.length ?? 0) > 0) s.plan = { ...s.plan, lead: Math.min(s.plan.lead, FIRST_TIME_LEAD) };
        s.take = ended.flight ? keeperTake(ended.flight) : null;
        s.t = s.plan ? -s.plan.lead : s.air && !wentUp ? -FIRST_TIME_LEAD : 0;
        if (s.air && wentUp) playFreeKickSfx("kick");
        const p = recorder.state.team?.pass;
        s.claim = null;
        if (!ended.flight && p?.high && s.cur.ball) {
          // The cross dealt with: held, punched or headed clear, or it ran out.
          const b = s.cur.ball;
          const met = p.at === p.total;
          s.claim = ended.outcome === "tackle" ? "catch" : "away";
          if (met) s.away.set(Math.sign(b.x || 1) * 6, 6.5, 12);
          else s.away.set((p.toX - p.fromX) / (p.total * TICK), 0, (p.toZ - p.fromZ) / (p.total * TICK)).multiplyScalar(0.7);
          // His to deal with: up for it, whether he holds it or punches it.
          if (met && Math.hypot(b.x - s.cur.kx, b.z - s.cur.kz) < CLAIM_RADIUS) s.take = "catch";
        }
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
        } else if (e.type === "save" || e.type === "wall") {
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
        <Players setup={setup} stage={stage} input={input} feint={feint} flight={flight} quality={quality} onReady={onReady} />
      </Suspense>
      <Ball stage={stage} flight={flight} skin={ball} quality={quality} />
      <CameraRig stage={stage} flight={flight} wide={"team" in setup} />
      <AimMarker stage={stage} input={input} />
      {"team" in setup && <PassMarks stage={stage} input={input} recorder={recorder} setup={setup as TeamSetup} pointers={pointers} />}
      <Confetti burstId={confetti} />
    </>
  );
}

type StageRef = MutableRefObject<Stage>;

/** Where the shot goes while the right thumb is down: a ring on the goal
 * line at the left stick's lean (the spot the aim resolves to). */
const AIM_MARK_Y = 0.9;
const AIM_LOB_Y = 2.1;
/** Past the bar the ring sits on it (the bar turns red on the button). */
const AIM_TOP_Y = 2.5;
function AimMarker({ stage, input }: { stage: StageRef; input: MutableRefObject<LiveInput> }) {
  const mark = useRef<THREE.Group>(null);
  const fade = useRef(0);
  useFrame((_, delta) => {
    const g = mark.current;
    if (!g) return;
    const on = input.current.aiming && !stage.current.end && !stage.current.cur.feintTicks;
    fade.current = THREE.MathUtils.damp(fade.current, on ? 1 : 0, 14, delta);
    g.visible = fade.current > 0.02;
    for (const c of g.children) ((c as THREE.Mesh).material as THREE.MeshBasicMaterial).opacity = fade.current;
    const inp = input.current;
    const x = (THREE.MathUtils.clamp(inp.aim, -1000, 1000) / 1000) * AIM_POST;
    const y = inp.lob ? AIM_LOB_Y : inp.power !== null ? Math.min(AIM_TOP_Y, driveHeight(inp.power)) : AIM_MARK_Y;
    g.position.set(on ? THREE.MathUtils.damp(g.position.x, x, 18, delta) : x, on ? THREE.MathUtils.damp(g.position.y, y, 18, delta) : y, 0.05);
  });
  // Dark under white under lime: readable over the net, the boards and the crowd.
  return (
    <group ref={mark} visible={false} renderOrder={5}>
      <mesh renderOrder={5}>
        <ringGeometry args={[0.3, 0.52, 40]} />
        <meshBasicMaterial color="#0b1830" transparent opacity={0} depthTest={false} toneMapped={false} />
      </mesh>
      <mesh renderOrder={6}>
        <ringGeometry args={[0.34, 0.47, 40]} />
        <meshBasicMaterial color="#c6e63a" transparent opacity={0} depthTest={false} toneMapped={false} />
      </mesh>
      <mesh renderOrder={6}>
        <circleGeometry args={[0.09, 20]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0} depthTest={false} toneMapped={false} />
      </mesh>
    </group>
  );
}

/** A teammate this far off the centre of the frame (±1 the edge) gets an arrow. */
const POINTER_FROM = 0.94;

/** The ring round the teammate the stick picks (red while he is offside),
 * and the last defender's line. */
function PassMarks({
  stage,
  input,
  recorder,
  setup,
  pointers,
}: {
  stage: StageRef;
  input: MutableRefObject<LiveInput>;
  recorder: EpisodeRecorder;
  setup: TeamSetup;
  pointers?: MutableRefObject<(HTMLDivElement | null)[]>;
}) {
  const camera = useThree((s) => s.camera);
  const size = useThree((s) => s.size);
  const spot = useMemo(() => new THREE.Vector3(), []);
  const ring = useRef<THREE.Mesh>(null);
  const line = useRef<THREE.Mesh>(null);
  const drop = useRef<THREE.Mesh>(null);
  const showLine = setup.team.kind === "through_ball";
  useFrame(() => {
    const s = recorder.state;
    const r = s.team;
    const m = ring.current;
    const free = !!r && !s.ended && !r.pass && r.windup === 0;
    if (m) {
      m.visible = free;
      if (free && r) {
        const i = pickMate(s, input.current.aim, input.current.back);
        const k = Math.min(1, stage.current.acc / TICK);
        const a = stage.current.prev.men[i] ?? r.men[i];
        const b = stage.current.cur.men[i] ?? r.men[i];
        m.position.set(lerp(a.x, b.x, k), 0.03, lerp(a.z, b.z, k));
        ((m.material as THREE.MeshBasicMaterial).color as THREE.Color).set(isOffside(s, i) ? "#ef4444" : "#c6e63a");
      }
    }
    // Where the cross comes down, and whose it looks like.
    if (drop.current) {
      const p = r?.pass;
      drop.current.visible = !!p?.high && !s.ended;
      if (p) {
        drop.current.position.set(p.toX, 0.03, p.toZ);
        ((drop.current.material as THREE.MeshBasicMaterial).color as THREE.Color).set(!p.reach ? "#ef4444" : p.claim ? "#f59e0b" : "#c6e63a");
      }
    }
    if (line.current) {
      line.current.visible = free;
      if (r) line.current.position.z = offsideLine(r);
    }
    // Out of the frame: an arrow on the edge he is off, by his height on screen.
    const picked = r ? pickMate(s, input.current.aim, input.current.back) : -1;
    pointers?.current.forEach((el, i) => {
      if (!el) return;
      const dot = stage.current.cur.men[i];
      const on = free && !!dot;
      if (dot) spot.set(dot.x, 1, dot.z).project(camera);
      const off = on && Math.abs(spot.x) > POINTER_FROM;
      el.style.opacity = off ? "1" : "0";
      if (!off) return;
      const right = spot.x > 0;
      const y = THREE.MathUtils.clamp((1 - spot.y) / 2, 0.2, 0.7) * size.height;
      el.style.transform = `translate(${right ? size.width - 46 : 10}px, ${y}px) scaleX(${right ? 1 : -1})`;
      el.style.color = i === picked ? (r && isOffside(s, i) ? "#ef4444" : "#c6e63a") : "#ffffff";
    });
  });
  return (
    <>
      <mesh ref={ring} rotation-x={-Math.PI / 2} visible={false}>
        <ringGeometry args={[0.55, 0.78, 32]} />
        <meshBasicMaterial color="#c6e63a" transparent opacity={0.9} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh ref={drop} rotation-x={-Math.PI / 2} visible={false}>
        <ringGeometry args={[0.9, 1.05, 40]} />
        <meshBasicMaterial color="#c6e63a" transparent opacity={0.8} depthWrite={false} toneMapped={false} />
      </mesh>
      {showLine && (
        <mesh ref={line} rotation-x={-Math.PI / 2} position={[0, 0.02, 0]} visible={false}>
          <planeGeometry args={[68, 0.12]} />
          <meshBasicMaterial color="#fde047" transparent opacity={0.55} depthWrite={false} toneMapped={false} />
        </mesh>
      )}
    </>
  );
}

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
const DEFENDER_LOOK = { shirt: "#dc2626", shorts: "#1f2937", socks: "#dc2626", skin: "#d9a57f", hair: "#2a1d15" };
const DEFENDER_LOOK_2 = { ...DEFENDER_LOOK, skin: "#8d5a3c", hair: "#0f0b08" };
const MATE_LOOK = { ...ATTACKER_LOOK, skin: "#b98262", hair: "#151010" };
/** The team episodes: the wind-up of a first-time shot (s), the pass's
 * strike played at this pace, a defender's slide at this pace. */
const FIRST_TIME_LEAD = 0.12;
const PASS_CLIP_SPEED = 1.15;
const REFEREE_LOOK = { shirt: "#111827", shorts: "#111827", socks: "#111827", skin: "#e2b08c", hair: "#5a4632" };

/** The others on the pitch — presentation only, they follow the attacker
 * and never touch the engine. The story: he has just got the ball in
 * behind; the defender he left is behind him to his left (out of the
 * frame at first) and chases, closing in (`gapRate` < 0, m/s) to his
 * shoulder (`minBack`) by the box; the other defender was marking our
 * teammate up ahead on the right and stays with him; the referee out wide
 * ahead of play. Where each wants to be is off the attacker along the line
 * to goal: `side` across it (m, + to his right), `back` behind him (−
 * ahead). */
type ExtraRole = "defender" | "mate" | "ref";
type ExtraSpec = {
  role: ExtraRole;
  look: typeof ATTACKER_LOOK;
  side: number;
  back: number;
  gapRate: number;
  minBack?: number;
  top: number;
  /** Shown on a slow phone too. */
  low: boolean;
};
const EXTRAS: ExtraSpec[] = [
  { role: "defender", look: DEFENDER_LOOK_2, side: -2.2, back: 5.5, gapRate: -0.45, minBack: 1.1, top: 9.4, low: true },
  { role: "mate", look: MATE_LOOK, side: 4.2, back: -9, gapRate: 0.2, top: 8.2, low: false },
  { role: "defender", look: DEFENDER_LOOK, side: 5.3, back: -8.2, gapRate: 0.2, top: 8.3, low: false },
  { role: "ref", look: REFEREE_LOOK, side: -7.5, back: -12, gapRate: 0.4, top: 6.8, low: true },
];
/** They don't follow him into the box's middle (m off the line). */
const EXTRAS_MIN_Z = 7;
/** After the end they pull up over this (s). */
const EXTRAS_STOP_S = 1.4;

function hipsOf(p: SkinnedPlayer): THREE.Object3D | null {
  let hips: THREE.Object3D | null = null;
  p.root.traverse((o) => {
    if (!hips && (o as THREE.Bone).isBone && /Hips$/.test(o.name)) hips = o;
  });
  return hips;
}

/** From the plant to the contact his standing foot stays where it came
 * down beside the ball (the clip is played in place, so it would slide back
 * under him): the body is moved over it instead. Its spot is where the clip
 * has it at the contact with his toe at the ball, so the contact is where
 * it was; the step into it eases in over PLANT_EASE_S. */
function plantFoot(
  p: SkinnedPlayer,
  feet: [THREE.Object3D, THREE.Object3D] | null,
  strike: StrikeTiming,
  plan: StrikePlan,
  f: ShotFlight,
  t: number,
  tmp: THREE.Vector3,
) {
  if (!feet || t > 0) return;
  const from = Math.max((strike.plant - strike.contact) / plan.timeScale, -plan.lead * 0.9);
  if (t < from - PLANT_EASE_S) return;
  const w = THREE.MathUtils.smoothstep(t, from - PLANT_EASE_S, from);
  const yaw = p.root.rotation.y;
  const spot = tmp.set(strike.plantAt.x - strike.toe.x, 0, strike.plantAt.z - strike.toe.z).applyAxisAngle(THREE.Object3D.DEFAULT_UP, yaw);
  const sx = f.from.x + spot.x;
  const sz = f.from.z + spot.z;
  p.root.updateMatrixWorld(true);
  const foot = feet[plan.clip.endsWith("_l") ? 1 : 0].getWorldPosition(tmp);
  p.root.position.x += (sx - foot.x) * w;
  p.root.position.z += (sz - foot.z) * w;
}
/** The step onto the standing foot is eased in over this long (s). */
const PLANT_EASE_S = 0.08;

/** The attacker's two toes (his stride: which foot comes through next; the plant). */
function feetOf(p: SkinnedPlayer): [THREE.Object3D, THREE.Object3D] | null {
  let l: THREE.Object3D | null = null;
  let r: THREE.Object3D | null = null;
  p.root.traverse((o) => {
    if (!(o as THREE.Bone).isBone) return;
    if (/LeftToeBase$/.test(o.name)) l = o;
    else if (/RightToeBase$/.test(o.name)) r = o;
  });
  return l && r ? [l, r] : null;
}
/** Running faster than this (m/s) his stride picks the striking foot. */
const STRIDE_FROM = 1.5;

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

/** After the contact he carries his pace on, slowing to a stop over this
 * (s); once the strike clip is over he runs the rest out down to this
 * speed (m/s). */
const FOLLOW_THROUGH_S = 0.9;
const RUN_OUT_FROM = 0.6;

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
  input,
  feint,
  flight,
  quality,
  onReady,
}: {
  setup: EpisodeSetup;
  stage: StageRef;
  input: MutableRefObject<LiveInput>;
  feint?: string | null;
  flight: ShotFlight | null;
  quality: Quality;
  onReady: () => void;
}) {
  const [gltf, extra, movesGltf] = useLoader(GLTFLoader, [FOOTBALLER_URL, MOVES_URL, ONE_ON_ONE_MOVES_URL], (loader) => {
    loader.setMeshoptDecoder(MeshoptDecoder);
  });
  const asset = useMemo<FootballerAsset>(() => prepareFootballer(gltf, extra), [gltf, extra]);
  const moves = useMemo<Moves>(() => prepareMoves(gltf, movesGltf), [gltf, movesGltf]);
  const style = feint ? FEINTS[feint] : undefined;
  const materials = useMemo(() => new MaterialCache("standard"), []);
  const man = useMemo(() => {
    const p = makePlayer(asset, ATTACKER_LOOK, materials);
    addMoves(p, moves);
    p.root.rotation.order = "YXZ";
    return { p, feet: feetOf(p), kick: null } as Actor;
  }, [asset, moves, materials]);
  // The team episodes' men: only once one of them is played.
  const hasTeam = "team" in setup;
  const squad = useMemo(() => {
    if (!hasTeam) return null;
    const mates = [0, 1].map(() => {
      const p = makePlayer(asset, ATTACKER_LOOK, materials);
      addMoves(p, moves);
      p.root.rotation.order = "YXZ";
      return { p, feet: feetOf(p), kick: null } as Actor;
    });
    const defs = [DEFENDER_LOOK, DEFENDER_LOOK_2, DEFENDER_LOOK].map((look) => {
      const p = makePlayer(asset, look, materials);
      addMoves(p, moves);
      return p;
    });
    return { mates, defs };
  }, [hasTeam, asset, moves, materials]);
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
    for (const p of [man.p, keeper, ...(squad?.mates.map((m) => m.p) ?? []), ...(squad?.defs ?? [])]) {
      p.root.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) o.castShadow = quality === "high";
      });
    }
  }, [man, keeper, squad, quality]);
  useEffect(() => () => {
    man.p.mixer.stopAllAction();
    keeper.mixer.stopAllAction();
    squad?.mates.forEach((m) => m.p.mixer.stopAllAction());
    squad?.defs.forEach((p) => p.mixer.stopAllAction());
    materials.dispose();
  }, [man, keeper, squad, materials]);
  useEffect(onReady, [onReady]);
  // The keeper's dive in the shot: where his hands go, which side, when.
  const dive = useMemo(() => {
    if (!flight || flight.keeper.lyingFor > 0) return null;
    const last = flight.samples[flight.samples.length - 1];
    const dx = last.handX - flight.keeper.x;
    return { dx, y: last.handY, arrival: flight.end.t, reaction: flight.keeper.reaction };
  }, [flight]);

  // A new episode: everyone back in his own slot.
  const castFor = useRef<EpisodeSetup | null>(null);

  useFrame((_, delta) => {
    const s = stage.current;
    if (castFor.current !== setup) {
      castFor.current = setup;
      const team = (setup as Partial<TeamSetup>).team;
      const mates = squad?.mates ?? [];
      man.kick = null;
      mates.forEach((m, i) => {
        m.kick = null;
        m.p.root.visible = i < (team?.men.length ?? 0);
      });
      squad?.defs.forEach((p, i) => (p.root.visible = i < (team?.defs.length ?? 0)));
      s.cast = { active: man, mates: mates.slice(0, team?.men.length ?? 0), defs: squad?.defs.slice(0, team?.defs.length ?? 0) ?? [] };
    }
    const actor = s.cast.active ?? man;
    const attacker = actor.p;
    const a = attackerAt(s);
    const k = keeperAt(s);
    const t = s.t;
    const end = s.end;

    // --- Attacker ---
    const styleMove = style && s.feintAt !== null ? (`${style.clip}_${s.cur.feintDir > 0 ? "r" : "l"}` as const) : null;
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
      // Eased, not snapped: through the wind-up he turns and steps from
      // where the run left him to where his toe meets the ball.
      const turn = THREE.MathUtils.smoothstep(t + plan.lead, 0, plan.lead * 0.8);
      const yaw = runYaw + wrapAngle(shotYaw - runYaw) * turn;
      attacker.root.rotation.set(-plan.lean * turn, yaw, 0);
      // The strike is in the run, not from a standstill: past the ball he
      // carries on at the pace he hit it, slowing over the follow-through,
      // and the last of it he runs out.
      const pace = s.cur.speed;
      const ft = Math.max(0, t);
      const carry = ft < FOLLOW_THROUGH_S ? pace * (ft - (ft * ft) / (2 * FOLLOW_THROUGH_S)) : (pace * FOLLOW_THROUGH_S) / 2;
      const left = pace * Math.max(0, 1 - ft / FOLLOW_THROUGH_S);
      const clipT = strike.contact + t * plan.timeScale;
      if (clipT < moves.clips[plan.clip].duration - 0.05) {
        const kick = play(attacker, plan.clip, true, 0.15);
        kick.time = THREE.MathUtils.clamp(clipT, 0, kick.getClip().duration);
        kick.paused = true;
      } else if (left > RUN_OUT_FROM) runAt(attacker, left, asset);
      else play(attacker, "idle", false, 0.3);
      const toe = tmp.v.set(strike.toe.x, 0, strike.toe.z).applyAxisAngle(THREE.Object3D.DEFAULT_UP, yaw);
      const step = THREE.MathUtils.smoothstep(t + plan.lead, 0, plan.lead);
      const hl = Math.hypot(a.hx, a.hz) || 1;
      attacker.root.position.set(
        lerp(a.x, f.from.x - toe.x, step) + (a.hx / hl) * carry,
        0,
        lerp(a.z, f.from.z - toe.z, step) + (a.hz / hl) * carry,
      );
      if (end.outcome === "goal" && t > f.end.t + 0.6) {
        attacker.root.rotation.x = 0;
        play(attacker, CELEBRATIONS[setup.seed % CELEBRATIONS.length], true, 0.3).paused = false;
      }
    } else if (s.air && (end || (s.cur.crossIn ?? 0) * TICK < AIR_WINDOW)) {
      // He meets it in the air: everything timed to the contact, `c` s off.
      const c = end ? t : -Math.max(0, s.cur.crossIn ?? 0) * TICK;
      const f = end?.flight;
      const spot = f ? f.from : s.cur.air ?? a;
      const y = f ? f.samples[0].ball.y : s.cur.air?.y ?? HEAD_Y;
      const v = f?.kick.velocity;
      const face = v ? Math.atan2(v.x, v.z) : Math.atan2(-spot.x, -spot.z);
      const yaw = runYaw + wrapAngle(face - runYaw) * THREE.MathUtils.smoothstep(c, -AIR_TURN, -0.05);
      const fx = Math.sin(yaw);
      const fz = Math.cos(yaw);
      const step = THREE.MathUtils.smoothstep(c, -AIR_UP, -0.02);
      if (s.air === "volley") {
        // The foot comes up to the ball as he goes over.
        const foot = scissorFoot(moves, y);
        const kick = play(attacker, "scissor", true, 0.1);
        kick.time = THREE.MathUtils.clamp(foot.t + c, 0, kick.getClip().duration);
        kick.paused = true;
        attacker.root.rotation.set(0, yaw, 0);
        const toe = tmp.v.set(foot.x, 0, foot.z).applyAxisAngle(THREE.Object3D.DEFAULT_UP, yaw);
        attacker.root.position.set(lerp(a.x, spot.x - toe.x, step), 0, lerp(a.z, spot.z - toe.z, step));
      } else {
        const head = play(attacker, "header", true, 0.12);
        head.paused = true;
        if (s.air === "header") {
          head.time = THREE.MathUtils.clamp(moves.headerAt + c, 0, head.getClip().duration);
          attacker.root.rotation.set(0, yaw, 0);
          const up = Math.max(0, 1 - (c * c) / (AIR_UP * AIR_UP));
          attacker.root.position.set(
            lerp(a.x, spot.x - fx * HEADER_REACH, step),
            Math.max(0, y - HEAD_Y) * up,
            lerp(a.z, spot.z - fz * HEADER_REACH, step),
          );
        } else {
          // In at it head first, and down on the grass.
          head.time = moves.headerAt;
          const over = THREE.MathUtils.smoothstep(c, -DIVE_S, 0);
          const fall = THREE.MathUtils.smoothstep(c, 0, 0.45);
          const pitch = lerp(DIVE_PITCH * over, DIVE_FLAT, fall);
          attacker.root.quaternion.setFromEuler(airEuler.set(pitch, yaw, 0, "YXZ"));
          const reach = DIVE_BODY * Math.sin(DIVE_PITCH);
          const slide = DIVE_SLIDE * Math.max(0, c);
          attacker.root.position.set(
            lerp(a.x, spot.x - fx * reach, step) + fx * slide,
            lerp(Math.max(0, y - DIVE_BODY * Math.cos(DIVE_PITCH)) * over, 0.1, fall),
            lerp(a.z, spot.z - fz * reach, step) + fz * slide,
          );
        }
      }
    } else if (end?.flight) {
      // Scored in the air, up off the grass: off to the corner.
      attacker.root.rotation.set(0, Math.atan2(end.flight.kick.velocity.x, end.flight.kick.velocity.z), 0);
      attacker.root.position.set(end.flight.from.x, 0, end.flight.from.z);
      if (end.outcome === "goal") play(attacker, CELEBRATIONS[setup.seed % CELEBRATIONS.length], true, 0.3).paused = false;
      else play(attacker, "idle", false, 0.4);
    } else if (!s.claim && (end?.outcome === "tackle" || end?.outcome === "dispossessed")) {
      // Into the keeper at his feet, or taken off them: he goes over.
      play(attacker, "trip", true, 0.1).paused = false;
      attacker.root.position.set(a.x, 0, a.z);
    } else if (s.cur.windup > 0) {
      // The pass: the strike timed for the ball to leave as the wind-up ends.
      const target = s.cur.men[s.cur.target];
      const toLeft = !!target && (target.x - a.x) * a.hz - (target.z - a.z) * a.hx > 0;
      if (s.cur.windup >= PASS_WINDUP - 1) s.passClip = `${s.cur.mode >= PASS_CROSS ? "shot" : "pass"}_${toLeft ? "r" : "l"}`;
      const clip = play(attacker, s.passClip, true, 0.08);
      clip.time = THREE.MathUtils.clamp(moves.strikes[s.passClip].contact - s.cur.windup * TICK * PASS_CLIP_SPEED, 0, clip.getClip().duration);
      clip.paused = true;
      attacker.root.position.set(a.x, 0, a.z);
    } else if (end) {
      play(attacker, "idle", false, 0.3);
      attacker.root.position.set(a.x, 0, a.z);
    } else if (s.cur.air?.reach && (s.cur.crossIn ?? 1) <= 0) {
      // Bringing the cross down.
      const trap = play(attacker, "receive", true, 0.12);
      trap.time = RECEIVE_TRAP - (s.cur.crossIn ?? 0) * TICK;
      trap.paused = true;
      attacker.root.position.set(a.x, 0, a.z);
    } else if (styleMove && s.run - (s.feintAt ?? 0) < (moves.clips[styleMove]?.duration ?? 0)) {
      // A style feint (the roulette): the same sidestep in the engine, the
      // whole move played through it and on into the run.
      const move = play(attacker, styleMove, true, 0.06);
      move.time = s.run - (s.feintAt ?? 0);
      move.paused = true;
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
    if (end?.flight && s.plan) plantFoot(attacker, actor.feet, moves.strikes[s.plan.clip], s.plan, end.flight, t, tmp.a);
    // His stride: the foot behind him is the next to come through (the
    // other is coming down to plant) — the one he'll strike with.
    if (!end) {
      const feet = actor.feet;
      if (feet && a.speed > STRIDE_FROM && !s.cur.feintTicks) {
        attacker.root.updateMatrixWorld(true);
        const l = feet[0].getWorldPosition(tmp.a);
        const r = feet[1].getWorldPosition(tmp.b);
        input.current.stride = (l.x - r.x) * a.hx + (l.z - r.z) * a.hz < 0 ? "left" : "right";
      } else input.current.stride = null;
    }

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
    } else if (s.take === "catch" && s.claim) {
      // Up off his line for the cross.
      play(keeper, "gk_catch_high", true, 0.08).timeScale = 1.6;
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
      // Set on his toes (mocap), or the model's own stance without it.
      play(keeper, moves.clips.gk_set ? "gk_set" : "gk_idle", false, 0.25);
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
      <primitive object={man.p.root} />
      <primitive object={keeper.root} position={[0, 0, KEEPER_START_Z]} />
      {squad ? (
        <TeamCast asset={asset} moves={moves} stage={stage} squad={squad} />
      ) : (
        <Others asset={asset} moves={moves} materials={materials} stage={stage} quality={quality} />
      )}
      {/* The line the keeper starts from, for the scale of how far he came. */}
      <mesh rotation-x={-Math.PI / 2} position={[setup.start.x, 0.01, setup.start.z]}>
        <ringGeometry args={[0.5, 0.62, 28]} />
        <meshBasicMaterial color="#c6e63a" transparent opacity={0.35} depthWrite={false} />
      </mesh>
    </>
  );
}

/** The team episodes' others, where the engine has them: the teammates
 * (the passer finishing his strike), the defenders (sliding in, down on the
 * grass, getting up). */
function TeamCast({ asset, moves, stage, squad }: {
  asset: FootballerAsset;
  moves: Moves;
  stage: StageRef;
  squad: { mates: Actor[]; defs: SkinnedPlayer[] };
}) {
  const downFor = useMemo(() => new Map<SkinnedPlayer, number>(), []);
  useFrame((_, delta) => {
    const s = stage.current;
    const k = s.end ? 1 : Math.min(1, s.acc / TICK);
    const scored = s.end?.outcome === "goal" && s.t > (s.end.flight?.end.t ?? 0) + 0.4;
    s.cast.mates.forEach((m, i) => {
      const a = s.prev.men[i];
      const b = s.cur.men[i];
      if (!a || !b) return;
      const speed = s.end ? 0 : Math.hypot(b.vx, b.vz);
      m.p.root.position.set(lerp(a.x, b.x, k), 0, lerp(a.z, b.z, k));
      const yaw = speed > 0.6 ? Math.atan2(b.vx, b.vz) : Math.atan2(s.ball.x - b.x, s.ball.z - b.z);
      m.p.root.rotation.y += wrapAngle(yaw - m.p.root.rotation.y) * (1 - Math.exp(-10 * delta));
      if (m.kick && !s.end) {
        const clip = moves.clips[m.kick.clip];
        const time = moves.strikes[m.kick.clip].contact + m.kick.t * PASS_CLIP_SPEED;
        m.kick.t += s.dt;
        if (time < clip.duration - 0.05) {
          const act = play(m.p, m.kick.clip, true, 0.05);
          act.time = time;
          act.paused = true;
        } else m.kick = null;
      } else if (scored) play(m.p, "celebrate", true, 0.3).paused = false;
      else if (speed < 0.4) play(m.p, "idle", false, 0.3);
      else runAt(m.p, speed, asset);
      m.p.mixer.update(s.dt);
    });
    s.cast.defs.forEach((p, i) => {
      const a = s.prev.defs[i];
      const b = s.cur.defs[i];
      if (!a || !b) return;
      p.root.position.set(lerp(a.x, b.x, k), 0, lerp(a.z, b.z, k));
      const speed = s.end ? 0 : Math.hypot(b.vx, b.vz);
      if (b.mode === "lunge") {
        p.root.rotation.y = Math.atan2(b.dirX, b.dirZ);
        const slide = play(p, b.dirX * b.dirZ > 0 ? "slide_l" : "slide_r", true, 0.06);
        slide.timeScale = slide.getClip().duration / (DEF_LUNGE_TICKS * TICK * 1.6);
        slide.paused = false;
        downFor.set(p, 0);
      } else if (b.mode === "down") {
        downFor.set(p, (downFor.get(p) ?? 0) + delta);
      } else {
        if (downFor.has(p)) {
          // Back up from the grass.
          play(p, "gk_getup", true, 0.1).paused = false;
          downFor.delete(p);
        }
        const yaw = speed > 0.6 ? Math.atan2(b.vx, b.vz) : Math.atan2(s.ball.x - b.x, s.ball.z - b.z);
        p.root.rotation.y += wrapAngle(yaw - p.root.rotation.y) * (1 - Math.exp(-10 * delta));
        if (scored && speed < 1.5) play(p, "gk_miss", true, 0.35);
        else if (speed < 0.4) play(p, "idle", false, 0.3);
        else runAt(p, speed, asset);
      }
      p.mixer.update(s.dt);
    });
  }, -0.4);
  return (
    <>
      {squad.mates.map((m, i) => (
        <primitive key={i} object={m.p.root} />
      ))}
      {squad.defs.map((p, i) => (
        <primitive key={`d${i}`} object={p.root} />
      ))}
    </>
  );
}

type Other = { p: SkinnedPlayer; spec: ExtraSpec; pos: THREE.Vector3; vel: THREE.Vector3; since: number };

/** The defenders, the teammate and the referee (see EXTRAS): each steers for
 * his spot off the attacker, no faster than he can run, and pulls up once
 * the attack is over — on a goal the defenders' hands go to their heads and
 * the teammate celebrates. Fewer of them on a slow phone. */
function Others({ asset, moves, materials, stage, quality }: {
  asset: FootballerAsset;
  moves: Moves;
  materials: MaterialCache;
  stage: StageRef;
  quality: Quality;
}) {
  const others = useMemo<Other[]>(
    () =>
      EXTRAS.filter((e) => quality === "high" || e.low).map((spec) => {
        const p = makePlayer(asset, spec.look, materials);
        addMoves(p, moves);
        p.root.traverse((o) => {
          if ((o as THREE.Mesh).isMesh) o.castShadow = quality === "high";
        });
        return { p, spec, pos: new THREE.Vector3(), vel: new THREE.Vector3(), since: 0 };
      }),
    [asset, moves, materials, quality],
  );
  useEffect(() => () => others.forEach((o) => o.p.mixer.stopAllAction()), [others]);
  const want = useMemo(() => new THREE.Vector3(), []);
  const placed = useRef(false);

  useFrame((_, delta) => {
    const s = stage.current;
    const a = attackerAt(s);
    const dt = s.dt;
    // Along the line to goal (more settled than his heading, which a feint jerks).
    const len = Math.hypot(a.x, a.z) || 1;
    const fx = -a.x / len;
    const fz = -a.z / len;
    const fresh = s.run === 0 && !s.end;
    for (const o of others) {
      const { spec } = o;
      // Ahead of him only while there is room: nearing the box they are
      // drawn level, and out wide rather than into the keeper's way.
      const room = THREE.MathUtils.clamp((a.z - EXTRAS_MIN_Z) / 14, 0, 1);
      const back = Math.max(spec.minBack ?? -Infinity, (spec.back < 0 ? spec.back * room : spec.back) + spec.gapRate * s.run);
      const side = spec.side * lerp(1.6, 1, room);
      want.set(a.x - fz * side - fx * back, 0, a.z + fx * side - fz * back);
      if (want.z < EXTRAS_MIN_Z) {
        want.x += Math.sign(side) * (EXTRAS_MIN_Z - want.z);
        want.z = EXTRAS_MIN_Z;
      }
      if (fresh || !placed.current) {
        o.pos.copy(want);
        o.vel.set(0, 0, 0);
        o.since = 0;
      } else {
        if (s.end) o.since += delta;
        const top = spec.top * Math.max(0, 1 - o.since / EXTRAS_STOP_S);
        const dx = want.x - o.pos.x;
        const dz = want.z - o.pos.z;
        const d = Math.hypot(dx, dz);
        const v = Math.min(top, d * 2.2);
        const k = 1 - Math.exp(-4 * delta);
        o.vel.x += ((d > 0.01 ? (dx / d) * v : 0) - o.vel.x) * k;
        o.vel.z += ((d > 0.01 ? (dz / d) * v : 0) - o.vel.z) * k;
        o.pos.addScaledVector(o.vel, delta);
      }
      const speed = Math.hypot(o.vel.x, o.vel.z);
      // Running: where he runs; standing: watching the ball.
      const yaw = speed > 0.6 ? Math.atan2(o.vel.x, o.vel.z) : Math.atan2(s.ball.x - o.pos.x, s.ball.z - o.pos.z);
      o.p.root.rotation.y += wrapAngle(yaw - o.p.root.rotation.y) * (1 - Math.exp(-10 * delta));
      o.p.root.position.copy(o.pos);
      const f = s.end?.flight;
      const scored = s.end?.outcome === "goal" && (!f || s.t > f.end.t + 0.4);
      if (scored && speed < 1.5 && spec.role === "defender") play(o.p, "gk_miss", true, 0.35);
      else if (scored && spec.role === "mate") play(o.p, "celebrate", true, 0.3).paused = false;
      else if (speed < 0.4) play(o.p, "idle", false, 0.3);
      else runAt(o.p, speed, asset);
      o.p.mixer.update(dt);
    }
    placed.current = true;
  }, -0.4);

  return (
    <>
      {others.map((o, i) => (
        <primitive key={i} object={o.p.root} />
      ))}
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
    if (s.claim === "catch" && s.cur.ball) {
      // Taken out of the air: into his gloves.
      const k = Math.min(1, s.t / INTO_HANDS);
      x = lerp(s.cur.ball.x, s.hands.x, k);
      y = lerp(s.cur.ball.y, s.hands.y, k);
      z = lerp(s.cur.ball.z, s.hands.z, k);
    } else if (s.claim && s.cur.ball) {
      // Punched or headed away (a cross gone astray just carries on).
      const t = s.t;
      x = s.cur.ball.x + s.away.x * t;
      y = Math.max(BALL_RADIUS, s.cur.ball.y + s.away.y * t - 4.9 * t * t);
      z = s.cur.ball.z + s.away.z * t;
    } else if (f && aftermath) {
      const t = s.t;
      const p = t < 0 ? f.samples[0].ball : t <= f.end.t ? flightAt(f, t).ball : aftermathAt(aftermath, t);
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
    } else if (s.cur.ball) {
      // A pass on its way (stopped dead where it was cut out).
      const k = s.end ? 1 : Math.min(1, s.acc / TICK);
      const from = s.prev.ball ?? s.cur.ball;
      x = lerp(from.x, s.cur.ball.x, k);
      y = lerp(from.y, s.cur.ball.y, k);
      z = lerp(from.z, s.cur.ball.z, k);
    } else if (end?.outcome === "dispossessed") {
      // Taken off his feet: it runs on with the slide.
      const d = s.cur.defs.find((o) => o.mode === "lunge");
      x = g.position.x + (d ? d.dirX * 5 * s.dt : 0);
      z = g.position.z + (d ? d.dirZ * 5 * s.dt : 0);
    } else {
      const a = attackerAt(s);
      // Dribbling: a touch every couple of strides runs it a little ahead.
      const moved = Math.hypot(a.x - stride.current.x, a.z - stride.current.z);
      stride.current.phase += moved / 1.1;
      const lead = s.cur.lead + 0.16 * Math.sin(stride.current.phase * Math.PI);
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

/** The camera behind him: this far (m) and this high near the goal and far
 * from it — far enough back that the players read as small as on a TV
 * broadcast, the goal and the defenders round him in the frame. */
const CAM_BACK_NEAR = 5.4;
const CAM_BACK_FAR = 7.6;
const CAM_UP_NEAR = 2.6;
const CAM_UP_FAR = 3.4;

/** The team episodes want the teammates in the frame: further back, higher. */
const CAM_WIDE_BACK = 1.75;
const CAM_WIDE_UP = 2.1;

function CameraRig({ stage, flight, wide }: { stage: StageRef; flight: ShotFlight | null; wide: boolean }) {
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
      const back = lerp(CAM_BACK_NEAR, CAM_BACK_FAR, near) * (wide ? CAM_WIDE_BACK : 1);
      tmp.want.set(a.x - (bx / bl) * back, lerp(CAM_UP_NEAR, CAM_UP_FAR, near) * (wide ? CAM_WIDE_UP : 1), a.z - (bz / bl) * back);
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
