/** The 22 footballers as skinned Mixamo models: placed and turned from
 * the key frames, animated by situation (lib/footballerMotion) — running
 * at their speed, the passer's and the scorer's strikes on the frame the
 * ball leaves, a header's jump, the keeper's dive, the celebration. The
 * model loads with the scene (Suspense: the simple figures stand in
 * meanwhile); animation runs on game time, so slow motion and pause apply. */
import { useFrame, useLoader } from "@react-three/fiber";
import { useEffect, useMemo, useRef, type MutableRefObject } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";

import type { CareerReplay } from "@/api/career";
import { DIVE_REACH, STEP_S, keeperMove, poseTime, keeperSlot, motionAt, placeForStrike, playerAction, strikeWeight, strikes } from "@/lib/footballerMotion";
import { ballState, toWorld, type GoalEpisode } from "@/lib/goalReplay3d";
import { SLOTS, type Timeline } from "@/lib/matchReplay";

import { FOOTBALLER_URL, MOVES_URL, MaterialCache, makePlayer, prepareFootballer, setClip, type SkinnedPlayer } from "./footballer";
import type { ReplayClock, SlotLook } from "./GoalScene";
import { numberTexture } from "./textures";

const SKINS = ["#ffffff", "#c98f68", "#7a4a32", "#e6b896", "#f1d2bd", "#9c6646"];
const HAIR = ["#3a2a20", "#1c1612", null, "#7a5a3a", "#b08a50", "#2a1f1a"];

function wrapAngle(a: number): number {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
}

export function SkinnedPlayers({ tl, replay, ep, flip, looks, clock, onReady }: {
  tl: Timeline;
  replay: CareerReplay;
  ep: GoalEpisode;
  flip: boolean;
  looks: SlotLook[];
  clock: MutableRefObject<ReplayClock>;
  onReady?: () => void;
}) {
  const [gltf, moves] = useLoader(GLTFLoader, [FOOTBALLER_URL, MOVES_URL], (loader) => {
    loader.setMeshoptDecoder(MeshoptDecoder);
  });
  const asset = useMemo(() => prepareFootballer(gltf, moves), [gltf, moves]);
  const materials = useMemo(() => new MaterialCache(), []);
  const players = useMemo<SkinnedPlayer[]>(() => looks.map((l, i) => makePlayer(asset, {
    shirt: l.keeper ? l.kit.gk : l.kit.fill,
    shorts: l.kit.shorts,
    socks: l.keeper ? l.kit.gk : l.kit.fill,
    skin: SKINS[(i * 5) % SKINS.length],
    hair: HAIR[(i * 7) % HAIR.length],
  }, materials)), [asset, looks, materials]);
  useEffect(() => () => players.forEach((p) => p.mixer.stopAllAction()), [players]);
  useEffect(() => {
    onReady?.();
  }, [onReady, players]);
  useEffect(() => () => materials.dispose(), [materials]);

  const numbers = useMemo(
    () => looks.map((l) => numberTexture(l.n, l.keeper ? l.kit.gk : l.kit.fill, l.kit.text)),
    [looks],
  );
  useEffect(() => () => numbers.forEach((t) => t.dispose()), [numbers]);
  const geo = useMemo(() => ({
    shadow: new THREE.CircleGeometry(0.45, 12).rotateX(-Math.PI / 2),
    ring: new THREE.RingGeometry(0.62, 0.82, 28).rotateX(-Math.PI / 2),
  }), []);
  const shadowMat = useMemo(() => new THREE.MeshBasicMaterial({ color: "#000000", transparent: true, opacity: 0.32, depthWrite: false }), []);
  useEffect(() => () => {
    geo.shadow.dispose();
    geo.ring.dispose();
    shadowMat.dispose();
  }, [geo, shadowMat]);

  const kicks = useMemo(() => strikes(replay, ep), [replay, ep]);
  const keeper = useMemo(() => keeperMove(tl, ep, flip), [tl, ep, flip]);
  const shadows = useRef<THREE.InstancedMesh>(null);
  const ring = useRef<THREE.Mesh>(null);
  const sprites = useRef<(THREE.Sprite | null)[]>([]);
  const state = useRef({ heading: new Float32Array(SLOTS), lastT: Number.NaN });
  const tmp = useMemo(() => new THREE.Matrix4(), []);

  useFrame((_, dtReal) => {
    const t = clock.current.t;
    const s = state.current;
    const dtGame = (t - s.lastT) * STEP_S;
    const jump = !(dtGame >= 0 && dtGame < 2);
    s.lastT = t;
    const ball = toWorld(ballState(tl, ep, t), flip);
    const ahead = toWorld(ballState(tl, ep, Math.min(ep.f1, t + 1)), flip);
    // Quick turns: the ball is at his feet the way he runs, so his body must
    // follow it closely.
    const turn = 1 - Math.exp(-18 * Math.min(dtReal, 0.1));
    for (let i = 0; i < SLOTS; i++) {
      const p = players[i];
      const m = motionAt(tl, i, poseTime(ep, i, t), flip);
      const act = playerAction(tl, replay, ep, i, t, flip, asset.timing, kicks);
      const celebrating = act.clip === "victory" || act.clip === "celebrate";
      // Facing: along the run; at a strike, where the ball goes; standing, the ball.
      let target: number;
      if (act.clip === "kick" || act.clip === "header") target = Math.atan2(ahead.x - m.x, ahead.z - m.z);
      // Backpedalling: facing the ball, moving away from it.
      else if (act.clip === "run_back") target = Math.atan2(ball.x - m.x, ball.z - m.z);
      else if (celebrating && t > ep.goal + 1) target = s.heading[i];
      else if (m.speed >= 0.9) target = Math.atan2(m.vx, m.vz);
      else target = Math.atan2(ball.x - m.x, ball.z - m.z);
      // The beaten keeper squares up to his line to dive along it / catch.
      if (act.clip.startsWith("gk_") && i === keeperSlot(ep) && t >= ep.goal - 1.2) target = keeper.heading;
      s.heading[i] = jump ? target : s.heading[i] + wrapAngle(target - s.heading[i]) * turn;
      p.root.position.set(m.x, 0, m.z);
      if (act.clip === "kick" && act.time !== null && act.strike !== undefined) {
        // Step into the ball: at the contact the striking toe is on it.
        const at = toWorld(ballState(tl, ep, act.strike), flip);
        const placed = placeForStrike(m, s.heading[i], at, asset.kickToe, strikeWeight(act.time, asset.timing.kickContact));
        p.root.position.set(placed.x, 0, placed.z);
      }
      if (i === keeperSlot(ep) && act.time !== null && act.clip.startsWith("gk_dive")) {
        // Nudge the dive so his hands meet the ball, not his reach (bounded:
        // more would read as sliding).
        const reach = DIVE_REACH[act.clip as keyof typeof DIVE_REACH];
        const progress = THREE.MathUtils.smoothstep(act.time, asset.timing.diveStart, asset.timing.diveReach);
        const extra = THREE.MathUtils.clamp(Math.abs(keeper.lateral) - reach, -1.6, 1.2) * Math.sign(keeper.lateral) * progress;
        p.root.position.x += keeper.left.x * extra;
        p.root.position.z += keeper.left.z * extra;
      }
      p.root.rotation.y = s.heading[i];

      const action = setClip(p, act.clip, act.time !== null, jump ? 0 : 0.15);
      if (act.time !== null) {
        action.timeScale = 0;
        action.time = act.time;
      } else {
        action.timeScale = act.speed;
      }
      p.mixer.update(jump ? 0 : Math.max(0, dtGame));

      if (shadows.current) {
        tmp.makeTranslation(m.x, 0.02, m.z);
        shadows.current.setMatrixAt(i, tmp);
      }
      const sp = sprites.current[i];
      if (sp) sp.position.set(m.x, 2.35, m.z);
      if (i === ep.scorer && ring.current) ring.current.position.set(m.x, 0.03, m.z);
    }
    if (shadows.current) shadows.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <group>
      {players.map((p, i) => <primitive key={i} object={p.root} />)}
      <instancedMesh ref={shadows} args={[geo.shadow, shadowMat, SLOTS]} frustumCulled={false} />
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
