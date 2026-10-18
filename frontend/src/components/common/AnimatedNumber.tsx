import { useEffect, useRef, useState } from "react";

import { prefersReducedMotion } from "@/lib/motion";

/** A number that rolls to its new value (~0.6 s, ease-out) and flashes
 * green when it grows, red when it shrinks. Instant with reduced motion. */
export default function AnimatedNumber({ value, className = "" }: { value: number; className?: string }) {
  const [shown, setShown] = useState(value);
  const [flash, setFlash] = useState<"up" | "down" | null>(null);
  const from = useRef(value);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    const start = from.current;
    if (start === value) return;
    setFlash(value > start ? "up" : "down");
    const clearFlash = window.setTimeout(() => setFlash(null), 900);
    if (prefersReducedMotion()) {
      setShown(value);
      from.current = value;
      return () => window.clearTimeout(clearFlash);
    }
    const began = performance.now();
    const duration = 600;
    const tick = (now: number) => {
      const t = Math.min(1, (now - began) / duration);
      const eased = 1 - (1 - t) ** 3;
      setShown(Math.round(start + (value - start) * eased));
      if (t < 1) frame.current = requestAnimationFrame(tick);
      else from.current = value;
    };
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      from.current = value;
      window.clearTimeout(clearFlash);
    };
  }, [value]);

  return (
    <span
      className={`transition-colors duration-300 ${flash === "up" ? "text-accent-lime" : flash === "down" ? "text-red-400" : ""} ${className}`}
    >
      {shown.toLocaleString("ru-RU")}
    </span>
  );
}
