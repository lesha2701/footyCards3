import { useId } from "react";

import type { MyPlayerAppearance } from "@/api/myPlayer";
import { EYE_COLORS, HAIR_COLORS, KIT_COLORS, SKIN_TONES } from "@/lib/myPlayer";

const LIGHT_KITS = new Set([4, 8]);

interface Props {
  appearance: MyPlayerAppearance;
  number?: number;
  className?: string;
  /** Stadium-glow backdrop (off where the avatar sits on its own surface). */
  background?: boolean;
  /** Equipped cosmetics (shop codes): headband | earring | chain | goggles |
   * captain | headphones | crown. */
  accessory?: string | null;
  /** bg_sunset | bg_neon | bg_gold | bg_night | bg_galaxy | bg_champions;
   * anything else = the default stadium. */
  backdrop?: string | null;
}

// Radial backdrop colours (centre, middle, edge) per background code.
const BACKDROPS: Record<string, [string, string, string]> = {
  default: ["#2b3a4d", "#16202c", "#0c1219"],
  bg_gold: ["#ffe8a3", "#c48a1c", "#4a3006"],
  bg_neon: ["#2a0f4d", "#120a2e", "#05030f"],
  bg_night: ["#27496d", "#0b1a2e", "#03070d"],
  bg_galaxy: ["#5b21b6", "#1e1b4b", "#05030f"],
  bg_champions: ["#1d4ed8", "#0c1a4a", "#020617"],
};

// Fixed star field for «Галактика» (x, y, r).
const GALAXY_STARS = [
  [14, 20, 1.2], [38, 52, 0.8], [62, 14, 1], [88, 34, 0.7], [120, 12, 1.3], [150, 40, 0.8], [178, 22, 1.1],
  [190, 70, 0.7], [24, 92, 0.9], [170, 104, 1], [8, 140, 0.8], [192, 150, 1.2], [44, 128, 0.6], [150, 132, 0.7],
  [100, 6, 0.9], [76, 70, 0.6], [132, 84, 0.8], [30, 172, 0.7], [182, 186, 0.9], [12, 60, 0.7],
];

function starPath(cx: number, cy: number, r: number): string {
  const points = Array.from({ length: 10 }, (_, i) => {
    const angle = (Math.PI / 5) * i - Math.PI / 2;
    const radius = i % 2 === 0 ? r : r * 0.45;
    return `${(cx + radius * Math.cos(angle)).toFixed(1)} ${(cy + radius * Math.sin(angle)).toFixed(1)}`;
  });
  return `M${points.join(" L")}Z`;
}

function shade(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16);
  const channel = (c: number) =>
    Math.max(0, Math.min(255, Math.round(amount >= 0 ? c + (255 - c) * amount : c * (1 + amount))));
  return `#${[n >> 16, (n >> 8) & 255, n & 255].map((c) => channel(c).toString(16).padStart(2, "0")).join("")}`;
}

// Head outline (also the stubble clip): 60..140 wide, crown at y=46.
const HEAD = "M60 96 Q60 46 100 46 Q140 46 140 96 L140 110 Q138 146 112 156 Q100 160 88 156 Q62 146 60 110Z";
const JAW = "M62 110 Q66 152 100 158 Q134 152 138 110 Q128 140 100 140 Q72 140 62 110Z";
const LIP = "M84 128 Q100 116 116 128 Q112 132 100 129 Q88 132 84 128Z";
const MOUSTACHE = "M84 126 Q100 118 116 126 Q100 124 84 126Z";

/** The constructor's footballer: a shaded head-and-shoulders SVG drawn from
 * option indexes (no uploaded photos — nothing to moderate). Option counts
 * must match backend my_player_service.APPEARANCE_OPTIONS. */
export default function PlayerAvatar({ appearance: a, number, className, background = true, accessory, backdrop }: Props) {
  const id = useId().replace(/:/g, "");
  const skin = SKIN_TONES[a.skin] ?? SKIN_TONES[0];
  const hair = HAIR_COLORS[a.hair_color] ?? HAIR_COLORS[0];
  const kit = KIT_COLORS[a.kit] ?? KIT_COLORS[0];
  const eye = EYE_COLORS[a.eye_color ?? 0] ?? EYE_COLORS[0];
  const light = LIGHT_KITS.has(a.kit);
  const trim = light ? "#1d4ed8" : "#ffffff";
  const [sk1, sk2, sk3] = [shade(skin, 0.18), shade(skin, -0.22), shade(skin, -0.38)];
  const [h1, h2] = [shade(hair, 0.28), shade(hair, -0.3)];
  const hairFill = `url(#hg${id})`;
  const strand = (d: string) => (
    <path key={d} d={d} stroke={h1} strokeWidth="1.6" fill="none" opacity="0.55" strokeLinecap="round" />
  );
  const stubble = (d: string, key: string) => (
    <g key={key}>
      <path d={d} fill={hair} opacity="0.26" />
      <path d={d} fill={`url(#dots${id})`} opacity="0.4" />
    </g>
  );

  const hairBack: Record<number, JSX.Element> = {
    4: <path d="M56 98 Q50 150 74 176 L126 176 Q150 150 144 98 Q140 60 100 56 Q60 60 56 98Z" fill={hairFill} />,
    6: (
      <>
        <circle cx="100" cy="88" r="58" fill={hairFill} />
        <circle cx="100" cy="88" r="58" fill={`url(#curl${id})`} opacity="0.5" />
      </>
    ),
    9: (
      <g stroke={hair} strokeWidth="8" strokeLinecap="round">
        {[60, 70, 80, 120, 130, 140].map((x, i) => (
          <path key={x} d={`M${x} 70 Q${x + (i < 3 ? -6 : 6)} 120 ${x + (i < 3 ? -2 : 2)} ${150 + (i % 3) * 8}`} fill="none" />
        ))}
      </g>
    ),
    10: <circle cx="100" cy="34" r="14" fill={hairFill} />,
  };

  const hairFront: Record<number, JSX.Element | null> = {
    0: (
      <>
        <path d="M60 96 Q60 50 100 48 Q140 50 140 96 Q132 70 100 68 Q68 70 60 96Z" fill={hair} opacity="0.7" />
        <path d="M60 96 Q60 50 100 48 Q140 50 140 96 Q132 70 100 68 Q68 70 60 96Z" fill={`url(#dots${id})`} opacity="0.5" />
      </>
    ),
    1: (
      <>
        <path d="M57 100 Q52 44 100 40 Q148 44 143 100 Q138 74 120 68 Q100 76 80 68 Q62 74 57 100Z" fill={hairFill} />
        {strand("M72 60 Q90 52 110 56")}
        {strand("M84 66 Q104 58 128 66")}
      </>
    ),
    2: (
      <>
        <path d="M57 100 Q52 46 92 40 Q104 18 132 30 Q122 34 126 40 Q148 50 143 100 Q138 74 120 68 Q100 76 80 68 Q62 74 57 100Z" fill={hairFill} />
        {strand("M96 40 Q110 26 128 30")}
        {strand("M74 60 Q94 48 120 52")}
      </>
    ),
    3: (
      <>
        {[[66, 66], [78, 52], [92, 44], [108, 42], [122, 48], [134, 60], [60, 82], [140, 82], [86, 58], [114, 56]].map(([x, y]) => (
          <g key={`${x}-${y}`}>
            <circle cx={x} cy={y} r="13" fill={hairFill} />
            <circle cx={x - 3} cy={y - 4} r="4" fill={h1} opacity="0.35" />
          </g>
        ))}
      </>
    ),
    4: (
      <>
        <path d="M55 108 Q50 40 100 38 Q150 40 145 108 Q138 70 100 66 Q62 70 55 108Z" fill={hairFill} />
        {strand("M70 58 Q96 46 126 56")}
        {strand("M62 84 Q66 64 84 58")}
      </>
    ),
    5: (
      <>
        <path d="M62 96 Q60 58 100 54 Q140 58 138 96 Q130 72 100 70 Q70 72 62 96Z" fill={hair} opacity="0.35" />
        <path d="M88 72 Q84 22 100 10 Q116 22 112 72Z" fill={hairFill} />
        {strand("M100 14 L100 66")}
      </>
    ),
    6: <path d="M58 100 Q58 66 100 64 Q142 66 142 100 Q132 80 100 78 Q68 80 58 100Z" fill={hairFill} />,
    7: <ellipse cx="88" cy="58" rx="16" ry="7" fill="#fff" opacity="0.16" />,
    // 8 — андеркат: buzzed sides, volume on top swept back.
    8: (
      <>
        <path d="M60 98 Q60 60 74 54 L74 80 Q66 84 60 98Z" fill={hair} opacity="0.55" />
        <path d="M140 98 Q140 60 126 54 L126 80 Q134 84 140 98Z" fill={hair} opacity="0.55" />
        <path d="M68 78 Q62 38 102 34 Q144 36 134 74 Q124 58 104 60 Q84 60 68 78Z" fill={hairFill} />
        {strand("M78 56 Q100 40 128 50")}
        {strand("M84 64 Q104 52 126 60")}
      </>
    ),
    // 9 — дреды (the long locks are in hairBack).
    9: (
      <>
        <path d="M56 100 Q52 44 100 40 Q148 44 144 100 Q138 70 100 66 Q62 70 56 100Z" fill={hairFill} />
        <g stroke={h2} strokeWidth="2" opacity="0.5">
          {[70, 84, 100, 116, 130].map((x) => <path key={x} d={`M${x} 46 Q${x - 2} 58 ${x - 6} 68`} fill="none" />)}
        </g>
      </>
    ),
    // 10 — пучок: slicked back, bun in hairBack.
    10: (
      <>
        <path d="M58 98 Q56 46 100 42 Q144 46 142 98 Q136 66 100 62 Q64 66 58 98Z" fill={hairFill} />
        {strand("M72 60 Q100 44 128 60")}
        {strand("M80 52 Q100 42 120 52")}
      </>
    ),
    // 11 — зачёс назад.
    11: (
      <>
        <path d="M58 96 Q56 42 100 40 Q144 42 142 96 Q138 62 100 58 Q62 62 58 96Z" fill={hairFill} />
        {strand("M66 70 Q90 50 126 48")}
        {strand("M72 60 Q100 44 134 58")}
        {strand("M64 84 Q78 62 100 56")}
      </>
    ),
    // 12 — боковой пробор.
    12: (
      <>
        <path d="M57 100 Q52 46 100 42 Q148 46 143 100 Q140 72 128 64 Q100 70 76 62 Q62 72 57 100Z" fill={hairFill} />
        <path d="M82 44 Q78 54 76 62" stroke={skin} strokeWidth="2" fill="none" opacity="0.7" />
        {strand("M86 52 Q108 46 132 58")}
      </>
    ),
    // 13 — косички (cornrows).
    13: (
      <>
        <path d="M60 96 Q60 50 100 48 Q140 50 140 96 Q132 70 100 68 Q68 70 60 96Z" fill={hair} opacity="0.45" />
        <g stroke={hairFill} strokeWidth="6" strokeLinecap="round" strokeDasharray="4 2.5" fill="none">
          {[68, 82, 100, 118, 132].map((x) => <path key={x} d={`M${x} 70 Q${x + (x - 100) * 0.1} 52 ${x + (x - 100) * 0.25} 46`} />)}
        </g>
      </>
    ),
  };

  const beard: Record<number, JSX.Element | null> = {
    0: null,
    // Stubble covers the jaw AND the upper lip (moustache area).
    1: (
      <>
        {stubble(JAW, "jaw")}
        {stubble(LIP, "lip")}
      </>
    ),
    2: (
      <>
        <path d="M88 136 Q100 162 112 136 Q100 142 88 136Z" fill={hairFill} />
        <path d={MOUSTACHE} fill={hair} stroke={hair} strokeWidth="3" strokeLinejoin="round" />
      </>
    ),
    3: (
      <>
        <path d="M60 104 Q60 156 100 164 Q140 156 140 104 Q136 134 116 136 Q100 128 84 136 Q64 134 60 104Z" fill={hairFill} />
        <path d={MOUSTACHE} fill={hair} stroke={hair} strokeWidth="3" strokeLinejoin="round" />
        {strand("M76 142 Q90 154 100 154")}
      </>
    ),
    4: <path d="M82 127 Q100 116 118 127 Q108 124 100 126 Q92 124 82 127Z" fill={hair} stroke={hair} strokeWidth="3.5" strokeLinejoin="round" />,
  };

  const pattern: Record<number, JSX.Element | null> = {
    0: null,
    1: <>{[44, 74, 104, 134, 164].map((x) => <rect key={x} x={x} y="160" width="14" height="80" fill={trim} opacity="0.85" />)}</>,
    2: <>{[192, 216].map((y) => <rect key={y} x="0" y={y} width="200" height="12" fill={trim} opacity="0.85" />)}</>,
    3: <path d="M40 166 L62 166 L176 240 L148 240Z" fill={trim} opacity="0.85" />,
  };

  return (
    <svg viewBox="0 0 200 240" className={className} role="img" aria-label="Аватар игрока" preserveAspectRatio="xMidYMax slice">
      <defs>
        <radialGradient id={`bg${id}`} cx="50%" cy="30%" r="80%">
          {(BACKDROPS[backdrop ?? ""] ?? BACKDROPS.default).map((color, i) => (
            <stop key={i} offset={[0, 0.6, 1][i]} stopColor={color} />
          ))}
        </radialGradient>
        <linearGradient id={`crown${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff3b0" />
          <stop offset="0.5" stopColor="#f5c542" />
          <stop offset="1" stopColor="#a8740f" />
        </linearGradient>
        <linearGradient id={`sunset${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ff9a3d" />
          <stop offset="0.45" stopColor="#d64a6b" />
          <stop offset="1" stopColor="#2a1446" />
        </linearGradient>
        <radialGradient id={`skin${id}`} cx="42%" cy="38%" r="70%">
          <stop offset="0" stopColor={sk1} />
          <stop offset="0.65" stopColor={skin} />
          <stop offset="1" stopColor={sk2} />
        </radialGradient>
        <linearGradient id={`neck${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={sk3} />
          <stop offset="0.55" stopColor={sk2} />
          <stop offset="1" stopColor={skin} />
        </linearGradient>
        <linearGradient id={`hg${id}`} x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0" stopColor={h1} />
          <stop offset="0.5" stopColor={hair} />
          <stop offset="1" stopColor={h2} />
        </linearGradient>
        <linearGradient id={`kit${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={shade(kit, 0.22)} />
          <stop offset="0.55" stopColor={kit} />
          <stop offset="1" stopColor={shade(kit, -0.35)} />
        </linearGradient>
        <linearGradient id={`fold${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.35" />
        </linearGradient>
        <pattern id={`dots${id}`} width="3" height="3" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="0.7" fill="#000" opacity="0.5" />
        </pattern>
        <pattern id={`curl${id}`} width="10" height="10" patternUnits="userSpaceOnUse">
          <circle cx="5" cy="5" r="4" fill="none" stroke={h1} strokeWidth="1.2" />
        </pattern>
        <clipPath id={`torso${id}`}>
          <path d="M8 240 Q10 186 52 172 L80 162 Q100 176 120 162 L148 172 Q190 186 192 240Z" />
        </clipPath>
      </defs>

      {background && (
        <>
          <rect width="200" height="240" fill={backdrop === "bg_sunset" ? `url(#sunset${id})` : `url(#bg${id})`} />
          {backdrop === "bg_sunset" && <circle cx="150" cy="70" r="30" fill="#ffd27a" opacity="0.55" />}
          {backdrop === "bg_neon" && (
            <>
              <circle cx="30" cy="40" r="60" fill="#22d3ee" opacity="0.18" />
              <circle cx="175" cy="70" r="55" fill="#e879f9" opacity="0.2" />
              <g stroke="#a78bfa" strokeOpacity="0.25" strokeWidth="1">
                {[150, 170, 190, 210, 230].map((y) => <path key={y} d={`M0 ${y} H200`} />)}
                {[0, 40, 80, 120, 160, 200].map((x) => <path key={x} d={`M100 140 L${x} 240`} />)}
              </g>
            </>
          )}
          {backdrop === "bg_night" && (
            <>
              <path d="M0 0 L40 0 L120 240 L70 240Z" fill="#e0f2fe" opacity="0.1" />
              <path d="M200 0 L160 0 L80 240 L130 240Z" fill="#e0f2fe" opacity="0.1" />
              {[10, 24, 176, 190].map((x) => <circle key={x} cx={x} cy="10" r="3.5" fill="#f8fafc" opacity="0.85" />)}
              <path d="M0 190 Q100 170 200 190 L200 240 L0 240Z" fill="#14532d" opacity="0.55" />
            </>
          )}
          {backdrop === "bg_galaxy" && (
            <>
              <ellipse cx="50" cy="60" rx="70" ry="34" fill="#ec4899" opacity="0.16" transform="rotate(-20 50 60)" />
              <ellipse cx="160" cy="110" rx="60" ry="26" fill="#22d3ee" opacity="0.14" transform="rotate(25 160 110)" />
              {GALAXY_STARS.map(([x, y, r]) => <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill="#fff" opacity="0.85" />)}
            </>
          )}
          {backdrop === "bg_champions" && (
            <g fill="#f8fafc" opacity="0.28">
              {Array.from({ length: 8 }, (_, i) => {
                const angle = (Math.PI * 2 * i) / 8 - Math.PI / 2;
                return <path key={i} d={starPath(100 + 64 * Math.cos(angle), 84 + 52 * Math.sin(angle), 10)} />;
              })}
            </g>
          )}
          <g opacity={backdrop === "bg_gold" ? 0.22 : 0.08} fill="#fff">
            <path d="M30 0 L60 0 L100 240 L90 240Z" />
            <path d="M150 0 L175 0 L115 240 L106 240Z" />
          </g>
        </>
      )}
      {hairBack[a.hair]}

      {/* torso + kit */}
      <g clipPath={`url(#torso${id})`}>
        <rect x="0" y="150" width="200" height="90" fill={`url(#kit${id})`} />
        {pattern[a.kit_pattern]}
        <path d="M8 240 Q14 196 46 182 L54 240Z" fill="#000" opacity="0.18" />
        <path d="M192 240 Q186 196 154 182 L146 240Z" fill="#000" opacity="0.22" />
        <path d="M46 182 Q52 214 48 240" stroke="#000" strokeOpacity="0.25" strokeWidth="2" fill="none" />
        <path d="M154 182 Q148 214 152 240" stroke="#000" strokeOpacity="0.25" strokeWidth="2" fill="none" />
        <rect x="0" y="150" width="200" height="90" fill={`url(#fold${id})`} />
      </g>
      {accessory === "captain" && (
        <g clipPath={`url(#torso${id})`}>
          <g transform="rotate(-10 30 210)">
            <rect x="10" y="202" width="40" height="15" rx="2" fill="#facc15" />
            <text x="30" y="214" textAnchor="middle" fontSize="12" fontWeight="900" fontFamily="system-ui, sans-serif" fill="#18181b">C</text>
          </g>
        </g>
      )}
      <path d="M80 162 Q100 190 120 162" fill="none" stroke={trim} strokeWidth="5" strokeLinecap="round" />
      <path d="M80 162 Q100 186 120 162" fill="none" stroke="#000" strokeOpacity="0.25" strokeWidth="1.5" />
      <g transform="translate(58 192)">
        <path d="M0 0 h14 v8 q0 8 -7 11 q-7 -3 -7 -11z" fill={trim} opacity="0.9" />
        <circle cx="7" cy="8" r="3" fill={kit} />
      </g>
      {number != null && (
        <text
          x="124" y="222" textAnchor="middle" fontSize="30" fontWeight="900" fontFamily="system-ui, sans-serif"
          fill={light ? "#18181b" : "#fff"} stroke={light ? "#fff" : "#000"} strokeOpacity="0.25" strokeWidth="2" paintOrder="stroke"
        >
          {number}
        </text>
      )}

      {/* neck, ears, head */}
      <path d="M80 126 L80 166 Q100 182 120 166 L120 126Z" fill={`url(#neck${id})`} />
      {accessory === "chain" && (
        <>
          <path d="M80 150 Q100 176 120 150" fill="none" stroke="#f5c542" strokeWidth="2.6" strokeDasharray="3 1.5" />
          <circle cx="100" cy="164" r="3.4" fill="#f5c542" stroke="#9a7212" strokeWidth="0.8" />
        </>
      )}
      <ellipse cx="58" cy="104" rx="9" ry="13" fill={skin} />
      <ellipse cx="59" cy="104" rx="4" ry="7" fill={sk2} opacity="0.6" />
      <ellipse cx="142" cy="104" rx="9" ry="13" fill={skin} />
      <ellipse cx="141" cy="104" rx="4" ry="7" fill={sk2} opacity="0.6" />
      <path d={HEAD} fill={`url(#skin${id})`} />
      <path d="M136 80 Q142 110 132 138" stroke="#fff" strokeOpacity="0.25" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      <ellipse cx="78" cy="122" rx="9" ry="5" fill="#e0715d" opacity="0.14" />
      <ellipse cx="122" cy="122" rx="9" ry="5" fill="#e0715d" opacity="0.14" />

      {beard[a.beard]}

      {/* brows + eyes */}
      <path d="M70 86 Q80 78 92 84" stroke={h2} strokeWidth="4.5" fill="none" strokeLinecap="round" />
      <path d="M108 84 Q120 78 130 86" stroke={h2} strokeWidth="4.5" fill="none" strokeLinecap="round" />
      {[[81, 82], [119, 118]].map(([white, iris]) => (
        <g key={white}>
          <ellipse cx={white} cy="98" rx="8" ry="5.5" fill="#fff" />
          <circle cx={iris} cy="98" r="4.2" fill={eye} />
          <circle cx={iris} cy="98" r="2.2" fill="#0d0d0d" />
          <circle cx={iris + 1.5} cy="96.5" r="1.2" fill="#fff" />
          <path d={`M${white - 9} 95 Q${white} 89 ${white + 9} 95`} stroke={sk3} strokeWidth="1.8" fill="none" />
        </g>
      ))}

      {/* nose + mouth */}
      <path d="M100 100 Q96 116 92 120 Q100 124 108 120 Q104 116 100 100" fill={sk2} opacity="0.35" />
      <path d="M93 121 Q96 124 99 122 M101 122 Q104 124 107 121" stroke={sk3} strokeWidth="1.6" fill="none" strokeLinecap="round" />
      {a.beard !== 3 && (
        <path d="M88 134 Q100 141 112 134 Q100 137 88 134Z" fill="#9b4a3a" stroke="#7a3428" strokeWidth="1.5" strokeLinejoin="round" />
      )}

      {hairFront[a.hair] ?? null}

      {accessory === "earring" && (
        <>
          <circle cx="57" cy="118" r="3.2" fill="#f5c542" stroke="#9a7212" strokeWidth="0.8" />
          <circle cx="56" cy="117" r="1" fill="#fff" opacity="0.8" />
        </>
      )}
      {accessory === "goggles" && (
        <>
          <path d="M58 96 L72 96 M128 96 L142 96" stroke="#18181b" strokeWidth="4" />
          {[81, 119].map((x) => (
            <g key={x}>
              <ellipse cx={x} cy="98" rx="12" ry="9" fill="#f97316" opacity="0.45" stroke="#18181b" strokeWidth="3" />
              <path d={`M${x - 7} 94 Q${x - 2} 91 ${x + 3} 93`} stroke="#fff" strokeWidth="1.5" opacity="0.7" fill="none" />
            </g>
          ))}
          <path d="M93 97 Q100 93 107 97" stroke="#18181b" strokeWidth="3" fill="none" />
        </>
      )}
      {accessory === "headphones" && (
        <>
          <path d="M74 160 Q100 192 126 160" fill="none" stroke="#18181b" strokeWidth="6" strokeLinecap="round" />
          {[72, 128].map((x) => (
            <g key={x}>
              <ellipse cx={x} cy="158" rx="10" ry="13" fill="#18181b" />
              <ellipse cx={x} cy="158" rx="5.5" ry="8" fill="#ef4444" />
            </g>
          ))}
        </>
      )}
      {accessory === "crown" && (
        <>
          <path d="M68 52 L74 20 L88 38 L100 12 L112 38 L126 20 L132 52Z" fill={`url(#crown${id})`} stroke="#8a5d08" strokeWidth="1.5" strokeLinejoin="round" />
          <rect x="67" y="48" width="66" height="9" rx="2" fill={`url(#crown${id})`} stroke="#8a5d08" strokeWidth="1.5" />
          {([[84, "#ef4444"], [100, "#22d3ee"], [116, "#22c55e"]] as const).map(([x, color]) => (
            <circle key={x} cx={x} cy="52" r="3" fill={color} />
          ))}
          <circle cx="100" cy="14" r="3" fill="#fff" opacity="0.9" />
        </>
      )}
      {accessory === "headband" && (
        <>
          <path d="M59 80 Q100 62 141 80 L141 88 Q100 70 59 88Z" fill={trim === "#ffffff" ? "#f4f4f5" : trim} />
          <path d="M59 84 Q100 66 141 84" stroke={kit} strokeWidth="2" fill="none" />
        </>
      )}
    </svg>
  );
}
