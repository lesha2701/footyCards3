import type { MyPlayerCabinet, MyPlayerTrophy } from "@/api/myPlayer";
import { staticUrl } from "@/lib/api";
import { SHOWCASE_STYLE } from "@/lib/myPlayer";
import { cabinetArt, trophyArt } from "@/lib/trophyArt";

function season(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

const TOTALS: [keyof MyPlayerCabinet["totals"], string][] = [
  ["seasons", "Сезоны"], ["matches", "Матчи"], ["goals", "Голы"], ["assists", "Передачи"], ["titles", "Титулы"],
];
const PER_SHELF = 3;
// The top of each shelf of the cabinet art (2:3), % of its height.
const SHELF_TOPS = [35, 59.5, 83];
const PER_CABINET = PER_SHELF * SHELF_TOPS.length;

export function TrophyImage({ code, icon, imagePath, className = "h-16 w-16" }: {
  code: string; icon: string; imagePath?: string | null; className?: string;
}) {
  const src = (imagePath && staticUrl(imagePath)) || trophyArt(code);
  if (src) {
    return <img src={src} alt="" className={`${className} object-contain drop-shadow-[0_6px_10px_rgba(0,0,0,0.55)]`} loading="lazy" decoding="async" />;
  }
  return <span className={`${className} flex items-center justify-center text-5xl drop-shadow-[0_6px_10px_rgba(0,0,0,0.55)]`}>{icon}</span>;
}

/** One kind of cup: the newest grant stands for all of them, the rest only
 * add to the counter. */
interface TrophyGroup { trophy: MyPlayerTrophy; all: MyPlayerTrophy[] }

/** Folds repeat cups (three league titles) into one with a «×N» counter, in
 * the order each kind was first won (newest first). */
function groupTrophies(trophies: MyPlayerTrophy[]): TrophyGroup[] {
  const groups = new Map<string, TrophyGroup>();
  for (const t of trophies) {
    const g = groups.get(t.code);
    if (g) g.all.push(t);
    else groups.set(t.code, { trophy: t, all: [t] });
  }
  return [...groups.values()];
}

function tooltip({ trophy, all }: TrophyGroup): string {
  const lines = all.map((t) => [t.message, season(t.granted_at)].filter(Boolean).join(" · "));
  return [all.length > 1 ? `${trophy.name} ×${all.length}` : trophy.name, ...lines].join("\n");
}

/** One cabinet: its art (or gradient with drawn shelves) and up to nine
 * kinds of cups standing on the three shelves. */
function Cabinet({ code, groups }: { code: string; groups: TrophyGroup[] }) {
  const style = SHOWCASE_STYLE[code] ?? SHOWCASE_STYLE.wood;
  const art = cabinetArt(code);
  return (
    <div
      className={`relative mx-auto aspect-[2/3] w-full max-w-sm overflow-hidden rounded-xl bg-gradient-to-b ${style.shelf} bg-cover bg-center ring-1 ${style.ring}`}
      style={art ? { backgroundImage: `url(${art})` } : undefined}
      data-testid="trophy-cabinet"
    >
      {SHELF_TOPS.map((top, shelf) => (
        <div key={shelf}>
          {!art && (
            <div className={`absolute inset-x-[9%] h-[2%] rounded-sm bg-gradient-to-b from-white/50 to-white/10 shadow-[0_6px_12px_rgba(0,0,0,0.5)]`}
              style={{ top: `${top}%` }} />
          )}
          <div className="absolute inset-x-[11%] grid grid-cols-3 items-end gap-1" style={{ bottom: `${100 - top - 0.8}%` }}>
            {groups.slice(shelf * PER_SHELF, shelf * PER_SHELF + PER_SHELF).map((g) => (
              <div key={g.trophy.code} className="relative flex flex-col items-center" title={tooltip(g)}>
                <TrophyImage code={g.trophy.code} icon={g.trophy.icon} imagePath={g.trophy.image_path} className="h-[4.6rem] w-[4.6rem]" />
                {g.all.length > 1 && (
                  <span className="absolute right-0 top-0 rounded-full bg-amber-400 px-1.5 text-[11px] font-black leading-5 text-black shadow ring-1 ring-black/40"
                    data-testid="trophy-count">
                    ×{g.all.length}
                  </span>
                )}
              </div>
            ))}
          </div>
          <div className="absolute inset-x-[11%] grid grid-cols-3 gap-1" style={{ top: `${top + 2.6}%` }}>
            {groups.slice(shelf * PER_SHELF, shelf * PER_SHELF + PER_SHELF).map(({ trophy: t }) => (
              <p key={t.code} className="mx-auto line-clamp-2 max-w-full rounded bg-black/60 px-1 text-center text-[9px] font-bold leading-tight text-amber-300">
                {t.name}
              </p>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/** «Шкаф трофеев»: «Карьера игрока» cups, newest first, on the shelves of the
 * chosen cabinet, with lifetime career totals and the «Меценат» badge. */
export default function TrophyShowcase({ trophies, emptyHint, cabinet }: {
  trophies: MyPlayerTrophy[]; emptyHint?: string; cabinet?: MyPlayerCabinet | null;
}) {
  if (!trophies.length && !emptyHint && !cabinet) return null;
  const code = cabinet?.showcase ?? "wood";
  const style = SHOWCASE_STYLE[code] ?? SHOWCASE_STYLE.wood;
  const totals = cabinet ? TOTALS.filter(([k]) => (cabinet.totals[k] ?? 0) > 0) : [];
  const groups = groupTrophies(trophies);
  const cabinets: TrophyGroup[][] = [];
  for (let i = 0; i < Math.max(groups.length, 1); i += PER_CABINET) cabinets.push(groups.slice(i, i + PER_CABINET));
  return (
    <section className="rounded-2xl bg-bg-surface p-4" data-testid="trophy-showcase">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-bold text-ink-chalk">Шкаф трофеев</h2>
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
      {trophies.length === 0 && emptyHint && <p className="mt-2 text-caption text-ink-mist">{emptyHint}</p>}
      <div className="mt-3 flex flex-col gap-3">
        {cabinets.map((chunk, i) => <Cabinet key={i} code={code} groups={chunk} />)}
      </div>
      <p className="mt-2 text-micro text-ink-mist-dim">{style.label}</p>
    </section>
  );
}
