import * as THREE from "three";

/** The kick (Mixamo "soccer penalty kick": an angled run-up from the left):
 * the moment the right foot meets the ball (30 fps), where the toe is then
 * in the character's own frame (it faces +z, +x is its left) — measured in
 * Blender when the GLB was built — and how much run-up is shown before the
 * ball leaves. */
export const KICK = { contact: 22 / 30, toe: new THREE.Vector3(-0.96, 0, 2.15), lead: 0.55 };
