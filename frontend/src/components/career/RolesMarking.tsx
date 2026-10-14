import { useMutation } from "@tanstack/react-query";

import { setCareerMarking, setCareerRoles, type CareerSeason, type CareerView, type TacticsCatalog } from "@/api/career";
import { Segmented } from "@/components/career/CareerTactics";
import { haptic } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

const NONE = "";

/** Player roles per line (wingers / holding midfielder / full-backs): only
 * the lines the formation has. Each role is a trade-off in duels. */
export function RolesCard({ season, catalog, onView, onError }: { season: CareerSeason; catalog: TacticsCatalog } & Handlers) {
  const save = useMutation({
    mutationFn: (roles: Record<string, string | null>) => setCareerRoles(roles, season.rounds_played),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  const positions = new Set(season.slots.map((s) => s.ideal_position));
  const groups = (catalog.roles ?? []).filter((g) => g.positions.some((p) => positions.has(p)));
  if (!groups.length) return null;
  const roles = season.roles ?? {};

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div>
        <p className="font-display text-base font-bold text-ink-chalk">Роли игроков</p>
        <p className="text-[11px] text-ink-mist">Работают в единоборствах: сильнее в одном — слабее в другом.</p>
      </div>
      {groups.map((g) => {
        const value = roles[g.group] ?? NONE;
        const chosen = g.values.find((v) => v.value === value);
        return (
          <div key={g.group} className="flex flex-col gap-1">
            <p className="text-[11px] font-semibold text-ink-chalk">{g.label}</p>
            <Segmented
              label={g.label}
              value={value}
              options={[{ value: NONE, label: "Обычная" }, ...g.values.map((v) => ({ value: v.value, label: v.label }))]}
              onChange={(v) => save.mutate({ ...roles, [g.group]: v || null })}
            />
            <p className="text-[10px] leading-snug text-ink-mist-dim">{chosen ? chosen.hint : "Без особой роли: без бонусов и без слабостей."}</p>
          </div>
        );
      })}
    </section>
  );
}

function squadName(season: CareerSeason, cardId: number): string {
  const s = season.squad.find((x) => x.card_id === cardId);
  return s?.card?.player.display_name ?? s?.my_player?.name ?? `#${cardId}`;
}

/** Man-marking of the next opponent's star by one of my outfield players
 * (this round only): the star's duels get harder, but the marker helps less
 * in attack and leaves a gap when someone else draws him. */
export function MarkingCard({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const scouting = season.scouting;
  const save = useMutation({
    mutationFn: (marker: number | null) => setCareerMarking(marker, season.rounds_played),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  if (!scouting || (!scouting.star && !scouting.marks_you)) return null;
  const outfield = Object.entries(season.lineup)
    .filter(([code]) => season.slots.find((s) => s.code === code)?.category !== "GK")
    .map(([, cardId]) => cardId);
  const marker = scouting.marking?.marker ?? null;

  return (
    <section className="flex flex-col gap-2 rounded-3xl bg-bg-surface p-4">
      <p className="font-display text-base font-bold text-ink-chalk">Персональная опека</p>
      {scouting.star && (
        <>
          <div className="flex items-center gap-3 rounded-2xl bg-bg-raised p-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-400/15 font-mono text-sm font-bold text-amber-300">
              {scouting.star.rating}
            </span>
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-ink-mist">Звезда соперника · {scouting.star.position}</p>
              <p className="truncate text-sm font-semibold text-ink-chalk">{scouting.star.name}</p>
            </div>
          </div>
          <label className="flex flex-col gap-1 text-[11px] text-ink-mist">
            Опекает
            <select
              value={marker ?? ""}
              disabled={save.isPending}
              onChange={(e) => save.mutate(e.target.value ? Number(e.target.value) : null)}
              className="rounded-xl bg-bg-raised px-3 py-2 text-sm text-ink-chalk"
            >
              <option value="">Никто — играем зонно</option>
              {outfield.map((id) => <option key={id} value={id}>{squadName(season, id)}</option>)}
            </select>
          </label>
          <p className="text-[10px] leading-snug text-ink-mist-dim">
            Звезде труднее выигрывать единоборства, но опекун меньше помогает в атаке и оставляет зону, когда его
            отвлекают. Действует один тур.
          </p>
        </>
      )}
      {scouting.marks_you && (
        <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-[11px] text-amber-200">
          Соперник уровня «Легенда» возьмёт под опеку твоего лучшего игрока.
        </p>
      )}
    </section>
  );
}

/** What could still be added to the match plan. */
export function PlanHints({ season }: { season: CareerSeason }) {
  const hints = season.plan_hints ?? [];
  if (!hints.length) return null;
  return (
    <section className="flex flex-col gap-1.5 rounded-3xl bg-accent-lime/5 p-4 ring-1 ring-accent-lime/20">
      <p className="text-[10px] font-bold uppercase tracking-wider text-accent-lime">Подсказки к плану</p>
      {hints.map((h) => (
        <p key={h.code} className="text-xs leading-snug text-ink-chalk">• {h.text}</p>
      ))}
    </section>
  );
}
