/** Drawn illustrations of the «Клубная база» buildings (SVG, pseudo-3D:
 * front face, right side, roof). Every building grows with its level —
 * more floors, then extra wings and landmark details at the top levels
 * (tiers: 1–3 small, 4–6 medium, 7–9 large, 10 landmark with gold trim).
 * Colours that must follow the light/dark theme are CSS variables; the
 * architecture's own colours are fixed like on any illustrated map. */
import { DX, DY, tier } from "./artMetrics";


const WALL = "rgb(var(--map-wall))";
const GOLD = "#f2c230";
const LIT = "rgb(var(--c-legend))";


/** A block: front face, darker right side, roof on top. (x, y) = front-bottom-left. */
export function Box({
  x, y, w, h, front = WALL, side, roof, dx = DX, dy = DY, stroke,
}: { x: number; y: number; w: number; h: number; front?: string; side?: string; roof?: string; dx?: number; dy?: number; stroke?: string }) {
  const top = y - h;
  return (
    <g>
      <polygon points={`${x + w},${y} ${x + w + dx},${y - dy} ${x + w + dx},${top - dy} ${x + w},${top}`} fill={side ?? front} />
      {!side && <polygon points={`${x + w},${y} ${x + w + dx},${y - dy} ${x + w + dx},${top - dy} ${x + w},${top}`} fill="#000" opacity="0.3" />}
      <rect x={x} y={top} width={w} height={h} fill={front} stroke={stroke} strokeWidth={stroke ? 0.5 : 0} />
      <polygon points={`${x},${top} ${x + w},${top} ${x + w + dx},${top - dy} ${x + dx},${top - dy}`} fill={roof ?? front} />
      {!roof && <polygon points={`${x},${top} ${x + w},${top} ${x + w + dx},${top - dy} ${x + dx},${top - dy}`} fill="#fff" opacity="0.18" />}
    </g>
  );
}

/** Rows of windows; `seed` makes the lit pattern stable per building. */
export function Windows({
  x, y, w, rows, cols, rowH = 6, seed = 1, color = LIT, dark = "#1c2620",
}: { x: number; y: number; w: number; rows: number; cols: number; rowH?: number; seed?: number; color?: string; dark?: string }) {
  const cells = [];
  const cw = w / cols;
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const lit = ((r * 7 + c * 3 + seed) % 5) !== 0;
      cells.push(
        <rect key={`${r}-${c}`} x={x + c * cw + cw * 0.18} y={y - (r + 1) * rowH + rowH * 0.25} width={cw * 0.64} height={rowH * 0.5}
              rx="0.5" fill={lit ? color : dark} opacity={lit ? 0.92 : 0.7} />,
      );
    }
  }
  return <g>{cells}</g>;
}

function Shadow({ x, y, w }: { x: number; y: number; w: number }) {
  return <ellipse cx={x + w / 2 + DX / 2} cy={y + 1.5} rx={w / 2 + 7} ry="4.5" fill="#000" opacity="0.22" />;
}

function Flag({ x, y, color = "rgb(var(--c-path))" }: { x: number; y: number; color?: string }) {
  return (
    <g>
      <line x1={x} y1={y} x2={x} y2={y - 12} stroke="#9aa59e" strokeWidth="0.8" />
      <path d={`M${x} ${y - 12} q 4 -1.5 8 0 q -4 2 -8 4 z`} fill={color}>
        <animate attributeName="d" dur="2.4s" repeatCount="indefinite"
                 values={`M${x} ${y - 12} q 4 -1.5 8 0 q -4 2 -8 4 z;M${x} ${y - 12} q 4 1.5 8 0.5 q -4 1 -8 3.5 z;M${x} ${y - 12} q 4 -1.5 8 0 q -4 2 -8 4 z`} />
      </path>
    </g>
  );
}

function GoldTrim({ x, y, w }: { x: number; y: number; w: number }) {
  return <polygon points={`${x},${y} ${x + w},${y} ${x + w + DX},${y - DY} ${x + DX},${y - DY}`} fill="none" stroke={GOLD} strokeWidth="1" />;
}

export type Art = { x: number; y: number; w: number; level: number };

// --- Штаб-квартира: glass tower on a stone podium -------------------------------------------------
export function HqArt({ x, y, w, level }: Art) {
  const t = tier(level);
  const floors = 2 + Math.ceil(level / 2);
  const tw = w - 18;
  const tx = x + 9;
  const th = floors * 6 + 2;
  const podium = 7;
  return (
    <g>
      <defs>
        <linearGradient id="hq-glass" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#8ec5f2" />
          <stop offset="1" stopColor="#2f5e9e" />
        </linearGradient>
      </defs>
      <Shadow x={x} y={y} w={w} />
      {t >= 1 && <Box x={x} y={y - podium} w={12} h={floors * 3} front="#cfd6d0" roof="#6f8aa6" />}
      {t >= 2 && <Box x={x + w - 12} y={y - podium} w={12} h={floors * 3.5} front="#cfd6d0" roof="#6f8aa6" />}
      <Box x={x} y={y} w={w} h={podium} front="#b9b2a2" roof="#d8d2c4" />
      <rect x={x + w / 2 - 4} y={y - 6} width="8" height="6" fill="#1d2b3a" />
      <Box x={tx} y={y - podium} w={tw} h={th} front="url(#hq-glass)" side="#244a7c" roof="#3f6fb5" />
      <Windows x={tx + 1} y={y - podium} w={tw - 2} rows={floors} cols={Math.max(3, Math.floor(tw / 6))} seed={3} color="#fff4b8" dark="#24466f" />
      {/* glass reflection */}
      <polygon points={`${tx + 2},${y - podium - 2} ${tx + 8},${y - podium - 2} ${tx + tw - 2},${y - podium - th + 2} ${tx + tw - 8},${y - podium - th + 2}`}
               fill="#fff" opacity="0.12" />
      <Flag x={tx + tw / 2 + DX / 2} y={y - podium - th - DY / 2} />
      {t >= 3 && <GoldTrim x={tx} y={y - podium - th} w={tw} />}
    </g>
  );
}

// --- Клубный отель: cream tower with balconies, neon sign, pool -----------------------------------
export function HotelArt({ x, y, w, level }: Art) {
  const t = tier(level);
  const floors = 2 + Math.ceil(level * 0.6);
  const h = floors * 5.5 + 4;
  const mw = t >= 2 ? w - 16 : w - 8;
  return (
    <g>
      <Shadow x={x} y={y} w={w} />
      {level >= 3 && (
        <g>
          <rect x={x - 14} y={y - 9} width="16" height="9" rx="2.5" fill="#5bc8e8" stroke="#e8f6fb" strokeWidth="0.8" />
          <path d={`M${x - 12} ${y - 5} q 3 -1.5 6 0 t 6 0`} fill="none" stroke="#fff" strokeOpacity="0.6" strokeWidth="0.6" />
          <rect x={x - 13} y={y - 12} width="4" height="2" rx="0.5" fill="#f08a2f" />
          <rect x={x - 7} y={y - 12} width="4" height="2" rx="0.5" fill="#f08a2f" />
        </g>
      )}
      {t >= 2 && <Box x={x + mw - 2} y={y} w={18} h={h * 0.7} front="#ead9bd" roof="#b8862f" />}
      <Box x={x} y={y} w={mw} h={h} front="#f1e4cc" roof="#b8862f" />
      <Windows x={x + 2} y={y - 2} w={mw - 4} rows={floors} cols={Math.max(3, Math.floor(mw / 6))} rowH={5.5} seed={5} />
      {Array.from({ length: floors }).map((_, i) => (
        <line key={i} x1={x + 1} x2={x + mw - 1} y1={y - 2 - i * 5.5} y2={y - 2 - i * 5.5} stroke="#a58a63" strokeWidth="0.7" />
      ))}
      <rect x={x + mw / 2 - 4} y={y - 6} width="8" height="6" fill="#5a3a20" />
      <rect x={x + mw / 2 - 6} y={y - 8} width="12" height="2" fill="#b8862f" />
      {/* neon sign */}
      <rect x={x - 3} y={y - h + 2} width="5" height={Math.min(h - 8, 24)} rx="1" fill="#2a1630" />
      <rect x={x - 2.2} y={y - h + 3} width="3" height={Math.min(h - 8, 24) - 2} rx="1" fill="#ff5fb0" opacity="0.9" />
      <rect x={x - 3.2} y={y - h + 2} width="5" height={Math.min(h - 8, 24)} rx="1.5" fill="#ff5fb0" opacity="0.25" />
      {t >= 3 && [0, 1, 2, 3, 4].map((i) => {
        const sx = x + mw / 2 + DX / 2 - 12 + i * 6;
        const sy = y - h - DY - 4;
        return <polygon key={i} fill={GOLD}
                        points={`${sx},${sy - 2.4} ${sx + 0.7},${sy - 0.7} ${sx + 2.4},${sy - 0.7} ${sx + 1},${sy + 0.4} ${sx + 1.5},${sy + 2.2} ${sx},${sy + 1.1} ${sx - 1.5},${sy + 2.2} ${sx - 1},${sy + 0.4} ${sx - 2.4},${sy - 0.7} ${sx - 0.7},${sy - 0.7}`} />;
      })}
    </g>
  );
}

// --- Тренировочный центр: indoor hall with a vaulted roof + gym -----------------------------------
export function TrainingArt({ x, y, w, level }: Art) {
  const t = tier(level);
  const h = 8 + level * 1.4;
  const r = 9 + level * 0.4;
  return (
    <g>
      <Shadow x={x} y={y} w={w} />
      {t >= 1 && <Box x={x - 10} y={y} w={12} h={h + 2} front="#d9ddd6" roof="#2f9e58" />}
      <Box x={x} y={y} w={w} h={h} front="#e2e6df" roof="#2f9e58" />
      {/* vaulted roof */}
      <path d={`M${x} ${y - h} Q ${x + w / 2 + DX / 2} ${y - h - r * 2} ${x + w + DX} ${y - h - DY}`} fill="#3cae66" stroke="#277d48" strokeWidth="0.8" />
      {Array.from({ length: 4 }).map((_, i) => (
        <path key={i} d={`M${x + (i + 1) * (w / 5)} ${y - h - 0.5} Q ${x + (i + 1) * (w / 5) + 3} ${y - h - r * 1.6} ${x + (i + 1) * (w / 5) + 6} ${y - h - DY}`}
              fill="none" stroke="#fff" strokeOpacity="0.25" strokeWidth="0.6" />
      ))}
      <rect x={x + 3} y={y - h + 2} width={w - 6} height={h - 4} fill="#bfe3cb" opacity="0.9" />
      {Array.from({ length: Math.max(2, Math.floor(w / 6)) }).map((_, i) => (
        <line key={i} x1={x + 3 + i * ((w - 6) / Math.max(2, Math.floor(w / 6)))} x2={x + 3 + i * ((w - 6) / Math.max(2, Math.floor(w / 6)))}
              y1={y - h + 2} y2={y - 2} stroke="#8fb79c" strokeWidth="0.5" />
      ))}
      {t >= 2 && (
        <g>
          <rect x={x + w + DX + 3} y={y - 9} width="16" height="9" rx="1" fill="#3c9a4f" />
          <rect x={x + w + DX + 4} y={y - 8} width="14" height="7" fill="none" stroke="#fff" strokeOpacity="0.7" strokeWidth="0.5" />
          <rect x={x + w + DX + 17.5} y={y - 6} width="1.5" height="3" fill="#fff" />
        </g>
      )}
      {t >= 3 && <GoldTrim x={x} y={y - h} w={w} />}
    </g>
  );
}

// --- Медцентр: white clinic, red cross, ambulance, helipad -----------------------------------------
export function MedicalArt({ x, y, w, level }: Art) {
  const t = tier(level);
  const floors = 1 + Math.ceil(level / 2.5);
  const h = floors * 6 + 4;
  return (
    <g>
      <Shadow x={x} y={y} w={w} />
      {t >= 2 && <Box x={x + w - 4} y={y} w={14} h={h * 0.6} front="#eef3f0" roof="#9fb7aa" />}
      <Box x={x} y={y} w={w} h={h} front="#f5f8f6" roof="#c9d6cf" />
      <Windows x={x + 2} y={y - 2} w={w - 4} rows={floors} cols={Math.max(3, Math.floor(w / 7))} seed={2} color="#a6e1ff" dark="#86a49a" />
      <rect x={x} y={y - 3} width={w} height="3" fill="#2f9e8a" />
      <circle cx={x + w / 2} cy={y - h + 6} r="4.6" fill="#fff" stroke="#d63b3b" strokeWidth="0.8" />
      <rect x={x + w / 2 - 1.2} y={y - h + 2.6} width="2.4" height="6.8" fill="#d63b3b" />
      <rect x={x + w / 2 - 3.4} y={y - h + 4.8} width="6.8" height="2.4" fill="#d63b3b" />
      {level >= 3 && (
        <g>
          <rect x={x - 12} y={y - 6} width="11" height="6" rx="1" fill="#fff" stroke="#d63b3b" strokeWidth="0.6" />
          <rect x={x - 4} y={y - 5} width="3" height="2.5" fill="#86c5e8" />
          <rect x={x - 10} y={y - 4} width="4" height="1.2" fill="#d63b3b" />
          <circle cx={x - 9} cy={y} r="1.2" fill="#222" />
          <circle cx={x - 3.5} cy={y} r="1.2" fill="#222" />
          <circle cx={x - 7} cy={y - 6.6} r="0.9" fill="#3d7bff">
            <animate attributeName="fill" values="#3d7bff;#ff4d4d;#3d7bff" dur="0.9s" repeatCount="indefinite" />
          </circle>
        </g>
      )}
      {t >= 1 && (
        <g>
          <ellipse cx={x + w / 2 + DX / 2} cy={y - h - DY / 2} rx={Math.min(9, w / 3)} ry="3" fill="#3a4a42" stroke="#f2c230" strokeWidth="0.6" />
          <text x={x + w / 2 + DX / 2} y={y - h - DY / 2 + 1.8} textAnchor="middle" fontSize="4.6" fontWeight="800" fill="#fff">H</text>
        </g>
      )}
      {t >= 3 && <GoldTrim x={x} y={y - h} w={w} />}
    </g>
  );
}

// --- Аналитический центр: dark glass, data wall, observatory dome ----------------------------------
export function AnalyticsArt({ x, y, w, level }: Art) {
  const t = tier(level);
  const h = 12 + level * 2.6;
  return (
    <g>
      <Shadow x={x} y={y} w={w} />
      <Box x={x} y={y} w={w} h={h} front="#2b3440" roof="#7a5cc4" />
      <rect x={x + 3} y={y - h + 3} width={w - 6} height={Math.min(16, h - 8)} rx="1" fill="#0f1a24" stroke="#5be0ff" strokeWidth="0.6" />
      <polyline
        points={[0, 1, 2, 3, 4, 5].map((i) => `${x + 5 + i * ((w - 10) / 5)},${y - h + 3 + Math.min(16, h - 8) - 3 - ((i * 37 + level * 11) % 9)}`).join(" ")}
        fill="none" stroke="#5be0ff" strokeWidth="0.9"
      />
      {[0, 1, 2].map((i) => (
        <rect key={i} x={x + 5 + i * 6} y={y - h + 3 + Math.min(16, h - 8) - 2 - (i + 1) * 2} width="3" height={(i + 1) * 2} fill="#a98bff" opacity="0.8" />
      ))}
      <Windows x={x + 2} y={y - 2} w={w - 4} rows={Math.max(1, Math.floor((h - Math.min(16, h - 8) - 6) / 6))} cols={4} seed={4} color="#9ad8ff" dark="#22303c" />
      {t >= 1 && (
        <g>
          <path d={`M${x + w / 2 - 6 + DX / 2} ${y - h - DY / 2} a 6.5 6 0 0 1 13 0 z`} fill="#c9cfe0" stroke="#8a90a6" strokeWidth="0.6" />
          <line x1={x + w / 2 + DX / 2} y1={y - h - DY / 2 - 6} x2={x + w / 2 + DX / 2 + 4} y2={y - h - DY / 2 - 9} stroke="#5a6070" strokeWidth="1.4" />
        </g>
      )}
      {t >= 2 && (
        <g>
          <line x1={x + w + DX - 2} y1={y - h - DY} x2={x + w + DX - 2} y2={y - h - DY - 14} stroke="#9aa59e" strokeWidth="0.7" />
          <circle cx={x + w + DX - 2} cy={y - h - DY - 14} r="1.1" fill="#5be0ff">
            <animate attributeName="opacity" values="1;0.2;1" dur="1.6s" repeatCount="indefinite" />
          </circle>
        </g>
      )}
      {t >= 3 && <GoldTrim x={x} y={y - h} w={w} />}
    </g>
  );
}

// --- Медиацентр: studio, satellite dishes, TV mast ------------------------------------------------
export function MediaArt({ x, y, w, level }: Art) {
  const t = tier(level);
  const h = 12 + level * 2.2;
  const dishes = 1 + Math.floor(level / 3);
  const mast = 14 + level * 2;
  return (
    <g>
      <Shadow x={x} y={y} w={w} />
      {/* lattice TV mast */}
      <g stroke="#c0504d" strokeWidth="0.7">
        <line x1={x - 6} y1={y} x2={x - 3} y2={y - mast} />
        <line x1={x} y1={y} x2={x - 3} y2={y - mast} />
        {Array.from({ length: Math.floor(mast / 5) }).map((_, i) => (
          <line key={i} x1={x - 6 + i * (3 / (mast / 5))} y1={y - i * 5} x2={x - i * (3 / (mast / 5))} y2={y - i * 5 - 5} strokeWidth="0.4" />
        ))}
      </g>
      <circle cx={x - 3} cy={y - mast - 1} r="1.3" fill="#ff4d4d">
        <animate attributeName="opacity" values="1;0.15;1" dur="1.3s" repeatCount="indefinite" />
      </circle>
      <Box x={x} y={y} w={w} h={h} front="#e7e1d8" roof="#c0504d" />
      <Windows x={x + 2} y={y - 2} w={w - 4} rows={Math.max(1, Math.floor((h - 4) / 6))} cols={Math.max(3, Math.floor(w / 7))} seed={6} />
      <rect x={x + 3} y={y - h + 2} width="14" height="5" rx="1" fill="#1a1a1a" />
      <circle cx={x + 6} cy={y - h + 4.5} r="1.3" fill="#ff3b3b" />
      <rect x={x + 9} y={y - h + 3.6} width="6" height="1" fill="#fff" opacity="0.8" />
      <rect x={x + 9} y={y - h + 5.2} width="4" height="1" fill="#fff" opacity="0.5" />
      {Array.from({ length: dishes }).map((_, i) => {
        const cx = x + 8 + i * Math.min(10, (w - 6) / dishes) + DX / 2;
        const cy = y - h - DY / 2;
        return (
          <g key={i}>
            <line x1={cx} y1={cy} x2={cx} y2={cy - 4} stroke="#8a8f8b" strokeWidth="0.8" />
            <ellipse cx={cx} cy={cy - 6} rx="3.6" ry="2.2" fill="#f2f4f2" stroke="#9aa59e" strokeWidth="0.5" transform={`rotate(-25 ${cx} ${cy - 6})`} />
          </g>
        );
      })}
      {t >= 3 && <GoldTrim x={x} y={y - h} w={w} />}
    </g>
  );
}

// --- Отдел маркетинга: office with a rooftop billboard --------------------------------------------
export function MarketingArt({ x, y, w, level }: Art) {
  const t = tier(level);
  const h = 10 + level * 2.2;
  const bw = Math.min(w + 4, 22 + level * 1.5);
  return (
    <g>
      <Shadow x={x} y={y} w={w} />
      <Box x={x} y={y} w={w} h={h} front="#f3e2d1" roof="#d9762b" />
      <Windows x={x + 2} y={y - 2} w={w - 4} rows={Math.max(1, Math.floor((h - 4) / 6))} cols={3} seed={7} />
      <rect x={x + w / 2 - 3} y={y - 6} width="6" height="6" fill="#6b3a12" />
      <line x1={x + 6} y1={y - h - 2} x2={x + 6} y2={y - h - 8} stroke="#555" strokeWidth="0.8" />
      <line x1={x + bw - 2} y1={y - h - 2} x2={x + bw - 2} y2={y - h - 8} stroke="#555" strokeWidth="0.8" />
      <rect x={x + 2} y={y - h - 18} width={bw} height="11" rx="1" fill="#fff" stroke="#333" strokeWidth="0.6" />
      <rect x={x + 3} y={y - h - 17} width={bw / 3} height="9" fill="#d9762b" />
      <rect x={x + 3 + bw / 3} y={y - h - 17} width={bw / 3} height="9" fill="#2f6fd6" />
      <circle cx={x + 3 + bw * 0.83} cy={y - h - 12.5} r="2.6" fill="#f2c230" />
      {t >= 1 && <circle cx={x + 3 + bw / 6} cy={y - h - 12.5} r="1.6" fill="#fff" />}
      {t >= 2 && Array.from({ length: 3 }).map((_, i) => (
        <circle key={i} cx={x + 6 + i * (bw / 3)} cy={y - h - 19} r="0.9" fill="#fff7c2">
          <animate attributeName="opacity" values="1;0.3;1" dur={`${1 + i * 0.3}s`} repeatCount="indefinite" />
        </circle>
      ))}
      {t >= 3 && <GoldTrim x={x} y={y - h} w={w} />}
    </g>
  );
}

// --- Клубный магазин: striped awning, shirt in the window ------------------------------------------
export function ShopArt({ x, y, w, level }: Art) {
  const t = tier(level);
  const h = 12 + level * 1.8;
  const stripes = 6;
  return (
    <g>
      <Shadow x={x} y={y} w={w} />
      <Box x={x} y={y} w={w} h={h} front="#f6efe6" roof="#cf3f6a" />
      {h > 18 && <Windows x={x + 2} y={y - 13} w={w - 4} rows={Math.max(1, Math.floor((h - 16) / 6))} cols={3} seed={8} />}
      {/* shop window with a shirt */}
      <rect x={x + 2} y={y - 9} width={w * 0.55} height="8" fill="#bfe6f5" stroke="#8aa" strokeWidth="0.4" />
      <path d={`M${x + 6} ${y - 7.5} l2 -1 h3 l2 1 l1.4 2 l-1.6 0.8 v4 h-6.6 v-4 l-1.6 -0.8 z`} fill="#cf3f6a" />
      <rect x={x + w * 0.66} y={y - 8} width={w * 0.24} height="8" fill="#5a2a2a" />
      {/* awning */}
      {Array.from({ length: stripes }).map((_, i) => (
        <polygon key={i}
                 points={`${x + (i * w) / stripes},${y - 10} ${x + ((i + 1) * w) / stripes},${y - 10} ${x + ((i + 1) * w) / stripes + 1},${y - 13} ${x + (i * w) / stripes + 1},${y - 13}`}
                 fill={i % 2 ? "#ffffff" : "#cf3f6a"} />
      ))}
      <path d={`M${x} ${y - 10} ${Array.from({ length: stripes }).map(() => `q ${w / stripes / 2} 2 ${w / stripes} 0`).join(" ")}`}
            fill="none" stroke="#cf3f6a" strokeWidth="0.8" />
      {t >= 3 && <GoldTrim x={x} y={y - h} w={w} />}
    </g>
  );
}

// --- Бухгалтерия: classical bank with columns and a gold coin -------------------------------------
export function AccountingArt({ x, y, w, level }: Art) {
  const t = tier(level);
  const h = 10 + level * 1.8;
  const cols = 4;
  return (
    <g>
      <Shadow x={x} y={y} w={w} />
      <rect x={x - 2} y={y - 2} width={w + 4} height="2" fill="#cfc6b2" />
      <Box x={x} y={y - 2} w={w} h={h} front="#ece4d2" roof="#3d8f8a" />
      {Array.from({ length: cols }).map((_, i) => (
        <g key={i}>
          <rect x={x + 3 + i * ((w - 6) / (cols - 1)) - 1.4} y={y - 2 - h + 4} width="2.8" height={h - 5} fill="#fbf7ee" />
          <rect x={x + 3 + i * ((w - 6) / (cols - 1)) - 2} y={y - 2 - h + 3} width="4" height="1.2" fill="#d8ccb2" />
        </g>
      ))}
      <polygon points={`${x - 1},${y - 2 - h} ${x + w + 1},${y - 2 - h} ${x + w / 2},${y - 2 - h - 7}`} fill="#e3d8bf" stroke="#bfae8a" strokeWidth="0.5" />
      <circle cx={x + w / 2} cy={y - 2 - h - 2.6} r="2.2" fill={GOLD} stroke="#b8862f" strokeWidth="0.4" />
      {t >= 1 && Array.from({ length: Math.min(3, t + 1) }).map((_, i) => (
        <ellipse key={i} cx={x + w + DX + 4} cy={y - 1 - i * 1.6} rx="3" ry="1.1" fill={GOLD} stroke="#b8862f" strokeWidth="0.3" />
      ))}
      {t >= 3 && <GoldTrim x={x} y={y - 2 - h} w={w} />}
    </g>
  );
}
