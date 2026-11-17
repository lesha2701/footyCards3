import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import type { VillaItem } from "@/api/town";
import { skyAt, type Sky } from "@/lib/town";
import {
  CODE_COLOR, HOME_VIEW, KIND_COLOR, PLOT_H, PLOT_W, artOf, blockHeight, clampView, corner, drawOrder, fencePieces,
  footprint, isFence, isPath, pathKerbs, plotArt, rhombus, spriteKey, spriteOf, unproject, zoomView, type View,
} from "@/lib/villa";
import { PLOT_CELLS } from "@/lib/villaPlot";
import { SPRITE_GROUND } from "@/lib/villaSprites";
const NIGHT: Record<Sky, string | null> = {
  day: null, dawn: "rgba(255,170,120,0.14)", dusk: "rgba(255,120,60,0.18)", night: "rgba(10,20,60,0.5)",
};

/** Night halo [radius, lift above the footprint centre] for each light source. */
const GLOW: Record<string, [number, number]> = { lamp: [12, 38], firepit: [14, 4], pizza_oven: [9, 8] };

type Drag = { id: number; dx: number; dy: number; x: number; y: number; moved: boolean };

/** «Моя вилла»: the plot picture, its grid on the lawn and the things on it
 * (pictures, or coloured blocks until a picture exists). Pinch / wheel /
 * the buttons zoom, a finger pans. Read-only unless onCell / onItem are
 * given (the owner's editor): a thing is dragged to a new spot with a green
 * / red ghost under it (onDrop), or tapped (selected) and a cell tapped. */
export default function VillaPlot({
  open, items, selectedId, onCell, onItem, onDrop, canPlace, poppedId, comboIds, mark, showGrid = true, label,
}: {
  /** A spot to show green / red (a thing waiting to be placed). */
  mark?: { x: number; y: number; w: number; h: number; ok: boolean } | null;
  /** The cell lines (cells stay tappable without them). */
  showGrid?: boolean;
  /** Meadow cells open now (the first of PLOT_CELLS, centre first). */
  open: number;
  items: VillaItem[];
  selectedId?: number | null;
  onCell?: (x: number, y: number) => void;
  onItem?: (item: VillaItem) => void;
  /** A thing dropped by drag at (x, y). */
  onDrop?: (id: number, x: number, y: number) => void;
  canPlace?: (id: number, x: number, y: number) => boolean;
  /** The thing just placed — it pops. */
  poppedId?: number | null;
  /** Things in a combo — a sparkle over them. */
  comboIds?: Set<number>;
  label: string;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState<View>(HOME_VIEW);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [sky, setSky] = useState<Sky>(() => skyAt(new Date().getHours()));
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ kind: "pan" | "pinch" | "drag"; startX: number; startY: number; view: View; dist?: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const ground = plotArt();
  const editing = Boolean(onCell);

  useEffect(() => {
    const id = window.setInterval(() => setSky(skyAt(new Date().getHours())), 60_000);
    return () => window.clearInterval(id);
  }, []);

  /** Picture point under a screen point. */
  const toPlot = (clientX: number, clientY: number): [number, number] | null => {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM?.();
    if (!svg || !ctm) return null;
    const p = svg.createSVGPoint();
    p.x = clientX;
    p.y = clientY;
    const q = p.matrixTransform(ctm.inverse());
    return [q.x, q.y];
  };
  const cellAt = (clientX: number, clientY: number): [number, number] | null => {
    const p = toPlot(clientX, clientY);
    if (!p) return null;
    const [gx, gy] = unproject(p[0], p[1]);
    return [Math.floor(gx), Math.floor(gy)];
  };

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    suppressClick.current = false;
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      gesture.current = { kind: "pinch", startX: (a.x + b.x) / 2, startY: (a.y + b.y) / 2, view, dist: Math.hypot(a.x - b.x, a.y - b.y), moved: true };
      setDrag(null);
      return;
    }
    if (!gesture.current || gesture.current.kind !== "drag") {
      gesture.current = { kind: "pan", startX: e.clientX, startY: e.clientY, view, moved: false };
    }
  };
  const startDrag = (item: VillaItem, e: React.PointerEvent) => {
    if (!editing || !onDrop || item.x == null || item.y == null) return;
    const cell = cellAt(e.clientX, e.clientY);
    if (!cell) return;
    gesture.current = { kind: "drag", startX: e.clientX, startY: e.clientY, view, moved: false };
    setDrag({ id: item.id, dx: cell[0] - item.x, dy: cell[1] - item.y, x: item.x, y: item.y, moved: false });
  };
  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!pointers.current.has(e.pointerId)) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const g = gesture.current;
    if (!g) return;
    const svg = svgRef.current;
    const scale = svg ? g.view.w / svg.clientWidth : 1;
    if (g.kind === "pinch" && pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const mid = toPlot((a.x + b.x) / 2, (a.y + b.y) / 2);
      if (mid && g.dist) setView((v) => zoomView(v, (dist / g.dist!) * (g.view.w / v.w), mid[0], mid[1]));
      return;
    }
    const far = Math.hypot(e.clientX - g.startX, e.clientY - g.startY) > 6;
    if (far) g.moved = true;
    if (!g.moved) return;
    suppressClick.current = true;
    if (g.kind === "pan") {
      setView(clampView({ ...g.view, x: g.view.x - (e.clientX - g.startX) * scale, y: g.view.y - (e.clientY - g.startY) * scale }));
    } else if (g.kind === "drag") {
      const cell = cellAt(e.clientX, e.clientY);
      if (cell) setDrag((d) => (d ? { ...d, x: cell[0] - d.dx, y: cell[1] - d.dy, moved: true } : d));
    }
  };
  const onPointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    pointers.current.delete(e.pointerId);
    const g = gesture.current;
    if (g?.kind === "drag" && drag) {
      if (drag.moved) onDrop?.(drag.id, drag.x, drag.y);
      setDrag(null);
    }
    if (pointers.current.size === 0) gesture.current = null;
    else if (g?.kind === "pinch") {
      const [p] = [...pointers.current.values()];
      gesture.current = { kind: "pan", startX: p.x, startY: p.y, view, moved: true };
    }
  };
  const onWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    const p = toPlot(e.clientX, e.clientY);
    if (p) setView((v) => zoomView(v, e.deltaY < 0 ? 1.15 : 1 / 1.15, p[0], p[1]));
  };
  const zoomBy = (factor: number) => setView((v) => zoomView(v, factor, v.x + v.w / 2, v.y + v.h / 2));

  const shown = useMemo(
    () => (drag?.moved ? items.map((i) => (i.id === drag.id ? { ...i, x: drag.x, y: drag.y } : i)) : items),
    [items, drag],
  );
  const dragged = drag?.moved ? shown.find((i) => i.id === drag.id) : undefined;
  const ghostOk = dragged && canPlace ? canPlace(dragged.id, drag!.x, drag!.y) : true;
  const paths = useMemo(() => {  // per kind of path: tiles join only their own kind
    const out = new Map<string, Set<string>>();
    for (const i of shown) {
      if (!isPath(i.code) || i.x == null) continue;
      if (!out.has(i.code)) out.set(i.code, new Set());
      out.get(i.code)!.add(`${i.x}:${i.y}`);
    }
    return out;
  }, [shown]);
  const fences = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const i of shown) {
      if (!isFence(i.code) || i.x == null) continue;
      if (!m.has(i.code)) m.set(i.code, new Set());
      m.get(i.code)!.add(`${i.x}:${i.y}`);
    }
    return m;
  }, [shown]);
  const lit = (code: string) => (sky === "night" ? ["lamp", "firepit", "pizza_oven"] : sky === "dusk" ? ["lamp", "firepit"] : []).includes(code);

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        className="block h-auto w-full select-none"
        style={{ touchAction: "none", aspectRatio: `${HOME_VIEW.w} / ${HOME_VIEW.h}` }}
        role="img"
        aria-label={label}
        data-testid="villa-plot"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onWheel={onWheel}
        onClickCapture={(e) => { if (suppressClick.current) { e.stopPropagation(); suppressClick.current = false; } }}
      >
        <defs>
          <style>{`
            @keyframes villa-pop { 0% { transform: scale(0.6); } 60% { transform: scale(1.12); } 100% { transform: scale(1); } }
            @keyframes villa-twinkle { 0%, 100% { opacity: 0.2; } 50% { opacity: 1; } }
            .villa-pop { animation: villa-pop 0.4s ease-out; transform-box: fill-box; transform-origin: 50% 100%; }
            .villa-twinkle { animation: villa-twinkle 1.8s ease-in-out infinite; }
          `}</style>
          <radialGradient id="villa-glow">
            <stop offset="0" stopColor="#ffe9a8" stopOpacity="0.7" />
            <stop offset="1" stopColor="#ffd36b" stopOpacity="0" />
          </radialGradient>
          <pattern id="villa-stone" width="14" height="10" patternUnits="userSpaceOnUse">
            <rect width="14" height="10" fill="#d9cdb4" />
            <path d="M0 5h14M7 0v5M3 5v5M11 5v5" stroke="#b9aa8c" strokeWidth="1" />
          </pattern>
        </defs>
        {ground ? (
          <image href={ground} x={0} y={0} width={PLOT_W} height={PLOT_H} />
        ) : (
          <rect x={0} y={0} width={PLOT_W} height={PLOT_H} fill="#6fc35f" />
        )}
        {/* the meadow cells the villa's level has not opened yet */}
        {editing && showGrid && PLOT_CELLS.slice(open).map(([x, y]) => (
          <polygon key={`l${x}:${y}`} points={rhombus(x, y, 1, 1)} fill="rgba(20,30,20,0.28)" pointerEvents="none" />
        ))}
        {editing && PLOT_CELLS.slice(0, open).map(([x, y], i) => {
          return (
            <polygon
              key={i}
              points={rhombus(x, y, 1, 1)}
              fill="transparent"
              stroke={showGrid || drag ? "rgba(255,255,255,0.3)" : "transparent"}
              strokeWidth={1.2}
              onClick={() => onCell?.(x, y)}
              data-testid={`villa-cell-${x}-${y}`}
            />
          );
        })}
        {/* paths lie flat under everything and join up */}
        {shown.filter((i) => isPath(i.code) && i.x != null).map((i) => (
          <PathTile key={i.id} item={i} kerbs={pathKerbs(paths.get(i.code)!, i.x!, i.y!)} selected={i.id === selectedId}
                    popped={i.id === poppedId} onTap={onItem ? () => onItem(i) : undefined} onDragStart={(e) => startDrag(i, e)} />
        ))}
        {drawOrder(shown.filter((i) => !isPath(i.code))).map((item) => (
          <Thing
            key={item.id}
            item={item}
            selected={item.id === selectedId}
            faded={item.id === dragged?.id}
            popped={item.id === poppedId}
            combo={comboIds?.has(item.id) ?? false}
            fence={isFence(item.code) ? fences.get(item.code) : undefined}
            onTap={onItem ? () => onItem(item) : undefined}
            onDragStart={(e) => startDrag(item, e)}
          />
        ))}
        {dragged && (
          <polygon
            points={rhombus(drag!.x, drag!.y, ...footprint(dragged))}
            fill={ghostOk ? "rgba(132,255,120,0.3)" : "rgba(255,80,80,0.38)"}
            stroke={ghostOk ? "#84ff78" : "#ff5050"}
            strokeWidth={3}
            pointerEvents="none"
            data-testid="villa-ghost"
          />
        )}
        {mark && !dragged && (
          <polygon
            points={rhombus(mark.x, mark.y, mark.w, mark.h)}
            fill={mark.ok ? "rgba(132,255,120,0.3)" : "rgba(255,80,80,0.38)"}
            stroke={mark.ok ? "#84ff78" : "#ff5050"}
            strokeWidth={3}
            pointerEvents="none"
            data-testid="villa-mark"
          />
        )}
        {NIGHT[sky] && <rect x={0} y={0} width={PLOT_W} height={PLOT_H} fill={NIGHT[sky]!} pointerEvents="none" />}
        {shown.filter((i) => i.x != null && lit(i.code)).map((i) => {
          const [w, h] = footprint(i);
          const [cx, cy] = corner(i.x! + w / 2, i.y! + h / 2);
          // a small halo right at the light itself: the lamp's head, the fire, the oven's mouth
          const [r, lift] = GLOW[i.code] ?? [10, 0];
          return <circle key={`g${i.id}`} cx={cx} cy={cy - lift} r={r} fill="url(#villa-glow)" pointerEvents="none" style={{ mixBlendMode: "screen" }} />;
        })}
      </svg>
      <div className="absolute right-2 top-2 flex flex-col gap-1">
        <button type="button" onClick={() => zoomBy(1.4)} aria-label="Приблизить" className="grid h-9 w-9 place-items-center rounded-full bg-black/45 text-lg font-bold text-white">+</button>
        <button type="button" onClick={() => zoomBy(1 / 1.4)} aria-label="Отдалить" className="grid h-9 w-9 place-items-center rounded-full bg-black/45 text-lg font-bold text-white">−</button>
        {view.w < PLOT_W && (
          <button type="button" onClick={() => setView(HOME_VIEW)} aria-label="Весь участок" className="grid h-9 w-9 place-items-center rounded-full bg-black/45 text-sm text-white">⤢</button>
        )}
      </div>
      {sky !== "day" && (
        <span className="pointer-events-none absolute left-2 top-2 rounded-full bg-black/40 px-2 py-0.5 text-[10px] font-bold text-white">
          {sky === "night" ? "🌙 Ночь" : sky === "dusk" ? "🌇 Вечер" : "🌅 Утро"}
        </span>
      )}
    </div>
  );
}

type ThingProps = {
  item: VillaItem;
  selected: boolean;
  popped: boolean;
  onTap?: () => void;
  onDragStart: (e: React.PointerEvent) => void;
};

function PathTile({ item, kerbs, selected, popped, onTap, onDragStart }: ThingProps & { kerbs: ReturnType<typeof pathKerbs> }) {
  const x = item.x!;
  const y = item.y!;
  const c = (gx: number, gy: number) => corner(gx, gy).map((n) => n.toFixed(1)).join(",");
  const stone = artOf(item.code);
  const [l, top, r] = [corner(x, y + 1), corner(x, y), corner(x + 1, y)];
  const edges: [boolean, string][] = [
    [kerbs.n, `M${c(x, y)}L${c(x + 1, y)}`], [kerbs.e, `M${c(x + 1, y)}L${c(x + 1, y + 1)}`],
    [kerbs.s, `M${c(x + 1, y + 1)}L${c(x, y + 1)}`], [kerbs.w, `M${c(x, y + 1)}L${c(x, y)}`],
  ];
  return (
    <g onClick={onTap} onPointerDown={onDragStart} className={popped ? "villa-pop" : undefined} data-testid={`villa-item-${item.code}`}
       style={{ cursor: onTap ? "pointer" : undefined }}>
      {stone ? (
        <image href={stone} x={l[0]} y={top[1]} width={r[0] - l[0]} height={(r[0] - l[0]) * (SPRITE_GROUND[item.code]?.[2] ?? 0.5)} preserveAspectRatio="none" />
      ) : (
        <polygon points={rhombus(x, y, 1, 1)} fill="url(#villa-stone)" />
      )}
      <path d={edges.filter(([on]) => on).map(([, d]) => d).join("")} stroke="#b59a70" strokeOpacity={0.7} strokeWidth={2} fill="none" />
      {selected && <polygon points={rhombus(x, y, 1, 1)} fill="rgba(255,226,92,0.3)" stroke="#ffe25c" strokeWidth={3} />}
    </g>
  );
}

function Thing({ item, selected, faded, popped, combo, fence, onTap, onDragStart }: ThingProps & {
  faded: boolean; combo: boolean;
  /** Cells of the same fence (for a fence section). */
  fence?: Set<string>;
}) {
  const [w, h] = footprint(item);
  const x = item.x ?? 0;
  const y = item.y ?? 0;
  const sprite = spriteOf(item);
  const front = corner(x + w, y + h);
  const leftC = corner(x, y + h);
  const rightC = corner(x + w, y);
  const backC = corner(x, y);
  const centerX = (leftC[0] + rightC[0]) / 2;
  const footW = rightC[0] - leftC[0];
  const outline = selected ? (
    <polygon points={rhombus(x, y, w, h)} fill="rgba(255,226,92,0.25)" stroke="#ffe25c" strokeWidth={3} />
  ) : null;
  const common = {
    onClick: onTap,
    onPointerDown: onDragStart,
    style: { cursor: onTap ? "grab" : undefined, opacity: faded ? 0.75 : 1 },
    className: popped ? "villa-pop" : undefined,
    "data-testid": `villa-item-${item.code}`,
  };
  const sparkle = combo ? (
    <text x={centerX} y={Math.min(backC[1], front[1] - footW * 0.9)} textAnchor="middle" fontSize={22} className="villa-twinkle" pointerEvents="none">✨</text>
  ) : null;
  /** A picture on this footprint (SPRITE_GROUND says where its own footprint lies). */
  const place = (key: string, href: string, flip: boolean, clip?: string) => {
    const [l, r, aspect, raise] = SPRITE_GROUND[key] ?? [0, 1, 1, 0];
    const spriteW = footW / (r - l);
    const spriteH = spriteW * aspect;
    const bottom = front[1] - raise * spriteW;
    return (
      <image
        key={key + (clip ?? "")}
        href={href}
        x={leftC[0] - l * spriteW}
        y={bottom - spriteH}
        width={spriteW}
        height={spriteH}
        preserveAspectRatio="none"
        clipPath={clip ? `url(#${clip})` : undefined}
        transform={flip ? `translate(${centerX * 2},0) scale(-1,1)` : undefined}
      />
    );
  };
  if (sprite && fence && isFence(item.code)) {
    const piece = (name: string) => artOf(`${item.code}_${name}`);
    const parts = fencePieces(fence, x, y, Boolean(item.rot));
    const out: ReactNode[] = [];
    const clipId = (side: "L" | "R") => `fence-${item.id}-${side}`;
    if (parts.full === "gate" || parts.full === "gate_b") {
      const g = piece("gate");
      if (g) out.push(place(`${item.code}_gate`, g, parts.full === "gate_b"));
    } else if (parts.full) {
      const g = piece(parts.full);
      if (g) out.push(place(`${item.code}_${parts.full}`, g, false));
    }
    // s (+y) and w (−x) lie left of the tile's middle, n and e right of it
    for (const half of parts.halves) {
      const name = half === "n" || half === "s" ? "a" : "b";
      const g = piece(name);
      if (g) out.push(place(`${item.code}_${name}`, g, false, clipId(half === "s" || half === "w" ? "L" : "R")));
    }
    const post = parts.post ? piece("post") : undefined;
    if (post) out.push(place(`${item.code}_post`, post, false));
    return (
      <g {...common}>
        <defs>
          <clipPath id={clipId("L")}><rect x={centerX - footW} y={backC[1] - footW * 3} width={footW} height={footW * 4} /></clipPath>
          <clipPath id={clipId("R")}><rect x={centerX} y={backC[1] - footW * 3} width={footW} height={footW * 4} /></clipPath>
        </defs>
        {outline}
        {out}
        {sparkle}
      </g>
    );
  }
  if (sprite) {
    return (
      <g {...common}>
        {outline}
        {place(spriteKey(item), sprite, Boolean(item.rot))}
        {sparkle}
      </g>
    );
  }
  const k = footW / ((w + h) * 32);
  const lift = blockHeight(item) * k;
  const [topC, sideL, sideR] = KIND_COLOR[item.kind];
  const fill = CODE_COLOR[item.code] ?? topC;
  const emojiSize = Math.min(30, 12 + (w + h) * 4) * k;
  return (
    <g {...common}>
      {outline}
      <polygon points={`${leftC[0]},${leftC[1]} ${front[0]},${front[1]} ${front[0]},${front[1] - lift} ${leftC[0]},${leftC[1] - lift}`} fill={sideL} />
      <polygon points={`${front[0]},${front[1]} ${rightC[0]},${rightC[1]} ${rightC[0]},${rightC[1] - lift} ${front[0]},${front[1] - lift}`} fill={sideR} />
      <polygon points={rhombus(x, y, w, h, lift)} fill={fill} stroke="rgba(0,0,0,0.12)" />
      <text x={centerX} y={(backC[1] + front[1]) / 2 - lift + emojiSize * 0.35} textAnchor="middle" fontSize={emojiSize}>
        {item.emoji}
      </text>
      {sparkle}
    </g>
  );
}
