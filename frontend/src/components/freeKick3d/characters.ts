import * as THREE from "three";

/** The generated footballers (one skinned mesh, a plain white kit; built by
 * tools/free-kick-3d/build_character.py with the Soccer pack's clips). The
 * kit is told apart from skin and hair by colour, and shirt / shorts /
 * socks by height in the bind pose — fractions of the body's height,
 * measured when the GLB was built. */
export type Character = {
  url: string;
  /** Where the right toe is at the kick's contact frame, in the
   * character's own frame (it faces +z, +x is its left). */
  toe: THREE.Vector3;
  /** Top of the socks (the bare knee is above it). */
  socksTop: number;
  /** The shirt's hem: shorts below, shirt above. */
  shirtHem: number;
  /** Above this it's hair, not skin. */
  hairline: number;
};

export const CHARACTERS = {
  blond: {
    url: "/free-kick-3d/blond.glb",
    toe: new THREE.Vector3(-1.08, 0, 2.32),
    socksTop: 0.31,
    shirtHem: 0.51,
    hairline: 0.95,
  },
  brown: {
    url: "/free-kick-3d/brown.glb",
    toe: new THREE.Vector3(-1.03, 0, 2.2),
    socksTop: 0.315,
    shirtHem: 0.52,
    hairline: 0.95,
  },
} satisfies Record<string, Character>;

export type CharacterId = keyof typeof CHARACTERS;
