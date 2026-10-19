import { useEffect, useState } from "react";

const PREFIX = "shop.seen.";

function read(scope: string): Set<string> | null {
  try {
    const raw = localStorage.getItem(PREFIX + scope);
    return raw ? new Set(JSON.parse(raw) as string[]) : null;
  } catch {
    return null;
  }
}

function write(scope: string, ids: Set<string>) {
  try {
    localStorage.setItem(PREFIX + scope, JSON.stringify([...ids]));
  } catch {
    /* storage off — badges just won't persist */
  }
}

/** «НОВОЕ» on shop items the player hasn't opened yet. The first visit
 * remembers everything already on sale (nothing is "new" on day one); an
 * item added later stays new until its details are opened. Per device. */
export function useSeenItems(scope: string, ids: (string | number)[] | undefined) {
  const [seen, setSeen] = useState<Set<string> | null>(() => read(scope));
  const key = ids?.map(String).join(",") ?? "";

  useEffect(() => {
    if (!ids?.length || seen) return;
    const all = new Set(ids.map(String));
    write(scope, all);
    setSeen(all);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, key, seen]);

  return {
    isNew: (id: string | number) => !!seen && !seen.has(String(id)),
    markSeen: (id: string | number) => {
      if (!seen || seen.has(String(id))) return;
      const next = new Set(seen).add(String(id));
      write(scope, next);
      setSeen(next);
    },
  };
}
