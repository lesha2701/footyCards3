// Creature portraits for «Мяч и Магия»: original cartoon busts drawn in pure
// SVG (viewBox 0 0 100 100). Heads stay in the top ~75% because the token
// covers the bottom strip with the footballer's photo.
import { useId, type ReactNode } from "react";

const K = "#1b1222";
const O = { stroke: K, strokeWidth: 2.2, strokeLinejoin: "round" as const, strokeLinecap: "round" as const };
const T = { ...O, strokeWidth: 1.4 };

type Faction = "dawn" | "ash" | "wild" | "none";
type Draw = (p: string) => ReactNode;

const BG: Record<Faction, [string, string, string]> = {
  dawn: ["#fff4c2", "#f2b33d", "#6b3410"],
  ash: ["#ff7a45", "#8c1c3c", "#22091f"],
  wild: ["#d4f27e", "#4c9a3a", "#13331b"],
  none: ["#c9cbd6", "#5d6478", "#1c1f2b"],
};

/** Thick outlined limb / pole: dark stroke underneath, colour on top. */
function Limb({ d, w, color }: { d: string; w: number; color: string }) {
  return (
    <g fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} stroke={K} strokeWidth={w + 4.4} />
      <path d={d} stroke={color} strokeWidth={w} />
    </g>
  );
}

/** Cartoon eye looking slightly right. */
function Eye({ x, y, r = 3, iris = K }: { x: number; y: number; r?: number; iris?: string }) {
  return (
    <g>
      <ellipse cx={x} cy={y} rx={r} ry={r * 1.15} fill="#fff" {...T} />
      <circle cx={x + r * 0.3} cy={y + r * 0.1} r={r * 0.58} fill={iris} />
      <circle cx={x + r * 0.55} cy={y - r * 0.3} r={r * 0.24} fill="#fff" />
    </g>
  );
}

/** Glowing eye made of soft layered circles (no filters, cheap at 40px). */
function GlowEye({ x, y, r = 2.6, color }: { x: number; y: number; r?: number; color: string }) {
  return (
    <g>
      <circle cx={x} cy={y} r={r * 2.4} fill={color} opacity={0.28} />
      <circle cx={x} cy={y} r={r * 1.5} fill={color} opacity={0.55} />
      <circle cx={x} cy={y} r={r} fill={color} />
      <circle cx={x + r * 0.2} cy={y - r * 0.2} r={r * 0.45} fill="#fffbe6" />
    </g>
  );
}

function Spark({ x, y, s = 3, color = "#fff7c8" }: { x: number; y: number; s?: number; color?: string }) {
  return (
    <path
      d={`M${x} ${y - s} Q${x + s * 0.2} ${y - s * 0.2} ${x + s} ${y} Q${x + s * 0.2} ${y + s * 0.2} ${x} ${y + s} Q${x - s * 0.2} ${y + s * 0.2} ${x - s} ${y} Q${x - s * 0.2} ${y - s * 0.2} ${x} ${y - s}Z`}
      fill={color}
    />
  );
}

function Lin({ id, c }: { id: string; c: [string, string] }) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0.3" y2="1">
      <stop offset="0" stopColor={c[0]} />
      <stop offset="1" stopColor={c[1]} />
    </linearGradient>
  );
}

function Rad({ id, c, o = [1, 0] }: { id: string; c: [string, string]; o?: [number, number] }) {
  return (
    <radialGradient id={id}>
      <stop offset="0" stopColor={c[0]} stopOpacity={o[0]} />
      <stop offset="1" stopColor={c[1]} stopOpacity={o[1]} />
    </radialGradient>
  );
}

function SunRays({ x, y, r1, r2, n, color, w = 2 }: { x: number; y: number; r1: number; r2: number; n: number; color: string; w?: number }) {
  return (
    <g stroke={color} strokeWidth={w} strokeLinecap="round">
      {Array.from({ length: n }, (_, i) => {
        const a = (i / n) * Math.PI * 2;
        return (
          <line key={i} x1={x + Math.cos(a) * r1} y1={y + Math.sin(a) * r1} x2={x + Math.cos(a) * r2} y2={y + Math.sin(a) * r2} />
        );
      })}
    </g>
  );
}

// ───────────────────────── Орден Рассвета ─────────────────────────

const dawnBanner: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}st`} c={["#f4f8ff", "#9fb4cf"]} />
      <Lin id={`${p}sh`} c={["#ffe27a", "#d98a1c"]} />
    </defs>
    {/* banner */}
    <rect x="72" y="8" width="5" height="94" rx="2" fill="#b4743a" {...O} />
    <path d="M72 11 L50 9 L54 16 L49 23 L72 25 Z" fill="#fff" {...O} />
    <path d="M71.5 15.5 L52.5 13.5 L54 16 L51.6 19.5 L71.5 20.5 Z" fill="#4fb0ff" />
    <circle cx="74.5" cy="7" r="3.6" fill="#ffd34d" {...O} />
    {/* body */}
    <path d="M24 100 L26 76 Q30 63 51 61 Q72 63 76 76 L78 100 Z" fill={`url(#${p}st)`} {...O} />
    <path d="M51 61 L51 100" stroke="#e8a21f" strokeWidth="5" />
    <path d="M60 64 Q72 66 75 78 L76 100 L68 100 Q68 80 60 64Z" fill="#7b8fae" opacity="0.45" />
    {/* head */}
    <ellipse cx="51" cy="46" rx="13" ry="13.5" fill="#f3c49c" {...O} />
    <path d="M58 50 Q62 56 54 59 Q61 59 63 50Z" fill="#d99a72" />
    <path d="M37.5 45 Q36 25 51 24 Q66 25 64.5 45 L61 41 Q51 37 41 41 Z" fill={`url(#${p}st)`} {...O} />
    <path d="M51 24.5 L51 39" stroke="#e8a21f" strokeWidth="3" strokeLinecap="round" />
    <path d="M42 30 Q46 27 50 27" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" />
    <rect x="49.6" y="39" width="3.4" height="9" rx="1.5" fill="#cfd9e8" {...T} />
    <Eye x={45.5} y={47} r={2.8} iris="#2a6fd6" />
    <Eye x={57.5} y={47} r={2.8} iris="#2a6fd6" />
    <path d="M47 54.5 Q52 58 57 54" fill="none" {...T} />
    <ellipse cx="43" cy="52.5" rx="2.2" ry="1.3" fill="#ff8f8f" opacity="0.6" />
    {/* scarf */}
    <path d="M38 60 Q51 66 64 60 L66 67 Q51 73 36 67Z" fill="#4fb0ff" {...O} />
    <path d="M44 62.6 L43 69.6 M51 63.6 L51 70.5 M58 62.6 L59 69.6" stroke="#fff" strokeWidth="2.6" />
    {/* hand on pole */}
    <circle cx="74.5" cy="72" r="5" fill="#f3c49c" {...O} />
    {/* tower shield */}
    <path d="M8 58 L36 58 L37 84 Q36 97 22.5 102 Q9 97 8 84Z" fill={`url(#${p}sh)`} {...O} />
    <path d="M12.5 62 L32 62 L32.5 83 Q31.5 93 22.5 97 Q13.5 93 12.5 83Z" fill="#fff8e6" />
    <path d="M26 62 L32 62 L32.5 83 Q31.5 93 22.5 97 Q28 88 26 62Z" fill="#f1d9a8" />
    <SunRays x={22.5} y={77} r1={6} r2={10} n={8} color="#e8a21f" w={2.2} />
    <circle cx="22.5" cy="77" r="5" fill="#ffc93a" {...T} />
    <path d="M11 61 L15 61" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
  </g>
);

const dawnSpear: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}tu`} c={["#7cc9ff", "#2f7fd0"]} />
    </defs>
    {/* quiver */}
    <g transform="rotate(-24 30 50)">
      <path d="M22 18 L25 8 L28 18Z M30 16 L33 5 L36 16Z" fill="#dfe8f5" {...T} />
      <path d="M25 18 V28 M33 16 V28" stroke="#9b6a3a" strokeWidth="2.4" />
      <rect x="20" y="26" width="18" height="40" rx="5" fill="#a5672f" {...O} />
      <path d="M20 34 H38" stroke="#ffd34d" strokeWidth="3" />
      <rect x="33" y="28" width="3.5" height="36" rx="1.6" fill="#7e4a20" />
    </g>
    {/* body */}
    <path d="M24 100 L27 77 Q31 65 48 63 Q65 65 69 77 L72 100 Z" fill={`url(#${p}tu)`} {...O} />
    <path d="M30 70 L66 98" stroke="#ffd34d" strokeWidth="5" />
    <circle cx="40" cy="84" r="5" fill="#fff" {...T} />
    <path d="M40 81.5 L42.3 83.2 L41.4 86 L38.6 86 L37.7 83.2Z" fill={K} />
    {/* raised arm + javelin */}
    <Limb d="M64 72 Q72 62 72 50" w={6.5} color="#f0b98d" />
    <Limb d="M50 82 L84 22" w={2.6} color="#c98c4c" />
    <path d="M84 22 L82 14 L89 18 Z" transform="rotate(-6 84 20)" fill="#e9f0fa" {...T} />
    <path d="M81 12 L90 10 L87 19 Z" fill="#e9f0fa" {...T} />
    <circle cx="72" cy="47" r="4.6" fill="#f0b98d" {...O} />
    {/* head */}
    <ellipse cx="47" cy="45" rx="12.5" ry="13" fill="#f0b98d" {...O} />
    <path d="M55 48 Q59 55 51 58 Q58 58 59.5 48Z" fill="#d0916a" />
    <path d="M35 42 Q33 30 40 27 Q37 24 42 22 Q44 26 47 23 Q50 20 52 24 Q57 21 58 27 Q62 30 60 40 Q55 33 46 34 Q39 35 35 42Z" fill="#ffcf3f" {...O} />
    <path d="M34 39 Q30 46 26 46 Q31 42 33 36" fill="#ffcf3f" {...T} />
    <path d="M35.2 40 Q47 33 59.8 39" stroke="#fff" strokeWidth="3.6" fill="none" />
    <path d="M35.2 40 Q47 33 59.8 39" stroke="#4fb0ff" strokeWidth="1.6" fill="none" strokeDasharray="3 3" />
    <Eye x={43} y={46.5} r={2.6} iris="#2e7a3a" />
    <Eye x={54} y={46.5} r={2.6} iris="#2e7a3a" />
    <path d="M40 42 L45 41.2 M52 41 L57 42" stroke={K} strokeWidth="1.6" strokeLinecap="round" />
    <path d="M45 53 Q49 56.5 54 53" fill="none" {...T} />
  </g>
);

const dawnPriest: Draw = (p) => (
  <g>
    <defs>
      <Rad id={`${p}orb`} c={["#fffbe0", "#ffd23d"]} o={[1, 0]} />
      <Lin id={`${p}rb`} c={["#ffffff", "#d7dcef"]} />
    </defs>
    {/* halo + staff glow */}
    <circle cx="78" cy="20" r="20" fill={`url(#${p}orb)`} />
    <ellipse cx="47" cy="38" rx="21" ry="21" fill="none" stroke="#ffe27a" strokeWidth="2.6" opacity="0.85" />
    {/* robe */}
    <path d="M18 100 L22 74 Q28 60 47 58 Q66 60 72 74 L76 100 Z" fill={`url(#${p}rb)`} {...O} />
    <path d="M47 64 L41 100 M47 64 L53 100" stroke="#e8a21f" strokeWidth="3" />
    <path d="M60 62 Q70 66 72 76 L75 100 L66 100 Q66 78 60 62Z" fill="#aab3d4" opacity="0.5" />
    {/* hood */}
    <path d="M27 60 Q24 24 47 20 Q70 24 67 60 Q62 52 60 44 Q56 32 47 32 Q38 32 34 44 Q32 52 27 60Z" fill={`url(#${p}rb)`} {...O} />
    <path d="M58 26 Q67 34 66 54 Q63 47 61 40 Q60 31 58 26Z" fill="#aab3d4" opacity="0.6" />
    <path d="M40 24 Q34 27 31 34" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" />
    {/* face */}
    <path d="M35 45 Q35 33 47 33 Q59 33 59 45 Q59 56 47 57 Q35 56 35 45Z" fill="#f2c09a" {...O} />
    <path d="M37 50 Q40 64 47 67 Q55 64 58 50 Q53 55 47 55 Q41 55 37 50Z" fill="#f6f2e8" {...O} />
    <path d="M42 53 Q47 50 53 53" fill="none" stroke="#c9c2b0" strokeWidth="1.6" strokeLinecap="round" />
    <path d="M41 45 Q43.5 43 46 45 M50 45 Q52.5 43 55 45" fill="none" {...O} strokeWidth="1.8" />
    <path d="M39.5 40 L45 39 M50 39 L55.5 40" stroke="#f6f2e8" strokeWidth="2.2" strokeLinecap="round" />
    <circle cx="47" cy="36.5" r="1.6" fill="#ffc93a" />
    {/* staff */}
    <rect x="75.5" y="26" width="5" height="76" rx="2" fill="#c08a45" {...O} />
    <circle cx="78" cy="70" r="5" fill="#f2c09a" {...O} />
    <SunRays x={78} y={20} r1={9} r2={14} n={10} color="#fff3a0" w={2.4} />
    <circle cx="78" cy="20" r="7.5" fill="#ffd84a" {...O} />
    <circle cx="76" cy="18" r="3" fill="#fffbe0" />
    <Spark x={60} y={12} s={2.6} />
    <Spark x={90} y={40} s={2.2} />
  </g>
);

const WING = "M38 68 C26 60 10 44 5 16 C14 20 22 26 28 32 C22 26 18 18 19 8 C27 16 33 24 37 34 C34 26 34 18 37 12 C42 22 44 34 44 48 Z";
const WING_FEATHERS = "M10 26 Q20 40 32 46 M18 16 Q26 34 36 44 M28 30 Q34 42 40 50";

const dawnGuard: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}wg`} c={["#ffffff", "#bcd9f5"]} />
      <Lin id={`${p}gd`} c={["#ffe680", "#d98317"]} />
      <Rad id={`${p}gl`} c={["#fffbe0", "#ffe27a"]} o={[0.9, 0]} />
    </defs>
    <circle cx="50" cy="42" r="34" fill={`url(#${p}gl)`} />
    {/* wings */}
    {[false, true].map((m) => (
      <g key={String(m)} transform={m ? "translate(100 0) scale(-1 1)" : undefined}>
        <path d={WING} fill={`url(#${p}wg)`} {...O} />
        <path d={WING_FEATHERS} stroke="#8fb7e0" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      </g>
    ))}
    {/* halberd */}
    <rect x="80" y="10" width="4.6" height="92" rx="2" fill="#8a5a30" {...O} />
    <path d="M84 18 Q97 22 95 36 Q90 31 84 32Z" fill="#e3ecf7" {...O} />
    <path d="M80 20 L74 24 L80 28Z" fill="#e3ecf7" {...T} />
    <path d="M82.3 10 L78.5 2 L86 2 Z" fill="#e3ecf7" {...T} />
    {/* body */}
    <path d="M22 100 L25 76 Q30 62 51 60 Q72 62 77 76 L80 100 Z" fill={`url(#${p}gd)`} {...O} />
    <path d="M38 70 Q51 64 64 70 L62 90 Q51 96 40 90Z" fill="#fff3c4" {...T} />
    <SunRays x={51} y={80} r1={5} r2={9} n={8} color="#e8a21f" w={2} />
    <circle cx="51" cy="80" r="4.2" fill="#ffc93a" {...T} />
    <path d="M66 64 Q76 68 77 80 L79 100 L71 100 Q71 80 66 64Z" fill="#b3640f" opacity="0.4" />
    <circle cx="82.3" cy="70" r="5" fill="#e3ecf7" {...O} />
    {/* head */}
    <ellipse cx="51" cy="45" rx="12.5" ry="13" fill="#f2c09a" {...O} />
    <path d="M36.5 47 Q34 23 51 21 Q68 23 65.5 47 L61 50 L61 40 Q51 35 41 40 L41 50Z" fill={`url(#${p}gd)`} {...O} />
    <path d="M44 26 Q40 29 39 35" stroke="#fff6c8" strokeWidth="2.2" fill="none" strokeLinecap="round" />
    <path d="M51 21 Q46 10 56 4 Q54 10 60 10 Q57 16 51 21Z" fill="#4fb0ff" {...O} />
    <Eye x={46.5} y={46} r={2.7} iris="#2a6fd6" />
    <Eye x={56.5} y={46} r={2.7} iris="#2a6fd6" />
    <path d="M43 41.6 L49 42.4 M54 42.4 L60 41.6" stroke={K} strokeWidth="1.8" strokeLinecap="round" />
    <path d="M48 53.5 L55 53.5" {...T} />
    <Spark x={20} y={60} s={2.4} />
    <Spark x={70} y={8} s={2} />
  </g>
);

const FLAME_WING = "M46 62 C30 60 12 50 5 28 C13 32 18 32 22 30 C15 24 12 15 14 6 C21 16 29 21 35 23 C33 16 33 9 37 3 C42 16 47 30 50 46 Z";

const dawnPhoenix: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}fi`} c={["#fff6b0", "#ff6a1f"]} />
      <Lin id={`${p}bd`} c={["#ffd24a", "#f06a12"]} />
      <Rad id={`${p}gl`} c={["#fffbe0", "#ffb021"]} o={[1, 0]} />
    </defs>
    <circle cx="52" cy="44" r="46" fill={`url(#${p}gl)`} opacity="0.95" />
    <SunRays x={52} y={44} r1={30} r2={44} n={16} color="#fff2a8" w={1.6} />
    {/* wings */}
    {[false, true].map((m) => (
      <g key={String(m)} transform={m ? "translate(104 0) scale(-1 1)" : undefined}>
        <path d={FLAME_WING} fill={`url(#${p}fi)`} {...O} />
        <path d="M14 30 Q30 44 44 50 M24 18 Q34 32 44 40" stroke="#ffef9a" strokeWidth="2" fill="none" strokeLinecap="round" />
      </g>
    ))}
    {/* tail flames */}
    <path d="M40 76 C34 86 30 92 26 102 L78 102 C74 92 70 86 64 76Z" fill={`url(#${p}fi)`} {...O} />
    <path d="M44 80 Q42 92 38 102 M52 80 V102 M60 80 Q62 92 66 102" stroke="#fff3a8" strokeWidth="2.2" fill="none" strokeLinecap="round" />
    {/* body */}
    <path d="M52 34 C67 38 70 62 61 80 C57 88 47 88 43 80 C35 64 38 40 52 34Z" fill={`url(#${p}bd)`} {...O} />
    <path d="M46 56 Q52 50 58 56 Q52 54 46 60 Q52 58 58 64" stroke="#fff3a8" strokeWidth="2" fill="none" strokeLinecap="round" />
    <path d="M58 40 Q68 52 62 76 Q66 56 56 42Z" fill="#c9420c" opacity="0.5" />
    {/* crest */}
    <path d="M46 26 C40 16 42 8 47 1 C49 9 53 12 55 18 C57 9 62 4 68 3 C65 10 65 17 62 25Z" fill={`url(#${p}fi)`} {...O} />
    {/* head */}
    <circle cx="55" cy="31" r="11.5" fill={`url(#${p}bd)`} {...O} />
    <path d="M47 26 Q50 22 55 21.5" stroke="#fff6c8" strokeWidth="2.4" fill="none" strokeLinecap="round" />
    <path d="M64 26 L84 33 L65.5 37.5 Z" fill="#ffe680" {...O} />
    <path d="M65.5 35 L80 34.5 L66 38.5Z" fill="#d98317" />
    <GlowEye x={59} y={29} r={2.4} color="#ffffff" />
    <circle cx="59.6" cy="29" r="1.3" fill="#c2410c" />
    <Spark x={20} y={60} s={3} />
    <Spark x={86} y={58} s={3} />
    <Spark x={78} y={10} s={2.4} />
    <Spark x={28} y={8} s={2.2} />
  </g>
);

// ───────────────────────── Легион Пепла ─────────────────────────

const ashBones: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}bn`} c={["#f6f0dd", "#bdb293"]} />
    </defs>
    {/* club */}
    <Limb d="M64 86 L82 36" w={4} color="#8a5730" />
    <path d="M77 22 Q86 18 92 26 L86 46 Q80 48 76 42 Z" fill="#9a6337" {...O} />
    <path d="M82 22 L84 17 M90 30 L95 29 M88 40 L93 42 M79 34 L74 33" {...T} stroke="#cfd6df" strokeWidth="2" />
    <path d="M80 24 Q84 22 87 24" stroke="#c48a55" strokeWidth="2" fill="none" strokeLinecap="round" />
    {/* body: ragged hoodie */}
    <path d="M24 100 L27 78 Q32 64 50 62 Q68 64 72 78 L76 100 Z" fill="#4a4152" {...O} />
    <path d="M62 66 Q71 70 72 82 L74 100 L67 100 Q67 82 62 66Z" fill="#2d2735" />
    <path d="M42 80 Q50 76 58 80 M43 86 Q50 82 57 86 M44 92 Q50 88 56 92" stroke="#e9e2cf" strokeWidth="2.2" fill="none" strokeLinecap="round" />
    <circle cx="66" cy="84" r="5" fill={`url(#${p}bn)`} {...O} />
    {/* skull */}
    <path d="M35 42 Q35 24 50 24 Q65 24 65 42 Q65 50 60 52 L60 58 L40 58 L40 52 Q35 50 35 42Z" fill={`url(#${p}bn)`} {...O} />
    <path d="M58 27 Q65 34 63 48 Q60 40 56 30Z" fill="#a89c7c" opacity="0.55" />
    <path d="M41 29 Q45 26 49 26" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" />
    <path d="M38.5 42 Q39 36 45 36.5 Q49 38 48 43 Q46 47 42 46 Q38.5 45.5 38.5 42Z" fill={K} />
    <path d="M52 43 Q51 37 56 36.5 Q62 36.5 61.5 42 Q61 46 57 46.5 Q52.5 46.5 52 43Z" fill={K} />
    <GlowEye x={44} y={41.5} r={1.8} color="#ff3b1f" />
    <GlowEye x={57} y={41.5} r={1.8} color="#ff3b1f" />
    <path d="M50 46 L48 50.5 L52 50.5Z" fill={K} />
    <path d="M42 53 H58 M45 51 V58 M50 51 V58 M55 51 V58" {...T} />
    <path d="M56 25 L54 30 L57 32" fill="none" {...T} />
    {/* torn scarf */}
    <path d="M34 60 Q50 67 66 60 L67 67 Q50 74 33 67Z" fill="#d1243a" {...O} />
    <path d="M41 62.5 L40 70 M50 64 V71.5 M59 62.5 L60 70" stroke={K} strokeWidth="3" />
    <path d="M36 66 L30 84 L33 82 L34 86 L37 82 L40 85 L41 68Z" fill="#d1243a" {...O} />
    <path d="M33.5 72 L39.5 74 M32 78 L38.5 80" stroke={K} strokeWidth="2.4" />
  </g>
);

const ashImp: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}sk`} c={["#ff6a45", "#b8241f"]} />
      <Rad id={`${p}fb`} c={["#fffbd0", "#ff7a1a"]} o={[1, 0.9]} />
      <Rad id={`${p}fg`} c={["#ffb347", "#ff3d1a"]} o={[0.9, 0]} />
    </defs>
    {/* body */}
    <path d="M32 100 L34 82 Q38 70 50 69 Q62 70 66 82 L68 100 Z" fill={`url(#${p}sk)`} {...O} />
    <path d="M42 84 Q50 80 58 84" stroke="#8a1a1f" strokeWidth="2" fill="none" strokeLinecap="round" />
    {/* tail */}
    <path d="M30 92 Q14 90 16 74 Q17 68 12 66" fill="none" stroke={K} strokeWidth="5" strokeLinecap="round" />
    <path d="M30 92 Q14 90 16 74 Q17 68 12 66" fill="none" stroke="#d8392a" strokeWidth="2.4" strokeLinecap="round" />
    <path d="M12 66 L7 62 L15 60Z" fill="#d8392a" {...T} />
    {/* arm + fireball */}
    <Limb d="M62 76 Q74 70 76 56" w={5.5} color="#e04a30" />
    <circle cx="80" cy="40" r="17" fill={`url(#${p}fg)`} />
    <path d="M71 44 Q70 32 78 26 Q78 31 82 30 Q84 25 88 26 Q86 30 90 34 Q92 46 82 50 Q73 50 71 44Z" fill={`url(#${p}fb)`} {...O} />
    <circle cx="80" cy="41" r="4" fill="#fffbe0" />
    <path d="M70 55 Q74 50 80 54 Q78 58 74 58Z" fill="#e04a30" {...O} />
    {/* ears */}
    <path d="M33 46 L16 40 L32 54Z" fill={`url(#${p}sk)`} {...O} />
    <path d="M66 46 L82 50 L65 54Z" fill={`url(#${p}sk)`} {...O} />
    {/* horns */}
    <path d="M38 34 Q30 22 34 12 Q38 22 45 29Z" fill="#3b2436" {...O} />
    <path d="M58 30 Q62 18 72 14 Q67 24 64 34Z" fill="#3b2436" {...O} />
    {/* head */}
    <ellipse cx="49" cy="49" rx="17" ry="16" fill={`url(#${p}sk)`} {...O} />
    <path d="M38 38 Q43 34 49 34" stroke="#ffb08f" strokeWidth="2.4" fill="none" strokeLinecap="round" />
    <ellipse cx="43" cy="46" rx="4.4" ry="5" fill="#ffe14a" {...T} />
    <ellipse cx="55" cy="46" rx="4.4" ry="5" fill="#ffe14a" {...T} />
    <ellipse cx="44" cy="46.5" rx="1.2" ry="3.4" fill={K} />
    <ellipse cx="56" cy="46.5" rx="1.2" ry="3.4" fill={K} />
    <path d="M38 40 L46 42.5 M60 40 L52 42.5" stroke={K} strokeWidth="2.2" strokeLinecap="round" />
    <path d="M39 55 Q49 66 60 54 Q50 58 39 55Z" fill="#3a0f1a" {...T} />
    <path d="M42 56 L44 60 L46 57 M53 57.4 L55 60.5 L57 56" fill="#fff" stroke="#fff" strokeWidth="0.6" />
  </g>
);

const ashWitch: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}ht`} c={["#7a3aa0", "#3a1650"]} />
      <Rad id={`${p}cg`} c={["#c56bff", "#7a1fd0"]} o={[0.8, 0]} />
    </defs>
    <circle cx="80" cy="44" r="18" fill={`url(#${p}cg)`} />
    {/* shawl */}
    <path d="M20 100 L24 78 Q30 64 48 62 Q66 64 72 78 L76 100 Z" fill="#3c2a4a" {...O} />
    <path d="M28 74 L48 92 L68 74" fill="none" stroke="#e0562b" strokeWidth="2.6" strokeDasharray="4 3" />
    {/* ladle */}
    <Limb d="M58 92 L78 52" w={3.4} color="#6f4a36" />
    <path d="M70 48 Q72 38 80 38 Q90 38 90 48 Q88 56 80 56 Q72 55 70 48Z" fill="#4a4152" {...O} />
    <ellipse cx="80" cy="45" rx="8" ry="3.4" fill="#b54dff" />
    <circle cx="77" cy="44.5" r="1.4" fill="#f0d2ff" />
    <path d="M76 36 Q72 30 77 26 Q82 22 78 16 M84 35 Q88 29 84 24" stroke="#cdb8d8" strokeWidth="3" fill="none" strokeLinecap="round" opacity="0.85" />
    <circle cx="80" cy="12" r="3" fill="#cdb8d8" opacity="0.7" />
    <circle cx="62" cy="86" r="4.6" fill="#b6c4a8" {...O} />
    {/* hair */}
    <path d="M30 40 Q22 60 28 72 Q32 64 34 66 Q34 56 36 50Z M64 40 Q72 58 68 70 Q64 64 62 66 Q63 56 60 50Z" fill="#2a1840" {...O} />
    {/* face */}
    <path d="M35 46 Q35 34 48 34 Q61 34 61 46 Q61 60 48 62 Q35 60 35 46Z" fill="#b6c4a8" {...O} />
    <path d="M56 40 Q62 48 57 58 Q60 48 54 40Z" fill="#8c9c80" />
    <path d="M47 46 Q55 52 52 56 Q49 56 48 53" fill="#9fb092" {...T} />
    <GlowEye x={42} y={46} r={2.2} color="#ff8a2a" />
    <GlowEye x={55} y={45} r={2.2} color="#ff8a2a" />
    <path d="M38 41 L45 43 M58 40 L51 42" stroke={K} strokeWidth="2" strokeLinecap="round" />
    <path d="M42 57 Q48 60 55 56 L53 58" fill="none" {...T} />
    <circle cx="40" cy="53" r="1" fill="#5c6e50" />
    {/* hat */}
    <path d="M24 40 Q48 32 72 40 Q66 44 48 43 Q30 44 24 40Z" fill={`url(#${p}ht)`} {...O} />
    <path d="M34 40 Q38 22 50 12 Q56 6 64 10 Q58 12 58 18 Q60 30 62 40 Q48 37 34 40Z" fill={`url(#${p}ht)`} {...O} />
    <path d="M34.8 36 Q48 33 61.4 36 L62 40 Q48 37 34 40Z" fill="#e0562b" />
    <rect x="45" y="34" width="6" height="5" rx="1" fill="#ffc93a" {...T} />
    <path d="M42 30 Q44 22 50 16" stroke="#9b5ccf" strokeWidth="2" fill="none" strokeLinecap="round" />
    <Spark x={22} y={24} s={2.4} color="#d79bff" />
    <Spark x={88} y={66} s={2} color="#d79bff" />
  </g>
);

const ashGolem: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}rk`} c={["#8a8290", "#4c4552"]} />
      <Rad id={`${p}lv`} c={["#ffb347", "#ff3d1a"]} o={[0.85, 0]} />
    </defs>
    <circle cx="50" cy="48" r="40" fill={`url(#${p}lv)`} opacity="0.55" />
    {/* shoulders */}
    <path d="M4 100 L6 70 Q8 54 26 52 L74 52 Q92 54 94 70 L96 100 Z" fill={`url(#${p}rk)`} {...O} />
    <path d="M6 70 Q8 56 24 54 Q30 64 26 74 Q14 78 6 70Z" fill="#9b94a0" {...T} />
    <path d="M94 70 Q92 56 76 54 Q70 64 74 74 Q86 78 94 70Z" fill="#6f6875" {...T} />
    <path d="M32 62 L68 62 L64 100 L36 100Z" fill="#5c5562" {...T} />
    {/* lava cracks */}
    <g fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 82 L22 76 L20 90 L28 96 M78 80 L84 88 L80 96 M46 70 L52 78 L48 86 L54 94" stroke="#ff5a1a" strokeWidth="3.6" />
      <path d="M14 82 L22 76 L20 90 L28 96 M78 80 L84 88 L80 96 M46 70 L52 78 L48 86 L54 94" stroke="#ffe066" strokeWidth="1.4" />
    </g>
    {/* head */}
    <path d="M34 26 L66 24 L70 50 Q50 60 30 50Z" fill={`url(#${p}rk)`} {...O} />
    <path d="M62 26 L66 24 L70 50 Q66 52 62 53Z" fill="#433c48" />
    <path d="M37 28 L48 27.5" stroke="#aaa2b0" strokeWidth="2.4" strokeLinecap="round" />
    <path d="M32 38 L68 36 L68 41 L32 43Z" fill="#433c48" {...T} />
    <GlowEye x={42} y={43.5} r={2.4} color="#ff7a1a" />
    <GlowEye x={58} y={43} r={2.4} color="#ff7a1a" />
    <path d="M40 51 L45 49 L50 52 L55 49 L60 51" fill="none" stroke="#ff5a1a" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M52 24.5 L49 32 L53 36" fill="none" stroke="#ff7a1a" strokeWidth="2" strokeLinecap="round" />
    <Spark x={18} y={30} s={2} color="#ffb347" />
    <Spark x={84} y={36} s={2.4} color="#ffb347" />
    <circle cx="78" cy="20" r="1.6" fill="#ffb347" />
    <circle cx="24" cy="44" r="1.3" fill="#ffb347" />
  </g>
);

const ashDragon: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}dk`} c={["#6a3d8a", "#25123a"]} />
      <Lin id={`${p}fl`} c={["#fff3a0", "#ff3d1a"]} />
      <Rad id={`${p}gl`} c={["#ff7a2a", "#9b1c4c"]} o={[0.9, 0]} />
    </defs>
    <circle cx="58" cy="44" r="44" fill={`url(#${p}gl)`} />
    {/* neck */}
    <path d="M8 102 Q14 66 36 46 L56 54 Q40 70 40 102Z" fill={`url(#${p}dk)`} {...O} />
    <path d="M22 102 Q28 74 46 56" fill="none" stroke="#c2412c" strokeWidth="6" />
    <path d="M24 92 L34 94 M28 80 L38 82 M34 69 L43 72" stroke={K} strokeWidth="1.6" />
    <path d="M14 76 L6 72 L14 68 M20 62 L12 56 L22 54 M28 50 L22 42 L32 44" fill="#3e2156" {...T} />
    {/* horns */}
    <path d="M40 30 Q24 22 14 6 Q30 14 46 22Z" fill="#e5d7c6" {...O} />
    <path d="M48 26 Q40 14 38 2 Q50 12 56 22Z" fill="#e5d7c6" {...O} />
    {/* ember breath */}
    <path d="M78 46 Q90 38 97 34 Q94 44 98 50 Q92 52 97 60 Q88 58 78 54Z" fill={`url(#${p}fl)`} {...T} />
    <circle cx="94" cy="64" r="1.8" fill="#ffd34d" />
    <circle cx="90" cy="30" r="1.4" fill="#ffd34d" />
    {/* head */}
    <path d="M32 40 Q34 22 52 22 Q64 22 70 30 L86 36 Q90 40 86 44 L72 46 Q60 50 48 56 Q36 56 32 40Z" fill={`url(#${p}dk)`} {...O} />
    <path d="M50 50 Q64 46 80 48 L76 54 Q62 56 52 60 Q46 58 50 50Z" fill="#4a2a63" {...O} />
    <path d="M72 46 L74 50 L76 46.5 M80 47.5 L81 51" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
    <path d="M70 47 Q76 48 79 50" stroke="#ff7a2a" strokeWidth="1.6" fill="none" />
    <path d="M38 30 Q44 24 52 24" stroke="#9a6ac0" strokeWidth="2.4" fill="none" strokeLinecap="round" />
    <path d="M48 32 L62 30 L58 36Z" fill={K} />
    <GlowEye x={56} y={33.5} r={2.6} color="#ffcf3a" />
    <ellipse cx="56.5" cy="33.5" rx="0.8" ry="2.2" fill={K} />
    <circle cx="82" cy="38" r="1.2" fill={K} />
    <path d="M60 22 L64 16 L66 25 M68 28 L74 24 L74 32" fill="#3e2156" {...T} />
    <Spark x={22} y={24} s={2.4} color="#ffb347" />
    <Spark x={70} y={10} s={2.6} color="#ffb347" />
  </g>
);

// ───────────────────────── Дикие ─────────────────────────

const wildThug: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}sk`} c={["#e8ad7c", "#b6764a"]} />
    </defs>
    {/* body */}
    <path d="M20 100 L23 76 Q28 62 50 60 Q72 62 77 76 L80 100 Z" fill={`url(#${p}sk)`} {...O} />
    <path d="M32 100 L33 70 Q50 76 67 70 L68 100Z" fill="#3e8a3a" {...O} />
    <path d="M40 78 H60" stroke="#f4d03f" strokeWidth="3" />
    {/* head */}
    <path d="M42 60 L58 60 L60 52 L40 52Z" fill="#c98a5c" {...O} />
    <ellipse cx="50" cy="40" rx="15" ry="16" fill={`url(#${p}sk)`} {...O} />
    <ellipse cx="35" cy="42" rx="3" ry="4.5" fill="#d99a6a" {...O} />
    <path d="M40 28 Q45 25 51 25" stroke="#fff1dc" strokeWidth="2.4" fill="none" strokeLinecap="round" />
    <path d="M36 50 Q50 64 64 50 Q60 58 50 58 Q40 58 36 50Z" fill="#8a5a3a" opacity="0.55" />
    <path d="M40 37 L57 36.5" stroke={K} strokeWidth="3.4" strokeLinecap="round" />
    <path d="M44 41 L47 41 M53.5 41 L56.5 41" stroke={K} strokeWidth="2.6" strokeLinecap="round" />
    <path d="M48 42 Q53 44 51 49 L47 49Z" fill="#cf8f60" {...T} />
    <path d="M46 44 L55 46" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
    <path d="M44 53 Q50 56 57 52.5" fill="none" {...T} />
    <rect x="50" y="53.2" width="2.4" height="2.4" fill="#fff" stroke={K} strokeWidth="0.8" />
    {/* fists */}
    {[
      [22, 72],
      [76, 66],
    ].map(([x, y]) => (
      <g key={x}>
        <rect x={x - 9} y={y - 8} width="18" height="16" rx="6" fill="#f2f2ea" {...O} />
        <path d={`M${x - 9} ${y - 2} H${x + 9} M${x - 9} ${y + 3} H${x + 9} M${x - 3} ${y - 8} V${y - 2} M${x + 3} ${y - 8} V${y - 2}`} stroke="#b9b9ad" strokeWidth="1.4" />
      </g>
    ))}
  </g>
);

const wildSling: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}hd`} c={["#6fbf4a", "#3a7a2e"]} />
    </defs>
    {/* motion arcs */}
    <path d="M60 14 Q78 2 92 18" fill="none" stroke="#f4ffd6" strokeWidth="2" strokeDasharray="3 3" strokeLinecap="round" />
    <path d="M64 6 Q80 -2 94 10" fill="none" stroke="#f4ffd6" strokeWidth="1.4" strokeLinecap="round" opacity="0.6" />
    {/* hoodie */}
    <path d="M22 100 L25 78 Q30 66 46 64 Q62 66 67 78 L70 100 Z" fill={`url(#${p}hd)`} {...O} />
    <path d="M38 66 Q46 74 54 66" fill="none" {...T} />
    <path d="M36 84 H56 V94 H36Z" fill="#2f6a26" {...T} />
    {/* arm + sling */}
    <Limb d="M62 76 Q72 64 72 42" w={6} color="#e7b088" />
    <path d="M72 36 L80 18 M72 36 L86 24" stroke="#7a4a24" strokeWidth="1.6" strokeLinecap="round" />
    <path d="M78 16 Q88 16 87 25 Q82 23 78 16Z" fill="#8a5a30" {...T} />
    <circle cx="83.5" cy="19" r="3" fill="#a7a3a0" {...T} />
    <circle cx="72" cy="39" r="4.6" fill="#e7b088" {...O} />
    {/* head */}
    <ellipse cx="45" cy="46" rx="14" ry="14" fill="#e7b088" {...O} />
    <path d="M53 50 Q57 56 50 59 Q56 59 57.5 50Z" fill="#c98e66" />
    <ellipse cx="31" cy="47" rx="2.6" ry="3.8" fill="#e7b088" {...O} />
    {/* backwards cap */}
    <path d="M31 42 Q30 28 45 27 Q60 28 59 42 Q45 36 31 42Z" fill="#e8742a" {...O} />
    <path d="M32 40 Q24 40 22 36 Q26 33 33 35" fill="#c2561a" {...O} />
    <path d="M38 31 Q42 29 46 29" stroke="#ffb27a" strokeWidth="2" fill="none" strokeLinecap="round" />
    <path d="M45 27.5 V31" {...T} />
    <path d="M56 38 L59 33 L58 40 M53 37 L55 33" fill="none" stroke="#6b3a1a" strokeWidth="2" strokeLinecap="round" />
    <Eye x={41} y={47} r={2.8} iris="#6b3a1a" />
    <Eye x={51.5} y={46.5} r={2.8} iris="#6b3a1a" />
    <path d="M37.5 42 L44 43 M49 42.5 L55 41" stroke={K} strokeWidth="1.8" strokeLinecap="round" />
    <path d="M41 53.5 Q46 58 52 53" fill="#7a2a2a" {...T} />
    <rect x="44.6" y="53.6" width="2" height="2" fill="#fff" />
    <g fill="#b9683a">
      <circle cx="38" cy="51" r="0.8" />
      <circle cx="40" cy="52.3" r="0.8" />
      <circle cx="54" cy="51" r="0.8" />
      <circle cx="56" cy="52.3" r="0.8" />
    </g>
  </g>
);

const wildTroll: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}sk`} c={["#86c060", "#3f7a3a"]} />
      <Lin id={`${p}dr`} c={["#e0412e", "#9a1f1f"]} />
    </defs>
    {/* shoulders */}
    <path d="M10 100 L13 72 Q20 56 50 54 Q80 56 87 72 L90 100 Z" fill={`url(#${p}sk)`} {...O} />
    <path d="M14 66 Q20 58 28 58" stroke="#a8d884" strokeWidth="2.4" fill="none" strokeLinecap="round" />
    {/* ears */}
    <path d="M30 38 L12 30 Q16 44 30 48Z" fill="#6aa84f" {...O} />
    <path d="M70 38 L88 30 Q84 44 70 48Z" fill="#4f8f42" {...O} />
    {/* head */}
    <ellipse cx="50" cy="40" rx="21" ry="18" fill={`url(#${p}sk)`} {...O} />
    <path d="M30 32 Q30 18 44 19 Q46 13 54 16 Q62 14 66 22 Q73 24 71 34 Q64 26 50 26 Q36 26 30 32Z" fill="#2f6a2a" {...O} />
    <circle cx="58" cy="17" r="2.4" fill="#ffe14a" {...T} />
    <path d="M38 23 Q44 21 50 22" stroke="#5aa04a" strokeWidth="2" fill="none" strokeLinecap="round" />
    <path d="M33 44 L38 46 M33 48 L38 49" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
    <path d="M63 44 L68 43 M63 48 L68 47.5" stroke="#4fb0ff" strokeWidth="2" strokeLinecap="round" />
    <Eye x={43} y={36} r={2.5} iris="#7a3a1a" />
    <Eye x={57} y={36} r={2.5} iris="#7a3a1a" />
    <path d="M39 31.5 L46 33 M54 33 L61 31.5" stroke={K} strokeWidth="2.4" strokeLinecap="round" />
    <path d="M45 38 Q50 36 55 38 Q58 46 50 47 Q42 46 45 38Z" fill="#5c9a46" {...T} />
    <path d="M38 50 Q50 57 62 50" fill="none" {...O} />
    <path d="M40 51.5 L40 45 L43 52.5Z M60 51.5 L60 45 L57 52.5Z" fill="#fff6dc" {...T} />
    {/* drum */}
    <path d="M18 76 L18 98 Q50 106 82 98 L82 76Z" fill={`url(#${p}dr)`} {...O} />
    <ellipse cx="50" cy="76" rx="32" ry="7" fill="#f6ecd2" {...O} />
    <path d="M18 84 L34 100 L50 84 L66 100 L82 84" fill="none" stroke="#f6ecd2" strokeWidth="2" strokeLinejoin="round" />
    <ellipse cx="44" cy="75" rx="12" ry="2.4" fill="#fff" opacity="0.7" />
    {/* sticks */}
    <Limb d="M24 62 L42 74" w={2.4} color="#d8b27a" />
    <Limb d="M78 60 L62 74" w={2.4} color="#d8b27a" />
    <circle cx="22" cy="62" r="5" fill="#6aa84f" {...O} />
    <circle cx="79" cy="60" r="5" fill="#5c9a46" {...O} />
  </g>
);

const wildOgre: Draw = (p) => (
  <g>
    <defs>
      <Lin id={`${p}sk`} c={["#c9b766", "#7f7a3a"]} />
    </defs>
    {/* goalpost club over shoulder */}
    <g transform="rotate(16 70 60)">
      <rect x="58" y="10" width="28" height="22" fill="#eef2f6" opacity="0.3" />
      <path d="M58 15.5 H86 M58 21 H86 M58 26.5 H86 M65 10 V32 M72 10 V32 M79 10 V32" stroke="#eef2f6" strokeWidth="1.1" />
      <path d="M58 34 L58 10 L86 10 L86 34" fill="none" stroke={K} strokeWidth="6.4" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M58 34 L58 10 L86 10 L86 34" fill="none" stroke="#fff" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M72 32 L72 86" stroke={K} strokeWidth="7.4" strokeLinecap="round" />
      <path d="M72 32 L72 86" stroke="#fff" strokeWidth="3.6" strokeLinecap="round" />
      <path d="M70 60 H74 M70 66 H74" stroke="#d1243a" strokeWidth="3" />
    </g>
    {/* shoulders */}
    <path d="M2 100 L4 74 Q10 54 46 52 Q82 54 88 74 L92 100 Z" fill={`url(#${p}sk)`} {...O} />
    <path d="M30 60 Q46 70 62 60 L64 100 L28 100Z" fill="#7a4a2a" {...T} />
    <path d="M30 60 L46 100 M62 60 L46 100" stroke="#5a3418" strokeWidth="1.6" />
    <circle cx="66" cy="72" r="8" fill="#b8a55a" {...O} />
    {/* head */}
    <ellipse cx="44" cy="38" rx="20" ry="19" fill={`url(#${p}sk)`} {...O} />
    <ellipse cx="24" cy="40" rx="3.4" ry="5" fill="#b8a55a" {...O} />
    <path d="M44 19 Q40 12 46 8 Q46 13 50 13 Q48 17 44 19Z" fill="#4a2e1a" {...O} />
    <path d="M32 26 Q38 21 45 21" stroke="#e6dc9a" strokeWidth="2.4" fill="none" strokeLinecap="round" />
    <path d="M30 33 Q42 27 58 32 L57 36 Q44 33 31 37Z" fill="#8a8040" {...T} />
    <circle cx="39" cy="38.5" r="1.8" fill={K} />
    <circle cx="51" cy="38.5" r="1.8" fill={K} />
    <circle cx="39.6" cy="37.9" r="0.6" fill="#fff" />
    <circle cx="51.6" cy="37.9" r="0.6" fill="#fff" />
    <path d="M44 39 Q52 44 47 48 Q43 48 42 45" fill="#b0a052" {...T} />
    <path d="M32 50 Q44 58 58 49 Q56 54 45 55 Q35 55 32 50Z" fill="#3a2a1a" {...T} />
    <path d="M38 52 L39 46 L42 53Z" fill="#fff6dc" {...T} />
    <path d="M54 46 Q62 50 56 54" stroke="#6b6232" strokeWidth="1.6" fill="none" />
  </g>
);

const fallback: Draw = () => (
  <g fill="#3a3f52" {...O}>
    <path d="M22 100 L25 76 Q30 62 50 60 Q70 62 75 76 L78 100 Z" />
    <circle cx="50" cy="42" r="15" />
    <path d="M45 38 Q45 32 50 32 Q55 32 55 37 Q55 40 50 42 V45" fill="none" stroke="#c9cbd6" strokeWidth="3" />
    <circle cx="50" cy="50" r="1.8" fill="#c9cbd6" stroke="none" />
  </g>
);

const CREATURES: Record<string, [Faction, Draw]> = {
  dawn_banner: ["dawn", dawnBanner],
  dawn_spear: ["dawn", dawnSpear],
  dawn_priest: ["dawn", dawnPriest],
  dawn_guard: ["dawn", dawnGuard],
  dawn_phoenix: ["dawn", dawnPhoenix],
  ash_bones: ["ash", ashBones],
  ash_imp: ["ash", ashImp],
  ash_witch: ["ash", ashWitch],
  ash_golem: ["ash", ashGolem],
  ash_dragon: ["ash", ashDragon],
  wild_thug: ["wild", wildThug],
  wild_sling: ["wild", wildSling],
  wild_troll: ["wild", wildTroll],
  wild_ogre: ["wild", wildOgre],
};

export const CREATURE_CODES: readonly string[] = Object.keys(CREATURES);

/** Portrait of a creature (bust) on a soft faction-coloured glow. */
export function CreatureArt({ unit, size = 64, className }: { unit: string; size?: number; className?: string }) {
  const p = useId().replace(/:/g, "");
  const [faction, draw] = CREATURES[unit] ?? ["none", fallback];
  const [c0, c1, c2] = BG[faction];
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`${p}bg`} cx="50%" cy="40%" r="70%">
          <stop offset="0" stopColor={c0} />
          <stop offset="0.45" stopColor={c1} />
          <stop offset="1" stopColor={c2} />
        </radialGradient>
      </defs>
      <rect width="100" height="100" fill={`url(#${p}bg)`} />
      {draw(p)}
    </svg>
  );
}
