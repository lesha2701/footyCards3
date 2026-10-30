import { useFrame } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { GOAL_HALF_WIDTH, GOAL_HEIGHT } from "@/lib/freeKick3d/trajectory";

const COUNT = 220;
const COLORS = ["#3ed17e", "#c6e63a", "#22d3c4", "#f8fafc", "#facc15"];
const LIFETIME = 3.2;

type Piece = { p: THREE.Vector3; v: THREE.Vector3; spin: THREE.Vector3; rot: THREE.Euler };

/** A burst of confetti over the goal; `burstId` changes → a new burst.
 * One instanced draw call, hidden when idle. */
export default function Confetti({ burstId }: { burstId: number }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const started = useRef(-1);
  const pieces = useMemo<Piece[]>(
    () =>
      Array.from({ length: COUNT }, () => ({
        p: new THREE.Vector3(),
        v: new THREE.Vector3(),
        spin: new THREE.Vector3(),
        rot: new THREE.Euler(),
      })),
    [],
  );
  const dummy = useMemo(() => new THREE.Object3D(), []);

  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    const color = new THREE.Color();
    for (let i = 0; i < COUNT; i++) m.setColorAt(i, color.set(COLORS[i % COLORS.length]));
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }, []);

  useLayoutEffect(() => {
    if (burstId <= 0) return;
    started.current = -2; // armed: the next frame records the start time
    for (const piece of pieces) {
      piece.p.set((Math.random() * 2 - 1) * GOAL_HALF_WIDTH * 1.4, GOAL_HEIGHT + 0.5 + Math.random(), -1 - Math.random() * 2);
      piece.v.set((Math.random() * 2 - 1) * 3, 4 + Math.random() * 6, 1 + Math.random() * 4);
      piece.spin.set(Math.random() * 10, Math.random() * 10, Math.random() * 10);
      piece.rot.set(Math.random() * 6, Math.random() * 6, Math.random() * 6);
    }
  }, [burstId, pieces]);

  useFrame((state, delta) => {
    const m = mesh.current;
    if (!m) return;
    const now = state.clock.getElapsedTime();
    if (started.current === -2) started.current = now;
    const age = started.current < 0 ? Infinity : now - started.current;
    m.visible = age < LIFETIME;
    if (!m.visible) return;
    const dt = Math.min(delta, 0.05);
    pieces.forEach((piece, i) => {
      piece.v.y -= 6 * dt;
      piece.v.multiplyScalar(1 - 1.6 * dt); // paper flutters: heavy drag
      piece.p.addScaledVector(piece.v, dt);
      piece.rot.x += piece.spin.x * dt;
      piece.rot.y += piece.spin.y * dt;
      piece.rot.z += piece.spin.z * dt;
      dummy.position.copy(piece.p);
      dummy.rotation.copy(piece.rot);
      dummy.scale.setScalar(Math.max(0, 1 - Math.max(0, age - LIFETIME + 0.6) / 0.6));
      dummy.updateMatrix();
      m.setMatrixAt(i, dummy.matrix);
    });
    m.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, COUNT]} visible={false} frustumCulled={false}>
      <planeGeometry args={[0.09, 0.14]} />
      <meshBasicMaterial side={THREE.DoubleSide} toneMapped={false} />
    </instancedMesh>
  );
}
