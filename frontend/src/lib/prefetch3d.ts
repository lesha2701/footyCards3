/** Warms the browser cache with the 3D engine and the shared footballer
 * model while the player is one tap away from a 3D screen (the Play hub, a
 * finished career match with goals to replay), so opening it doesn't wait
 * on ~0.5 MB of downloads. Everything it fetches is content-hashed and
 * cached "immutable" by nginx, so it costs each device one download per
 * release at most — and nothing on a slow or data-saving connection. */
import footballerUrl from "@/assets/3d/footballer.glb?url";
import movesUrl from "@/assets/3d/footballer-moves.glb?url";

type Connection = { saveData?: boolean; effectiveType?: string };

/** No prefetching on "Data Saver" or anything slower than 4G; unknown
 * (iOS has no Network Information API) counts as fine. */
export function canPrefetch(connection: Connection | undefined): boolean {
  if (!connection) return true;
  if (connection.saveData) return false;
  return !connection.effectiveType || connection.effectiveType === "4g";
}

const done = new Set<string>();

function whenIdle(fn: () => void): void {
  const idle = (window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback;
  if (idle) idle(fn, { timeout: 4000 });
  else setTimeout(fn, 1500);
}

/** `load` is a dynamic import of the screen's own chunk (it pulls three.js
 * and its renderer with it); `assets` are extra files to warm. Each key runs
 * once per page load. */
export function prefetch3D(key: string, load: () => Promise<unknown>, assets: string[] = [footballerUrl, movesUrl]): void {
  if (done.has(key) || typeof window === "undefined" || import.meta.env.MODE === "test") return;
  if (!canPrefetch((navigator as Navigator & { connection?: Connection }).connection)) return;
  done.add(key);
  whenIdle(() => {
    load().catch(() => done.delete(key));
    for (const url of assets) {
      if (done.has(url)) continue;
      done.add(url);
      fetch(url, { priority: "low" } as RequestInit).catch(() => done.delete(url));
    }
  });
}
