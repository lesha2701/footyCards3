import { staticUrl } from "@/lib/api";
import { SEAT_COLORS } from "@/lib/clubBase";
import type { ClubBaseBuilding, ClubBaseCode, ClubBaseLook, ClubBaseState } from "@/types";

/** «Клубная база» as a drawn campus: contour-line terrain, a river with a
 * bridge, roads, trees and training pitches; the stadium in the middle, the
 * buildings around it (a floor of lit windows per level, a crane over the
 * one under construction) and the «Академия» district. An admin-uploaded
 * background / building picture replaces the drawn one. Purely
 * illustrative — every number is in the building sheet. */

type Spot = { x: number; y: number; w: number; roof: string };

// x, y = front-bottom-left corner of the building block.
const SPOTS: Record<Exclude<ClubBaseCode, "stadium">, Spot> = {
  hq: { x: 152, y: 62, w: 56, roof: "#3f6fb5" },
  training: { x: 112, y: 112, w: 34, roof: "#2f9e58" },
  media: { x: 266, y: 62, w: 44, roof: "#c0504d" },
  analytics: { x: 290, y: 136, w: 42, roof: "#7a5cc4" },
  hotel: { x: 286, y: 222, w: 50, roof: "#b8862f" },
  medical: { x: 28, y: 206, w: 46, roof: "#e2e8e4" },
  marketing: { x: 196, y: 298, w: 34, roof: "#d9762b" },
  shop: { x: 236, y: 298, w: 34, roof: "#cf3f6a" },
  accounting: { x: 276, y: 298, w: 34, roof: "#3d8f8a" },
};

const STADIUM = { cx: 180, cy: 182, rx: 72, ry: 46 };
const DX = 8;
const DY = 6;
const FLOOR = 7;

function blockHeight(level: number): number {
  return 10 + Math.max(1, level) * FLOOR;
}

const TREES: [number, number, number][] = [
  [12, 22, 7], [26, 16, 6], [40, 26, 5], [100, 20, 6], [118, 28, 5], [222, 18, 6], [238, 26, 5],
  [336, 24, 7], [346, 44, 5], [12, 160, 6], [22, 172, 5], [96, 220, 6], [108, 234, 5], [250, 120, 5],
  [262, 112, 6], [340, 178, 6], [350, 256, 5], [160, 250, 5], [176, 258, 4], [10, 250, 6], [342, 300, 5],
];

function Terrain() {
  return (
    <g>
      <rect x="0" y="0" width="360" height="330" fill="rgb(var(--map-land))" />
      <path d="M0 0 H360 V150 C300 120 250 140 200 120 C150 100 90 130 0 110 Z" fill="rgb(var(--map-land-2))" opacity="0.7" />
      {/* Topographic contour lines (hills in the corners). */}
      <g fill="none" stroke="rgb(var(--map-contour))" strokeWidth="0.7" opacity="0.35">
        {[0, 1, 2, 3].map((i) => (
          <path key={`a${i}`} d={`M${-10} ${60 - i * 12} C ${40 + i * 6} ${70 - i * 14}, ${70 + i * 8} ${20 - i * 8}, ${60 + i * 12} ${-10}`} />
        ))}
        {[0, 1, 2, 3].map((i) => (
          <path key={`b${i}`} d={`M${370} ${90 - i * 14} C ${320 - i * 8} ${100 - i * 12}, ${300 - i * 10} ${40 - i * 6}, ${330 - i * 8} ${-10}`} />
        ))}
        {[0, 1, 2].map((i) => (
          <ellipse key={`c${i}`} cx="18" cy="262" rx={34 - i * 10} ry={22 - i * 6} />
        ))}
        {[0, 1, 2].map((i) => (
          <ellipse key={`d${i}`} cx="352" cy="230" rx={30 - i * 9} ry={40 - i * 12} />
        ))}
      </g>
      {/* River with a bridge on the main road. */}
      <path d="M0 316 C 60 304, 120 330, 180 318 S 300 300, 360 318 V330 H0 Z" fill="rgb(var(--map-water))" opacity="0.85" />
      <path d="M0 316 C 60 304, 120 330, 180 318 S 300 300, 360 318" fill="none" stroke="#ffffff" strokeOpacity="0.25" strokeWidth="0.8" />
      <rect x="168" y="306" width="24" height="24" rx="2" fill="rgb(var(--map-road))" />
      <line x1="168" y1="306" x2="168" y2="330" stroke="rgb(var(--map-wall))" strokeWidth="1.2" />
      <line x1="192" y1="306" x2="192" y2="330" stroke="rgb(var(--map-wall))" strokeWidth="1.2" />
    </g>
  );
}

function Roads() {
  const r = { fill: "none", stroke: "rgb(var(--map-road))", strokeLinecap: "round" as const };
  return (
    <g>
      <ellipse cx={STADIUM.cx} cy={STADIUM.cy} rx={STADIUM.rx + 18} ry={STADIUM.ry + 16} {...r} strokeWidth="7" />
      <path d="M180 306 V244" {...r} strokeWidth="9" />
      <path d="M180 120 V68" {...r} strokeWidth="6" />
      <path d="M100 160 C 70 160, 60 190, 52 206" {...r} strokeWidth="5" />
      <path d="M260 172 C 290 172, 300 200, 310 222" {...r} strokeWidth="5" />
      <path d="M248 140 C 270 120, 280 90, 288 64" {...r} strokeWidth="5" />
      <path d="M248 150 L 300 138" {...r} strokeWidth="5" />
      <path d="M180 244 C 190 270, 230 280, 270 298" {...r} strokeWidth="5" />
      <path d="M180 244 C 160 270, 120 280, 80 296" {...r} strokeWidth="5" />
      <path d="M120 140 L 128 112" {...r} strokeWidth="4" />
    </g>
  );
}

function Trees() {
  return (
    <g>
      {TREES.map(([x, y, s]) => (
        <g key={`${x}-${y}`}>
          <ellipse cx={x + 1} cy={y + s * 0.8} rx={s * 0.9} ry={s * 0.35} fill="#000" opacity="0.18" />
          <circle cx={x} cy={y} r={s} fill="rgb(var(--map-tree))" />
          <circle cx={x - s * 0.3} cy={y - s * 0.3} r={s * 0.45} fill="#ffffff" opacity="0.12" />
        </g>
      ))}
    </g>
  );
}

function Pitch({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx="2" fill="#3c9a4f" />
      {Array.from({ length: 6 }).map((_, i) => (
        <rect key={i} x={x + (i * w) / 6} y={y} width={w / 12} height={h} fill="#ffffff" opacity="0.06" />
      ))}
      <g fill="none" stroke="#ffffff" strokeOpacity="0.7" strokeWidth="0.7">
        <rect x={x + 2} y={y + 2} width={w - 4} height={h - 4} />
        <line x1={x + w / 2} y1={y + 2} x2={x + w / 2} y2={y + h - 2} />
        <circle cx={x + w / 2} cy={y + h / 2} r={h / 6} />
      </g>
    </g>
  );
}

function Crane({ x, top }: { x: number; top: number }) {
  return (
    <g stroke="rgb(var(--c-legend))" strokeWidth="1.3" fill="none">
      <line x1={x} y1={top + 40} x2={x} y2={top - 14} />
      <line x1={x - 26} y1={top - 12} x2={x + 8} y2={top - 12} />
      <line x1={x} y1={top - 14} x2={x - 18} y2={top - 12} />
      <line x1={x - 22} y1={top - 12} x2={x - 22} y2={top + 4} strokeDasharray="2 1.5" />
      <rect x={x - 25} y={top + 4} width="6" height="4" fill="rgb(var(--c-legend))" stroke="none" />
      <circle cx={x} cy={top - 16} r="1.6" fill="#ff5a4e" stroke="none">
        <animate attributeName="opacity" values="1;0.2;1" dur="1.2s" repeatCount="indefinite" />
      </circle>
    </g>
  );
}

function LevelPill({ x, y, level }: { x: number; y: number; level: number }) {
  return (
    <g>
      <circle cx={x} cy={y} r="6" fill="rgb(var(--c-bg-base))" stroke="rgb(var(--c-path))" strokeWidth="1" />
      <text x={x} y={y + 2.6} textAnchor="middle" fontSize="7" fontWeight="700" fill="rgb(var(--c-ink-chalk))">{level}</text>
    </g>
  );
}

function Block({ b, spot, art }: { b: ClubBaseBuilding; spot: Spot; art?: string }) {
  const { x, y, w, roof } = spot;
  const h = blockHeight(b.level);
  const top = y - h;
  if (art) {
    return (
      <g>
        <image href={staticUrl(art)} x={x - 4} y={y - w - 10} width={w + DX + 8} height={w + 10} preserveAspectRatio="xMidYMax meet" />
        {b.building && <Crane x={x + w + DX + 4} top={y - w} />}
        {b.level > 0 && <LevelPill x={x + w + DX} y={y - w - 4} level={b.level} />}
      </g>
    );
  }
  if (b.level === 0) {
    return (
      <g>
        <rect x={x} y={y - 10} width={w} height="10" rx="2" fill="rgb(var(--map-road))" opacity="0.45"
              stroke="rgb(var(--c-ink-mist))" strokeDasharray="3 2" strokeWidth="0.8" />
        <text x={x + w / 2} y={y - 22} textAnchor="middle" fontSize="12" opacity={b.locked ? 0.45 : 0.9}>{b.emoji}</text>
        <text x={x + w / 2} y={y - 2.5} textAnchor="middle" fontSize="7" fill="rgb(var(--c-ink-mist))">
          {b.building ? "стройка" : b.locked ? "🔒" : "+"}
        </text>
        {b.building && <Crane x={x + w + 4} top={y - 30} />}
      </g>
    );
  }
  const windows = [];
  for (let f = 0; f < b.level; f += 1) {
    const cols = Math.max(2, Math.floor((w - 6) / 9));
    for (let c = 0; c < cols; c += 1) {
      windows.push(
        <rect key={`${f}-${c}`} x={x + 4 + c * ((w - 8) / cols)} y={y - 9 - f * FLOOR - 4} width={(w - 8) / cols - 3} height="3.6" rx="0.6"
              fill="rgb(var(--c-legend))" opacity={0.55 + ((f + c) % 3) * 0.15} />,
      );
    }
  }
  return (
    <g>
      <ellipse cx={x + w / 2 + DX} cy={y + 1} rx={w / 2 + 6} ry="4" fill="#000" opacity="0.2" />
      {/* side, front, roof */}
      <polygon points={`${x + w},${y} ${x + w + DX},${y - DY} ${x + w + DX},${top - DY} ${x + w},${top}`} fill="rgb(var(--map-wall))" />
      <polygon points={`${x + w},${y} ${x + w + DX},${y - DY} ${x + w + DX},${top - DY} ${x + w},${top}`} fill="#000" opacity="0.28" />
      <rect x={x} y={top} width={w} height={h} fill="rgb(var(--map-wall))" />
      <rect x={x + w / 2 - 3} y={y - 7} width="6" height="7" fill="#000" opacity="0.35" />
      {windows}
      <polygon points={`${x},${top} ${x + w},${top} ${x + w + DX},${top - DY} ${x + DX},${top - DY}`} fill={roof} />
      <text x={x + w / 2 + DX / 2} y={top - DY - 4} textAnchor="middle" fontSize="11">{b.emoji}</text>
      {b.building && (
        <>
          <rect x={x - 2} y={top - DY - 2} width={w + DX + 4} height={h + DY + 2} fill="none"
                stroke="rgb(var(--c-legend))" strokeDasharray="2 2" strokeWidth="0.9" />
          <Crane x={x + w + DX + 5} top={top} />
        </>
      )}
      <LevelPill x={x + w + DX} y={top - DY} level={b.level} />
    </g>
  );
}

function Stadium({ b, look, art }: { b: ClubBaseBuilding; look: ClubBaseLook; art?: string }) {
  const { cx, cy, rx, ry } = STADIUM;
  if (art) {
    return (
      <g>
        <image href={staticUrl(art)} x={cx - rx - 6} y={cy - ry - 18} width={(rx + 6) * 2} height={(ry + 14) * 2}
               preserveAspectRatio="xMidYMid meet" />
        {b.building && <Crane x={cx + rx} top={cy - ry} />}
        {b.level > 0 && <LevelPill x={cx + rx - 4} y={cy - ry - 2} level={b.level} />}
      </g>
    );
  }
  if (b.level === 0) {
    return (
      <g>
        <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="rgb(var(--map-road))" opacity="0.35"
                 stroke="rgb(var(--c-ink-mist))" strokeDasharray="4 3" />
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize="16">🏟️</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize="8" fill="rgb(var(--c-ink-mist))">
          {b.building ? "строится" : "участок под стадион"}
        </text>
        {b.building && <Crane x={cx + rx - 6} top={cy - ry + 10} />}
      </g>
    );
  }
  const stand = 8 + b.level * 3;
  const seat = SEAT_COLORS[look.seats] ?? SEAT_COLORS.red;
  const irx = rx - stand;
  const iry = ry - stand * 0.66;
  const masts: [number, number][] = [[cx - rx + 6, cy - ry + 8], [cx + rx - 6, cy - ry + 8], [cx - rx + 6, cy + ry - 8], [cx + rx - 6, cy + ry - 8]];
  return (
    <g>
      <defs>
        <clipPath id="base-pitch-clip"><ellipse cx={cx} cy={cy} rx={irx} ry={iry} /></clipPath>
        <radialGradient id="base-light-glow">
          <stop offset="0" stopColor="#fff7c2" stopOpacity="0.9" />
          <stop offset="1" stopColor="#fff7c2" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse cx={cx + 2} cy={cy + 6} rx={rx + 2} ry={ry + 2} fill="#000" opacity="0.25" />
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="rgb(var(--map-wall))" />
      <ellipse cx={cx} cy={cy} rx={rx - 2} ry={ry - 2} fill={seat} />
      {/* Seat rows */}
      {Array.from({ length: Math.min(6, b.level + 1) }).map((_, i) => (
        <ellipse key={i} cx={cx} cy={cy} rx={rx - 4 - i * (stand / 6)} ry={ry - 4 - i * (stand / 9)} fill="none" stroke="#000" strokeOpacity="0.16" strokeWidth="0.7" />
      ))}
      <g clipPath="url(#base-pitch-clip)">
        <rect x={cx - irx} y={cy - iry} width={irx * 2} height={iry * 2} fill="#3c9a4f" />
        {Array.from({ length: 8 }).map((_, i) => (
          <rect key={i} x={cx - irx + (i * irx) / 4} y={cy - iry} width={irx / 8} height={iry * 2} fill="#fff" opacity="0.07" />
        ))}
        <g fill="none" stroke="#fff" strokeOpacity="0.75" strokeWidth="0.8">
          <rect x={cx - irx + 8} y={cy - iry + 5} width={irx * 2 - 16} height={iry * 2 - 10} />
          <line x1={cx} y1={cy - iry + 5} x2={cx} y2={cy + iry - 5} />
          <circle cx={cx} cy={cy} r={iry / 3.2} />
          <rect x={cx - irx + 8} y={cy - iry / 2.4} width={irx / 5} height={iry / 1.2} />
          <rect x={cx + irx - 8 - irx / 5} y={cy - iry / 2.4} width={irx / 5} height={iry / 1.2} />
        </g>
      </g>
      {look.roof === "canopy" && (
        <g fill="none" stroke="rgb(var(--map-roof))" strokeOpacity="0.85" strokeWidth={stand * 0.8}>
          <path d={`M ${cx - rx * 0.7} ${cy - ry * 0.74} A ${rx - stand / 2} ${ry - stand / 3} 0 0 1 ${cx + rx * 0.7} ${cy - ry * 0.74}`} />
          <path d={`M ${cx - rx * 0.7} ${cy + ry * 0.74} A ${rx - stand / 2} ${ry - stand / 3} 0 0 0 ${cx + rx * 0.7} ${cy + ry * 0.74}`} />
        </g>
      )}
      {look.roof === "full" && (
        <ellipse cx={cx} cy={cy} rx={rx - stand / 2} ry={ry - stand / 3} fill="none" stroke="rgb(var(--map-roof))"
                 strokeOpacity="0.8" strokeWidth={stand * 0.9} />
      )}
      {look.screen && (
        <g>
          <rect x={cx - 14} y={cy - ry - 9} width="28" height="11" rx="1.5" fill="#101418" stroke="rgb(var(--map-wall))" strokeWidth="0.8" />
          <text x={cx} y={cy - ry - 1} textAnchor="middle" fontSize="6.5" fontWeight="700" fill="#7cf0b0">2 : 1</text>
        </g>
      )}
      {look.lights && masts.map(([mx, my]) => (
        <g key={`${mx}-${my}`}>
          <circle cx={mx} cy={my} r="14" fill="url(#base-light-glow)" />
          <rect x={mx - 3} y={my - 2} width="6" height="3" rx="0.8" fill="#fffbe0" />
        </g>
      ))}
      {b.building && <Crane x={cx + rx + 4} top={cy - ry} />}
      <LevelPill x={cx + rx - 4} y={cy - ry - 2} level={b.level} />
    </g>
  );
}

function AcademyDistrict({ level, maxLevel, busy }: { level: number; maxLevel: number; busy: boolean }) {
  const houses = 5;
  const lit = maxLevel ? Math.round((level / maxLevel) * houses * 3) : 0;
  return (
    <g>
      <rect x="24" y="252" width="126" height="54" rx="8" fill="rgb(var(--c-path))" opacity="0.1"
            stroke="rgb(var(--c-path))" strokeOpacity="0.4" strokeDasharray="3 2" />
      {Array.from({ length: houses }).map((_, i) => {
        const x = 32 + i * 23;
        const h = 14 + ((i * 7) % 3) * 4;
        return (
          <g key={i}>
            <rect x={x} y={296 - h} width="17" height={h} fill="rgb(var(--map-wall))" />
            <polygon points={`${x - 2},${296 - h} ${x + 8.5},${288 - h} ${x + 19},${296 - h}`} fill="rgb(var(--c-path))" opacity="0.85" />
            {[0, 1, 2].map((r) => (
              <rect key={r} x={x + 4} y={292 - h + 6 + r * 4} width="9" height="2" rx="0.5"
                    fill="rgb(var(--c-legend))" opacity={i * 3 + r < lit ? 0.85 : 0.15} />
            ))}
          </g>
        );
      })}
      <text x="87" y="262" textAnchor="middle" fontSize="8" fontWeight="700" fill="rgb(var(--c-path))">🌱 Академия · {level}</text>
      {busy && <Crane x={150} top={262} />}
    </g>
  );
}

export default function BaseMap({
  state, onPick, onAcademy,
}: { state: ClubBaseState; onPick: (code: ClubBaseCode) => void; onAcademy: () => void }) {
  const byCode = Object.fromEntries(state.buildings.map((b) => [b.code, b])) as Record<ClubBaseCode, ClubBaseBuilding>;
  const art = state.art ?? { background: null, buildings: {} };
  const interactive = (code: ClubBaseCode, label: string, node: React.ReactNode) => (
    <g
      key={code}
      role="button"
      tabIndex={0}
      aria-label={label}
      className="cursor-pointer outline-none [&:focus-visible]:opacity-80"
      onClick={() => onPick(code)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onPick(code)}
    >
      {node}
    </g>
  );
  const stadium = byCode.stadium;
  const academyBusy = state.construction?.owner === "academy";
  // Draw back to front so nearer buildings overlap farther ones.
  const order = (Object.keys(SPOTS) as Exclude<ClubBaseCode, "stadium">[]).sort((a, b) => SPOTS[a].y - SPOTS[b].y);
  return (
    <svg viewBox="0 0 360 330" className="w-full rounded-2xl" role="img"
         aria-label={`Клубная база, уровень ${state.total_level}`}>
      {art.background ? (
        <image href={staticUrl(art.background)} x="0" y="0" width="360" height="330" preserveAspectRatio="xMidYMid slice" />
      ) : (
        <>
          <Terrain />
          <Roads />
          <Pitch x={20} y={94} w={80} h={44} />
          <Pitch x={56} y={30} w={44} h={24} />
          <Trees />
        </>
      )}
      {order.filter((code) => SPOTS[code].y < STADIUM.cy).map((code) =>
        byCode[code] && interactive(code, `${byCode[code].name}, уровень ${byCode[code].level}`,
          <Block b={byCode[code]} spot={SPOTS[code]} art={art.buildings[code]} />))}
      {stadium && interactive("stadium", `Стадион, уровень ${stadium.level}`,
        <Stadium b={stadium} look={state.stadium.look} art={art.buildings.stadium} />)}
      {order.filter((code) => SPOTS[code].y >= STADIUM.cy).map((code) =>
        byCode[code] && interactive(code, `${byCode[code].name}, уровень ${byCode[code].level}`,
          <Block b={byCode[code]} spot={SPOTS[code]} art={art.buildings[code]} />))}
      <g role="button" tabIndex={0} aria-label="Академия" className="cursor-pointer outline-none" onClick={onAcademy}
         onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onAcademy()}>
        <AcademyDistrict level={state.academy_level} maxLevel={state.academy_max_level} busy={academyBusy} />
      </g>
      <rect x="196" y="301" width="118" height="12" rx="6" fill="rgb(var(--c-bg-base))" opacity="0.7" />
      <text x="255" y="309.5" textAnchor="middle" fontSize="7.5" fontWeight="700" fill="rgb(var(--c-ink-chalk))">
        💼 Финансовый департамент
      </text>
    </svg>
  );
}
