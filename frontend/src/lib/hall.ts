/** «Зал славы»: the isometric room's geometry (SVG units, viewBox 400×400).
 * The back corner is at (200, 40); walls rise 160 units; the floor is a 2:1
 * diamond. Exhibits stand on fixed anchors: three frames on the left wall,
 * six cabinet cells on the right wall, five pedestals on the floor. When the
 * painted room (assets/hall/room_*.webp) arrives, only these anchors move. */

export const HALL_VIEW = 400;

/** Left wall: local (u, v) → screen, the wall going down-left at 2:1. */
export function leftWall(u: number, v: number): [number, number] {
  return [200 - u, 40 + u / 2 + v];
}

/** Right wall: local (u, v) → screen, the wall going down-right at 2:1. */
export function rightWall(u: number, v: number): [number, number] {
  return [200 + u, 40 + u / 2 + v];
}

/** Frames on the left wall: their left edge `u` from the corner (frames are
 * drawn in screen space with a skew, so x0 is the frame's left x). */
export const FRAME_SLOTS = [{ x0: 40 }, { x0: 92 }, { x0: 144 }];
export const FRAME_W = 42;
export const FRAME_H = 60;
/** Frame top: 34 units under the wall top at the frame's left edge. */
export function frameOrigin(x0: number): [number, number] {
  return [x0, 40 + (200 - x0) / 2 + 34];
}

/** Cabinet on the right wall: from u = CAB_U, 3 columns × 2 shelves. */
export const CAB_U = 26;
export const CAB_W = 148;
export const CAB_TOP = 22;
export const CAB_H = 128;
export const CAB_COLS = 3;
/** Where a cabinet cell's item stands (screen point of the shelf under it). */
export function cabinetSlot(i: number): [number, number] {
  const col = i % CAB_COLS;
  const row = Math.floor(i / CAB_COLS);
  const u = CAB_U + (CAB_W / CAB_COLS) * (col + 0.5);
  const v = CAB_TOP + (row === 0 ? 58 : 118);
  return rightWall(u, v);
}

/** Pedestals on the floor, back to front (paint order). */
export const PEDESTALS: [number, number][] = [
  [168, 238],
  [236, 252],
  [132, 288],
  [272, 302],
  [200, 330],
];
