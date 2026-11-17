import { useEffect, useRef, type PointerEvent as ReactPointerEvent } from "react";

import { inMap, isSeen } from "@/components/magic/mapPath";
import type { MagicRun } from "@/types";

type Box = { l: number; t: number; r: number; b: number };

/** A small schematic of the playable map in a corner: seen / unseen land,
 *  blocks, castles, the heroes and the screen's frame. Tap or drag on it to
 *  look there. Drawn on a canvas, redrawn only when the run changes. */
export default function MiniMap({ run, bounds, project, colors, frame, onLook, onLookEnd }: {
  run: MagicRun;
  /** The playable area on the big map (map coordinates). */
  bounds: Box;
  /** Cell → its centre on the big map. */
  project: (x: number, y: number) => [number, number];
  colors: { land: string; water: string; road: string };
  /** The screen's frame on the big map (map coordinates). */
  frame: { x: number; y: number; w: number; h: number };
  /** Centre the camera on this big-map point. */
  onLook: (x: number, y: number) => void;
  onLookEnd: () => void;
}) {
  const cw = bounds.r - bounds.l;
  const ch = bounds.b - bounds.t;
  const k = Math.min(96 / cw, 132 / ch);
  const w = Math.round(cw * k);
  const h = Math.round(ch * k);
  const canvas = useRef<HTMLCanvasElement>(null);
  const dragging = useRef(false);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    el.width = Math.round(w * dpr);
    el.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const hw = 32 * k * 1.06;
    const hh = 16 * k * 1.06;
    const cell = (x: number, y: number, color: string) => {
      const [mx, my] = project(x, y);
      const px = (mx - bounds.l) * k;
      const py = (my - bounds.t) * k;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(px, py - hh);
      ctx.lineTo(px + hw, py);
      ctx.lineTo(px, py + hh);
      ctx.lineTo(px - hw, py);
      ctx.closePath();
      ctx.fill();
    };
    const dot = (x: number, y: number, r: number, color: string) => {
      const [mx, my] = project(x, y);
      ctx.fillStyle = color;
      ctx.strokeStyle = "#1b1222";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc((mx - bounds.l) * k, (my - bounds.t) * k, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    };
    const seen = (x: number, y: number) => !!isSeen(run, x, y);
    const blocks = new Map(run.blocks.map(([x, y, kind]) => [`${x},${y}`, kind]));
    const road = new Set(run.road.map(([x, y]) => `${x},${y}`));
    const BLOCK: Record<string, string> = { tree: "#2f6b2c", rock: "#8b8f98", mountain: "#6b6f78" };
    for (let y = 0; y < run.map_h; y++) {
      for (let x = 0; x < run.map_w; x++) {
        if (!inMap(run, x, y)) continue;
        if (!seen(x, y)) {
          cell(x, y, "#141a2b");
          continue;
        }
        const kk = `${x},${y}`;
        const b = blocks.get(kk);
        cell(x, y, b === "water" ? colors.water : b ? BLOCK[b] ?? colors.land : road.has(kk) ? colors.road : colors.land);
      }
    }
    for (const o of run.objects) {
      if (o.kind !== "castle") continue;
      if (o.owner !== "me" && !seen(o.x, o.y)) continue;
      const [mx, my] = project(o.x, o.y);
      const s = Math.max(4, 40 * k);
      ctx.fillStyle = o.owner === "me" ? "#60a5fa" : "#b91c1c";
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1;
      ctx.fillRect((mx - bounds.l) * k - s / 2, (my - bounds.t) * k - s / 2, s, s);
      ctx.strokeRect((mx - bounds.l) * k - s / 2, (my - bounds.t) * k - s / 2, s, s);
    }
    if (run.bot.visible && run.bot.x !== undefined && run.bot.y !== undefined) dot(run.bot.x, run.bot.y, 3, "#ef4444");
    dot(run.hero.x, run.hero.y, 3.2, "#fde047");
  }, [run, w, h, k, bounds.l, bounds.t, colors.land, colors.water, colors.road]); // eslint-disable-line react-hooks/exhaustive-deps

  const look = (e: ReactPointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = Math.max(0, Math.min(w, e.clientX - r.left));
    const py = Math.max(0, Math.min(h, e.clientY - r.top));
    onLook(bounds.l + px / k, bounds.t + py / k);
  };

  // The screen's frame, clipped to the mini-map.
  const fl = Math.max(0, (frame.x - bounds.l) * k);
  const ft = Math.max(0, (frame.y - bounds.t) * k);
  const fr = Math.min(w, (frame.x + frame.w - bounds.l) * k);
  const fb = Math.min(h, (frame.y + frame.h - bounds.t) * k);

  return (
    <div
      className="relative cursor-pointer touch-none overflow-hidden rounded-lg"
      style={{ width: w, height: h }}
      onPointerDown={(e) => {
        e.stopPropagation();
        dragging.current = true;
        e.currentTarget.setPointerCapture?.(e.pointerId);
        look(e);
      }}
      onPointerMove={(e) => {
        e.stopPropagation();
        if (dragging.current) look(e);
      }}
      onPointerUp={(e) => {
        e.stopPropagation();
        dragging.current = false;
        onLookEnd();
      }}
      onPointerCancel={(e) => {
        e.stopPropagation();
        dragging.current = false;
        onLookEnd();
      }}
      aria-label="Мини-карта"
    >
      <canvas ref={canvas} style={{ width: w, height: h }} className="block" />
      {fr > fl && fb > ft && (
        <div className="pointer-events-none absolute rounded-[2px] border border-white/90 shadow-[0_0_0_1px_rgba(0,0,0,0.5)]"
          style={{ left: fl, top: ft, width: fr - fl, height: fb - ft }} />
      )}
    </div>
  );
}
