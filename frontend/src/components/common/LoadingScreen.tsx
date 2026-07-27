export default function LoadingScreen() {
  return (
    <div className="flex h-screen w-screen flex-col items-center justify-center gap-4 bg-bg-base">
      <img src="/brand/victor-fc-crest.jpg" alt="" className="h-12 w-12 animate-pulse rounded-full ring-1 ring-white/10" />
      <p className="font-display text-sm font-bold tracking-wide text-ink-chalk">
        VICTOR <span className="text-accent-lime">FC</span>
      </p>
    </div>
  );
}
