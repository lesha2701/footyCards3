import { useTexture } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { Suspense, useLayoutEffect, useMemo, useRef, type MutableRefObject } from "react";
import * as THREE from "three";

import { PITCH_DEPTH, PITCH_WIDTH, PITCH_Z0, ledTexture, pitchOverlayTexture, skyTexture } from "./textures";

export type Quality = "high" | "low";

/** 0 = calm crowd, 1 = a goal just went in (decays in the scene). */
export type Hype = MutableRefObject<number>;

/** Art generated for the prototype (public/free-kick-3d, webp). */
const ASSETS = {
  stands: "/free-kick-3d/stands.webp",
  fans: "/free-kick-3d/fans.webp",
  grass: "/free-kick-3d/grass.webp",
  led: "/free-kick-3d/led.webp",
};

/** The stadium: sky, pitch, a crowd panorama for the stands, a few close
 * rows of live fans that celebrate (the hybrid: the panorama gives the
 * density, the sprites the reaction), LED boards. Images load lazily; until they do,
 * a plain pitch and the sky stand in. */
export function Stadium({ quality, hype, farStands = false }: { quality: Quality; hype: Hype; farStands?: boolean }) {
  return (
    <>
      <Sky />
      <Suspense fallback={<PlainPitch quality={quality} />}>
        <Pitch quality={quality} />
        <Backdrop />
        {/* Seen from behind the goal (a penalty in goal), the other end fills too. */}
        {farStands && <Backdrop radius={44} centerZ={12} facing="pitch" />}
        <FanSection quality={quality} hype={hype} />
        <LedBoards hype={hype} />
      </Suspense>
    </>
  );
}

function Sky() {
  const tex = useMemo(skyTexture, []);
  return (
    <mesh>
      <sphereGeometry args={[160, 24, 16]} />
      <meshBasicMaterial map={tex} side={THREE.BackSide} fog={false} depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

const PITCH_CENTER: [number, number, number] = [0, 0, PITCH_Z0 + PITCH_DEPTH / 2];

function PlainPitch({ quality }: { quality: Quality }) {
  return (
    <mesh rotation-x={-Math.PI / 2} position={PITCH_CENTER} receiveShadow={quality === "high"}>
      <planeGeometry args={[PITCH_WIDTH, PITCH_DEPTH]} />
      <meshLambertMaterial color="#2c8a47" />
    </mesh>
  );
}

/** Tiled grass photo, plus a transparent layer on top with the mowing
 * stripes and the markings (crisp at any distance, independent of the tile). */
function Pitch({ quality }: { quality: Quality }) {
  const grass = useTexture(ASSETS.grass, (t) => {
    const tex = t as THREE.Texture;
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(PITCH_WIDTH / 4, PITCH_DEPTH / 4);
    tex.anisotropy = 8;
    tex.colorSpace = THREE.SRGBColorSpace;
  });
  const overlay = useMemo(pitchOverlayTexture, []);
  const shadows = quality === "high";
  return (
    <>
      <mesh rotation-x={-Math.PI / 2} position={PITCH_CENTER} receiveShadow={shadows}>
        <planeGeometry args={[PITCH_WIDTH, PITCH_DEPTH]} />
        {/* Toned down a little: it's a night match under floodlights. */}
        <meshLambertMaterial map={grass} color="#b8d8b4" />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[PITCH_CENTER[0], 0.004, PITCH_CENTER[2]]} receiveShadow={shadows}>
        <planeGeometry args={[PITCH_WIDTH, PITCH_DEPTH]} />
        <meshLambertMaterial map={overlay} transparent depthWrite={false} polygonOffset polygonOffsetFactor={-1} />
      </mesh>
    </>
  );
}

/** The stands: an arc of a cylinder around the goal end, seen from the
 * inside, papered with the crowd panorama. Stretched once over the arc the
 * people would come out three times life size, so the picture is laid
 * three times (stands.webp is cut to tile seamlessly: the flags at its
 * edges trimmed, the ends crossfaded). Its dark
 * board line at the bottom sits just below the pitch. */
const BACKDROP_RADIUS = 82;
const BACKDROP_ARC = (150 / 180) * Math.PI;
const BACKDROP_CENTER_Z = 18;
const BACKDROP_TILES = 3;

function Backdrop({
  radius = BACKDROP_RADIUS,
  centerZ = BACKDROP_CENTER_Z,
  facing = "goal",
}: {
  radius?: number;
  centerZ?: number;
  /** «goal»: the stands behind the goal; «pitch»: the far end. */
  facing?: "goal" | "pitch";
}) {
  const tex = useTexture(ASSETS.stands, (t) => {
    const tex = t as THREE.Texture;
    // Seen from inside the cylinder the u axis runs right → left: mirror it.
    tex.wrapS = THREE.RepeatWrapping;
    tex.repeat.x = -BACKDROP_TILES;
    tex.anisotropy = 4;
    tex.colorSpace = THREE.SRGBColorSpace;
  });
  const image = tex.image as { width: number; height: number };
  // The same picture size per metre of arc whatever the radius.
  const height = (BACKDROP_RADIUS * BACKDROP_ARC * image.height) / (image.width * BACKDROP_TILES);
  const start = (facing === "goal" ? Math.PI : 0) - BACKDROP_ARC / 2;
  return (
    <mesh position={[0, height / 2 - 1.5, centerZ]}>
      <cylinderGeometry args={[radius, radius, height, 48, 1, true, start, BACKDROP_ARC]} />
      <meshBasicMaterial map={tex} side={THREE.BackSide} fog={false} toneMapped={false} depthWrite={false} />
    </mesh>
  );
}

/** Supporters right behind the boards, cut from a 4×4 sprite sheet: one
 * instanced draw call, the cell picked per instance and the bobbing done
 * in the vertex shader — no per-frame CPU work. They jump on a goal. */
function FanSection({ quality, hype }: { quality: Quality; hype: Hype }) {
  const sheet = useTexture(ASSETS.fans, (t) => {
    (t as THREE.Texture).colorSpace = THREE.SRGBColorSpace;
  });
  const mesh = useRef<THREE.InstancedMesh>(null);
  // Just the front rows: the panorama behind is the rest of the crowd.
  const rows = quality === "high" ? 3 : 2;
  const fans = useMemo(() => {
    const out: { x: number; y: number; z: number; cell: number; scale: number }[] = [];
    let seed = 11;
    const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    for (let r = 0; r < rows; r++) {
      const cols = 46 + r * 4;
      for (let c = 0; c < cols; c++) {
        if (rnd() < 0.12) continue; // a few empty seats
        const x = -24 - r * 2 + ((c + 0.5 + (rnd() - 0.5) * 0.5) / cols) * (48 + r * 4);
        out.push({ x, y: 0.55 + r * 0.55, z: -6.6 - r * 0.85, cell: Math.floor(rnd() * 16), scale: 0.95 + rnd() * 0.2 });
      }
    }
    return out;
  }, [rows]);

  const material = useMemo(() => {
    const m = new THREE.MeshBasicMaterial({ map: sheet, alphaTest: 0.5, color: "#c9cbd6" });
    m.onBeforeCompile = (shader) => {
      shader.uniforms.uTime = { value: 0 };
      shader.uniforms.uHype = { value: 0 };
      m.userData.shader = shader;
      shader.vertexShader = shader.vertexShader
        .replace(
          "#include <common>",
          "#include <common>\nattribute float aCell;\nuniform float uTime;\nuniform float uHype;",
        )
        .replace(
          "#include <uv_vertex>",
          `#include <uv_vertex>
          vMapUv = (vMapUv + vec2(mod(aCell, 4.0), 3.0 - floor(aCell / 4.0))) / 4.0;`,
        )
        .replace(
          "#include <begin_vertex>",
          `#include <begin_vertex>
          float ph = float(gl_InstanceID) * 1.618;
          float sway = sin(uTime * (1.4 + fract(ph) * 1.4) + ph * 6.0);
          float jump = abs(sin(uTime * (6.5 + fract(ph * 3.1) * 3.0) + ph * 9.0));
          transformed.y += sway * 0.025 + jump * uHype * 0.4;`,
        );
    };
    return m;
  }, [sheet]);

  const geometry = useMemo(() => {
    const g = new THREE.PlaneGeometry(1, 1);
    g.setAttribute("aCell", new THREE.InstancedBufferAttribute(new Float32Array(fans.map((f) => f.cell)), 1));
    return g;
  }, [fans]);

  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    const o = new THREE.Object3D();
    fans.forEach((f, i) => {
      o.position.set(f.x, f.y, f.z);
      o.scale.setScalar(f.scale);
      o.updateMatrix();
      m.setMatrixAt(i, o.matrix);
    });
    m.instanceMatrix.needsUpdate = true;
  }, [fans]);

  useFrame((state) => {
    const shader = material.userData.shader as { uniforms: Record<string, { value: number }> } | undefined;
    if (!shader) return;
    shader.uniforms.uTime.value = state.clock.getElapsedTime();
    shader.uniforms.uHype.value = hype.current;
  });

  return (
    <instancedMesh key={fans.length} ref={mesh} args={[geometry, material, fans.length]} frustumCulled={false} />
  );
}

/** LED boards behind the goal line, scrolling; on a goal they flash «ГОЛ!». */
function LedBoards({ hype }: { hype: Hype }) {
  const BOARD = 60;
  const brand = useTexture(ASSETS.led, (t) => {
    const tex = t as THREE.Texture;
    const image = tex.image as { width: number; height: number };
    tex.wrapS = THREE.RepeatWrapping;
    tex.repeat.set(BOARD / (image.width / image.height), 1);
    tex.colorSpace = THREE.SRGBColorSpace;
  });
  const goal = useMemo(() => {
    const tex = ledTexture("ГОЛ!", "#c6e63a");
    tex.repeat.set(BOARD / 16, 1);
    return tex;
  }, []);
  const mat = useRef<THREE.MeshBasicMaterial>(null);
  useFrame((_, delta) => {
    const m = mat.current;
    if (!m) return;
    const celebrating = hype.current > 0.3;
    const tex = celebrating ? goal : brand;
    if (m.map !== tex) {
      m.map = tex;
      m.needsUpdate = true;
    }
    tex.offset.x = (tex.offset.x + delta * (celebrating ? 0.6 : 0.08)) % 1;
  });
  return (
    <mesh position={[0, 0.5, -5]}>
      <boxGeometry args={[BOARD, 1, 0.15]} />
      <meshBasicMaterial ref={mat} map={brand} toneMapped={false} />
    </mesh>
  );
}
