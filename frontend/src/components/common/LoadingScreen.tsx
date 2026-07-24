export default function LoadingScreen() {
  return (
    <div className="flex h-screen w-screen flex-col items-center justify-center gap-4 bg-bg-base">
      <div className="h-12 w-12 animate-spin rounded-full border-4 border-accent/30 border-t-accent" />
      <p className="font-display text-lg tracking-wide text-slate-300">FootyCards</p>
    </div>
  );
}
