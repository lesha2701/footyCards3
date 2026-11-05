import { useState } from "react";
import { createPortal } from "react-dom";
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

export function TrophyImage({ code, icon, imagePath, name, className = "h-16 w-16" }: {
  code: string; icon: string; imagePath?: string | null; name?: string; className?: string;
}) {
  // An uploaded image that fails to load falls back to the built-in art, then
  // to the emoji — a broken file never leaves an empty spot on the shelf.
  const sources = [imagePath && staticUrl(imagePath), trophyArt(code, name)].filter((s): s is string => !!s);
  const [failed, setFailed] = useState(0);
  const src = sources[failed];
  if (src) {
    return <img key={src} src={src} alt="" className={`${className} object-contain drop-shadow-[0_6px_10px_rgba(0,0,0,0.55)]`}
      decoding="async" onError={() => setFailed((n) => n + 1)} />;
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

/** What a cup was awarded for: every win of this kind, newest first. */
function TrophyDetails({ group, onClose }: { group: TrophyGroup; onClose: () => void }) {
  const { trophy, all } = group;
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-end justify-center bg-black/60 p-3" onClick={onClose}>
      <div className="flex max-h-[80vh] w-full max-w-md flex-col items-center gap-2 overflow-y-auto rounded-3xl bg-bg-surface p-4"
        role="dialog" aria-label={trophy.name} onClick={(e) => e.stopPropagation()} data-testid="trophy-details">
        <TrophyImage code={trophy.code} icon={trophy.icon} imagePath={trophy.image_path} name={trophy.name} className="h-32 w-32" />
        <p className="text-center font-display text-base font-bold text-ink-chalk">
          {trophy.name}{all.length > 1 && <span className="text-amber-300"> ×{all.length}</span>}
        </p>
        <ul className="flex w-full flex-col gap-1.5">
          {all.map((t) => (
            <li key={t.id} className="rounded-xl bg-white/5 px-3 py-2">
              {t.message && <p className="text-sm text-ink-chalk">{t.message}</p>}
              <p className="text-micro text-ink-mist">{season(t.granted_at)}</p>
            </li>
          ))}
        </ul>
        <button onClick={onClose} className="w-full rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-chalk">Закрыть</button>
      </div>
    </div>,
    document.body,
  );
}

/** One cabinet: its art (or gradient with drawn shelves) and up to nine
 * kinds of cups standing on the three shelves; a tap on a cup opens what it
 * was awarded for. */
function Cabinet({ code, groups, onOpen }: { code: string; groups: TrophyGroup[]; onOpen: (group: TrophyGroup) => void }) {
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
              <button key={g.trophy.code} type="button" onClick={() => onOpen(g)} aria-label={g.trophy.name}
                className="relative flex flex-col items-center" data-testid="trophy-cup">
                <TrophyImage code={g.trophy.code} icon={g.trophy.icon} imagePath={g.trophy.image_path} name={g.trophy.name} className="h-[4.6rem] w-[4.6rem]" />
                {g.all.length > 1 && (
                  <span className="absolute right-0 top-0 rounded-full bg-amber-400 px-1.5 text-[11px] font-black leading-5 text-black shadow ring-1 ring-black/40"
                    data-testid="trophy-count">
                    ×{g.all.length}
                  </span>
                )}
              </button>
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
  const [opened, setOpened] = useState<TrophyGroup | null>(null);
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
        {cabinets.map((chunk, i) => <Cabinet key={i} code={code} groups={chunk} onOpen={setOpened} />)}
      </div>
      <p className="mt-2 text-micro text-ink-mist-dim">{style.label}</p>
      {opened && <TrophyDetails group={opened} onClose={() => setOpened(null)} />}
    </section>
  );
}
