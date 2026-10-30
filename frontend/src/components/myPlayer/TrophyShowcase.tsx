import type { MyPlayerCabinet, MyPlayerTrophy } from "@/api/myPlayer";
import { staticUrl } from "@/lib/api";
import { SHOWCASE_STYLE } from "@/lib/myPlayer";

function season(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

const TOTALS: [keyof MyPlayerCabinet["totals"], string][] = [
  ["seasons", "Сезоны"], ["matches", "Матчи"], ["goals", "Голы"], ["assists", "Передачи"], ["titles", "Титулы"],
];

/** «Шкаф трофеев»: «Карьера игрока» cups, newest first, on the shelf of the
 * chosen showcase, with lifetime career totals and the «Меценат» badge. */
export default function TrophyShowcase({ trophies, emptyHint, cabinet }: {
  trophies: MyPlayerTrophy[]; emptyHint?: string; cabinet?: MyPlayerCabinet | null;
}) {
  if (!trophies.length && !emptyHint && !cabinet) return null;
  const style = SHOWCASE_STYLE[cabinet?.showcase ?? "wood"] ?? SHOWCASE_STYLE.wood;
  const totals = cabinet ? TOTALS.filter(([k]) => (cabinet.totals[k] ?? 0) > 0) : [];
  return (
    <section className={`rounded-2xl bg-gradient-to-b ${style.shelf} p-4 ring-1 ${style.ring}`} data-testid="trophy-showcase">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-bold text-ink-chalk">Витрина трофеев</h2>
        {cabinet?.patron.name && (
          <span className="rounded-full bg-amber-400/20 px-2.5 py-1 text-micro font-bold text-amber-300">🎁 {cabinet.patron.name}</span>
        )}
      </div>
      {totals.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1" data-testid="career-totals">
          {totals.map(([k, label]) => (
            <span key={k} className="text-caption text-ink-mist">{label} <b className="text-ink-chalk">{cabinet!.totals[k]}</b></span>
          ))}
        </div>
      )}
      {trophies.length === 0 ? (
        emptyHint && <p className="mt-2 text-caption text-ink-mist">{emptyHint}</p>
      ) : (
        <div className="mt-3 flex gap-2 overflow-x-auto border-b-4 border-black/30 pb-2">
          {trophies.map((t) => (
            <div key={t.id} className={`flex w-24 shrink-0 flex-col items-center rounded-xl bg-bg-raised/80 p-2 text-center ring-1 ${style.ring}`}>
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
      <p className="mt-2 text-micro text-ink-mist-dim">{style.label}</p>
    </section>
  );
}
