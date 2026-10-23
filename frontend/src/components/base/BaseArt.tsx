/** Isometric illustrations of the «Клубная база»: primitives (a box with
 * its two visible walls and roof, windows on a wall, a pitch, trees) and
 * one drawing per building. Light comes from the upper left, so the left
 * wall is the lit one and the right wall is in shade. Buildings grow with
 * their visual level (1–10, artMetrics.visualLevel): more floors, then
 * wings and details; the top level gets a gold rim. The architecture's own
 * colours are fixed like on any illustrated map; ground, glass light and
 * accents follow the theme through CSS variables. */
import { tier } from "./artMetrics";
import { ISO_C, type Pt, ellipseR, onLeft, onRight, pt, pts, shade } from "./iso";

const LIT = "rgb(var(--c-legend))";
const GOLD = "#f2c230";

export type Art = { x: number; y: number; w: number; d: number; vl: number };

// --- primitives -----------------------------------------------------------------------------------

export function IsoBox({
  x, y, w, d, h, z = 0, color, top, right, left, edge = true,
}: { x: number; y: number; w: number; d: number; h: number; z?: number; color: string; top?: string; right?: string; left?: string; edge?: boolean }) {
  const stroke = edge ? shade(color, 0.55) : "none";
  return (
    <g strokeWidth="0.35" stroke={stroke} strokeLinejoin="round">
      <polygon points={pts([pt(x, y + d, z), pt(x + w, y + d, z), pt(x + w, y + d, z + h), pt(x, y + d, z + h)])} fill={left ?? color} />
      <polygon points={pts([pt(x + w, y, z), pt(x + w, y + d, z), pt(x + w, y + d, z + h), pt(x + w, y, z + h)])} fill={right ?? shade(color, 0.7)} />
      <polygon points={pts([pt(x, y, z + h), pt(x + w, y, z + h), pt(x + w, y + d, z + h), pt(x, y + d, z + h)])} fill={top ?? shade(color, 1.2)} />
    </g>
  );
}

export function Quad({
  x, y, w, d, z = 0, fill, opacity, stroke, strokeWidth = 0.4, dash,
}: { x: number; y: number; w: number; d: number; z?: number; fill: string; opacity?: number; stroke?: string; strokeWidth?: number; dash?: string }) {
  return (
    <polygon points={pts([pt(x, y, z), pt(x + w, y, z), pt(x + w, y + d, z), pt(x, y + d, z)])}
             fill={fill} opacity={opacity} stroke={stroke} strokeWidth={stroke ? strokeWidth : 0} strokeDasharray={dash} />
  );
}

/** Windows on a visible wall of the box (x, y, w, d) between z and z+h. */
export function WallWindows({
  x, y, w, d, z, h, rows, cols, face, seed = 1, lit = LIT, dark = "#26312b",
}: { x: number; y: number; w: number; d: number; z: number; h: number; rows: number; cols: number; face: "L" | "R"; seed?: number; lit?: string; dark?: string }) {
  const len = face === "L" ? w : d;
  const at = (u: number, v: number): Pt => (face === "L" ? onLeft(x, y + d, z, u, v) : onRight(x + w, y, z, u, v));
  const cells = [];
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const u0 = ((c + 0.22) / cols) * len;
      const u1 = ((c + 0.78) / cols) * len;
      const v0 = (r + 0.3) * (h / rows);
      const v1 = v0 + 0.42 * (h / rows);
      const on = ((r * 7 + c * 3 + seed) % 5) !== 0;
      cells.push(
        <polygon key={`${r}-${c}`} points={pts([at(u0, v0), at(u1, v0), at(u1, v1), at(u0, v1)])}
                 fill={on ? lit : dark} opacity={on ? (face === "L" ? 0.95 : 0.75) : 0.6} />,
      );
    }
  }
  return <g>{cells}</g>;
}

export function GroundEllipse({ cx, cy, r, z = 0, fill, opacity, stroke }: { cx: number; cy: number; r: number; z?: number; fill: string; opacity?: number; stroke?: string }) {
  const [rx, ry] = ellipseR(r);
  const [px, py] = pt(cx, cy, z);
  return <ellipse cx={px} cy={py} rx={rx} ry={ry} fill={fill} opacity={opacity} stroke={stroke} strokeWidth={stroke ? 0.5 : 0} />;
}

/** A football pitch lying on the plane z: grass pattern and markings. */
export function IsoPitch({ x, y, w, d, z = 0, pattern = "stripes" }: { x: number; y: number; w: number; d: number; z?: number; pattern?: string }) {
  const m = Math.min(w, d) * 0.06;
  const line = { fill: "none", stroke: "#fff", strokeOpacity: 0.85, strokeWidth: 0.55 };
  const bw = w * 0.13;
  const bd = d * 0.44;
  const n = 10;
  const stripes = [];
  for (let i = 0; i < n; i += 1) {
    if (pattern === "checks") {
      for (let j = 0; j < 6; j += 1) {
        if ((i + j) % 2) stripes.push(<Quad key={`${i}-${j}`} x={x + (i * w) / n} y={y + (j * d) / 6} w={w / n} d={d / 6} z={z} fill="#fff" opacity={0.08} />);
      }
    } else if (pattern === "diagonal") {
      if (i % 2) stripes.push(<Quad key={i} x={x} y={y + (i * d) / n} w={w} d={d / n} z={z} fill="#fff" opacity={0.08} />);
    } else if (i % 2) {
      stripes.push(<Quad key={i} x={x + (i * w) / n} y={y} w={w / n} d={d} z={z} fill="#fff" opacity={0.08} />);
    }
  }
  const [crx, cry] = ellipseR(Math.min(w, d) * 0.14);
  const [cx, cy] = pt(x + w / 2, y + d / 2, z);
  return (
    <g>
      <Quad x={x - 0.15} y={y - 0.15} w={w + 0.3} d={d + 0.3} z={z} fill="#2f8a43" />
      <Quad x={x} y={y} w={w} d={d} z={z} fill="#3c9a4f" />
      {stripes}
      <g {...line}>
        <polygon points={pts([pt(x + m, y + m, z), pt(x + w - m, y + m, z), pt(x + w - m, y + d - m, z), pt(x + m, y + d - m, z)])} />
        <polyline points={pts([pt(x + w / 2, y + m, z), pt(x + w / 2, y + d - m, z)])} />
        <ellipse cx={cx} cy={cy} rx={crx} ry={cry} />
        <polygon points={pts([pt(x + m, y + d / 2 - bd / 2, z), pt(x + m + bw, y + d / 2 - bd / 2, z), pt(x + m + bw, y + d / 2 + bd / 2, z), pt(x + m, y + d / 2 + bd / 2, z)])} />
        <polygon points={pts([pt(x + w - m, y + d / 2 - bd / 2, z), pt(x + w - m - bw, y + d / 2 - bd / 2, z), pt(x + w - m - bw, y + d / 2 + bd / 2, z), pt(x + w - m, y + d / 2 + bd / 2, z)])} />
      </g>
      <circle cx={cx} cy={cy} r="0.7" fill="#fff" />
    </g>
  );
}

export function Tree({ x, y, s = 1 }: { x: number; y: number; s?: number }) {
  const [bx, by] = pt(x, y, 0);
  const [cx, cy] = pt(x, y, 0.9 + s * 0.7);
  const r = s * ISO_C * 0.75;
  return (
    <g>
      <ellipse cx={bx + 2} cy={by + 1} rx={r * 0.9} ry={r * 0.4} fill="#000" opacity="0.2" />
      <line x1={bx} y1={by} x2={bx} y2={cy} stroke="#6b4a2f" strokeWidth="1" />
      <circle cx={cx} cy={cy} r={r} fill="rgb(var(--map-tree))" />
      <circle cx={cx + r * 0.3} cy={cy + r * 0.2} r={r * 0.75} fill="#000" opacity="0.12" />
      <circle cx={cx - r * 0.3} cy={cy - r * 0.3} r={r * 0.42} fill="#fff" opacity="0.15" />
    </g>
  );
}

export function Pine({ x, y, s = 1 }: { x: number; y: number; s?: number }) {
  const [bx, by] = pt(x, y, 0);
  const [, ty] = pt(x, y, 2.6 * s);
  const r = s * ISO_C * 0.55;
  return (
    <g>
      <ellipse cx={bx + 1.5} cy={by + 0.8} rx={r} ry={r * 0.4} fill="#000" opacity="0.2" />
      <polygon points={`${bx},${ty} ${bx + r},${by - 1} ${bx - r},${by - 1}`} fill="rgb(var(--map-tree))" />
      <polygon points={`${bx},${ty} ${bx + r},${by - 1} ${bx},${by - 1}`} fill="#000" opacity="0.18" />
    </g>
  );
}

function Flag({ at, color = "rgb(var(--c-path))" }: { at: Pt; color?: string }) {
  const [x, y] = at;
  return (
    <g>
      <line x1={x} y1={y} x2={x} y2={y - 11} stroke="#9aa59e" strokeWidth="0.7" />
      <path d={`M${x} ${y - 11} q 3.5 -1.4 7 0 q -3.5 1.8 -7 3.6 z`} fill={color}>
        <animate attributeName="d" dur="2.4s" repeatCount="indefinite"
                 values={`M${x} ${y - 11} q 3.5 -1.4 7 0 q -3.5 1.8 -7 3.6 z;M${x} ${y - 11} q 3.5 1.4 7 0.4 q -3.5 1 -7 3.2 z;M${x} ${y - 11} q 3.5 -1.4 7 0 q -3.5 1.8 -7 3.6 z`} />
      </path>
    </g>
  );
}

function GoldRim({ x, y, w, d, z }: { x: number; y: number; w: number; d: number; z: number }) {
  return <polygon points={pts([pt(x, y, z), pt(x + w, y, z), pt(x + w, y + d, z), pt(x, y + d, z)])} fill="none" stroke={GOLD} strokeWidth="0.9" />;
}

// --- buildings --------------------------------------------------------------------------------------

export function HqArt({ x, y, w, d, vl }: Art) {
  const t = tier(vl);
  const floors = 2 + Math.ceil(vl / 2);
  const th = 1.6 + vl * 0.5;
  const tx = x + 0.9;
  const ty = y + 0.6;
  const tw = w - 1.8;
  const td = d - 1.2;
  return (
    <g>
      <IsoBox x={x} y={y} w={w} d={d} h={0.8} color="#bdb6a6" />
      {t >= 1 && <IsoBox x={x + 0.1} y={y + 0.2} w={0.8} d={d - 0.4} h={0.8 + th * 0.45} color="#d3d9d3" top="#6f8aa6" />}
      {t >= 2 && <IsoBox x={x + w - 0.9} y={y + 0.2} w={0.8} d={d - 0.4} h={0.8 + th * 0.55} color="#d3d9d3" top="#6f8aa6" />}
      <IsoBox x={tx} y={ty} w={tw} d={td} h={th} z={0.8} color="#5a8fd0" right="#2f5e9e" top="#3f6fb5" />
      <WallWindows x={tx} y={ty} w={tw} d={td} z={0.8} h={th} rows={floors} cols={4} face="L" seed={3} lit="#fff4b8" dark="#28507f" />
      <WallWindows x={tx} y={ty} w={tw} d={td} z={0.8} h={th} rows={floors} cols={3} face="R" seed={5} lit="#fff4b8" dark="#203f66" />
      <polygon points={pts([onLeft(x + 1.6, y + d, 0, 0, 0), onLeft(x + 1.6, y + d, 0, 0.8, 0), onLeft(x + 1.6, y + d, 0, 0.8, 0.6), onLeft(x + 1.6, y + d, 0, 0, 0.6)])} fill="#1d2b3a" />
      <Flag at={pt(tx + tw / 2, ty + td / 2, 0.8 + th)} />
      {t >= 3 && <GoldRim x={tx} y={ty} w={tw} d={td} z={0.8 + th} />}
    </g>
  );
}

export function HotelArt({ x, y, w, d, vl }: Art) {
  const t = tier(vl);
  const floors = 2 + Math.ceil(vl * 0.6);
  const h = 1.6 + vl * 0.55;
  const bx = x + 0.9;
  const bw = w - 0.9;
  const bd = d - 0.9;
  return (
    <g>
      {vl >= 3 && (
        <g>
          <Quad x={x + 0.1} y={y + d - 0.8} w={w - 0.2} d={0.7} z={0.02} fill="#e8e1d3" />
          <Quad x={x + 0.25} y={y + d - 0.7} w={w - 0.5} d={0.5} z={0.04} fill="#5bc8e8" stroke="#e8f6fb" />
        </g>
      )}
      {t >= 2 && <IsoBox x={x} y={y + 0.2} w={0.9} d={bd - 0.4} h={h * 0.65} color="#e9d8bc" top="#b8862f" />}
      <IsoBox x={bx} y={y} w={bw} d={bd} h={h} color="#f1e4cc" right="#c9b893" top="#b8862f" />
      <WallWindows x={bx} y={y} w={bw} d={bd} z={0} h={h} rows={floors} cols={3} face="L" seed={5} />
      <WallWindows x={bx} y={y} w={bw} d={bd} z={0} h={h} rows={floors} cols={3} face="R" seed={2} />
      {/* neon strip on the corner */}
      <polygon points={pts([onLeft(bx, y + bd, 0, 0.05, h * 0.25), onLeft(bx, y + bd, 0, 0.22, h * 0.25), onLeft(bx, y + bd, 0, 0.22, h * 0.9), onLeft(bx, y + bd, 0, 0.05, h * 0.9)])}
               fill="#ff5fb0" />
      {t >= 3 && [0, 1, 2, 3, 4].map((i) => {
        const [sx, sy] = pt(bx + 0.3 + i * 0.35, y + bd / 2, h + 0.2);
        return <circle key={i} cx={sx} cy={sy - 2} r="1.2" fill={GOLD} />;
      })}
    </g>
  );
}

export function TrainingArt({ x, y, w, d, vl }: Art) {
  const t = tier(vl);
  const h = 0.8 + vl * 0.1;
  const rise = w * 0.32;
  const steps = 10;
  // Barrel roof along y: its cross-section in x–z.
  const arc = (i: number) => {
    const a = Math.PI * (1 - i / steps);
    return { u: (w / 2) * (1 + Math.cos(a)), v: h + rise * Math.sin(a) };
  };
  const strips = [];
  for (let i = 0; i < steps; i += 1) {
    const a0 = arc(i);
    const a1 = arc(i + 1);
    const light = 0.85 + (i / steps) * 0.3;
    strips.push(
      <polygon key={i} points={pts([pt(x + a0.u, y, a0.v), pt(x + a1.u, y, a1.v), pt(x + a1.u, y + d, a1.v), pt(x + a0.u, y + d, a0.v)])}
               fill={shade("#3cae66", light)} stroke="#277d48" strokeWidth="0.25" />,
    );
  }
  const front = Array.from({ length: steps + 1 }, (_, i) => arc(i)).map(({ u, v }) => pt(x + u, y + d, v));
  return (
    <g>
      {t >= 1 && <IsoBox x={x - 0.9} y={y + 0.4} w={0.9} d={d - 0.8} h={h + 0.5} color="#d9ddd6" top="#2f9e58" />}
      <IsoBox x={x} y={y} w={w} d={d} h={h} color="#e2e6df" />
      {strips}
      <polygon points={pts([pt(x, y + d, h), ...front, pt(x + w, y + d, h)])} fill="#bfe3cb" stroke="#277d48" strokeWidth="0.3" />
      {[0.25, 0.5, 0.75].map((f) => (
        <polyline key={f} points={pts([onLeft(x, y + d, 0, w * f, 0.1), onLeft(x, y + d, 0, w * f, h + rise * Math.sin(Math.PI * f) * 0.95)])}
                  stroke="#8fb79c" strokeWidth="0.4" fill="none" />
      ))}
      {t >= 3 && <GoldRim x={x} y={y} w={w} d={d} z={h} />}
    </g>
  );
}

export function MedicalArt({ x, y, w, d, vl }: Art) {
  const t = tier(vl);
  const floors = 1 + Math.ceil(vl / 2.5);
  const h = 1.2 + vl * 0.32;
  const [hx, hy] = pt(x + w / 2, y + d / 2, h);
  const [hrx, hry] = ellipseR(0.75);
  return (
    <g>
      {t >= 2 && <IsoBox x={x + w - 0.1} y={y + 0.3} w={0.9} d={d - 0.6} h={h * 0.55} color="#eef3f0" top="#9fb7aa" />}
      <IsoBox x={x} y={y} w={w} d={d} h={h} color="#f5f8f6" right="#c6d2cb" top="#dfe7e2" />
      <WallWindows x={x} y={y} w={w} d={d} z={0.3} h={h - 0.3} rows={floors} cols={4} face="L" seed={2} lit="#a6e1ff" dark="#86a49a" />
      <WallWindows x={x} y={y} w={w} d={d} z={0.3} h={h - 0.3} rows={floors} cols={3} face="R" seed={4} lit="#a6e1ff" dark="#7f998f" />
      <polygon points={pts([onLeft(x, y + d, 0, 0, 0), onLeft(x, y + d, 0, w, 0), onLeft(x, y + d, 0, w, 0.25), onLeft(x, y + d, 0, 0, 0.25)])} fill="#2f9e8a" />
      {/* red cross on the left wall */}
      <polygon points={pts([onLeft(x, y + d, 0, w / 2 - 0.1, h - 0.85), onLeft(x, y + d, 0, w / 2 + 0.1, h - 0.85), onLeft(x, y + d, 0, w / 2 + 0.1, h - 0.25), onLeft(x, y + d, 0, w / 2 - 0.1, h - 0.25)])} fill="#d63b3b" />
      <polygon points={pts([onLeft(x, y + d, 0, w / 2 - 0.32, h - 0.65), onLeft(x, y + d, 0, w / 2 + 0.32, h - 0.65), onLeft(x, y + d, 0, w / 2 + 0.32, h - 0.45), onLeft(x, y + d, 0, w / 2 - 0.32, h - 0.45)])} fill="#d63b3b" />
      {t >= 1 && (
        <g>
          <ellipse cx={hx} cy={hy} rx={hrx} ry={hry} fill="#3a4a42" stroke={GOLD} strokeWidth="0.5" />
          <g stroke="#fff" strokeWidth="0.7">
            <line x1={hx - 2.2} y1={hy - 1} x2={hx - 2.2} y2={hy + 1} />
            <line x1={hx + 2.2} y1={hy - 1} x2={hx + 2.2} y2={hy + 1} />
            <line x1={hx - 2.2} y1={hy} x2={hx + 2.2} y2={hy} />
          </g>
        </g>
      )}
      {vl >= 3 && <IsoBox x={x + 0.2} y={y + d + 0.15} w={0.9} d={0.45} h={0.45} color="#ffffff" right="#d9d9d9" top="#f0f0f0" />}
      {t >= 3 && <GoldRim x={x} y={y} w={w} d={d} z={h} />}
    </g>
  );
}

export function AnalyticsArt({ x, y, w, d, vl }: Art) {
  const t = tier(vl);
  const h = 1.4 + vl * 0.38;
  const screen = (u: number, v: number) => onLeft(x, y + d, 0, u, v);
  const sv0 = h * 0.4;
  const sv1 = h * 0.9;
  const chart = [0, 1, 2, 3, 4, 5].map((i) => screen(0.35 + i * ((w - 0.7) / 5), sv0 + 0.15 + (((i * 37 + vl * 11) % 9) / 9) * (sv1 - sv0 - 0.3)));
  const [dx, dy] = pt(x + w / 2, y + d / 2, h);
  const [drx] = ellipseR(0.7);
  return (
    <g>
      <IsoBox x={x} y={y} w={w} d={d} h={h} color="#323c49" right="#232b35" top="#7a5cc4" />
      <polygon points={pts([screen(0.2, sv0), screen(w - 0.2, sv0), screen(w - 0.2, sv1), screen(0.2, sv1)])} fill="#0f1a24" stroke="#5be0ff" strokeWidth="0.5" />
      <polyline points={pts(chart)} fill="none" stroke="#5be0ff" strokeWidth="0.8" />
      <WallWindows x={x} y={y} w={w} d={d} z={0.2} h={sv0 - 0.3} rows={1} cols={4} face="L" seed={4} lit="#9ad8ff" dark="#22303c" />
      <WallWindows x={x} y={y} w={w} d={d} z={0.2} h={h - 0.4} rows={Math.max(2, Math.ceil(vl / 2))} cols={3} face="R" seed={6} lit="#9ad8ff" dark="#1d2730" />
      {t >= 1 && (
        <g>
          <path d={`M${dx - drx} ${dy} a ${drx} ${drx * 0.85} 0 0 1 ${drx * 2} 0 z`} fill="#c9cfe0" stroke="#8a90a6" strokeWidth="0.5" />
          <line x1={dx} y1={dy - drx * 0.6} x2={dx + 4} y2={dy - drx * 0.6 - 3} stroke="#5a6070" strokeWidth="1.3" />
        </g>
      )}
      {t >= 2 && (() => {
        const [ax, ay] = pt(x + w - 0.3, y + 0.3, h);
        return (
          <g>
            <line x1={ax} y1={ay} x2={ax} y2={ay - 13} stroke="#9aa59e" strokeWidth="0.6" />
            <circle cx={ax} cy={ay - 13} r="1" fill="#5be0ff">
              <animate attributeName="opacity" values="1;0.2;1" dur="1.6s" repeatCount="indefinite" />
            </circle>
          </g>
        );
      })()}
      {t >= 3 && <GoldRim x={x} y={y} w={w} d={d} z={h} />}
    </g>
  );
}

export function MediaArt({ x, y, w, d, vl }: Art) {
  const t = tier(vl);
  const h = 1.2 + vl * 0.3;
  const dishes = 1 + Math.floor(vl / 3);
  const [mx, my] = pt(x + 0.35, y + 0.35, 0);
  const mast = 18 + vl * 2.4;
  return (
    <g>
      {/* lattice TV mast behind the studio */}
      <g stroke="#c0504d" strokeWidth="0.6">
        <line x1={mx - 2.5} y1={my} x2={mx} y2={my - mast} />
        <line x1={mx + 2.5} y1={my} x2={mx} y2={my - mast} />
        {Array.from({ length: Math.floor(mast / 5) }).map((_, i) => {
          const f = (i * 5) / mast;
          return <line key={i} x1={mx - 2.5 * (1 - f)} y1={my - i * 5} x2={mx + 2.5 * (1 - f - 5 / mast)} y2={my - i * 5 - 5} strokeWidth="0.35" />;
        })}
      </g>
      <circle cx={mx} cy={my - mast - 1} r="1.2" fill="#ff4d4d">
        <animate attributeName="opacity" values="1;0.15;1" dur="1.3s" repeatCount="indefinite" />
      </circle>
      <IsoBox x={x + 0.8} y={y} w={w - 0.8} d={d} h={h} color="#e7e1d8" right="#bdb4a7" top="#c0504d" />
      <WallWindows x={x + 0.8} y={y} w={w - 0.8} d={d} z={0} h={h} rows={Math.max(1, Math.ceil(vl / 2))} cols={3} face="L" seed={6} />
      <WallWindows x={x + 0.8} y={y} w={w - 0.8} d={d} z={0} h={h} rows={Math.max(1, Math.ceil(vl / 2))} cols={2} face="R" seed={1} />
      {/* on-air plate */}
      <polygon points={pts([onLeft(x + 0.8, y + d, 0, 0.2, h - 0.5), onLeft(x + 0.8, y + d, 0, 1.0, h - 0.5), onLeft(x + 0.8, y + d, 0, 1.0, h - 0.15), onLeft(x + 0.8, y + d, 0, 0.2, h - 0.15)])} fill="#1a1a1a" />
      {(() => { const [rx, ry] = onLeft(x + 0.8, y + d, 0, 0.35, h - 0.32); return <circle cx={rx} cy={ry} r="0.7" fill="#ff3b3b" />; })()}
      {Array.from({ length: dishes }).map((_, i) => {
        const [cx, cy] = pt(x + 1.2 + i * ((w - 1.5) / Math.max(1, dishes)), y + d / 2, h);
        return (
          <g key={i}>
            <line x1={cx} y1={cy} x2={cx} y2={cy - 3} stroke="#8a8f8b" strokeWidth="0.7" />
            <ellipse cx={cx} cy={cy - 4.5} rx="2.8" ry="1.7" fill="#f2f4f2" stroke="#9aa59e" strokeWidth="0.4" transform={`rotate(-25 ${cx} ${cy - 4.5})`} />
          </g>
        );
      })}
      {t >= 3 && <GoldRim x={x + 0.8} y={y} w={w - 0.8} d={d} z={h} />}
    </g>
  );
}

export function MarketingArt({ x, y, w, d, vl }: Art) {
  const t = tier(vl);
  const h = 1 + vl * 0.25;
  const p0 = y + d * 0.55;
  const board = (u: number, v: number) => pt(x + 0.1 + u, p0, h + v);
  const bw = w - 0.2;
  return (
    <g>
      <IsoBox x={x} y={y} w={w} d={d} h={h} color="#f3e2d1" right="#cbb59f" top="#d9762b" />
      <WallWindows x={x} y={y} w={w} d={d} z={0.4} h={h - 0.4} rows={Math.max(1, Math.ceil(vl / 3))} cols={2} face="L" seed={7} />
      <WallWindows x={x} y={y} w={w} d={d} z={0.4} h={h - 0.4} rows={Math.max(1, Math.ceil(vl / 3))} cols={2} face="R" seed={8} />
      <polygon points={pts([onLeft(x, y + d, 0, w / 2 - 0.2, 0), onLeft(x, y + d, 0, w / 2 + 0.2, 0), onLeft(x, y + d, 0, w / 2 + 0.2, 0.55), onLeft(x, y + d, 0, w / 2 - 0.2, 0.55)])} fill="#6b3a12" />
      <line x1={board(0.2, 0)[0]} y1={board(0.2, 0)[1]} x2={board(0.2, 0.5)[0]} y2={board(0.2, 0.5)[1]} stroke="#555" strokeWidth="0.6" />
      <line x1={board(bw - 0.2, 0)[0]} y1={board(bw - 0.2, 0)[1]} x2={board(bw - 0.2, 0.5)[0]} y2={board(bw - 0.2, 0.5)[1]} stroke="#555" strokeWidth="0.6" />
      <polygon points={pts([board(0, 0.5), board(bw, 0.5), board(bw, 1.9), board(0, 1.9)])} fill="#fff" stroke="#333" strokeWidth="0.4" />
      <polygon points={pts([board(0.08, 0.6), board(bw * 0.4, 0.6), board(bw * 0.4, 1.8), board(0.08, 1.8)])} fill="#d9762b" />
      <polygon points={pts([board(bw * 0.4, 0.6), board(bw * 0.75, 0.6), board(bw * 0.75, 1.8), board(bw * 0.4, 1.8)])} fill="#2f6fd6" />
      {(() => { const [cx, cy] = board(bw * 0.87, 1.2); return <circle cx={cx} cy={cy} r="1.8" fill={GOLD} />; })()}
      {t >= 2 && [0.2, 0.5, 0.8].map((f) => { const [lx, ly] = board(bw * f, 1.95); return <circle key={f} cx={lx} cy={ly - 1} r="0.8" fill="#fff7c2" />; })}
      {t >= 3 && <GoldRim x={x} y={y} w={w} d={d} z={h} />}
    </g>
  );
}

export function ShopArt({ x, y, w, d, vl }: Art) {
  const t = tier(vl);
  const h = 1 + vl * 0.22;
  const stripes = 6;
  return (
    <g>
      <IsoBox x={x} y={y} w={w} d={d} h={h} color="#f6efe6" right="#d1c8bc" top="#cf3f6a" />
      {h > 1.4 && <WallWindows x={x} y={y} w={w} d={d} z={1.05} h={h - 1.05} rows={Math.max(1, Math.ceil(vl / 3))} cols={2} face="L" seed={8} />}
      <WallWindows x={x} y={y} w={w} d={d} z={0.3} h={h - 0.3} rows={Math.max(1, Math.ceil(vl / 3))} cols={2} face="R" seed={3} />
      {/* shop window with a shirt */}
      <polygon points={pts([onLeft(x, y + d, 0, 0.15, 0.1), onLeft(x, y + d, 0, w * 0.6, 0.1), onLeft(x, y + d, 0, w * 0.6, 0.75), onLeft(x, y + d, 0, 0.15, 0.75)])} fill="#bfe6f5" />
      <polygon points={pts([onLeft(x, y + d, 0, 0.45, 0.2), onLeft(x, y + d, 0, 0.85, 0.2), onLeft(x, y + d, 0, 0.85, 0.55), onLeft(x, y + d, 0, 0.95, 0.5), onLeft(x, y + d, 0, 0.85, 0.65), onLeft(x, y + d, 0, 0.45, 0.65), onLeft(x, y + d, 0, 0.35, 0.5), onLeft(x, y + d, 0, 0.45, 0.55)])} fill="#cf3f6a" />
      <polygon points={pts([onLeft(x, y + d, 0, w * 0.7, 0), onLeft(x, y + d, 0, w * 0.92, 0), onLeft(x, y + d, 0, w * 0.92, 0.75), onLeft(x, y + d, 0, w * 0.7, 0.75)])} fill="#5a2a2a" />
      {/* striped awning sloping out over the window */}
      {Array.from({ length: stripes }).map((_, i) => (
        <polygon key={i} fill={i % 2 ? "#ffffff" : "#cf3f6a"}
                 points={pts([pt(x + (i * w) / stripes, y + d, 0.95), pt(x + ((i + 1) * w) / stripes, y + d, 0.95), pt(x + ((i + 1) * w) / stripes, y + d + 0.45, 0.72), pt(x + (i * w) / stripes, y + d + 0.45, 0.72)])} />
      ))}
      {t >= 3 && <GoldRim x={x} y={y} w={w} d={d} z={h} />}
    </g>
  );
}

export function AccountingArt({ x, y, w, d, vl }: Art) {
  const t = tier(vl);
  const h = 1 + vl * 0.22;
  const cols = 4;
  const ped = 0.6;
  return (
    <g>
      <IsoBox x={x - 0.1} y={y - 0.1} w={w + 0.2} d={d + 0.2} h={0.15} color="#cfc6b2" />
      <IsoBox x={x} y={y} w={w} d={d} h={h} z={0.15} color="#ece4d2" right="#c4bba6" top="#3d8f8a" />
      {Array.from({ length: cols }).map((_, i) => {
        const u = 0.2 + i * ((w - 0.4) / (cols - 1));
        return (
          <polygon key={i} fill="#fbf7ee" stroke="#d8ccb2" strokeWidth="0.25"
                   points={pts([onLeft(x, y + d, 0.15, u - 0.08, 0.05), onLeft(x, y + d, 0.15, u + 0.08, 0.05), onLeft(x, y + d, 0.15, u + 0.08, h - 0.1), onLeft(x, y + d, 0.15, u - 0.08, h - 0.1)])} />
        );
      })}
      {/* pediment: a triangular prism along x */}
      <polygon points={pts([pt(x, y + d, 0.15 + h), pt(x + w, y + d, 0.15 + h), pt(x + w / 2, y + d, 0.15 + h + ped)])} fill="#e3d8bf" stroke="#bfae8a" strokeWidth="0.3" />
      <polygon points={pts([pt(x + w, y + d, 0.15 + h), pt(x + w, y, 0.15 + h), pt(x + w / 2, y, 0.15 + h + ped), pt(x + w / 2, y + d, 0.15 + h + ped)])} fill="#3d8f8a" />
      {(() => { const [cx, cy] = pt(x + w / 2, y + d, 0.15 + h + ped * 0.4); return <circle cx={cx} cy={cy} r="1.3" fill={GOLD} stroke="#b8862f" strokeWidth="0.3" />; })()}
      {t >= 1 && Array.from({ length: Math.min(3, t + 1) }).map((_, i) => {
        const [cx, cy] = pt(x + w + 0.35, y + d - 0.3, 0.12 * i);
        return <ellipse key={i} cx={cx} cy={cy} rx="2" ry="0.9" fill={GOLD} stroke="#b8862f" strokeWidth="0.25" />;
      })}
      {t >= 3 && <GoldRim x={x} y={y} w={w} d={d} z={0.15 + h} />}
    </g>
  );
}

/** «Академия»: one school building with two training pitches. */
export function AcademyArt({ x, y, w, d, vl }: Art) {
  const h = 0.9 + vl * 0.28;
  const floors = 1 + Math.ceil(vl / 3.4);
  return (
    <g>
      <IsoBox x={x} y={y} w={w} d={d} h={h} color="#f1efe6" right="#c9c6b8" top="rgb(var(--c-path))" />
      <WallWindows x={x} y={y} w={w} d={d} z={0.2} h={h - 0.2} rows={floors} cols={5} face="L" seed={9} />
      <WallWindows x={x} y={y} w={w} d={d} z={0.2} h={h - 0.2} rows={floors} cols={3} face="R" seed={4} />
      <polygon points={pts([onLeft(x, y + d, 0, w / 2 - 0.25, 0), onLeft(x, y + d, 0, w / 2 + 0.25, 0), onLeft(x, y + d, 0, w / 2 + 0.25, 0.6), onLeft(x, y + d, 0, w / 2 - 0.25, 0.6)])} fill="#2d4a3c" />
      <polygon points={pts([onLeft(x, y + d, 0, 0.2, h - 0.25), onLeft(x, y + d, 0, w - 0.2, h - 0.25), onLeft(x, y + d, 0, w - 0.2, h - 0.08), onLeft(x, y + d, 0, 0.2, h - 0.08)])} fill="rgb(var(--c-path))" />
    </g>
  );
}
