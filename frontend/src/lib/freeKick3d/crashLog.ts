import { useEffect, useRef } from "react";

/** An error's message plus the top of its stack. */
export function describe(err: Error) {
  return [err.message, ...(err.stack ?? "").split("\n").slice(1, 4)].join("\n");
}

/** Diagnostics: every error while the scene is open, in order — when it
 * crashes, the first one is the cause (later ones are often fallout from
 * tearing the 3D scene down). */
export function useCrashLog() {
  const log = useRef<string[]>([]);
  useEffect(() => {
    const push = (e: unknown) => {
      const err = e instanceof Error ? e : null;
      const text = err ? describe(err) : String(e);
      if (log.current.length < 8) log.current.push(text);
    };
    const onError = (e: ErrorEvent) => push(e.error ?? e.message);
    const onRejection = (e: PromiseRejectionEvent) => push(e.reason);
    const original = console.error;
    console.error = (...args: unknown[]) => {
      push(args.find((a) => a instanceof Error) ?? args.map(String).join(" "));
      original(...args);
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      console.error = original;
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);
  return log;
}
