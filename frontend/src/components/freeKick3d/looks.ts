/** Per-player variety on the one shared model: the skin and hair colours
 * multiply its textures (so only darken), `hair: null` is a shaved head,
 * height/width scale the whole body a little. */
export type Look = { skin: string; hair: string | null; height: number; width: number };

export const LOOKS: Look[] = [
  { skin: "#ffffff", hair: "#ffffff", height: 1, width: 1 },
  { skin: "#c98f68", hair: "#3a2a20", height: 1.05, width: 1.04 },
  { skin: "#f1d2bd", hair: null, height: 0.96, width: 1.02 },
  { skin: "#7a4a32", hair: "#1c1612", height: 1.07, width: 1.05 },
  { skin: "#e6b896", hair: "#7a5a3a", height: 0.97, width: 0.97 },
  { skin: "#9c6646", hair: null, height: 1.03, width: 1.06 },
  { skin: "#f6dcc8", hair: "#b08a50", height: 1.01, width: 0.98 },
];

export const KEEPER_LOOK: Look = { skin: "#dcae8c", hair: "#2a1f1a", height: 1.06, width: 1.03 };
export const KICKER_LOOK: Look = LOOKS[0];
