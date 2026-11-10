import { useEffect, useRef, useState, type ReactNode } from "react";

import {
  SCENE_H, SCENE_W, SEASON_PARTICLES, SPRITES, moverAt, seasonAt, skyAt, type Box, type Mover, type Sky,
} from "@/lib/town";

const SPRITE_URLS = import.meta.glob<string>("@/assets/town/{people,vehicles}/*.webp", { eager: true, import: "default" });
const spriteUrl = (key: string) => SPRITE_URLS[`/src/assets/town/${key}.webp`];

export type SceneZone = { code: string; label: string; zone: Box; locked?: boolean; badge?: ReactNode };

const pct = (v: number, of: number) => `${(v / of) * 100}%`;

// A tint over the picture (under the badges): multiplied, so the lights stay bright.
const SKY_TINT: Record<Sky, { color: string; opacity: number } | null> = {
  dawn: { color: "#ffb9a8", opacity: 0.22 },
  day: null,
  dusk: { color: "#ff8a4c", opacity: 0.3 },
  night: { color: "#1b2a6b", opacity: 0.62 },
};

function useSky(): Sky {
  const [sky, setSky] = useState<Sky>(() => skyAt(new Date().getHours()));
  useEffect(() => {
    const id = window.setInterval(() => setSky(skyAt(new Date().getHours())), 60_000);
    return () => window.clearInterval(id);
  }, []);
  return sky;
}

// Fixed spots so the drift looks the same on every render: [left %, delay s, duration s, size rem].
const FLAKES: [number, number, number, number][] = [
  [6, 0, 9, 0.8], [18, 3.5, 11, 0.6], [31, 1.2, 8, 0.9], [44, 5, 12, 0.7], [57, 2.2, 10, 0.8],
  [69, 6.4, 9, 0.6], [81, 0.6, 11, 0.9], [92, 4.1, 10, 0.7],
];

/** Snow, petals or leaves drifting down the map, by the month. */
function SeasonDrift() {
  const glyph = SEASON_PARTICLES[seasonAt(new Date().getMonth() + 1)];
  if (!glyph || prefersReducedMotion()) return null;
  return (
    <span aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden" data-testid="town-season-drift">
      <style>{"@keyframes town-drift{0%{transform:translate(0,-10%) rotate(0)}100%{transform:translate(18px,1300%) rotate(220deg)}}"}</style>
      {FLAKES.map(([left, delay, duration, size], i) => (
        <span
          key={i}
          className="absolute top-0 opacity-80"
          style={{ left: `${left}%`, fontSize: `${size}rem`, animation: `town-drift ${duration}s linear ${delay}s infinite` }}
        >
          {glyph}
        </span>
      ))}
    </span>
  );
}

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/** One illustrated town picture (900×1200) with tap zones over its buildings
 * and a light layer of residents and vehicles walking their routes. The
 * sprites are SVG images moved every frame (requestAnimationFrame stops in a
 * hidden tab by itself); with reduced motion they stand still. */
export default function TownScene({
  art, label, zones, movers = [], water, overlay, decorations = [], onPick,
}: {
  art: string; label: string; zones: SceneZone[]; movers?: Mover[]; water?: Box;
  /** «Сезонный город»: the owner's limited decorations, shown on the map. */
  decorations?: { code: string; emoji: string; name: string; serial: number }[];
  /** Decoration drawn over the picture, under the tap zones (fireworks). */
  overlay?: ReactNode;
  onPick: (code: string) => void;
}) {
  const refs = useRef<(SVGGElement | null)[]>([]);
  const [hint, setHint] = useState<string | null>(null);
  const sky = useSky();
  const tint = SKY_TINT[sky];

  useEffect(() => {
    const place = (seconds: number) => {
      movers.forEach((m, i) => {
        const g = refs.current[i];
        if (!g) return;
        const s = SPRITES[m.sprite];
        const { x, y, dx } = moverAt(m, seconds);
        const flip = (dx < 0) === s.facesRight ? -1 : 1;
        const bob = m.sprite.startsWith("people/") ? (1 - Math.cos(seconds * 8 + i)) * 0.3 : 0;
        g.setAttribute("transform", `translate(${x.toFixed(1)} ${(y - bob).toFixed(1)}) scale(${flip} 1)`);
      });
    };
    place(0);
    if (prefersReducedMotion() || movers.length === 0) return;
    let frame = 0;
    const started = performance.now();
    const tick = (now: number) => {
      place((now - started) / 1000);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [movers]);

  return (
    <div className="relative">
      <div
        className="relative w-full overflow-hidden rounded-2xl ring-1 ring-white/10"
        style={{ aspectRatio: `${SCENE_W} / ${SCENE_H}` }}
        role="img"
        aria-label={label}
        data-sky={sky}
      >
        <img src={art} alt="" className="absolute inset-0 h-full w-full object-cover" draggable={false} />
        {water && (
          <span
            aria-hidden
            className="town-water pointer-events-none absolute"
            style={{ left: pct(water[0], SCENE_W), top: pct(water[1], SCENE_H), width: pct(water[2] - water[0], SCENE_W), height: pct(water[3] - water[1], SCENE_H) }}
          />
        )}
        <svg
          viewBox={`0 0 ${SCENE_W} ${SCENE_H}`}
          className="pointer-events-none absolute inset-0 h-full w-full"
          aria-hidden
          data-testid="town-movers"
        >
          {movers.map((m, i) => {
            const s = SPRITES[m.sprite];
            const w = (s.w / s.h) * s.height;
            return (
              <g key={i} ref={(el) => { refs.current[i] = el; }}>
                <ellipse cx={0} cy={0} rx={w * 0.35} ry={w * 0.12} fill="black" opacity={0.25} />
                <image href={spriteUrl(m.sprite)} x={-w / 2} y={-s.height} width={w} height={s.height} />
              </g>
            );
          })}
        </svg>
        {tint && (
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 transition-opacity duration-1000"
            style={{ background: tint.color, opacity: tint.opacity, mixBlendMode: "multiply" }}
          />
        )}
        {sky === "night" && (
          // Windows and street lamps: a warm glow over the lit-up parts of the picture.
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0"
            style={{ background: "radial-gradient(ellipse at 50% 60%, rgba(255,190,90,0.18), transparent 60%)", mixBlendMode: "screen" }}
          />
        )}
        <SeasonDrift />
        {decorations.length > 0 && (
          <span className="pointer-events-none absolute bottom-2 right-2 flex gap-1 rounded-full bg-black/45 px-2 py-0.5 text-base" data-testid="town-decorations">
            {decorations.map((d) => <span key={d.code} title={`${d.name} № ${d.serial}`}>{d.emoji}</span>)}
          </span>
        )}
        {overlay}
        {zones.map((z) => {
          const [x0, y0, x1, y1] = z.zone;
          return (
            <button
              key={z.code}
              type="button"
              onClick={() => onPick(z.code)}
              onMouseEnter={() => setHint(z.label)}
              onMouseLeave={() => setHint(null)}
              onFocus={() => setHint(z.label)}
              onBlur={() => setHint(null)}
              aria-label={z.label}
              className="group absolute rounded-xl outline-none transition-shadow hover:ring-2 hover:ring-white/50 focus-visible:ring-2 focus-visible:ring-accent-lime"
              style={{ left: pct(x0, SCENE_W), top: pct(y0, SCENE_H), width: pct(x1 - x0, SCENE_W), height: pct(y1 - y0, SCENE_H) }}
            >
              {z.locked && (
                // Not bought yet: the drawn house fades a little.
                <span className="absolute inset-0 rounded-xl bg-black/10 [backdrop-filter:saturate(0.7)]" aria-hidden />
              )}
              {z.badge}
            </button>
          );
        })}
      </div>
      {hint && (
        <span className="pointer-events-none absolute bottom-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-black/80 px-3 py-1 text-xs font-bold text-white ring-1 ring-white/20">
          {hint}
        </span>
      )}
    </div>
  );
}
