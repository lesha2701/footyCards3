/** Which stickers of each album page the player has already looked at, so
 * a card got since the last visit is pressed in with «NEW». Per device
 * (localStorage); the very first visit of a page marks everything seen. */
const KEY = "fc_album_seen_v1";

function load(): Record<string, number[]> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Record<string, number[]>;
  } catch {
    return {};
  }
}

/** The owned players of a page that are new since the last visit. */
export function freshOnPage(collectionId: number, owned: number[]): Set<number> {
  const seen = load()[String(collectionId)];
  if (!seen) return new Set();
  const was = new Set(seen);
  return new Set(owned.filter((id) => !was.has(id)));
}

export function markPageSeen(collectionId: number, owned: number[]): void {
  try {
    const all = load();
    all[String(collectionId)] = owned;
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    /* private mode: no «NEW», nothing else breaks */
  }
}
