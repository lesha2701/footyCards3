import { useMotionValue, useSpring, type MotionValue } from "framer-motion";
import { useEffect, useRef, type PointerEvent } from "react";

import { getTelegramWebApp, isInsideTelegram } from "@/lib/telegram";

const MAX_DEG = 12;

export interface CardTilt {
  rotateX: MotionValue<number>;
  rotateY: MotionValue<number>;
  onPointerMove: (e: PointerEvent<HTMLElement>) => void;
  onPointerLeave: () => void;
}

const clamp = (v: number) => Math.max(-MAX_DEG, Math.min(MAX_DEG, v));

/** 3D tilt for the hero card: follows the finger/mouse and, inside Telegram
 * (Bot API 8.0+), the phone's gyroscope; plain browsers fall back to the
 * `deviceorientation` event where it fires without a permission prompt. */
export function useCardTilt(enabled = true): CardTilt {
  const rawX = useMotionValue(0);
  const rawY = useMotionValue(0);
  const rotateX = useSpring(rawX, { stiffness: 150, damping: 18 });
  const rotateY = useSpring(rawY, { stiffness: 150, damping: 18 });
  const touching = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    let base: { beta: number; gamma: number } | null = null;
    const apply = (beta: number, gamma: number) => {
      if (touching.current) return;
      base ??= { beta, gamma };
      rawX.set(clamp(-(beta - base.beta) * 0.6));
      rawY.set(clamp((gamma - base.gamma) * 0.6));
    };
    const webApp = getTelegramWebApp();
    const orientation = webApp?.DeviceOrientation;
    if (isInsideTelegram() && orientation && webApp?.isVersionAtLeast?.("8.0")) {
      const onChange = () => {
        if (orientation.beta == null || orientation.gamma == null) return;
        apply((orientation.beta * 180) / Math.PI, (orientation.gamma * 180) / Math.PI);
      };
      try {
        orientation.start({ refresh_rate: 50 });
        webApp.onEvent("deviceOrientationChanged", onChange);
      } catch {
        return;
      }
      return () => {
        webApp.offEvent("deviceOrientationChanged", onChange);
        try { orientation.stop(); } catch { /* already stopped */ }
      };
    }
    const onOrientation = (e: DeviceOrientationEvent) => {
      if (e.beta != null && e.gamma != null) apply(e.beta, e.gamma);
    };
    window.addEventListener("deviceorientation", onOrientation);
    return () => window.removeEventListener("deviceorientation", onOrientation);
  }, [enabled, rawX, rawY]);

  return {
    rotateX,
    rotateY,
    onPointerMove: (e) => {
      if (!enabled) return;
      touching.current = true;
      const rect = e.currentTarget.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width - 0.5;
      const py = (e.clientY - rect.top) / rect.height - 0.5;
      rawX.set(clamp(-py * 2 * MAX_DEG));
      rawY.set(clamp(px * 2 * MAX_DEG));
    },
    onPointerLeave: () => {
      touching.current = false;
      rawX.set(0);
      rawY.set(0);
    },
  };
}
