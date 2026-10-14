import { useLayoutEffect, useState, type RefObject } from "react";

import { chemistryFrozenText, type ChemistrySwapHint } from "@/lib/chemistry";
import type { ChemistryLinkLevel, ChemistryOut } from "@/types";

const LINK_STROKE: Record<ChemistryLinkLevel, string> = {
  strong: "#3ed17e",
  medium: "#facc15",
  none: "#ef4444",
};

const NO_LINKS: ChemistryOut["links"] = [];

interface Segment {
  key: string;
  level: ChemistryLinkLevel;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

const MIN_LINK_PX = 22;

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Where the segment from the centre of `box` towards (tx, ty) leaves the
 * box (plus a small gap), so a link runs from card edge to card edge. */
function edgePoint(box: Box, tx: number, ty: number, gap = 2): { x: number; y: number } {
  const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
  const dx = tx - cx, dy = ty - cy;
  if (dx === 0 && dy === 0) return { x: cx, y: cy };
  const sx = dx !== 0 ? (box.w / 2 + gap) / Math.abs(dx) : Infinity;
  const sy = dy !== 0 ? (box.h / 2 + gap) / Math.abs(dy) : Infinity;
  const t = Math.min(sx, sy, 1);
  return { x: cx + dx * t, y: cy + dy * t };
}

/** Green/yellow/red lines between neighbouring cards on the pitch. Cards are
 * found by their `data-chem-slot` attribute inside `containerRef` and
 * measured from the DOM, so the overlay follows whatever layout the editor
 * uses (re-measuring on resize and when card images finish loading). Each
 * line spans the gap between the cards' EDGES (at least MIN_LINK_PX) and is
 * drawn above the cards with a dark halo, so it stays visible however big or opaque the
 * cards (photos) are — drawn centre-to-centre beneath them, links between
 * photo cards used to be almost entirely hidden. */
export function ChemistryLinksOverlay({
  containerRef,
  chemistry,
}: {
  containerRef: RefObject<HTMLElement>;
  chemistry: ChemistryOut | undefined;
}) {
  const [segments, setSegments] = useState<Segment[]>([]);
  // Stable empty array: a fresh [] each render would re-run the effect forever.
  const links = chemistry?.enabled ? chemistry.links : NO_LINKS;

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container || links.length === 0) {
      setSegments([]);
      return;
    }
    const measure = () => {
      const box = container.getBoundingClientRect();
      const boxes = new Map<string, Box>();
      container.querySelectorAll<HTMLElement>("[data-chem-slot]").forEach((el) => {
        const r = el.getBoundingClientRect();
        boxes.set(el.dataset.chemSlot!, { x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height });
      });
      setSegments(
        links.flatMap((l) => {
          const a = boxes.get(l.a), b = boxes.get(l.b);
          if (!a || !b) return [];
          const ax = a.x + a.w / 2, ay = a.y + a.h / 2, bx = b.x + b.w / 2, by = b.y + b.h / 2;
          const dist = Math.hypot(bx - ax, by - ay);
          if (dist < 1) return [];
          const p1 = edgePoint(a, bx, by);
          const p2 = edgePoint(b, ax, ay);
          // Cards that (nearly) fill the pitch leave gaps of a few pixels:
          // stretch the link to a readable minimum, centred on the gap, so it
          // slightly overlaps the card frames.
          const ux = (bx - ax) / dist, uy = (by - ay) / dist;
          const gap = Math.max(0, (p2.x - p1.x) * ux + (p2.y - p1.y) * uy);
          const len = Math.min(Math.max(gap, MIN_LINK_PX), dist * 0.6);
          const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2;
          return [{
            key: `${l.a}-${l.b}`, level: l.level,
            x1: mx - (ux * len) / 2, y1: my - (uy * len) / 2, x2: mx + (ux * len) / 2, y2: my + (uy * len) / 2,
          }];
        }),
      );
    };
    measure();
    // Card photos change card sizes as they load.
    const images = Array.from(container.querySelectorAll("img"));
    images.forEach((img) => img.addEventListener("load", measure));
    if (typeof ResizeObserver === "undefined") {
      return () => images.forEach((img) => img.removeEventListener("load", measure));
    }
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    container.querySelectorAll<HTMLElement>("[data-chem-slot]").forEach((el) => observer.observe(el));
    return () => {
      observer.disconnect();
      images.forEach((img) => img.removeEventListener("load", measure));
    };
  }, [containerRef, links]);

  if (segments.length === 0) return null;
  return (
    <svg className="pointer-events-none absolute inset-0 z-10 h-full w-full" aria-hidden>
      {segments.map((s) => (
        <g key={s.key}>
          <line
            x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
            stroke="#04130c" strokeOpacity={0.75} strokeWidth={s.level === "strong" ? 6 : 5} strokeLinecap="round"
          />
          <line
            x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
            stroke={LINK_STROKE[s.level]}
            strokeWidth={s.level === "strong" ? 3.5 : 2.5}
            strokeDasharray={s.level === "none" ? "3 3" : undefined}
            strokeLinecap="round"
          />
        </g>
      ))}
    </svg>
  );
}

/** 0–max chemistry diamonds under a card. */
export function ChemistryDiamonds({ points, max, onPosition }: { points: number; max: number; onPosition: boolean }) {
  if (max <= 0) return null;
  const color = points >= 3 ? "bg-accent-green" : points === 2 ? "bg-accent-lime" : points === 1 ? "bg-yellow-400" : "bg-red-500/80";
  return (
    <span
      className="flex items-center gap-0.5"
      title={onPosition ? `Химия ${points}/${max}` : "Не на своей позиции — химия 0"}
      aria-label={`Химия ${points} из ${max}`}
    >
      {Array.from({ length: max }, (_, i) => (
        <span key={i} className={`h-1.5 w-1.5 rotate-45 rounded-[1px] ${i < points ? color : "bg-white/15"}`} />
      ))}
    </span>
  );
}

/** «Химия N/M» counter with the strength bonus and a short rules hint. */
export function ChemistrySummary({ chemistry }: { chemistry: ChemistryOut | undefined }) {
  const [open, setOpen] = useState(false);
  if (!chemistry?.enabled) return null;
  const rules = chemistry.rules;
  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between rounded-xl bg-white/5 px-3 py-2 active:scale-[0.99]"
      >
        <span className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wide text-ink-mist-dim">Химия</span>
          <span className="font-mono text-sm font-bold text-ink-chalk">{chemistry.team}/{chemistry.team_max}</span>
        </span>
        <span className="flex items-center gap-2 text-[11px]">
          {chemistry.strength_bonus != null && chemistry.strength_bonus !== 0 && (
            <span className="font-mono font-bold text-accent-green">
              {chemistry.strength_bonus > 0 ? "+" : ""}{chemistry.strength_bonus} к силе
            </span>
          )}
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-white/10 text-[10px] font-bold text-ink-mist-dim">?</span>
        </span>
      </button>
      {open && rules && (
        <div className="mt-1.5 rounded-xl bg-white/5 px-3 py-2 text-[11px] leading-relaxed text-ink-mist">
          <p>· Линия между соседями: <span className="text-accent-green">зелёная</span> — один клуб и одна страна, <span className="text-yellow-400">жёлтая</span> — клуб или страна, <span className="text-red-400">красная</span> — ничего общего</p>
          <p>· Химия игрока 0–{rules.player_max} растёт от связей с соседями; не на своей позиции — 0</p>
          <p>· Каждое очко химии: +{rules.rating_per_point} к рейтингу игрока в матче{rules.off_position_penalty > 0 ? `, не на своей позиции −${rules.off_position_penalty}` : ""}</p>
          {chemistry.coach_country && (rules.coach_country_points ?? 0) > 0 && (
            <p>· Тренер-земляк ({chemistry.coach_country}): +{rules.coach_country_points} к химии игроков этой страны</p>
          )}
          {chemistry.stadium_club && (rules.stadium_club_points ?? 0) > 0 && (
            <p>· Домашний стадион ({chemistry.stadium_club}): +{rules.stadium_club_points} к химии игроков клуба — только в домашних матчах</p>
          )}
          <p className="mt-1 text-ink-mist-dim">Рейтинг на самой карточке не меняется.</p>
        </div>
      )}
    </div>
  );
}

/** Tells the player that the running tournament keeps the chemistry rules it
 * started with (backend freezes them per tournament), so a settings change —
 * including switching the mechanic on — only applies from the next one. */
export function ChemistryFrozenNote({ chemistry }: { chemistry: ChemistryOut | undefined }) {
  const text = chemistryFrozenText(chemistry);
  if (!text) return null;
  return <p className="mb-3 rounded-xl bg-white/5 px-3 py-2 text-[11px] leading-relaxed text-ink-mist">{text}</p>;
}

/** "Поставь X на DEF2 — +N к химии" one-tap swaps. */
export function ChemistryHints({
  hints, onApply, busy,
}: {
  hints: ChemistrySwapHint[];
  onApply: (hint: ChemistrySwapHint) => void;
  busy?: boolean;
}) {
  if (hints.length === 0) return null;
  return (
    <section className="mb-3 rounded-2xl border border-accent-green/20 bg-accent-green/5 p-3">
      <p className="text-xs font-semibold text-accent-green">Можно поднять химию</p>
      <ul className="mt-2 flex flex-col gap-1.5">
        {hints.map((h) => (
          <li key={h.slotCode} className="flex items-center gap-2 text-xs">
            <span className="w-9 shrink-0 font-mono text-[10px] text-ink-mist">{h.slotCode}</span>
            <span className="min-w-0 flex-1 truncate text-ink-chalk">
              {h.name}
              <span className="text-ink-mist">{h.currentName ? ` вместо ${h.currentName}` : " в пустой слот"}</span>
            </span>
            <span className="shrink-0 font-mono text-[11px] font-bold text-accent-green">+{h.gain} хим.</span>
            <button
              onClick={() => onApply(h)}
              disabled={busy}
              className="shrink-0 rounded-full bg-accent-green/15 px-2 py-0.5 text-[11px] font-semibold text-accent-green disabled:opacity-50"
            >
              Поставить
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
