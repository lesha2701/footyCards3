import { useEffect, useRef } from "react";

const MIN_DISTANCE = 70;
// Mostly-horizontal: |dx| must beat |dy| by this factor (else it's a scroll).
const DIRECTION_RATIO = 1.8;

/** True when the touch started inside something that scrolls sideways itself
 * (chip rows, tables) or is a form field — those keep their own gestures. */
function startsInHorizontalScroller(target: EventTarget | null): boolean {
  let el = target instanceof Element ? target : null;
  while (el && el !== document.body) {
    if (el.matches("input, textarea, select, [data-no-swipe]")) return true;
    const style = getComputedStyle(el);
    if ((style.overflowX === "auto" || style.overflowX === "scroll") && el.scrollWidth > el.clientWidth) return true;
    el = el.parentElement;
  }
  return false;
}

/** Horizontal swipe anywhere on the page (touch only): onLeft = finger moved
 * left (go to the next screen), onRight = moved right (previous). Ignored
 * while a modal is open and when the gesture starts in a sideways scroller. */
export function usePageSwipe(onLeft: (() => void) | null, onRight: (() => void) | null) {
  const handlers = useRef({ onLeft, onRight });
  handlers.current = { onLeft, onRight };

  useEffect(() => {
    let start: { x: number; y: number } | null = null;
    const down = (e: TouchEvent) => {
      if (e.touches.length !== 1 || document.querySelector("[role=dialog]") || startsInHorizontalScroller(e.target)) {
        start = null;
        return;
      }
      start = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    };
    const up = (e: TouchEvent) => {
      if (!start) return;
      const t = e.changedTouches[0];
      const dx = t.clientX - start.x;
      const dy = t.clientY - start.y;
      start = null;
      if (Math.abs(dx) < MIN_DISTANCE || Math.abs(dx) < Math.abs(dy) * DIRECTION_RATIO) return;
      if (dx < 0) handlers.current.onLeft?.();
      else handlers.current.onRight?.();
    };
    document.addEventListener("touchstart", down, { passive: true });
    document.addEventListener("touchend", up, { passive: true });
    return () => {
      document.removeEventListener("touchstart", down);
      document.removeEventListener("touchend", up);
    };
  }, []);
}

/** Swipe down on a bottom sheet's grab area closes it. Spread the returned
 * handlers on the element the finger should start on (handle + header). */
export function useSwipeDownToClose(onClose: () => void) {
  const start = useRef<{ x: number; y: number } | null>(null);
  return {
    onTouchStart: (e: React.TouchEvent) => {
      start.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    },
    onTouchEnd: (e: React.TouchEvent) => {
      const s = start.current;
      start.current = null;
      if (!s) return;
      const t = e.changedTouches[0];
      const dy = t.clientY - s.y;
      if (dy > 90 && dy > Math.abs(t.clientX - s.x) * 1.5) onClose();
    },
  };
}
