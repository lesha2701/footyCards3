import { useId } from "react";

import type { ManagerItemArt, ManagerVipRole } from "@/api/manager";

const DEFAULT: Record<ManagerVipRole, Required<Pick<ManagerItemArt, "skin" | "hair" | "hair_style" | "outfit" | "accent">>> = {
  assistant: { skin: "#f1c7a5", hair: "#3b2416", hair_style: "bun", outfit: "#1f2a44", accent: "#c6e63a" },
  analyst: { skin: "#f0c6a0", hair: "#4a3426", hair_style: "short", outfit: "#33475b", accent: "#7fd1ff" },
};

/** Hair behind the head (long styles fall onto the shoulders). */
function BackHair({ style, color }: { style: string; color: string }) {
  switch (style) {
    case "long":
      return <path d="M30 58 C26 30 44 16 60 16 C76 16 94 30 90 58 L94 104 C84 110 72 104 70 96 L50 96 C48 104 36 110 26 104 Z" fill={color} />;
    case "bob":
      return <path d="M32 60 C28 30 44 17 60 17 C76 17 92 30 88 60 L90 80 C80 84 74 80 72 76 L48 76 C46 80 40 84 30 80 Z" fill={color} />;
    case "curls":
      return (
        <g fill={color}>
          {[[34, 44], [30, 60], [33, 76], [40, 88], [86, 44], [90, 60], [87, 76], [80, 88], [44, 26], [60, 20], [76, 26]].map(([x, y]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r={11} />
          ))}
        </g>
      );
    case "pony":
      return <path d="M84 40 C100 44 104 70 96 92 C92 80 88 66 82 56 Z" fill={color} />;
    case "bun":
      return <circle cx={60} cy={18} r={11} fill={color} />;
    default:
      return null;
  }
}

/** The fringe / top of the hair over the forehead. */
function FrontHair({ style, color }: { style: string; color: string }) {
  switch (style) {
    case "short":
      return <path d="M36 50 C34 30 48 22 60 22 C74 22 88 30 84 50 C78 40 70 36 60 37 C50 36 42 40 36 50 Z" fill={color} />;
    case "side":
      return <path d="M36 52 C33 30 50 21 64 23 C80 25 88 36 84 50 C76 36 60 34 48 40 C42 43 38 47 36 52 Z" fill={color} />;
    case "curls":
      return (
        <g fill={color}>
          {[[42, 34], [52, 28], [64, 27], [76, 33], [84, 42], [37, 44]].map(([x, y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r={8} />)}
        </g>
      );
    case "bob":
      return <path d="M35 54 C33 30 48 22 60 22 C74 22 88 30 85 54 C80 42 72 38 62 40 C56 46 46 50 35 54 Z" fill={color} />;
    default:
      // long, pony, bun: a soft side part
      return <path d="M35 52 C34 30 48 22 60 22 C74 22 87 30 85 52 C80 40 70 34 58 36 C50 38 42 44 35 52 Z" fill={color} />;
  }
}

/** A drawn bust of the VIP staff from the skin's colours — no image assets,
 * every skin is a palette (`staff_items[].art`). */
export default function StaffPortrait({ role, art, size = 88, className = "" }: {
  role: ManagerVipRole; art?: ManagerItemArt | null; size?: number; className?: string;
}) {
  const uid = useId().replace(/:/g, "");
  const a = { ...DEFAULT[role], ...(art ?? {}) };
  const female = role === "assistant";
  return (
    <svg viewBox="0 0 120 130" width={size} height={size * 130 / 120} className={className} role="img" aria-label={female ? "Помощница" : "Аналитик"}>
      <defs>
        <radialGradient id={`bg${uid}`} cx="50%" cy="38%" r="70%">
          <stop offset="0%" stopColor={a.accent} stopOpacity={0.55} />
          <stop offset="100%" stopColor={a.accent} stopOpacity={0} />
        </radialGradient>
        <linearGradient id={`suit${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={a.outfit} />
          <stop offset="100%" stopColor="#000" stopOpacity={0.55} />
        </linearGradient>
      </defs>
      <circle cx={60} cy={58} r={56} fill={`url(#bg${uid})`} />
      <BackHair style={a.hair_style} color={a.hair} />
      {/* shoulders and the outfit */}
      <path d="M14 130 C14 104 30 92 48 88 L72 88 C90 92 106 104 106 130 Z" fill={a.outfit} />
      <path d="M14 130 C14 104 30 92 48 88 L72 88 C90 92 106 104 106 130 Z" fill={`url(#suit${uid})`} opacity={0.5} />
      <rect x={52} y={72} width={16} height={20} rx={6} fill={a.skin} />
      {female ? (
        <>
          <path d="M48 88 L60 106 L72 88 Z" fill={a.skin} />
          <path d="M44 89 L60 112 L52 130 L36 130 Z" fill="#000" opacity={0.18} />
          <path d="M76 89 L60 112 L68 130 L84 130 Z" fill="#000" opacity={0.18} />
          <circle cx={60} cy={104} r={2.6} fill={a.accent} />
        </>
      ) : (
        <>
          <path d="M49 88 L60 100 L71 88 Z" fill="#f4f6f8" />
          <path d="M58 98 L62 98 L64 122 L60 127 L56 122 Z" fill={a.accent} />
          <path d="M44 89 L58 102 L50 130 L34 130 Z" fill="#000" opacity={0.2} />
          <path d="M76 89 L62 102 L70 130 L86 130 Z" fill="#000" opacity={0.2} />
        </>
      )}
      {/* head */}
      <ellipse cx={60} cy={52} rx={24} ry={28} fill={a.skin} />
      <ellipse cx={36} cy={56} rx={4} ry={6} fill={a.skin} />
      <ellipse cx={84} cy={56} rx={4} ry={6} fill={a.skin} />
      {female && <><circle cx={36} cy={64} r={2.4} fill={a.accent} /><circle cx={84} cy={64} r={2.4} fill={a.accent} /></>}
      <FrontHair style={a.hair_style} color={a.hair} />
      {/* face */}
      <path d={female ? "M44 50 Q50 46 55 49" : "M44 49 Q50 46 55 48"} stroke={a.hair} strokeWidth={2} fill="none" strokeLinecap="round" />
      <path d={female ? "M65 49 Q70 46 76 50" : "M65 48 Q70 46 76 49"} stroke={a.hair} strokeWidth={2} fill="none" strokeLinecap="round" />
      <ellipse cx={50} cy={56} rx={3} ry={female ? 3.6 : 3} fill="#1b1b22" />
      <ellipse cx={70} cy={56} rx={3} ry={female ? 3.6 : 3} fill="#1b1b22" />
      <circle cx={51} cy={55} r={1} fill="#fff" />
      <circle cx={71} cy={55} r={1} fill="#fff" />
      {female && (
        <>
          <path d="M45 54 L43 52 M75 54 L77 52" stroke="#1b1b22" strokeWidth={1.4} strokeLinecap="round" />
          <ellipse cx={44} cy={65} rx={4.5} ry={2.6} fill="#ff7a8a" opacity={0.35} />
          <ellipse cx={76} cy={65} rx={4.5} ry={2.6} fill="#ff7a8a" opacity={0.35} />
        </>
      )}
      <path d="M58 60 Q60 64 62 60" stroke="#000" strokeOpacity={0.25} strokeWidth={1.4} fill="none" strokeLinecap="round" />
      <path d={female ? "M53 68 Q60 74 67 68" : "M54 69 Q60 72 66 69"} stroke={female ? "#c2394f" : "#7a3b2e"} strokeWidth={female ? 2.6 : 2}
        fill={female ? "#e0566c" : "none"} strokeLinecap="round" />
      {a.glasses && (
        <g stroke={a.accent} strokeWidth={2} fill="#fff" fillOpacity={0.08}>
          <rect x={41} y={50} width={17} height={12} rx={4} />
          <rect x={62} y={50} width={17} height={12} rx={4} />
          <path d="M58 55 L62 55" />
        </g>
      )}
    </svg>
  );
}
