import type { TownJobs } from "@/api/town";
import { IconCoin } from "@/components/icons";

// The employers' pictures: assets/town/jobs/<code>.webp (none → the emoji).
const ART = Object.fromEntries(
  Object.entries(import.meta.glob("../../assets/town/jobs/*.webp", { eager: true, import: "default" }) as Record<string, string>)
    .map(([path, url]) => [path.slice(path.lastIndexOf("/") + 1, -".webp".length), url]),
);

const fmt = (n: number) => n.toLocaleString("ru-RU");

/**
 * «🏭 Рабочие места»: the town's employers (backend town_service.JOBS). Each
 * is bought and levelled for coins, every level adds jobs; free residents
 * (not on the «Менеджер» staff) take them by themselves and pay extra tax,
 * and the population brings fans to the player's club.
 */
export default function TownJobsPanel({ jobs, balance, busy, onBuy }: {
  jobs: TownJobs; balance: number; busy: boolean; onBuy: (code: string) => void;
}) {
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-bg-surface p-3" aria-label="Рабочие места" data-testid="town-jobs">
      <p className="text-sm font-bold text-ink-chalk">🏭 Рабочие места</p>
      <p className="text-[11px] leading-snug text-ink-mist" data-testid="town-jobs-summary">
        Работают {fmt(jobs.employed)} из {fmt(jobs.population)} жителей · налог +{fmt(jobs.tax_per_day)} 🪙/день ·
        болельщики клуба +{fmt(jobs.club_fans)}
      </p>
      {jobs.staff > 0 && (
        <p className="text-[10px] text-ink-mist-dim">В штабе клуба: {fmt(jobs.staff)} — они в городе не работают</p>
      )}
      {jobs.buildings.map((b) => {
        const price = b.next_price;
        const short = price != null ? Math.max(0, price - balance) : 0;
        const label = b.level > 0 ? `${b.name}: уровень ${b.level + 1}` : `${b.name}: купить`;
        return (
          <div key={b.code} className="flex items-center gap-2">
            {ART[b.code]
              ? <img src={ART[b.code]} alt="" aria-hidden className="h-11 w-11 shrink-0 object-contain drop-shadow" />
              : <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/5 text-lg" aria-hidden>{b.emoji}</span>}
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold text-ink-chalk">
                {b.name}{b.level > 0 && <span className="text-ink-mist"> · ур. {b.level}/{b.max_level}</span>}
              </p>
              <p className="truncate text-[10px] text-ink-mist">
                {b.level > 0 ? `${fmt(b.jobs)} мест` : "не построено"} · +{fmt(b.jobs_per_level)} за уровень
              </p>
            </div>
            {price == null ? (
              <span className="shrink-0 text-[11px] font-bold text-accent-lime">макс.</span>
            ) : (
              <button
                type="button"
                disabled={busy || short > 0}
                onClick={() => onBuy(b.code)}
                aria-label={`${label} за ${fmt(price)} монет`}
                className={`flex shrink-0 items-center gap-0.5 rounded-lg px-2 py-1 text-[11px] font-bold ${short > 0 ? "bg-white/5 text-ink-mist" : "bg-floodlight text-bg-base"}`}
              >
                {b.level > 0 ? "⬆" : "+"} <IconCoin size={11} /> {fmt(price)}
              </button>
            )}
          </div>
        );
      })}
    </section>
  );
}
