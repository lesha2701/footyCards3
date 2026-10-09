import { useEffect, useState } from "react";

/** useState that remembers its value in localStorage (per device). Storage can
 * be unavailable (private mode, Telegram webview quirks) — then it is just
 * plain in-memory state. */
export function usePersistentState<T>(key: string, initial: T) {
  const storageKey = `fc.${key}`;
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(value));
    } catch {
      /* storage unavailable */
    }
  }, [storageKey, value]);
  return [value, setValue] as const;
}
