import type { CharacterId } from "./characters";

/** Per-player variety: which generated footballer, and the skin and hair
 * colours that multiply its texture (so only darken — the models are
 * fair-skinned, one blond, one brown-haired), height/width scale the
 * whole body a little. */
export type Look = { character: CharacterId; skin: string; hair: string; height: number; width: number };

export const LOOKS: Look[] = [
  { character: "blond", skin: "#ffffff", hair: "#ffffff", height: 1, width: 1 },
  { character: "brown", skin: "#c98f68", hair: "#3a2a20", height: 1.05, width: 1.04 },
  { character: "blond", skin: "#f1d2bd", hair: "#8a6a4a", height: 0.96, width: 1.02 },
  { character: "brown", skin: "#7a4a32", hair: "#1c1612", height: 1.07, width: 1.05 },
  { character: "blond", skin: "#e6b896", hair: "#5a4030", height: 0.97, width: 0.97 },
  { character: "brown", skin: "#9c6646", hair: "#2a201a", height: 1.03, width: 1.06 },
  { character: "brown", skin: "#f6dcc8", hair: "#ffffff", height: 1.01, width: 0.98 },
];

export const KEEPER_LOOK: Look = { character: "brown", skin: "#dcae8c", hair: "#6a5040", height: 1.06, width: 1.03 };
export const KICKER_LOOK: Look = LOOKS[0];
