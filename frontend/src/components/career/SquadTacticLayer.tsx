/** The team's tactic drawn faintly under the squad's cards on the «Состав»
 * pitch: where attacks go (flanks / centre), how the ball is moved up, the
 * defensive line at its height with the pressing zone, and what the team
 * does after losing the ball. Positions follow the rows of cards actually
 * on the pitch (rows carry `data-row="<line>"`). A picture only: the
 * numbers live on the server. */
import { useLayoutEffect, useState, type RefObject } from "react";

import type { Tactic } from "@/api/career";
import { lineY, type Band } from "@/lib/squadTactic";

interface Rows { w: number; h: number; FWD?: Band; MID?: Band; DEF?: Band; GK?: Band }

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

export function SquadTacticLayer({ containerRef, tactic, lineLabel, layoutKey }: {
  containerRef: RefObject<HTMLElement>; tactic: Tactic; lineLabel?: string;
  /** Changes when the rows of cards do (formation, view): measure again. */
  layoutKey?: string;
}) {
  const [rows, setRows] = useState<Rows | null>(null);
  useLayoutEffect(() => {
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

  const { FWD: fwd, MID: mid, DEF: def, GK: gk } = rows ?? {};
  if (!rows || !fwd || !mid || !def || rows.w < 10) return null;
  const { w, h } = rows;
  const block = tactic.block ?? "mid";
  const ly = lineY(block, mid, def, gk);
  const zone = block === "high" ? [0, mid.mid] : block === "low" ? [mid.top, gk ? gk.mid : h] : [fwd.bottom, def.mid];
  const wings = tactic.direction !== "center";
  const center = tactic.direction !== "wings";
  const arrowW = tactic.direction === "mixed" ? 2.5 : 3.5;
  const top = fwd.top + 4;

  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" width={w} height={h} viewBox={`0 0 ${w} ${h}`}
      aria-hidden="true" data-testid="squad-tactic-layer">
      <defs>
        <marker id="stl-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="3.2" markerHeight="3.2" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="#ffffff" fillOpacity="0.8" />
        </marker>
      </defs>
      {/* Where the team presses. */}
      <rect x="0" y={zone[0]} width={w} height={Math.max(0, zone[1] - zone[0])} fill="#38bdf8" opacity="0.09" data-zone={block} />
      {/* Attacks: along the flanks and / or through the middle. */}
      <g stroke="#ffffff" strokeOpacity="0.5" fill="none" strokeLinecap="round" markerEnd="url(#stl-arrow)" data-direction={tactic.direction ?? "mixed"}>
        {wings && (
          <>
            <path d={`M${w * 0.07} ${mid.mid} C ${w * 0.03} ${(mid.mid + top) / 2}, ${w * 0.05} ${top + 10}, ${w * 0.16} ${top}`} strokeWidth={arrowW} />
            <path d={`M${w * 0.93} ${mid.mid} C ${w * 0.97} ${(mid.mid + top) / 2}, ${w * 0.95} ${top + 10}, ${w * 0.84} ${top}`} strokeWidth={arrowW} />
          </>
        )}
        {center && <path d={`M${w / 2} ${mid.top} L${w / 2} ${top}`} strokeWidth={arrowW} />}
      </g>
      {/* Building up: short passes from the back, or long balls forward. */}
      <g stroke="#fef08a" strokeOpacity="0.55" fill="none" strokeWidth="1.6" data-buildup={tactic.buildup ?? "mixed"}>
        {tactic.buildup === "direct" && (
          <path d={`M${w * 0.36} ${def.mid} Q ${w * 0.3} ${mid.mid}, ${w * 0.62} ${fwd.bottom}`} strokeDasharray="6 4" markerEnd="url(#stl-arrow)" />
        )}
        {tactic.buildup === "short" && (
          <polyline points={[[0.3, def.mid], [0.4, (def.mid + mid.mid) / 2], [0.32, mid.mid], [0.44, (mid.mid + fwd.bottom) / 2]]
            .map(([x, y]) => `${w * x},${y}`).join(" ")} strokeDasharray="2.5 3" strokeLinecap="round" />
        )}
      </g>
      {/* After losing the ball: press at once, or drop back into shape. */}
      <g stroke="#7dd3fc" strokeOpacity="0.6" fill="none" strokeWidth="1.8" strokeLinecap="round" markerEnd="url(#stl-arrow)"
        data-on-loss={tactic.on_loss ?? "drop"}>
        {tactic.on_loss === "counterpress" ? (
          <>
            <path d={`M${w * 0.2} ${mid.bottom} L${w * 0.28} ${mid.top}`} />
            <path d={`M${w * 0.8} ${mid.bottom} L${w * 0.72} ${mid.top}`} />
          </>
        ) : (
          <>
            <path d={`M${w * 0.2} ${mid.top} L${w * 0.2} ${mid.bottom}`} />
            <path d={`M${w * 0.8} ${mid.top} L${w * 0.8} ${mid.bottom}`} />
          </>
        )}
      </g>
      {/* The defensive line at its height. */}
      <line x1={w * 0.03} y1={ly} x2={w * 0.97} y2={ly} stroke="#facc15" strokeOpacity="0.75" strokeWidth="1.6" strokeDasharray="7 5" data-line={block} />
      {lineLabel && (
        <g data-line-label="">
          <rect x={w * 0.03} y={ly - 6.5} width={lineLabel.length * 5 + 10} height="13" rx="6.5" fill="#0b1a12" fillOpacity="0.85" stroke="#facc15" strokeOpacity="0.6" strokeWidth="0.8" />
          <text x={w * 0.03 + 5} y={ly + 3} fontSize="8.5" fontWeight="700" fill="#facc15">{lineLabel}</text>
        </g>
      )}
      <text x={w / 2} y="12" textAnchor="middle" fontSize="8" fontWeight="700" letterSpacing="1.5" fill="#ffffff" fillOpacity="0.45">
        ▲ АТАКА
      </text>
    </svg>
  );
}
