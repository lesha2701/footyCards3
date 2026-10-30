import { useEffect, useState } from "react";

/** After this long the screen says it's still working, so a slow server
 * doesn't look like a frozen app. */
const SLOW_HINT_MS = 5_000;

export default function LoadingScreen() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_HINT_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div className="flex h-screen w-screen flex-col items-center justify-center gap-4 bg-bg-base px-6 text-center">
      <img decoding="async" src="/brand/victor-fc-crest.jpg" alt="" className="h-12 w-12 animate-pulse rounded-full ring-1 ring-white/10" />
      <p className="font-display text-sm font-bold tracking-wide text-ink-chalk">
        VICTOR <span className="text-accent-lime">FC</span>
      </p>
      {slow && (
        <p className="max-w-xs text-caption text-ink-mist" role="status">
          Загрузка идёт дольше обычного — подключаемся к серверу…
        </p>
      )}
    </div>
  );
}
