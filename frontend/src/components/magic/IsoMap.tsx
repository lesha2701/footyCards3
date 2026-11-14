import { motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { CastleArt, DecorArt, HeroArt, MapObjectArt, ObstacleArt } from "@/components/magic/art/mapObjects";

const REUSABLE = new Set(["market", "medic", "tunnel"]);
import { pngArt, texArt } from "@/components/magic/art/pngArt";
import { AmbientParticles, CampSmoke, CastlePennant, Cloud, MapLifeStyle, Sway, WaterGlint } from "@/components/magic/mapLife";
import { inMap, isSeen } from "@/components/magic/mapPath";
import MiniMap from "@/components/magic/MiniMap";
import type { MagicBiome, MagicRun } from "@/types";

// Isometric cell: a 64×32 diamond. Cell (x, y) → its centre on the big SVG.
const TW = 64;
const TH = 32;
const PAD = 48;
const PAD_TOP = 120;
const DEPTH = 22; // room under the map's front corner
const RING = 3; // wild cells drawn around the playable map
const FAR = 2400; // the endless land reaches this far past the map

const GROUND: Record<MagicBiome, { tiles: string[]; road: string; roadEdge: string; water: string; shine: string; side: string; sideDark: string; bg: string }> = {
  meadow: { tiles: ["#62b240", "#5fae3e", "#65b543"], road: "#d2ae72", roadEdge: "#b48d55", water: "#3d9fdc", shine: "#bfe8ff", side: "#7a5a37", sideDark: "#5e432a", bg: "#16301d" },
  desert: { tiles: ["#e8bd6c", "#e5b866", "#eac171"], road: "#b88a4c", roadEdge: "#9c7038", water: "#33c3c0", shine: "#d8fffb", side: "#a8743e", sideDark: "#86592c", bg: "#3a2715" },
  snow: { tiles: ["#e9f1fa", "#e5eef8", "#edf4fb"], road: "#a8b9cc", roadEdge: "#8a9db3", water: "#8fd0f2", shine: "#ffffff", side: "#7d8ea6", sideDark: "#5f6f86", bg: "#16223a" },
  ash: { tiles: ["#4b3b40", "#48393e", "#4f3e44"], road: "#2c2427", roadEdge: "#1d1719", water: "#ff6a1c", shine: "#ffd36b", side: "#2a2023", sideDark: "#1b1416", bg: "#120c0e" },
};

export function cellCenter(x: number, y: number, h: number): [number, number] {
  return [PAD + (x - y + h) * (TW / 2), PAD_TOP + (x + y) * (TH / 2) + TH / 2];
}

const diamond = (cx: number, cy: number, s = 1) =>
  `${cx},${cy - (TH / 2) * s} ${cx + (TW / 2) * s},${cy} ${cx},${cy + (TH / 2) * s} ${cx - (TW / 2) * s},${cy}`;

const hash = (x: number, y: number) => ((x * 73856093) ^ (y * 19349663)) >>> 0;

type Sprite = { key: string; x: number; y: number; order: number; node: JSX.Element };

/** The adventure map: a juicy isometric world drawn from the run's terrain,
 *  objects and heroes, under fog of war. Drag to look around, tap a place. */
// The shore around lakes: a sandy / snowy / crusted rim, a darker inner line and a foam line.
const SHORE: Record<MagicBiome, { edge: string; inner: string; foam: string }> = {
  meadow: { edge: "#d9c48b", inner: "#0b3d5c", foam: "#ffffff" },
  desert: { edge: "#f1dba3", inner: "#0b4f4c", foam: "#ffffff" },
  snow: { edge: "#f6faff", inner: "#3a6c8f", foam: "#ffffff" },
  ash: { edge: "#1b1210", inner: "#000000", foam: "#ffb347" },
};

/** A steady pseudo-random number in [0, 1) for a point (the same every time). */
function noise(x: number, y: number, salt: number): number {
  const s = Math.sin(x * 12.9898 + y * 78.233 + salt * 37.719) * 43758.5453;
  return s - Math.floor(s);
}

/** The outline of every lake: the boundary of its cells, rounded by corner cutting, in screen space. */
function waterPath(water: Set<string>, H: number): string {
  // Directed boundary edges between grid corners, clockwise around each lake (holes go the other way).
  const next = new Map<string, string[]>();
  const add = (ax: number, ay: number, bx: number, by: number) => {
    const k = `${ax},${ay}`;
    if (!next.has(k)) next.set(k, []);
    next.get(k)!.push(`${bx},${by}`);
  };
  for (const k of water) {
    const [x, y] = k.split(",").map(Number);
    if (!water.has(`${x},${y - 1}`)) add(x, y, x + 1, y);
    if (!water.has(`${x + 1},${y}`)) add(x + 1, y, x + 1, y + 1);
    if (!water.has(`${x},${y + 1}`)) add(x + 1, y + 1, x, y + 1);
    if (!water.has(`${x - 1},${y}`)) add(x, y + 1, x, y);
  }
  let d = "";
  while (next.size) {
    const start = next.keys().next().value as string;
    let pts: [number, number][] = [];
    let cur = start;
    for (let guard = 0; guard < 10000; guard++) {
      const list = next.get(cur);
      if (!list) break;
      const to = list.pop()!;
      if (!list.length) next.delete(cur);
      const [px, py] = cur.split(",").map(Number);
      pts.push([px, py]);
      cur = to;
      if (cur === start) break;
    }
    if (pts.length < 3) continue;
    // A natural bank: split every cell edge in two and nudge each point (the same nudge for the
    // same point in every run, and a shared point moves the same in every loop), then smooth.
    const rough: [number, number][] = [];
    for (let i = 0; i < pts.length; i++) {
      const [ax, ay] = pts[i];
      const [bx, by] = pts[(i + 1) % pts.length];
      rough.push([ax, ay], [(ax + bx) / 2, (ay + by) / 2]);
    }
    pts = rough.map(([px, py]) => [px + (noise(px * 2, py * 2, 1) - 0.5) * 0.5, py + (noise(px * 2, py * 2, 2) - 0.5) * 0.5]);
    // Chaikin corner cutting: the jagged outline becomes a smooth, uneven shore.
    for (let it = 0; it < 3; it++) {
      const r: [number, number][] = [];
      for (let i = 0; i < pts.length; i++) {
        const [ax, ay] = pts[i];
        const [bx, by] = pts[(i + 1) % pts.length];
        r.push([ax * 0.75 + bx * 0.25, ay * 0.75 + by * 0.25], [ax * 0.25 + bx * 0.75, ay * 0.25 + by * 0.75]);
      }
      pts = r;
    }
    // Small waves along the bank, pushed out along the outline's normal.
    pts = pts.map(([px, py], i) => {
      const [ax, ay] = pts[(i + pts.length - 1) % pts.length];
      const [bx, by] = pts[(i + 1) % pts.length];
      const tx = bx - ax;
      const ty = by - ay;
      const len = Math.hypot(tx, ty) || 1;
      const w = Math.sin(i * 0.9 + noise(Math.round(px * 4), Math.round(py * 4), 3) * 2.5) * 0.06;
      return [px + (ty / len) * w, py - (tx / len) * w];
    });
    // A grid corner (gx, gy) sits half a cell up-left of the centre of cell (gx, gy).
    d += pts.map(([gx, gy], i) => {
      const [sx, sy] = cellCenter(gx - 0.5, gy - 0.5, H);
      return `${i ? "L" : "M"}${sx.toFixed(1)},${sy.toFixed(1)}`;
    }).join(" ") + " Z ";
  }
  return d;
}

// Painted bridges: the picture spans upper-left → lower-right (along x); mirrored for y.
// Deck ends sit at 13% and 84% of the picture's width, its middle at (0.49, 0.35)·width.
const BRIDGE_IMG: Record<string, [string, number]> = {
  meadow: ["bridge_wood", 0.802], snow: ["bridge_wood", 0.802],
  desert: ["bridge_stone", 0.727], ash: ["bridge_stone", 0.727],
};

/** Bridges where the road crosses the river: one road-sized painted bridge per bridge cell, so a wide
 *  river gets several short bridges in a row instead of one huge one. */
function bridgeArt(run: MagicRun, H: number, roads: Set<string>): JSX.Element[] {
  const img = BRIDGE_IMG[run.biome];
  if (!img) return bridgeSvg(run, H, roads);
  const cells = new Set((run.bridges ?? []).map(([x, y]) => `${x},${y}`));
  const out: JSX.Element[] = [];
  for (const [x, y] of run.bridges ?? []) {
    const alongX = roads.has(`${x - 1},${y}`) || roads.has(`${x + 1},${y}`) || cells.has(`${x - 1},${y}`) || cells.has(`${x + 1},${y}`);
    const [dx, dy] = alongX ? [1, 0] : [0, 1];
    // Deck from edge to edge of the cell, a touch onto the next one so a chain reads as one crossing.
    const [ax, ay] = cellCenter(x - dx * 0.56, y - dy * 0.56, H);
    const [bx, by] = cellCenter(x + dx * 0.56, y + dy * 0.56, H);
    const w = Math.abs(bx - ax) / 0.71;
    const h = w * img[1];
    const cx = (ax + bx) / 2;
    const cy = (ay + by) / 2;
    out.push(
      <image key={`br${x},${y}`} href={`${import.meta.env.BASE_URL}magic/terrain/${img[0]}.png`}
        x={cx - 0.49 * w} y={cy - 0.35 * w} width={w} height={h}
        transform={alongX ? undefined : `translate(${2 * cx},0) scale(-1,1)`} />,
    );
  }
  return out;
}

/** Fallback SVG bridge: a plank deck along the road, with rails. */
function bridgeSvg(run: MagicRun, H: number, roads: Set<string>): JSX.Element[] {
  return (run.bridges ?? []).map(([x, y]) => {
    // Along the road: x when the road goes on to x±1, else y.
    const alongX = roads.has(`${x - 1},${y}`) || roads.has(`${x + 1},${y}`);
    const at = (a: number, b: number) => cellCenter(alongX ? x + a : x + b, alongX ? y + b : y + a, H);
    const L = 0.62; // half length: a little onto the banks
    const W = 0.26; // half width
    const quad = (a0: number, a1: number, b0: number, b1: number) =>
      [at(a0, b0), at(a1, b0), at(a1, b1), at(a0, b1)].map(([px, py]) => `${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
    const planks = Array.from({ length: 7 }, (_, i) => -L + ((i + 1) * 2 * L) / 8);
    const rail = (b: number) => {
      const [ax, ay] = at(-L, b);
      const [bx, by] = at(L, b);
      return { ax, ay: ay - 3, bx, by: by - 3 };
    };
    return (
      <g key={`br${x},${y}`}>
        <polygon points={quad(-L, L, -W, W)} fill="#000" opacity={0.3} transform="translate(0,2.5)" />
        <polygon points={quad(-L, L, -W, W)} fill="#a0703f" stroke="#4e3219" strokeWidth={0.9} strokeLinejoin="round" />
        {planks.map((a) => {
          const [ax, ay] = at(a, -W);
          const [bx, by] = at(a, W);
          return <line key={a} x1={ax} y1={ay} x2={bx} y2={by} stroke="#5e3d1f" strokeWidth={0.7} opacity={0.8} />;
        })}
        {[-W, W].map((b) => {
          const r = rail(b);
          return (
            <g key={b} stroke="#4a2f17" strokeLinecap="round">
              {[-L + 0.08, 0, L - 0.08].map((a) => {
                const [px, py] = at(a, b);
                return <line key={a} x1={px} y1={py} x2={px} y2={py - 3} strokeWidth={1.2} />;
              })}
              <line x1={r.ax} y1={r.ay} x2={r.bx} y2={r.by} strokeWidth={1.4} />
            </g>
          );
        })}
      </g>
    );
  });
}

// Road pieces: which diamond edges a cell's road leaves through. UL / UR / LR / LL are the
// upper-left … lower-left edges, i.e. the neighbours (x-1,y) / (x,y-1) / (x+1,y) / (x,y+1).
type Edge = "UL" | "UR" | "LR" | "LL";
const STEP: Record<string, Edge> = { "1,0": "LR", "-1,0": "UL", "0,1": "LL", "0,-1": "UR" };
const FLIP_X: Record<Edge, Edge> = { UL: "UR", UR: "UL", LL: "LR", LR: "LL" };
const FLIP_Y: Record<Edge, Edge> = { UL: "LL", LL: "UL", UR: "LR", LR: "UR" };
// Each painted piece and the edges it connects in its own picture.
const PIECES: [string, Edge[]][] = [
  ["straight", ["UL", "LR"]], ["turn_top", ["UL", "UR"]], ["turn_bottom", ["LL", "LR"]],
  ["turn_side", ["UR", "LR"]], ["fork", ["LR", "UL", "UR"]], ["end", ["LR"]],
];

/** The piece (and mirroring) that draws a cell whose road leaves through these edges. */
function pieceFor(edges: Set<Edge>): [string, boolean, boolean] | null {
  for (const [name, own] of PIECES) {
    for (const fx of [false, true]) {
      for (const fy of [false, true]) {
        const got = own.map((e) => (fy ? FLIP_Y[fx ? FLIP_X[e] : e] : fx ? FLIP_X[e] : e));
        if (got.length === edges.size && got.every((e) => edges.has(e))) return [name, fx, fy];
      }
    }
  }
  return null;
}

/** The road drawn from the biome's painted pieces, one per road cell. */
function roadTiles(run: MagicRun, H: number, roads: Set<string>): JSX.Element[] {
  const edges = new Map<string, Set<Edge>>();
  const link = (ax: number, ay: number, bx: number, by: number) => {
    const e = STEP[`${bx - ax},${by - ay}`];
    if (!e) return;
    if (!edges.has(`${ax},${ay}`)) edges.set(`${ax},${ay}`, new Set());
    if (!edges.has(`${bx},${by}`)) edges.set(`${bx},${by}`, new Set());
    edges.get(`${ax},${ay}`)!.add(e);
    edges.get(`${bx},${by}`)!.add(FLIP_Y[FLIP_X[e]]);
  };
  if (run.tracks?.length) {
    for (const track of run.tracks) for (let i = 1; i < track.length; i++) link(track[i - 1][0], track[i - 1][1], track[i][0], track[i][1]);
  } else {
    // Older runs without tracks: every pair of neighbouring road cells is linked.
    for (const [x, y] of run.road) {
      if (roads.has(`${x + 1},${y}`)) link(x, y, x + 1, y);
      if (roads.has(`${x},${y + 1}`)) link(x, y, x, y + 1);
    }
  }
  const out: JSX.Element[] = [];
  // A touch larger than the cell, so neighbouring pieces overlap instead of leaving a hairline.
  const s = 1.04;
  for (const [k, set] of edges) {
    const [x, y] = k.split(",").map(Number);
    const [cx, cy] = cellCenter(x, y, H);
    const parts = set.size === 4 ? [pieceFor(new Set<Edge>(["UL", "LR"])), pieceFor(new Set<Edge>(["UR", "LL"]))] : [pieceFor(set)];
    parts.forEach((pc, i) => {
      if (!pc) return;
      const [name, fx, fy] = pc;
      const href = pngArt(`terrain/${run.biome}_road_${name}`);
      if (!href) return;
      const transform = fx || fy ? `translate(${fx ? 2 * cx : 0},${fy ? 2 * cy : 0}) scale(${fx ? -1 : 1},${fy ? -1 : 1})` : undefined;
      out.push(<image key={`rd${k}-${i}`} href={href} x={cx - (TW / 2) * s} y={cy - (TH / 2) * s} width={TW * s} height={TH * s} preserveAspectRatio="none" transform={transform} />);
    });
  }
  return out;
}

export default function IsoMap({ run, selected, path, walk, onCell }: {
  run: MagicRun;
  selected: [number, number] | null;
  /** The planned route to the selected place (dots on the ground). */
  path: [number, number][] | null;
  /** The route the hero just walked (animated), from the previous position. */
  walk: [number, number][] | null;
  onCell: (x: number, y: number) => void;
}) {
  const W = run.map_w;
  const H = run.map_h;
  const g = GROUND[run.biome] ?? GROUND.meadow;
  const mapW = (W + H) * (TW / 2) + PAD * 2;
  const mapH = (W + H) * (TH / 2) + PAD_TOP + DEPTH + PAD;
  const shape = run.map_shape ?? null;
  const inside = (x: number, y: number) => inMap(run, x, y);
  // How many cells (x, y) lies outside the playable map (0 — inside).
  const outside = (x: number, y: number) =>
    shape
      ? Math.max(0, Math.abs(x - y) - shape[0], shape[1] - (x + y), x + y - shape[2])
      : Math.max(0, -x, x - W + 1, -y, y - H + 1);
  // The nearest playable cell (for the fog over the wild edge).
  const nearest = (x: number, y: number): [number, number] => {
    if (!shape) return [Math.max(0, Math.min(W - 1, x)), Math.max(0, Math.min(H - 1, y))];
    const u = Math.max(-shape[0], Math.min(shape[0], x - y));
    let v = Math.max(shape[1], Math.min(shape[2], x + y));
    if ((u + v) % 2) v += v < (shape[1] + shape[2]) / 2 ? 1 : -1;
    return [(u + v) / 2, (v - u) / 2];
  };
  // The playable area's box on the big SVG (a tall band fills the screen).
  const area = shape
    ? {
        l: PAD + (H - shape[0]) * (TW / 2) - TW / 4,
        r: PAD + (H + shape[0]) * (TW / 2) + TW / 4,
        t: PAD_TOP + shape[1] * (TH / 2),
        b: PAD_TOP + shape[2] * (TH / 2) + TH,
      }
    : null;

  const box = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const [view, setView] = useState({ w: 360, h: 600 });
  const [zoomPick, setZoom] = useState(1.2);
  const [cam, setCam] = useState<{ x: number; y: number } | null>(null);
  const drag = useRef<{ px: number; py: number; cx: number; cy: number; moved: boolean; at: number; id: number } | null>(null);
  const miniDrag = useRef(false);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setView({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setView({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const zoomMin = area ? Math.min(1.8, Math.max(0.8, view.w / (area.r - area.l), view.h / (area.b - area.t))) : 0.8;
  const zoomMax = Math.max(1.6, zoomMin + 0.5);
  const zoom = Math.max(zoomMin, Math.min(zoomMax, zoomPick));

  const clamp = (c: { x: number; y: number }) => {
    if (area) {
      // Keep the screen over the playable band (centre it when the band is narrower).
      const fit = (pos: number, lo: number, hi: number, size: number) =>
        (hi - lo) * zoom <= size ? size / 2 - ((lo + hi) / 2) * zoom : Math.min(-lo * zoom, Math.max(size - hi * zoom, pos));
      return { x: fit(c.x, area.l, area.r, view.w), y: fit(c.y, area.t, area.b, view.h) };
    }
    const mx = (view.w / 2 - c.x) / zoom;
    const my = (view.h * 0.45 - c.y) / zoom;
    const u = (mx - PAD) / (TW / 2) - H; // x − y
    const v = (my - PAD_TOP - TH / 2) / (TH / 2); // x + y
    const x = Math.max(0, Math.min(W - 1, (u + v) / 2));
    const y = Math.max(0, Math.min(H - 1, (v - u) / 2));
    const [cx, cy] = cellCenter(x, y, H);
    return { x: view.w / 2 - cx * zoom, y: view.h * 0.45 - cy * zoom };
  };
  const centerOn = (x: number, y: number) => {
    const [cx, cy] = cellCenter(x, y, H);
    return clamp({ x: view.w / 2 - cx * zoom, y: view.h * 0.45 - cy * zoom });
  };

  // Follow the hero: centre on him at start and whenever he walks off-centre.
  useEffect(() => {
    const [cx, cy] = cellCenter(run.hero.x, run.hero.y, H);
    setCam((c) => {
      if (!c) return centerOn(run.hero.x, run.hero.y);
      const sx = c.x + cx * zoom;
      const sy = c.y + cy * zoom;
      const far = sx < view.w * 0.2 || sx > view.w * 0.8 || sy < view.h * 0.18 || sy > view.h * 0.75;
      return far ? centerOn(run.hero.x, run.hero.y) : clamp(c);
    });
  }, [run.hero.x, run.hero.y, view.w, view.h, zoom]); // eslint-disable-line react-hooks/exhaustive-deps

  const onDown = (e: ReactPointerEvent) => {
    if (!cam || (drag.current && drag.current.id !== e.pointerId)) return; // a second finger doesn't restart the drag
    drag.current = { px: e.clientX, py: e.clientY, cx: cam.x, cy: cam.y, moved: false, at: Date.now(), id: e.pointerId };
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: ReactPointerEvent) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.px;
    const dy = e.clientY - d.py;
    // A finger shakes more than a mouse: a touch becomes a drag only past 12 px.
    if (Math.abs(dx) + Math.abs(dy) > (e.pointerType === "mouse" ? 7 : 12)) d.moved = true;
    if (d.moved) setCam(clamp({ x: d.cx + dx, y: d.cy + dy }));
  };
  const onUp = (e: ReactPointerEvent) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    // A quick touch is a tap even when the finger slid a little (phones report a few px of drift).
    const slid = Math.abs(e.clientX - d.px) + Math.abs(e.clientY - d.py);
    const tap = !d.moved || (e.pointerType !== "mouse" && Date.now() - d.at < 350 && slid < 30);
    if (!tap || !box.current || !cam) return;
    // The map point under the finger, from the camera itself: the SVG sits at the box's
    // top-left, moved by translate(cam) scale(zoom). (Safari's getScreenCTM skips CSS
    // transforms, so on an iPhone every tap landed on the wrong cell.)
    const rect = box.current.getBoundingClientRect();
    const pt = { x: (e.clientX - rect.left - cam.x) / zoom, y: (e.clientY - rect.top - cam.y) / zoom };
    // Taps on a tall sprite land a bit above its cell: aim at the ground first.
    const u = (pt.x - PAD) / (TW / 2) - H;
    const v = (pt.y - PAD_TOP - TH / 2) / (TH / 2);
    const x = Math.round((u + v) / 2);
    const y = Math.round((v - u) / 2);
    if (inside(x, y)) onCell(x, y);
  };

  const seen = (x: number, y: number) => !!isSeen(run, x, y);
  // Animate only what is on (or near) the screen: keeps big maps cheap.
  const onScreen = (x: number, y: number, m = 80) => {
    if (!cam) return false;
    const [cx, cy] = cellCenter(x, y, H);
    const sx = cam.x + cx * zoom;
    const sy = cam.y + cy * zoom;
    return sx > -m && sx < view.w + m && sy > -m && sy < view.h + m * 1.5;
  };
  const reach = useMemo(() => new Set(run.reachable.map(([x, y]) => `${x},${y}`)), [run.reachable]);
  const roads = useMemo(() => new Set(run.road.map(([x, y]) => `${x},${y}`)), [run.road]);
  // A few cloud spots spread over the unseen part of the map.
  const clouds = useMemo(() => {
    const dark: [number, number][] = [];
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (inside(x, y) && !seen(x, y) && (x + 2 * y) % 3 === 0) dark.push([x, y]);
    const n = Math.min(6, Math.ceil(dark.length / 40));
    return Array.from({ length: n }, (_, i) => dark[Math.floor(((i + 0.5) * dark.length) / n)]);
  }, [run.seen, run.seen_hex?.join(), W, H, shape?.join()]); // eslint-disable-line react-hooks/exhaustive-deps
  const water = useMemo(() => new Set(run.blocks.filter((b) => b[2] === "water").map(([x, y]) => `${x},${y}`)), [run.blocks]);
  const groundTex = texArt(`${run.biome}_ground`);
  const waterTex = texArt(`${run.biome}_water`);

  // Ground, roads, water.
  const ground = useMemo(() => {
    const out: JSX.Element[] = [];
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        if (!inside(x, y)) continue;
        const [cx, cy] = cellCenter(x, y, H);
        const k = `${x},${y}`;
        const tile = pngArt(`terrain/${run.biome}_ground`);
        if (groundTex) {
          // The whole land is one seamless texture (the background pattern): nothing per cell.
        } else if (tile) {
          // One painted tile for the biome; mirrored on every other cell so it doesn't read as a pattern.
          const flip = hash(x, y) % 2 ? `translate(${2 * cx},0) scale(-1,1)` : undefined;
          out.push(<image key={k} href={tile} x={cx - TW / 2 - 0.75} y={cy - TH / 2 - 0.75} width={TW + 1.5} height={TH + 1.5} preserveAspectRatio="none" transform={flip} />);
        } else {
          out.push(<polygon key={k} points={diamond(cx, cy, 1.02)} fill={g.tiles[hash(x, y) % g.tiles.length]} />);
          // A few soft blades / specks so the ground isn't flat colour.
          const h = hash(x + 7, y + 3);
          out.push(<ellipse key={`${k}s`} cx={cx - 10 + (h % 20)} cy={cy - 4 + ((h >> 5) % 8)} rx={7} ry={2.5} fill="#fff" opacity={0.07} />);
        }
        if (water.has(k) && !waterTex) {
          out.push(<polygon key={`${k}w`} points={diamond(cx, cy, 1.03)} fill={g.water} />);
          if (hash(x, y) % 2) out.push(<path key={`${k}ws`} d={`M${cx - 12},${cy} q6,-3 12,0 t12,0`} stroke={g.shine} strokeWidth={1.4} fill="none" opacity={0.6} />);
        }
      }
    }
    // Lakes (lava in the ash lands) as smooth shapes with a shore, filled with their texture.
    // The river runs on past the band's edge and under its bridges.
    const wet = new Set(water);
    for (const [x, y] of [...(run.river ?? []), ...(run.bridges ?? [])]) wet.add(`${x},${y}`);
    if (waterTex && wet.size) {
      const d = waterPath(wet, H);
      const shore = SHORE[run.biome];
      out.push(
        <g key="water">
          <path d={d} fill="none" stroke={shore.edge} strokeWidth={8} strokeLinejoin="round" opacity={0.95} />
          <path d={d} fill="url(#magic-water)" fillRule="evenodd" />
          <path d={d} fill="none" stroke={shore.inner} strokeWidth={3} strokeLinejoin="round" opacity={0.22} />
          <path d={d} fill="none" stroke={shore.foam} strokeWidth={1.1} strokeLinejoin="round" opacity={0.7} />
        </g>,
      );
    }
    // The road from painted pieces, when the biome has them: each road cell gets the piece
    // for the edges it connects through (a straight, a turn, a fork or an end), mirrored as needed.
    if (pngArt(`terrain/${run.biome}_road_straight`)) {
      out.push(...roadTiles(run, H, roads));
      out.push(...bridgeArt(run, H, roads));
      return out;
    }
    // Otherwise a narrow winding dirt track. Each road cell bends the track
    // through a wobbly point near its centre, from one edge midpoint to the
    // next, so the staircase of cells reads as a meandering path.
    const trail: string[] = [];
    const pebbles: JSX.Element[] = [];
    const wob = (x: number, y: number): [number, number] => {
      const [cx, cy] = cellCenter(x, y, H);
      const h = hash(x + 31, y + 17);
      return [cx + ((h % 13) - 6), cy + (((h >> 4) % 7) - 3)];
    };
    for (const track of run.tracks ?? []) {
      // Through the midpoints between cells, bending at each (wobbly) cell.
      const pts = track.map(([x, y]) => wob(x, y));
      if (pts.length < 2) continue;
      let d = `M${pts[0][0]},${pts[0][1]}`;
      for (let i = 1; i < pts.length - 1; i++) {
        const nx = (pts[i][0] + pts[i + 1][0]) / 2;
        const ny = (pts[i][1] + pts[i + 1][1]) / 2;
        d += ` Q${pts[i][0]},${pts[i][1]} ${nx},${ny}`;
      }
      d += ` L${pts[pts.length - 1][0]},${pts[pts.length - 1][1]}`;
      trail.push(d);
    }
    for (const [x, y] of run.road) {
      const h = hash(x + 5, y + 9);
      const c = wob(x, y);
      if (h % 3 === 0) pebbles.push(<ellipse key={`pb${x},${y}`} cx={c[0] + ((h >> 3) % 14) - 7} cy={c[1] + ((h >> 6) % 6) - 3} rx={1.6} ry={1} fill={g.roadEdge} opacity={0.8} />);
      if (run.tracks?.length) continue;
      // Older runs without tracks: bend through every pair of road neighbours.
      const nbs = [[x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]].filter(([nx, ny]) => roads.has(`${nx},${ny}`));
      const mid = (nx: number, ny: number): [number, number] => {
        const o = wob(nx, ny);
        return [(c[0] + o[0]) / 2, (c[1] + o[1]) / 2];
      };
      if (nbs.length === 1) {
        const [mx, my] = mid(nbs[0][0], nbs[0][1]);
        trail.push(`M${c[0]},${c[1]} L${mx},${my}`);
      }
      for (let i = 0; i < nbs.length; i++) {
        for (let j = i + 1; j < nbs.length; j++) {
          const [ax, ay] = mid(nbs[i][0], nbs[i][1]);
          const [bx, by] = mid(nbs[j][0], nbs[j][1]);
          trail.push(`M${ax},${ay} Q${c[0]},${c[1]} ${bx},${by}`);
        }
      }
    }
    out.push(...bridgeArt(run, H, roads));
    if (trail.length) {
      const d = trail.join(" ");
      out.push(<path key="road-edge" d={d} stroke={g.roadEdge} strokeWidth={8.5} strokeLinecap="round" strokeLinejoin="round" fill="none" opacity={0.45} />);
      out.push(<path key="road" d={d} stroke={g.road} strokeWidth={5.5} strokeLinecap="round" strokeLinejoin="round" fill="none" opacity={0.85} />);
      out.push(<path key="road-ruts" d={d} stroke="#fff" strokeWidth={1} strokeDasharray="2 7" strokeLinecap="round" fill="none" opacity={0.18} />);
      out.push(...pebbles);
    }
    return out;
  }, [run.biome, W, H, shape?.join(), water, roads]); // eslint-disable-line react-hooks/exhaustive-deps

  // Everything standing on the map, painted back to front.
  const sprites: Sprite[] = [];
  const place = (key: string, x: number, y: number, order: number, node: JSX.Element) => sprites.push({ key, x, y, order, node });
  for (const [x, y, v] of run.decor) if (seen(x, y)) place(`d${x},${y}`, x, y, 0, <DecorArt biome={run.biome} variant={v} />);
  for (const [x, y, kind, v] of run.blocks) {
    if (kind === "water" || !seen(x, y)) continue;
    const art = <ObstacleArt kind={kind} biome={run.biome} variant={v} />;
    place(`b${x},${y}`, x, y, 1, kind === "tree" && onScreen(x, y) ? <Sway seed={hash(x, y)}>{art}</Sway> : art);
  }
  for (const o of run.objects) {
    let node: JSX.Element;
    if (o.kind === "castle") {
      const mine = o.owner === "me";
      node = <CastleArt faction={mine ? run.faction : run.rival} skin={mine ? run.castle_skin : run.mode === "adventure" ? "victor" : "default"} rival={!mine} />;
      if (onScreen(o.x, o.y, 120) && (mine || run.mode !== "adventure")) node = <g>{node}<CastlePennant color={mine ? "#fbbf24" : "#ef4444"} seed={hash(o.x, o.y)} /></g>;
    } else {
      // A market, the medic tent and a tunnel stay in use after a visit.
      const taken = !!o.taken_by && !REUSABLE.has(o.kind);
      node = <MapObjectArt kind={o.kind} variant={o.variant ?? undefined} level={o.level ?? undefined} taken={taken} faction={run.faction} style={o.style} />;
      if (o.kind === "mine" && o.taken_by) {
        node = <g>{node}<circle cx={16} cy={-30} r={5} fill={o.taken_by === "me" ? "#fbbf24" : "#ef4444"} stroke="#1b1222" strokeWidth={1.5} /></g>;
      }
      if (o.kind === "camp" && !o.taken_by && seen(o.x, o.y) && onScreen(o.x, o.y)) node = <g>{node}<CampSmoke seed={hash(o.x, o.y)} /></g>;
    }
    place(o.id, o.x, o.y, 2, node);
  }
  for (let y = -RING; y < H + RING; y++) {
    for (let x = -RING; x < W + RING; x++) {
      const d = outside(x, y);
      if (d < 1 || d > RING) continue;
      const h = hash(x + 101, y + 57);
      if (h % 100 >= (d === 1 ? 45 : 70)) continue;
      const kind = h % 7 === 0 ? "mountain" : h % 5 === 0 ? "rock" : "tree";
      const art = <ObstacleArt kind={kind} biome={run.biome} variant={(h >> 4) % 3} />;
      place(`w${x},${y}`, x, y, 1, kind === "tree" && onScreen(x, y) ? <Sway seed={h}>{art}</Sway> : art);
    }
  }
  if (run.bot.visible && run.bot.x !== undefined && run.bot.y !== undefined) {
    place("bot", run.bot.x, run.bot.y, 3, <HeroArt faction={run.rival} rival />);
  }

  // The hero walks his route cell by cell, then stands.
  const heroCells = walk && walk.length > 1 ? walk : [[run.hero.x, run.hero.y] as [number, number]];
  const heroXs = heroCells.map(([x, y]) => cellCenter(x, y, H)[0]);
  const heroYs = heroCells.map(([x, y]) => cellCenter(x, y, H)[1]);
  sprites.sort((a, b) => a.x + a.y - (b.x + b.y) || a.order - b.order || a.x - b.x);
  const heroDepth = run.hero.x + run.hero.y;
  const before = sprites.filter((s) => s.x + s.y <= heroDepth);
  const after = sprites.filter((s) => s.x + s.y > heroDepth);
  const draw = (s: Sprite) => {
    const [cx, cy] = cellCenter(s.x, s.y, H);
    return <g key={s.key} transform={`translate(${cx},${cy})`}>{s.node}</g>;
  };

  // Fog: every unseen cell, blurred together into clouds.
  const fog: JSX.Element[] = [];
  for (let y = -RING; y < H + RING; y++) {
    for (let x = -RING; x < W + RING; x++) {
      if (outside(x, y) > RING) continue;
      const [nx, ny] = nearest(x, y);
      if (seen(nx, ny)) continue;
      const [cx, cy] = cellCenter(x, y, H);
      fog.push(<polygon key={`f${x},${y}`} points={diamond(cx, cy - 8, 1.25)} />);
    }
  }

  const sel = selected ? cellCenter(selected[0], selected[1], H) : null;
  // Steps to the selected place: today's cost, or how far it gets today.
  const steps = path && path.length >= 2 ? path.length - 1 : 0;
  const moves = run.hero.moves;
  const stepsLabel = !steps ? null : steps <= moves ? `−${steps} 👣` : moves > 0 ? `${moves}/${steps} 👣 · завтра` : "завтра";

  // Glints on the water cells in sight.
  const glints: JSX.Element[] = [];
  for (const [x, y, kind] of run.blocks) {
    if (kind !== "water" || glints.length >= 36) continue;
    const h = hash(x + 13, y + 41);
    if (h % 2 || !seen(x, y) || !onScreen(x, y, 20)) continue;
    const [cx, cy] = cellCenter(x, y, H);
    glints.push(<WaterGlint key={`g${x},${y}`} x={cx - 12 + ((h >> 3) % 24)} y={cy - 5 + ((h >> 7) % 10)} seed={h} color={g.shine} />);
  }
  // No badges over the camps: the strength is in the camp's card when it is tapped.
  const landTile = pngArt(`terrain/${run.biome}_ground`);
  const camStyle = cam
    ? { transform: `translate(${cam.x}px, ${cam.y}px) scale(${zoom})`, transition: drag.current || miniDrag.current ? "none" : "transform 0.45s ease-out" }
    : undefined;
  // The playable area on the big SVG, for the mini-map.
  const bounds = area ?? (() => {
    const [l] = cellCenter(0, H - 1, H);
    const [r] = cellCenter(W - 1, 0, H);
    const [, t] = cellCenter(0, 0, H);
    const [, b] = cellCenter(W - 1, H - 1, H);
    return { l: l - TW / 2, r: r + TW / 2, t: t - TH / 2, b: b + TH / 2 };
  })();
  // The diamond of the playable map plus its wild ring.
  const corner = (x: number, y: number) => cellCenter(x, y, H);
  const [tx, ty] = corner(-RING - 0.5, -RING - 0.5);
  const [rx, ry] = corner(W + RING - 0.5, -RING - 0.5);
  const [bx, by] = corner(W + RING - 0.5, H + RING - 0.5);
  const [lx, ly] = corner(-RING - 0.5, H + RING - 0.5);
  const outer = area
    ? `M${area.l - RING * TW / 2},${area.t - RING * TH / 2} H${area.r + RING * TW / 2} V${area.b + RING * TH / 2} H${area.l - RING * TW / 2} Z`
    : `M${tx},${ty} L${rx},${ry} L${bx},${by} L${lx},${ly} Z`;

  return (
    <div
      ref={box}
      className="relative h-full w-full touch-none select-none overflow-hidden"
      style={{ background: `radial-gradient(ellipse at 50% 35%, ${g.bg} 0%, #05070d 80%)` }}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={() => { drag.current = null; }}
    >
      {cam && (
        <svg
          ref={svg}
          width={mapW}
          height={mapH}
          viewBox={`0 0 ${mapW} ${mapH}`}
          className="absolute left-0 top-0 origin-top-left overflow-visible"
          style={camStyle}
        >
          <MapLifeStyle />
          <defs>
            {waterTex && (
              <pattern id="magic-water" width={96} height={96} patternUnits="userSpaceOnUse" patternTransform="scale(1,0.5) rotate(45)">
                <image href={waterTex} width={96} height={96} preserveAspectRatio="none" />
              </pattern>
            )}
            {groundTex ? (
              // One seamless texture under the whole map, turned into the isometric view.
              <pattern id="magic-land" width={128} height={128} patternUnits="userSpaceOnUse" patternTransform="scale(1,0.5) rotate(45)">
                <image href={groundTex} width={128} height={128} preserveAspectRatio="none" />
              </pattern>
            ) : (
            <pattern id="magic-land" width={TW} height={TH} patternUnits="userSpaceOnUse" x={PAD} y={PAD_TOP + TH / 2}>
              {landTile ? (
                [[0, 0], [-TW / 2, -TH / 2], [TW / 2, -TH / 2], [-TW / 2, TH / 2], [TW / 2, TH / 2]].map(([dx, dy]) => (
                  <image key={`${dx},${dy}`} href={landTile} x={dx - 0.75} y={dy - 0.75} width={TW + 1.5} height={TH + 1.5} preserveAspectRatio="none" />
                ))
              ) : (
                <rect width={TW} height={TH} fill={g.tiles[0]} />
              )}
            </pattern>
            )}
            <filter id="magic-fog" x="-10%" y="-10%" width="120%" height="120%">
              <feGaussianBlur stdDeviation="9" />
            </filter>
          </defs>
          <rect x={-FAR} y={-FAR} width={mapW + FAR * 2} height={mapH + FAR * 2} fill="url(#magic-land)" />
          {ground}
          {/* Past the wild ring the land fades into the night. */}
          <path fillRule="evenodd" fill="#05070d" opacity={0.55}
            d={`M${-FAR},${-FAR} h${mapW + FAR * 2} v${mapH + FAR * 2} h${-(mapW + FAR * 2)} Z ${outer}`} />
          {glints}
          {/* Where the hero can go today: a thin golden border around the area, no haze over the ground. */}
          {run.reachable.length > 0 && (() => {
            const reach = new Set(run.reachable.map(([x, y]) => `${x},${y}`));
            const d: string[] = [];
            for (const [x, y] of run.reachable) {
              const [cx, cy] = cellCenter(x, y, H);
              const T = `${cx},${cy - TH / 2}`, R = `${cx + TW / 2},${cy}`, B = `${cx},${cy + TH / 2}`, L = `${cx - TW / 2},${cy}`;
              if (!reach.has(`${x + 1},${y}`)) d.push(`M${R}L${B}`);
              if (!reach.has(`${x - 1},${y}`)) d.push(`M${L}L${T}`);
              if (!reach.has(`${x},${y + 1}`)) d.push(`M${B}L${L}`);
              if (!reach.has(`${x},${y - 1}`)) d.push(`M${T}L${R}`);
            }
            return (
              <path d={d.join("")} fill="none" stroke="#fde68a" strokeWidth={1.6} strokeOpacity={0.75}
                strokeDasharray="5 4" strokeLinecap="round" />
            );
          })()}
          {/* The rival's footprints from last night (where you can see). */}
          {(run.bot.trail ?? []).map(([x, y], i, all) => {
            const [cx, cy] = cellCenter(x, y, H);
            const side = i % 2 ? 4 : -4;
            return (
              <g key={`t${i}`} transform={`translate(${cx + side},${cy})`} opacity={0.35 + (0.5 * i) / Math.max(1, all.length)}>
                <ellipse cx={-2} cy={0} rx={3.2} ry={1.8} fill="#ef4444" />
                <ellipse cx={3} cy={-1.5} rx={1.4} ry={1} fill="#ef4444" />
              </g>
            );
          })}
          {/* The planned route. */}
          {path && path.slice(1).map(([x, y], i) => {
            const [cx, cy] = cellCenter(x, y, H);
            const ok = reach.has(`${x},${y}`) || i < run.hero.moves;
            return <ellipse key={`p${i}`} cx={cx} cy={cy} rx={6} ry={3.4} fill={ok ? "#fde68a" : "#f87171"} stroke="#1b1222" strokeWidth={1} opacity={0.95} />;
          })}
          {sel && (
            <polygon points={diamond(sel[0], sel[1], 0.9)} fill="none" stroke="#fde047" strokeWidth={2.5} strokeLinejoin="round">
              <animate attributeName="stroke-opacity" values="1;0.35;1" dur="1.2s" repeatCount="indefinite" />
            </polygon>
          )}
          {before.map(draw)}
          <motion.g
            key={heroCells.map((c) => c.join(",")).join(";")}
            initial={{ x: heroXs[0], y: heroYs[0] }}
            animate={{ x: heroXs, y: heroYs }}
            transition={{ duration: Math.max(0.01, (heroCells.length - 1) * 0.17), ease: "linear" }}
          >
            {/* Standing in a castle: step out in front of the gate so he isn't lost in the towers. */}
            <g transform={run.objects.some((o) => o.kind === "castle" && o.x === run.hero.x && o.y === run.hero.y) && !(walk && walk.length > 1) ? "translate(22,10)" : undefined}>
              <HeroArt faction={run.faction} skin={run.hero_skin} heroClass={run.hero_class} />
            </g>
          </motion.g>
          {after.map(draw)}
          <g filter="url(#magic-fog)" fill="#0a0e1a">{fog}</g>
          {/* A bouncing marker over the chosen place, above sprites and fog. */}
          {sel && (
            <g transform={`translate(${sel[0]},${sel[1] - 58})`}>
              <path d="M-7,-9 L7,-9 L0,0 Z" fill="#fde047" stroke="#1b1222" strokeWidth={1.5} strokeLinejoin="round">
                <animateTransform attributeName="transform" type="translate" values="0,0;0,-6;0,0" dur="0.9s" repeatCount="indefinite" />
              </path>
            </g>
          )}
        </svg>
      )}
      {/* HTML over the map, in map coordinates: clouds over the fog, the steps pill. */}
      {cam && (
        <div className="pointer-events-none absolute left-0 top-0 origin-top-left" style={{ ...camStyle, width: mapW, height: mapH }}>
          {clouds.map(([x, y], i) => {
            const [cx, cy] = cellCenter(x, y, H);
            return <Cloud key={i} x={cx} y={cy} seed={hash(x, y)} />;
          })}
          {sel && stepsLabel && (
            <div className="absolute whitespace-nowrap rounded-full bg-black/75 px-2 py-0.5 text-[10px] font-black leading-tight text-amber-100 ring-1 ring-amber-300/60"
              style={{ left: sel[0] + 11, top: sel[1] - 74 }}>
              {stepsLabel}
            </div>
          )}
        </div>
      )}
      <AmbientParticles biome={run.biome} height={view.h} />
      {/* Mini-map */}
      {cam && (
        <div className="absolute right-3 top-3 rounded-xl bg-black/55 p-1 ring-1 ring-white/20 backdrop-blur" onPointerDown={(e) => e.stopPropagation()}>
          <MiniMap
            run={run}
            bounds={bounds}
            project={(x, y) => cellCenter(x, y, H)}
            colors={{ land: g.tiles[0], water: g.water, road: g.road }}
            frame={{ x: -cam.x / zoom, y: -cam.y / zoom, w: view.w / zoom, h: view.h / zoom }}
            onLook={(x, y) => {
              miniDrag.current = true;
              setCam(clamp({ x: view.w / 2 - x * zoom, y: view.h / 2 - y * zoom }));
            }}
            onLookEnd={() => { miniDrag.current = false; }}
          />
        </div>
      )}
      {/* Zoom */}
      <div className="absolute bottom-3 right-3 flex flex-col gap-1.5" onPointerDown={(e) => e.stopPropagation()}>
        {[["+", 0.15], ["−", -0.15]].map(([label, d]) => (
          <button
            key={label as string}
            onClick={() => setZoom(Math.max(zoomMin, Math.min(zoomMax, zoom + (d as number))))}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-black/55 text-lg font-black text-white ring-1 ring-white/20 backdrop-blur active:scale-90"
          >
            {label}
          </button>
        ))}
        <button
          onClick={() => setCam(centerOn(run.hero.x, run.hero.y))}
          className="flex h-9 w-9 items-center justify-center rounded-full bg-black/55 text-base ring-1 ring-white/20 backdrop-blur active:scale-90"
          aria-label="К герою"
        >
          🎯
        </button>
      </div>
    </div>
  );
}
