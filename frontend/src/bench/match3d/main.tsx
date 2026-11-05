/** The benchmark of the 11-a-side match: runs the renderers under test one
 * after another on this device and reports the numbers (the dev server's
 * /__bench keeps them). Not part of the app: /bench/match3d.html. */
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";

import { FOOTBALLER_URL, MOVES_URL, MaterialCache, makePlayer, prepareFootballer, setClip, type SkinnedPlayer } from "@/components/career/goal3d/footballer";
import { pitchTexture } from "@/components/career/goal3d/textures";
import { ONE_ON_ONE_MOVES_URL, prepareMoves } from "@/components/oneOnOne/moves";
import { daySkyTexture } from "@/components/freeKick3d/textures";
import { enterImmersive } from "@/lib/immersive";
import { PITCH_L, PITCH_W } from "@/lib/matchReplay";

import { BAKE_FPS, bakeClips, clusterLod, makeCrowd, mergeModel, type Baked, type Crowd, type Merged } from "./baked";
import { HZ, N, createProto, stepProto, type Proto } from "./proto";

type Run = { id: string; mode: "full" | "inst" | "none"; geo?: "full" | "lod"; dpr: number; planar?: boolean; seconds: number };

const WARM = 1.5;
/** Bind-space units: the model stands 0.0785 tall there, so about 5 cm. */
const LOD_CELL = 0.0022;
const RUNS: Run[] = [
  { id: "стадион без игроков", mode: "none", dpr: 1.5, seconds: 5 },
  { id: "как в реплее: 22 скелета, dpr 1", mode: "full", dpr: 1, seconds: 7 },
  { id: "как в реплее: 22 скелета, dpr 1.5", mode: "full", dpr: 1.5, seconds: 7 },
  { id: "инстанс, полная модель, dpr 1.5", mode: "inst", geo: "full", dpr: 1.5, seconds: 7 },
  { id: "инстанс, LOD, dpr 1", mode: "inst", geo: "lod", dpr: 1, seconds: 7 },
  { id: "инстанс, LOD, dpr 1.5", mode: "inst", geo: "lod", dpr: 1.5, seconds: 7 },
  { id: "инстанс, LOD, тени, dpr 1.5", mode: "inst", geo: "lod", dpr: 1.5, planar: true, seconds: 7 },
  { id: "инстанс, LOD, тени, dpr 2", mode: "inst", geo: "lod", dpr: 2, planar: true, seconds: 7 },
];
const SOAK: Run = { id: "прогрев 2 мин: инстанс, LOD, тени, dpr 1.5", mode: "inst", geo: "lod", dpr: 1.5, planar: true, seconds: 120 };

type Row = { id: string; fps: number; p95: number; js: number; sim: number; calls: number; tris: number; dpr: number; soak?: number[] };
type Info = { gpu: string; ua: string; bakeMs: number; bakeH: number; lodTris: number; fullTris: number; screen: string };

const stats = { frames: [] as number[], js: [] as number[], sim: [] as number[], calls: 0, tris: 0 };

const lerpAngle = (a: number, b: number, k: number) => {
  let d = b - a;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return a + d * k;
};

function Stands() {
  const pitch = useMemo(() => pitchTexture(), []);
  const sky = useMemo(() => daySkyTexture(), []);
  const { stands, led } = useLoader(THREE.TextureLoader, ["/free-kick-3d/stands.webp", "/free-kick-3d/led.webp"], undefined).reduce(
    (o, t, i) => ({ ...o, [i ? "led" : "stands"]: t }), {} as { stands: THREE.Texture; led: THREE.Texture });
  useMemo(() => {
    for (const t of [stands, led]) {
      t.colorSpace = THREE.SRGBColorSpace;
      t.wrapS = THREE.RepeatWrapping;
      t.anisotropy = 4;
    }
  }, [stands, led]);
  const sides: [number, number, number, number][] = [
    [0, -PITCH_W / 2 - 17, PITCH_L + 40, 0], [0, PITCH_W / 2 + 17, PITCH_L + 40, Math.PI],
    [-PITCH_L / 2 - 18, 0, PITCH_W + 40, Math.PI / 2], [PITCH_L / 2 + 18, 0, PITCH_W + 40, -Math.PI / 2],
  ];
  return (
    <>
      <mesh><sphereGeometry args={[340, 24, 16]} /><meshBasicMaterial map={sky} side={THREE.BackSide} fog={false} depthWrite={false} /></mesh>
      <mesh rotation-x={-Math.PI / 2} position-y={-0.02}><planeGeometry args={[PITCH_L + 22, PITCH_W + 18]} /><meshLambertMaterial color="#2f7f3a" /></mesh>
      <mesh rotation-x={-Math.PI / 2}><planeGeometry args={[PITCH_L, PITCH_W]} /><meshLambertMaterial map={pitch} /></mesh>
      {sides.map(([x, z, w, r], i) => (
        <group key={i} position={[x, 9, z]} rotation={[0, r, 0]}>
          <mesh rotation-x={-0.6}><planeGeometry args={[w, 24]} /><meshBasicMaterial map={stands} /></mesh>
          <mesh position={[0, -8.5, 13]}><boxGeometry args={[w * 0.8, 0.9, 0.15]} /><meshBasicMaterial map={led} /></mesh>
        </group>
      ))}
    </>
  );
}

/** Heading and clip state of a footballer, in the render's time. */
type Mover = { yaw: Float32Array; clip: Int8Array; t: Float32Array; prev: Int8Array; prevT: Float32Array; fade: Float32Array };
const RUN_NAMES = ["idle", "run", "sprint"] as const;
const clipFor = (v: number) => (v < 0.7 ? 0 : v < 5.2 ? 1 : 2);

function useProto() {
  const sim = useRef<{ s: Proto; acc: number; px: Float64Array; pz: Float64Array } | null>(null);
  if (!sim.current) sim.current = { s: createProto(7), acc: 0, px: new Float64Array(N), pz: new Float64Array(N) };
  return sim;
}

function Scene({ run, onDone }: { run: Run; onDone: (r: Row) => void }) {
  const sim = useProto();
  const players = useRef<{ update: (dt: number, alpha: number, s: Proto, px: Float64Array, pz: Float64Array) => void } | null>(null);
  const ball = useRef<THREE.Mesh>(null);
  const { camera, gl, scene, setDpr } = useThree();
  const clock = useRef({ t: 0 });
  useEffect(() => { setDpr(run.dpr); stats.frames = []; stats.js = []; stats.sim = []; clock.current.t = 0; }, [run, setDpr]);
  const soak = useRef<{ next: number; out: number[]; n: number; sum: number }>({ next: 20, out: [], n: 0, sum: 0 });
  useFrame((_, delta) => {
    const start = performance.now();
    const c = clock.current;
    const dt = Math.min(delta, 0.1);
    c.t += delta;
    const st = sim.current!;
    st.acc += dt;
    const simStart = performance.now();
    let ticks = 0;
    while (st.acc >= 1 / HZ) {
      st.px.set(st.s.x);
      st.pz.set(st.s.z);
      stepProto(st.s);
      st.acc -= 1 / HZ;
      ticks += 1;
    }
    const simMs = performance.now() - simStart;
    const alpha = st.acc * HZ;
    players.current?.update(dt, alpha, st.s, st.px, st.pz);
    const bx = st.s.bx, bz = st.s.bz;
    if (ball.current) ball.current.position.set(bx, 0.15, bz);
    camera.position.lerp(new THREE.Vector3(bx * 0.72, 24, 62), 0.06);
    camera.lookAt(bx * 0.8, 0, bz * 0.5);
    gl.render(scene, camera);
    if (c.t > WARM) {
      stats.frames.push(delta * 1000);
      stats.js.push(performance.now() - start);
      if (ticks) stats.sim.push(simMs / ticks);
      stats.calls = gl.info.render.calls;
      stats.tris = gl.info.render.triangles;
      const so = soak.current;
      so.n += 1;
      so.sum += delta;
      if (run.seconds > 60 && c.t > so.next) {
        so.out.push(Math.round(so.n / so.sum));
        so.n = 0;
        so.sum = 0;
        so.next += 20;
      }
    }
    if (c.t > run.seconds) {
      const sorted = [...stats.frames].sort((a, b) => a - b);
      const avg = (x: number[]) => x.reduce((a, b) => a + b, 0) / Math.max(1, x.length);
      onDone({
        id: run.id,
        fps: Math.round(1000 / avg(sorted)),
        p95: Math.round(sorted[Math.floor(sorted.length * 0.95)] ?? 0),
        js: +avg(stats.js).toFixed(1),
        sim: +avg(stats.sim).toFixed(2),
        calls: stats.calls,
        tris: stats.tris,
        dpr: gl.getPixelRatio(),
        soak: run.seconds > 60 ? soak.current.out : undefined,
      });
    }
  }, 1);
  return (
    <>
      <color attach="background" args={["#9cc3ea"]} />
      <fog attach="fog" args={["#c4d6e6", 140, 330]} />
      <hemisphereLight args={["#d6e8ff", "#3f6b32", 1.5]} />
      <directionalLight position={[-40, 60, 25]} intensity={2.1} color="#fff2d8" />
      <Stands />
      <mesh ref={ball}><sphereGeometry args={[0.25, 12, 8]} /><meshLambertMaterial color="#fff" /></mesh>
      {run.mode === "full" && <Skeletons key={run.id} handle={players} />}
      {run.mode === "inst" && <Instanced key={run.id} run={run} handle={players} />}
    </>
  );
}

type Handle = { current: { update: (dt: number, alpha: number, s: Proto, px: Float64Array, pz: Float64Array) => void } | null };

function makeMover(): Mover {
  return { yaw: new Float32Array(N), clip: new Int8Array(N), t: new Float32Array(N), prev: new Int8Array(N), prevT: new Float32Array(N), fade: new Float32Array(N).fill(1) };
}

function useAssets() {
  const [gltf, base, moves] = useLoader(GLTFLoader, [FOOTBALLER_URL, MOVES_URL, ONE_ON_ONE_MOVES_URL], (l) => {
    l.setMeshoptDecoder(MeshoptDecoder);
  });
  return useMemo(() => {
    const asset = prepareFootballer(gltf, base);
    const extra = prepareMoves(gltf, moves);
    return { gltf, asset, clips: { ...asset.clips, ...extra.clips } as Record<string, THREE.AnimationClip> };
  }, [gltf, base, moves]);
}

function Skeletons({ handle }: { handle: Handle }) {
  const { asset } = useAssets();
  const materials = useMemo(() => new MaterialCache(), []);
  const list = useMemo<SkinnedPlayer[]>(() => Array.from({ length: N }, (_, i) => makePlayer(asset, {
    shirt: i % 11 === 0 ? "#f4d03f" : i < 11 ? "#d7263d" : "#1e88e5", shorts: i < 11 ? "#ffffff" : "#10243d", socks: i < 11 ? "#d7263d" : "#1e88e5",
    skin: ["#ffffff", "#c98f68", "#7a4a32", "#e6b896"][i % 4], hair: i % 3 ? "#3a2a20" : "#7a5a3a",
  }, materials)), [asset, materials]);
  const mv = useMemo(makeMover, []);
  useEffect(() => {
    handle.current = {
      update: (dt, alpha, s, px, pz) => {
        for (let i = 0; i < N; i++) {
          const v = Math.sqrt(s.vx[i] ** 2 + s.vz[i] ** 2);
          const p = list[i];
          p.root.position.set(px[i] + (s.x[i] - px[i]) * alpha, 0, pz[i] + (s.z[i] - pz[i]) * alpha);
          if (v > 0.4) mv.yaw[i] = lerpAngle(mv.yaw[i], Math.atan2(s.vx[i], s.vz[i]), 0.2);
          p.root.rotation.y = mv.yaw[i];
          const a = setClip(p, RUN_NAMES[clipFor(v)], false);
          a.timeScale = clipFor(v) === 0 ? 1 : v / (clipFor(v) === 1 ? asset.timing.runSpeed : asset.timing.sprintSpeed);
          p.mixer.update(dt);
        }
      },
    };
    return () => { handle.current = null; list.forEach((p) => p.mixer.stopAllAction()); materials.dispose(); };
  }, [asset, handle, list, materials, mv]);
  return <>{list.map((p, i) => <primitive key={i} object={p.root} />)}</>;
}

const shared: { baked?: Baked; full?: Merged; lod?: Merged } = {};
export const info: Info = { gpu: "", ua: navigator.userAgent, bakeMs: 0, bakeH: 0, lodTris: 0, fullTris: 0, screen: "" };

function Instanced({ run, handle }: { run: Run; handle: Handle }) {
  const { gltf, clips } = useAssets();
  const crowd = useMemo<Crowd>(() => {
    if (!shared.baked) {
      const t0 = performance.now();
      const { merged, boneNames } = mergeModel(gltf);
      shared.full = merged;
      shared.lod = clusterLod(merged, LOD_CELL);
      shared.baked = bakeClips(gltf, clips, boneNames);
      info.bakeMs = Math.round(performance.now() - t0);
      info.bakeH = shared.baked.height;
      info.fullTris = merged.index.length / 3;
      info.lodTris = shared.lod.index.length / 3;
    }
    let map: THREE.Texture | null = null;
    gltf.scene.traverse((o) => {
      const mat = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined;
      if (mat?.map && /body/i.test(mat.map.name || mat.name || "body") && !map) map = mat.map;
    });
    return makeCrowd(run.geo === "lod" ? shared.lod! : shared.full!, shared.baked, map, N, !!run.planar);
  }, [clips, gltf, run]);
  const mv = useMemo(makeMover, []);
  useEffect(() => {
    const rows = RUN_NAMES.map((n) => shared.baked!.rows[n]);
    const frame = (c: number, t: number) => {
      const r = rows[c];
      const f = ((t % r.duration) / r.duration) * (r.count - 1);
      return { a: r.first + Math.floor(f), w: f - Math.floor(f), next: r.first + (Math.floor(f) + 1) % r.count };
    };
    const pose = crowd.pose.array as Float32Array;
    handle.current = {
      update: (dt, alpha, s, px, pz) => {
        for (let i = 0; i < N; i++) {
          const v = Math.sqrt(s.vx[i] ** 2 + s.vz[i] ** 2);
          const c = clipFor(v);
          if (c !== mv.clip[i]) {
            mv.prev[i] = mv.clip[i];
            mv.prevT[i] = mv.t[i];
            mv.clip[i] = c;
            mv.t[i] = 0;
            mv.fade[i] = 0;
          }
          const speed = c === 0 ? 1 : (v / (c === 1 ? 5.5 : 8)) * 1;
          mv.t[i] += dt * speed;
          mv.prevT[i] += dt;
          mv.fade[i] = Math.min(1, mv.fade[i] + dt / 0.15);
          const now = frame(c, mv.t[i]);
          if (mv.fade[i] < 1) {
            const old = frame(mv.prev[i], mv.prevT[i]);
            pose[i * 3] = old.a;
            pose[i * 3 + 1] = now.a;
            pose[i * 3 + 2] = mv.fade[i];
          } else {
            pose[i * 3] = now.a;
            pose[i * 3 + 1] = now.next;
            pose[i * 3 + 2] = now.w;
          }
          if (v > 0.4) mv.yaw[i] = lerpAngle(mv.yaw[i], Math.atan2(s.vx[i], s.vz[i]), 0.2);
          crowd.set(i, px[i] + (s.x[i] - px[i]) * alpha, pz[i] + (s.z[i] - pz[i]) * alpha, mv.yaw[i]);
        }
        crowd.commit();
      },
    };
    return () => { handle.current = null; crowd.dispose(); };
  }, [crowd, handle, mv]);
  return <primitive object={crowd.group} />;
}

function GpuName() {
  const gl = useThree((s) => s.gl);
  useEffect(() => {
    const c = gl.getContext();
    const ext = c.getExtension("WEBGL_debug_renderer_info");
    info.gpu = ext ? String(c.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : String(c.getParameter(c.RENDERER));
    info.screen = `${window.innerWidth}×${window.innerHeight} @${window.devicePixelRatio}`;
  }, [gl]);
  return null;
}

function App() {
  const [phase, setPhase] = useState<"idle" | "run" | "done">("idle");
  const [step, setStep] = useState(0);
  const [rows, setRows] = useState<Row[]>([]);
  const [plan, setPlan] = useState<Run[]>(RUNS);
  const [sent, setSent] = useState("");
  const start = (soak: boolean) => {
    enterImmersive();
    setPlan(soak ? [...RUNS, SOAK] : RUNS);
    setRows([]);
    setStep(0);
    setPhase("run");
  };
  const onDone = (r: Row) => {
    if (rows.length > step) return;
    const next = [...rows, r];
    setRows(next);
    if (step + 1 >= plan.length) {
      setPhase("done");
      const heap = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize;
      fetch("/__bench", { method: "POST", body: JSON.stringify({ info, heapMb: heap ? Math.round(heap / 1e6) : null, bakeFps: BAKE_FPS, rows: next }) })
        .then((res) => setSent(res.ok ? "Результаты отправлены" : "Не отправилось: сделайте скриншот"))
        .catch(() => setSent("Не отправилось: сделайте скриншот"));
    } else setStep(step + 1);
  };
  return (
    <div style={{ position: "fixed", inset: 0, background: "#0b1a2b", color: "#fff", font: "13px system-ui" }}>
      {phase === "run" && (
        <Canvas dpr={1} frameloop="always" gl={{ antialias: false, powerPreference: "high-performance", stencil: false }} camera={{ fov: 30, near: 1, far: 500, position: [0, 24, 62] }}>
          <GpuName />
          <Suspense fallback={null}>
            <Scene key={step} run={plan[step]} onDone={onDone} />
          </Suspense>
        </Canvas>
      )}
      {phase === "run" && (
        <div style={{ position: "absolute", top: 8, left: 12, textShadow: "0 1px 3px #000", pointerEvents: "none" }}>
          Шаг {step + 1} из {plan.length}: {plan[step].id}
        </div>
      )}
      {phase !== "run" && (
        <div style={{ position: "absolute", inset: 0, overflow: "auto", padding: 16 }}>
          <h3 style={{ margin: "0 0 8px" }}>Замер матча 11 на 11</h3>
          <p style={{ margin: "0 0 12px" }}>Закройте другие приложения и не выключайте экран.</p>
          <button onClick={() => start(false)} style={btn}>Быстрый замер (1 мин)</button>{" "}
          <button onClick={() => start(true)} style={btn}>С прогревом (3 мин)</button>
          {phase === "done" && <p>{sent}</p>}
          {rows.length > 0 && (
            <table style={{ marginTop: 12, borderCollapse: "collapse", fontSize: 11 }}>
              <thead><tr>{["режим", "fps", "p95 мс", "JS мс", "сим мс", "draw", "тыс. тр."].map((h) => <th key={h} style={{ textAlign: "left", paddingRight: 8 }}>{h}</th>)}</tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.id}><td style={{ paddingRight: 8 }}>{r.id}</td><td>{r.fps}</td><td>{r.p95}</td><td>{r.js}</td><td>{r.sim}</td><td>{r.calls}</td><td>{Math.round(r.tris / 1000)}</td></tr>
              ))}</tbody>
            </table>
          )}
          {rows.some((r) => r.soak) && <p>Прогрев, fps каждые 20 с: {rows.find((r) => r.soak)?.soak?.join(" · ")}</p>}
          {info.gpu && <p style={{ opacity: 0.7, fontSize: 11 }}>{info.gpu} · {info.screen} · запекание {info.bakeMs} мс</p>}
        </div>
      )}
    </div>
  );
}

const btn: React.CSSProperties = { padding: "12px 16px", borderRadius: 10, border: 0, background: "#2fbf71", color: "#04210f", fontWeight: 700, fontSize: 14 };

createRoot(document.getElementById("root")!).render(<App />);
