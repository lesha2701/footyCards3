/** «Зал славы»: the isometric room assembled from separate sprites
 * (assets/hall/*.webp, all drawn at the same 2:1 angle), in SVG units of a
 * 400×400 viewBox. The back corner is at (200, 40), the walls rise WALL_H,
 * the floor is a 2:1 diamond under them.
 *
 * Every sprite is the alpha-cropped PNG: `box` is that crop in the PNG's
 * original pixels, so every measured point below is in original pixels too
 * and `place` maps them into the room. */

export const HALL_VIEW = 400;
/** The room's drawn part: nothing above the back corner's trim. */
export const HALL_TOP = 28;
export const CORNER: Pt = [200, 40];
export const WALL_H = 140;

export type Pt = [number, number];
export type Box = [number, number, number, number];

/** The crops of the source PNGs (`x0, y0, x1, y1`). */
export const BOX = {
  wall_left: [538, 520, 1501, 1522],
  wall_right: [548, 519, 1510, 1522],
  floor: [82, 551, 1966, 1528],
  carpet: [17, 214, 813, 615],
  frame: [86, 17, 296, 365],
  cabinet: [62, 17, 485, 530],
  pedestal: [17, 30, 197, 183],
  plant: [59, 17, 283, 326],
  rope: [17, 22, 243, 238],
  spotlight: [100, 26, 156, 201],
  banner: [66, 17, 212, 262],
} satisfies Record<string, Box>;

/** A sprite in the room: screen = (ox + px·k, oy + py·ky), mirrored
 * around its own centre when `flip`. */
export interface Placed {
  box: Box;
  k: number;
  ky: number;
  ox: number;
  oy: number;
  flip?: boolean;
}

/** Puts the sprite's original pixel `px` onto the room point `at`. */
export function place(box: Box, k: number, px: Pt, at: Pt, ky = k, flip = false): Placed {
  return { box, k, ky, ox: at[0] - px[0] * k, oy: at[1] - px[1] * ky, flip };
}

/** The <image> rectangle of a placed sprite. */
export function rect(p: Placed) {
  const [x0, y0, x1, y1] = p.box;
  return { x: p.ox + x0 * p.k, y: p.oy + y0 * p.ky, width: (x1 - x0) * p.k, height: (y1 - y0) * p.ky };
}

/** A sprite pixel → the room point (flip-aware). */
export function pt(p: Placed, px: Pt): Pt {
  const x = p.ox + px[0] * p.k;
  if (!p.flip) return [x, p.oy + px[1] * p.ky];
  const r = rect(p);
  return [2 * r.x + r.width - x, p.oy + px[1] * p.ky];
}

/* Walls: their top corner end (measured) on the room's back corner. */
const KW = WALL_H / 540;
export const WALL_LEFT = place(BOX.wall_left, KW, [1499, 509], CORNER);
export const WALL_RIGHT = place(BOX.wall_right, KW, [550, 509], CORNER);

/* Floor: its diamond (top 1024,552 · half-width 940 · half-height 481)
 * stretched onto the room's exact 2:1 diamond under the walls. */
export const FLOOR = place(BOX.floor, 200 / 940, [1024, 552], [200, 40 + WALL_H], 100 / 481);

/* Carpet: a runner from the front edge up to the cabinet (mirrored, so it
 * runs up-right). */
export const CARPET = place(BOX.carpet, 0.25, [415, 415], [176, 292], 0.25, true);

/* Frames on the left wall. The velvet inside the frame sprite is a
 * parallelogram: left edge x 120 from y 130, 142 wide, 184 tall, its top
 * rising 1:2 — the card goes there under the same skew. */
const KF = 0.24;
const FRAME_INNER: Pt = [120, 130];
export const FRAME_IN_W = 142 * KF;
export const FRAME_IN_H = 184 * KF;
const FRAME_XS = [16, 74, 132];
/** Left wall top at screen x. */
const wallTop = (x: number) => 40 + (200 - x) / 2;
export const FRAMES = FRAME_XS.map((x) => {
  const inner: Pt = [x, wallTop(x) + 46];
  const cx = x + FRAME_IN_W / 2;
  return {
    frame: place(BOX.frame, KF, FRAME_INNER, inner),
    inner,
    /** The lamp over the frame, hung under the wall's top trim. */
    lamp: place(BOX.spotlight, 0.26, [128, 30], [cx, wallTop(cx) + 3]),
  };
});

/* Cabinet against the right wall, standing on the floor: its front-left
 * bottom corner (64, 345) placed 1 depth in front of the wall base. */
export const CABINET = place(BOX.cabinet, 0.4, [64, 345], [192, 212]);
/** Cell centres along the front: partitions at x 186 and 289 split 83…396. */
const CAB_COLS_PX = [134, 237, 340];
/** Where a cabinet cell's item stands: three per shelf, two shelves. */
export function cabinetSlot(i: number): Pt {
  const x = CAB_COLS_PX[i % 3];
  const y = (i < 3 ? 203 : 314) + (x - 80) / 2;
  return pt(CABINET, [x, y]);
}
/** The glass doors (for a faint reflection over the exhibits). */
export const CAB_GLASS: Pt[] = ([[78, 90], [395, 248], [395, 490], [78, 332]] as Pt[]).map((p) => pt(CABINET, p));
export const CAB_ITEM_W = 34;
export const CAB_ITEM_H = 40;

/* Pedestals: their base bottom (107, 180) on a floor point; the gift stands
 * on the top's centre (103, 62). Back to front = paint order. */
const KP = 0.23;
export const PEDESTAL_SPOTS: Pt[] = [
  [150, 252],
  [104, 276],
  [58, 300],
  [302, 304],
  [246, 334],
];
export const PEDESTALS = PEDESTAL_SPOTS.map((at) => {
  const sprite = place(BOX.pedestal, KP, [107, 180], at);
  return { sprite, top: pt(sprite, [103, 60]) };
});

/* Decor. */
export const PLANT = place(BOX.plant, 0.2, [171, 322], [370, 300]);
export const BANNER = place(BOX.banner, 0.2, [139, 20], [376, 140], 0.2, true);
export const ROPES = [
  place(BOX.rope, 0.26, [130, 236], [46, 346]),
  place(BOX.rope, 0.26, [130, 236], [340, 360], 0.26, true),
];
