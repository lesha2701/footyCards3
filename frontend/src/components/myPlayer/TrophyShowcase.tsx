import type { MyPlayerTrophy } from "@/api/myPlayer";
import { staticUrl } from "@/lib/api";

function season(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

/** «Витрина трофеев»: «Карьера игрока» cups, newest first, with the date
 * and what they were for. */
export default function TrophyShowcase({ trophies, emptyHint }: { trophies: MyPlayerTrophy[]; emptyHint?: string }) {
  if (!trophies.length && !emptyHint) return null;
  return (
    <section className="rounded-2xl bg-gradient-to-b from-amber-400/10 to-bg-surface p-4" data-testid="trophy-showcase">
      <h2 className="font-display text-base font-bold text-ink-chalk">Витрина трофеев</h2>
      {trophies.length === 0 ? (
        <p className="mt-2 text-caption text-ink-mist">{emptyHint}</p>
      ) : (
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
          {trophies.map((t) => (
            <div key={t.id} className="flex w-24 shrink-0 flex-col items-center rounded-xl bg-bg-raised p-2 text-center">
              {t.image_path ? (
                <img src={staticUrl(t.image_path) ?? undefined} alt="" className="h-12 w-12 object-contain" loading="lazy" decoding="async" />
              ) : (
                <span className="text-4xl leading-[3rem]">{t.icon}</span>
              )}
              <span className="mt-1 line-clamp-2 text-micro font-bold leading-tight text-amber-300">{t.name}</span>
              {t.message && <span className="mt-0.5 line-clamp-2 text-micro leading-tight text-ink-mist">{t.message}</span>}
              <span className="mt-0.5 text-micro text-ink-mist-dim">{season(t.granted_at)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
