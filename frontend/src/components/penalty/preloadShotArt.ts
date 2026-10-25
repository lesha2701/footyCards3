import freekickBg from "@/assets/shots/freekick-bg.webp";
import freekickWall from "@/assets/shots/freekick-wall.webp";
import keeperReadyBlue from "@/assets/shots/keeper-ready-blue.webp";
import keeperReady from "@/assets/shots/keeper-ready.webp";
import penaltyBg from "@/assets/shots/penalty-bg.webp";

let started = false;

/** Warms the browser cache with the Penalty / Free kick scene art (~350 KB)
 * once the Play hub has settled, so the first kick doesn't flash an empty
 * frame. The dive poses are small and load on the first dive. */
export function preloadShotArt(): void {
  if (started || typeof window === "undefined") return;
  started = true;
  const load = () => {
    for (const src of [penaltyBg, keeperReady, keeperReadyBlue, freekickBg, freekickWall]) {
      const img = new Image();
      img.decoding = "async";
      img.src = src;
    }
  };
  const idle = (window as Window & { requestIdleCallback?: (cb: () => void) => number }).requestIdleCallback;
  if (idle) idle(load);
  else setTimeout(load, 1500);
}
