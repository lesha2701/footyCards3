/** Full screen for the landscape 3D goal replay — its own module so the
 * main chunk (which holds lib/telegram) doesn't carry it. */
import { getTelegramWebApp, isInsideTelegram } from "@/lib/telegram";

/** Full screen for a landscape viewer. Inside
 * Telegram 8.0+ the Mini App goes full screen; on a phone browser the page
 * does and asks for landscape. Call it from the tap that opens the viewer
 * (browsers need a user gesture); the returned function undoes only what
 * this call did. */
export function enterImmersive(): () => void {
  const webApp = getTelegramWebApp();
  if (isInsideTelegram() && webApp?.requestFullscreen && webApp.isVersionAtLeast?.("8.0")) {
    if (webApp.isFullscreen) return () => {};
    try {
      webApp.requestFullscreen();
    } catch {
      return () => {};
    }
    return () => {
      try {
        webApp.exitFullscreen?.();
      } catch {
        // The client left full screen by itself.
      }
    };
  }
  const coarse = typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
  const root = document.documentElement;
  if (!coarse || !root.requestFullscreen || document.fullscreenElement) return () => {};
  type LockableOrientation = ScreenOrientation & { lock?: (o: string) => Promise<void> };
  const orientation = screen.orientation as LockableOrientation | undefined;
  root.requestFullscreen()
    .then(() => orientation?.lock?.("landscape"))
    .catch(() => {});
  return () => {
    orientation?.unlock?.();
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  };
}
