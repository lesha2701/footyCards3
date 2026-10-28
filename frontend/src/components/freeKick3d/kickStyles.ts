import * as THREE from "three";

import type { KickStyle } from "@/lib/freeKick3d/fx";

/** The two kicks: the moment the right foot meets the ball (30 fps) and
 * where the toe is then, in the character's own frame (it faces +z, +x is
 * its left) — measured in Blender when the GLB was built — and how much
 * run-up is shown before the ball leaves. `kick` comes in at an angle (a
 * curler), `strike` straight on (a drive). */
export const KICK_STYLES: Record<KickStyle, { contact: number; toe: THREE.Vector3; lead: number }> = {
  kick: { contact: 22 / 30, toe: new THREE.Vector3(-0.96, 0, 2.15), lead: 0.55 },
  strike: { contact: 14 / 30, toe: new THREE.Vector3(0.02, 0, 2.16), lead: 0.45 },
};
