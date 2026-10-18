import { useEffect, useState } from "react";

/** «Новое» marks for sections the player has never opened (per device).
 * A section's page calls useMarkSeen(key) on mount; entry points render
 * <NewBadge section={key} /> until then. Storage can be unavailable in some
 * Telegram webviews — then nothing is marked (no false «new» forever). */
const KEY = "fc.seen-sections";
const listeners = new Set<() => void>();

function read(): Set<string> | null {
  try {
    return new Set(JSON.parse(localStorage.getItem(KEY) ?? "[]") as string[]);
  } catch {
    return null;
  }
}

export function isSeen(section: string): boolean {
  const seen = read();
  return seen === null || seen.has(section);
}

export function markSeen(section: string): void {
  const seen = read();
  if (!seen || seen.has(section)) return;
  seen.add(section);
  try {
    localStorage.setItem(KEY, JSON.stringify([...seen]));
  } catch {
    /* storage unavailable */
  }
  listeners.forEach((l) => l());
}

export function useMarkSeen(section: string): void {
  useEffect(() => markSeen(section), [section]);
}

export function useIsNew(section: string): boolean {
  const [fresh, setFresh] = useState(() => !isSeen(section));
  useEffect(() => {
    const update = () => setFresh(!isSeen(section));
    listeners.add(update);
    return () => { listeners.delete(update); };
  }, [section]);
  return fresh;
}
