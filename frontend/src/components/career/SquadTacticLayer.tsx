/** The «Состав» pitch of «Карьера тренера» and the team's tactic drawn on
 * it under the cards: mown grass with true-to-shape markings, glowing lanes
 * where attacks go (flanks / centre), how the ball is moved up, the
 * defensive line at its height with the pressing zone, and what the team
 * does after losing the ball. Positions follow the rows of cards actually
 * on the pitch (rows carry `data-row="<line>"`). A picture only: the
 * numbers live on the server. */
import { useEffect, useState, type RefObject } from "react";

import type { Tactic } from "@/api/career";
import { lineY, type Band } from "@/lib/squadTactic";

interface Rows { w: number; h: number; FWD?: Band; MID?: Band; DEF?: Band; GK?: Band }

const LIME = "#c6f432";
const CYAN = "#67e8f9";
const GOLD = "#facc15";
const STRIPES = 12;

/** The rows of one line together (a 4-2-3-1 has two midfield rows). */
function measure(container: HTMLElement): Rows {
  const box = container.getBoundingClientRect();
  const out: Rows = { w: box.width, h: box.height };
  container.querySelectorAll<HTMLElement>("[data-row]").forEach((el) => {
    const r = el.getBoundingClientRect();
    const key = el.dataset.row as "FWD" | "MID" | "DEF" | "GK";
    const top = r.top - box.top, bottom = r.bottom - box.top;
    const was = out[key];
    const band = was ? { top: Math.min(was.top, top), bottom: Math.max(was.bottom, bottom), mid: 0 } : { top, bottom, mid: 0 };
    band.mid = (band.top + band.bottom) / 2;
    out[key] = band;
  });
  return out;
}

/** Grass and the markings, in real pixels so the circles stay round. */
function Pitch({ w, h }: { w: number; h: number }) {
  const m = 6;
  const cx = w / 2;
  const boxW = w * 0.62, boxD = h * 0.13, sixW = w * 0.3, sixD = h * 0.045, spotD = h * 0.095;
  const r = Math.min(w * 0.15, h * 0.09);
  // The penalty arc: the part of the circle around the spot outside the box.
  const dy = boxD - spotD;
  const dx = Math.sqrt(Math.max(0, r * r - dy * dy));
  const top = m, bottom = h - m;
  return (
    <g data-pitch="">
      {Array.from({ length: STRIPES }).map((_, i) => i % 2 === 0 && (
        <rect key={i} x="0" y={(h / STRIPES) * i} width={w} height={h / STRIPES} fill="#ffffff" fillOpacity="0.035" />
      ))}
      <rect x="0" y="0" width={w} height={h} fill="url(#cp-flood)" />
      <rect x="0" y="0" width={w} height={h} fill="url(#cp-vignette)" />
      <g fill="none" stroke="#ffffff" strokeOpacity="0.3" strokeWidth="1.3">
        <rect x={m} y={top} width={w - 2 * m} height={h - 2 * m} rx="3" />
        <line x1={m} y1={h / 2} x2={w - m} y2={h / 2} />
        <circle cx={cx} cy={h / 2} r={r} />
        {/* Top end. */}
        <rect x={cx - boxW / 2} y={top} width={boxW} height={boxD} />
        <rect x={cx - sixW / 2} y={top} width={sixW} height={sixD} />
        <path d={`M${cx - dx} ${top + boxD} A ${r} ${r} 0 0 0 ${cx + dx} ${top + boxD}`} />
        {/* Bottom end. */}
        <rect x={cx - boxW / 2} y={bottom - boxD} width={boxW} height={boxD} />
        <rect x={cx - sixW / 2} y={bottom - sixD} width={sixW} height={sixD} />
        <path d={`M${cx - dx} ${bottom - boxD} A ${r} ${r} 0 0 1 ${cx + dx} ${bottom - boxD}`} />
        {/* Corners. */}
        <path d={`M${m + 7} ${top} A 7 7 0 0 1 ${m} ${top + 7}`} />
        <path d={`M${w - m - 7} ${top} A 7 7 0 0 0 ${w - m} ${top + 7}`} />
        <path d={`M${m} ${bottom - 7} A 7 7 0 0 1 ${m + 7} ${bottom}`} />
        <path d={`M${w - m} ${bottom - 7} A 7 7 0 0 0 ${w - m - 7} ${bottom}`} />
      </g>
      <g fill="#ffffff" fillOpacity="0.35">
        <circle cx={cx} cy={h / 2} r="2" />
        <circle cx={cx} cy={top + spotD} r="1.6" />
        <circle cx={cx} cy={bottom - spotD} r="1.6" />
      </g>
    </g>
  );
}

/** A glowing lane up the pitch ending in an arrowhead. */
function lane(x: number, width: number, from: number, to: number): string {
  const head = Math.min(18, width * 0.9);
  const half = width / 2, tail = half * 0.55;
  return [
    `M${x - tail} ${from}`, `L${x - half} ${to + head}`, `L${x - half - 4} ${to + head}`, `L${x} ${to}`,
    `L${x + half + 4} ${to + head}`, `L${x + half} ${to + head}`, `L${x + tail} ${from}`, "Z",
  ].join(" ");
}

/** A rounded chevron, pointing up (dir -1) or down (dir 1). */
function chevron(x: number, y: number, dir: 1 | -1, size = 6): string {
  return `M${x - size} ${y - dir * size * 0.55} L${x} ${y + dir * size * 0.55} L${x + size} ${y - dir * size * 0.55}`;
}

export function SquadTacticLayer({ containerRef, tactic, lineLabel, layoutKey }: {
  containerRef: RefObject<HTMLElement>; tactic?: Tactic | null; lineLabel?: string;
  /** Changes when the rows of cards do (formation, view): measure again. */
  layoutKey?: string;
}) {
  const [rows, setRows] = useState<Rows | null>(null);
  // A passive effect, not a layout one: the parent's ref (the pitch) is
  // attached only after its children's layout effects have run.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const update = () => setRows(measure(container));
    update();
    const images = Array.from(container.querySelectorAll("img"));
    images.forEach((img) => img.addEventListener("load", update));
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(container);
    return () => {
      observer?.disconnect();
      images.forEach((img) => img.removeEventListener("load", update));
    };
  }, [containerRef, layoutKey]);

  if (!rows || rows.w < 10) return null;
  const { w, h, FWD: fwd, MID: mid, DEF: def, GK: gk } = rows;
  const drawTactic = !!tactic && !!fwd && !!mid && !!def;

  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" width={w} height={h} viewBox={`0 0 ${w} ${h}`}
      aria-hidden="true" data-testid="squad-tactic-layer">
      <defs>
        <radialGradient id="cp-flood" cx="50%" cy="0%" r="75%">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.12" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="cp-vignette" cx="50%" cy="50%" r="75%">
          <stop offset="0.6" stopColor="#000000" stopOpacity="0" />
          <stop offset="1" stopColor="#000000" stopOpacity="0.45" />
        </radialGradient>
        <linearGradient id="cp-lane" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor={LIME} stopOpacity="0" />
          <stop offset="0.75" stopColor={LIME} stopOpacity="0.3" />
          <stop offset="1" stopColor={LIME} stopOpacity="0.6" />
        </linearGradient>
        <linearGradient id="cp-zone" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={CYAN} stopOpacity="0" />
          <stop offset="0.5" stopColor={CYAN} stopOpacity="0.13" />
          <stop offset="1" stopColor={CYAN} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="cp-line" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor={GOLD} stopOpacity="0" />
          <stop offset="0.12" stopColor={GOLD} stopOpacity="0.95" />
          <stop offset="0.88" stopColor={GOLD} stopOpacity="0.95" />
          <stop offset="1" stopColor={GOLD} stopOpacity="0" />
        </linearGradient>
        <filter id="cp-glow" x="-10%" y="-300%" width="120%" height="700%">
          <feGaussianBlur stdDeviation="2.5" />
        </filter>
      </defs>
      <Pitch w={w} h={h} />
      {drawTactic && <TacticDrawing tactic={tactic!} w={w} h={h} fwd={fwd!} mid={mid!} def={def!} gk={gk} lineLabel={lineLabel} />}
    </svg>
  );
}

function TacticDrawing({ tactic, w, h, fwd, mid, def, gk, lineLabel }: {
  tactic: Tactic; w: number; h: number; fwd: Band; mid: Band; def: Band; gk?: Band; lineLabel?: string;
}) {
  const block = tactic.block ?? "mid";
  const ly = lineY(block, mid, def, gk);
  const zone = block === "high" ? [0, mid.mid] : block === "low" ? [mid.top, gk ? gk.mid : h] : [fwd.bottom, def.mid];
  const direction = tactic.direction ?? "mixed";
  const wings = direction !== "center";
  const center = direction !== "wings";
  const laneW = direction === "mixed" ? w * 0.09 : w * 0.12;
  // The arrowheads sit above the forwards, in the room left for them.
  const top = 5;
  const pill = lineLabel ? lineLabel.length * 5.2 + 14 : 0;
  return (
    <>
      {/* Where the team presses. */}
      <rect x="0" y={zone[0]} width={w} height={Math.max(0, zone[1] - zone[0])} fill="url(#cp-zone)" data-zone={block} />

      {/* Attacks: lanes along the flanks and / or through the middle. */}
      <g fill="url(#cp-lane)" data-direction={direction}>
        {wings && (
          <>
            <path d={lane(w * 0.075, laneW, mid.bottom, top)} />
            <path d={lane(w * 0.925, laneW, mid.bottom, top)} />
          </>
        )}
        {center && <path d={lane(w / 2, laneW, def.top, top)} />}
      </g>

      {/* Building up: a chain of short passes, or one long ball forward. */}
      <g data-buildup={tactic.buildup ?? "mixed"}>
        {tactic.buildup === "short" && (() => {
          const pts = [[0.34, def.mid], [0.27, (def.top + mid.bottom) / 2], [0.36, mid.mid], [0.29, (mid.top + fwd.bottom) / 2]]
            .map(([x, y]) => [w * x, y] as const);
          return (
            <>
              <polyline points={pts.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke="#ffffff" strokeOpacity="0.55"
                strokeWidth="1.6" strokeDasharray="0.1 5" strokeLinecap="round" />
              {pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="2.6" fill="#ffffff" fillOpacity={0.35 + i * 0.15} />)}
            </>
          );
        })()}
        {tactic.buildup === "direct" && (
          <>
            <path d={`M${w * 0.36} ${def.mid} Q ${w * 0.2} ${mid.top}, ${w * 0.62} ${fwd.bottom + 4}`} fill="none" stroke="#ffffff"
              strokeOpacity="0.6" strokeWidth="1.8" strokeDasharray="5 5" strokeLinecap="round" />
            <circle cx={w * 0.62} cy={fwd.bottom + 4} r="3.6" fill="#ffffff" stroke="#0b1a12" strokeWidth="1" />
          </>
        )}
      </g>

      {/* After losing the ball: press at once (up), or drop back into shape (down). */}
      <g fill="none" stroke={CYAN} strokeOpacity="0.85" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"
        data-on-loss={tactic.on_loss ?? "drop"}>
        {/* In the gap above the midfield, where no card covers them. */}
        {[w * 0.2, w * 0.8].map((x) => {
          const y = (fwd.bottom + mid.top) / 2;
          const dir = tactic.on_loss === "counterpress" ? -1 : 1;
          return (
            <g key={x}>
              <path d={chevron(x, y - 4, dir)} />
              <path d={chevron(x, y + 3, dir)} strokeOpacity="0.45" />
            </g>
          );
        })}
      </g>

      {/* The defensive line at its height. */}
      <g data-line={block}>
        {/* Rects, not lines: a gradient or a filter on a zero-height box draws nothing. */}
        <rect x={w * 0.04} y={ly - 2} width={w * 0.92} height="4" fill={GOLD} fillOpacity="0.5" filter="url(#cp-glow)" />
        <rect x="0" y={ly - 0.9} width={w} height="1.8" fill="url(#cp-line)" />
      </g>
      {lineLabel && (
        <g data-line-label="">
          <rect x={w - pill - 8} y={ly - 7.5} width={pill} height="15" rx="7.5" fill="#0b1a12" fillOpacity="0.92" stroke={GOLD} strokeOpacity="0.7" strokeWidth="1" />
          <text x={w - pill / 2 - 8} y={ly + 3.2} textAnchor="middle" fontSize="9" fontWeight="700" fill={GOLD}>{lineLabel}</text>
        </g>
      )}

    </>
  );
}
