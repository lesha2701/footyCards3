import { useId } from "react";

import type { MuseHeartState } from "@/lib/museDate";

const LABELS: Record<MuseHeartState, string> = {
  date: "Свидание доступно",
  inspired: "Муза вдохновлена",
  bored: "Муза скучает",
};

/** The heart on a Muse portrait: red — today's date is waiting; the brand
 * gradient (as the «Играть» button) — she is inspired; black — she misses
 * you (not inspired, no date left today). */
export default function MuseHeart({ state, size = 22, className = "" }: { state: MuseHeartState; size?: number; className?: string }) {
  const gradientId = useId();
  const fill = state === "date" ? "#ef4444" : state === "inspired" ? `url(#${gradientId})` : "#0b0d10";
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={`drop-shadow-[0_1px_3px_rgba(0,0,0,0.6)] ${className}`}
      role="img"
      aria-label={LABELS[state]}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#22d3c4" />
          <stop offset="55%" stopColor="#3ed17e" />
          <stop offset="100%" stopColor="#c6e63a" />
        </linearGradient>
      </defs>
      <path
        d="M12 21s-7.5-4.6-9.6-9.2C.9 8.5 2.9 4.5 6.7 4.5c2.1 0 3.6 1.1 5.3 3 1.7-1.9 3.2-3 5.3-3 3.8 0 5.8 4 4.3 7.3C19.5 16.4 12 21 12 21z"
        fill={fill}
        stroke={state === "bored" ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.85)"}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}
