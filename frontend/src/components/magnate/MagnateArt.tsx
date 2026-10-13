import type { MagnateCellType } from "@/types";

/** Shield crest in the club's colours with its abbreviation — drawn, not
 *  an image, so it weighs nothing and never resembles a real club badge. */
export function ClubCrest({
  short, colors, size = 18, className = "",
}: { short?: string | null; colors?: string[] | null; size?: number; className?: string }) {
  const primary = colors?.[0] ?? "#334155";
  const secondary = colors?.[1] ?? "#e2e8f0";
  const text = (short ?? "").slice(0, 4);
  const light = isLight(primary);
  return (
    <svg viewBox="0 0 32 36" width={size} height={size * 1.125} className={className} aria-hidden>
      <path d="M16 1 L30 5 V17 C30 26 23 32 16 35 C9 32 2 26 2 17 V5 Z" fill={primary} stroke={secondary} strokeWidth="2.2" />
      <path d="M16 3.5 V33" stroke={secondary} strokeWidth="3" opacity="0.35" />
      <text
        x="16" y="21" textAnchor="middle" fontSize={text.length > 3 ? 8 : 9.5} fontWeight="800"
        fontFamily="Manrope, system-ui, sans-serif" fill={light ? "#0f172a" : "#ffffff"}
        stroke={light ? "#ffffff" : "#0f172a"} strokeWidth="0.6" paintOrder="stroke"
      >
        {text}
      </text>
    </svg>
  );
}

function isLight(hex: string): boolean {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return false;
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return 0.299 * r + 0.587 * g + 0.114 * b > 170;
}

/** Small line icons for the non-club cells. */
export function CellIcon({ type, size = 16 }: { type: MagnateCellType; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  switch (type) {
    case "start": // whistle
      return (
        <svg {...common} stroke="#c6e63a">
          <circle cx="9" cy="14" r="5.5" />
          <path d="M13.5 10.5 L21 7 V11 L14.5 13.5" />
          <circle cx="9" cy="14" r="1.6" fill="#c6e63a" />
        </svg>
      );
    case "stadium":
      return (
        <svg {...common} stroke="#e2e8f0">
          <ellipse cx="12" cy="9" rx="9" ry="3.5" />
          <path d="M3 9 V15 C3 17 7 18.5 12 18.5 C17 18.5 21 17 21 15 V9" />
          <path d="M7 12.5 V17 M12 13 V18.5 M17 12.5 V17" />
        </svg>
      );
    case "var": // monitor
      return (
        <svg {...common} stroke="#22d3c4">
          <rect x="3" y="4.5" width="18" height="12" rx="2" />
          <path d="M9 20 H15 M12 16.5 V20" />
          <path d="M7.5 8 L9.5 13 L11.5 8 M13.5 13 L15 8 L16.5 13 M14 11.3 H16" strokeWidth="1.3" />
        </svg>
      );
    case "transfer": // swap arrows
      return (
        <svg {...common} stroke="#a78bfa">
          <path d="M4 8 H18 L14.5 4.5 M20 16 H6 L9.5 19.5" />
        </svg>
      );
    case "fine": // banknote with minus
      return (
        <svg {...common} stroke="#f87171">
          <rect x="2.5" y="6" width="19" height="12" rx="2" />
          <path d="M9 12 H15" />
        </svg>
      );
    case "jail": // bars
      return (
        <svg {...common} stroke="#f87171">
          <rect x="4" y="3.5" width="16" height="17" rx="2" />
          <path d="M8.5 3.5 V20.5 M12 3.5 V20.5 M15.5 3.5 V20.5" />
        </svg>
      );
    case "go_to_jail": // red card
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
          <rect x="6" y="2.5" width="12" height="17" rx="1.8" fill="#ef4444" transform="rotate(12 12 11)" />
          <rect x="6" y="2.5" width="12" height="17" rx="1.8" fill="none" stroke="#fff" strokeOpacity="0.5" transform="rotate(12 12 11)" />
        </svg>
      );
    case "break": // cup
      return (
        <svg {...common} stroke="#fbbf24">
          <path d="M5 8 H16 V13 A5.5 5.5 0 0 1 5 13 Z" />
          <path d="M16 9.5 H18 A2.5 2.5 0 0 1 18 14.5 H16" />
          <path d="M8 3.5 C8 5 9.5 5 9.5 6.5 M12 3.5 C12 5 13.5 5 13.5 6.5" strokeWidth="1.3" />
        </svg>
      );
    default:
      return null;
  }
}

/** Mown-stripes pitch with markings — the centre of the board. */
export function PitchBackground() {
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden>
      <defs>
        <radialGradient id="mg-light" cx="50%" cy="45%" r="70%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.25" />
        </radialGradient>
      </defs>
      {Array.from({ length: 10 }, (_, i) => (
        <rect key={i} x="0" y={i * 10} width="100" height="10" fill={i % 2 ? "#1f7a3c" : "#238a44"} />
      ))}
      <rect width="100" height="100" fill="url(#mg-light)" />
      <g fill="none" stroke="#ffffff" strokeOpacity="0.55" strokeWidth="0.6">
        <rect x="5" y="5" width="90" height="90" />
        <line x1="5" y1="50" x2="95" y2="50" />
        <circle cx="50" cy="50" r="11" />
        <rect x="27" y="5" width="46" height="15" />
        <rect x="38" y="5" width="24" height="6" />
        <rect x="27" y="80" width="46" height="15" />
        <rect x="38" y="89" width="24" height="6" />
        <path d="M42 20 A9 9 0 0 0 58 20" />
        <path d="M42 80 A9 9 0 0 1 58 80" />
      </g>
      <circle cx="50" cy="50" r="0.9" fill="#ffffff" fillOpacity="0.7" />
    </svg>
  );
}
