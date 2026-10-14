import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  setCareerPlan,
  type CareerSeason,
  type CareerSetPieces,
  type CareerSquadWarning,
  type CareerView,
  type TacticsCatalog,
} from "@/api/career";
import { haptic } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

const DEFAULTS: CareerSetPieces = {
  corner_taker: null, free_kick_taker: null, penalty_taker: null, corner_routine: "far", corner_defence: "zonal",
};
const TAKERS: { key: "corner_taker" | "free_kick_taker" | "penalty_taker"; label: string; icon: string }[] = [
  { key: "corner_taker", label: "Угловые", icon: "🚩" },
  { key: "free_kick_taker", label: "Штрафные", icon: "🎯" },
  { key: "penalty_taker", label: "Пенальти", icon: "⚽" },
];

/** Who takes corners / free kicks / penalties, how corners are delivered
 * and how the team defends them. Saved with the match plan. */
export function SetPiecesCard({ season, catalog, onView, onError }: {
  season: CareerSeason; catalog: TacticsCatalog;
} & Handlers) {
  const saved = { ...DEFAULTS, ...(season.set_pieces ?? {}) };
  const savedKey = JSON.stringify(saved);
  const [value, setValue] = useState<CareerSetPieces>(saved);
  useEffect(() => setValue(JSON.parse(savedKey) as CareerSetPieces), [savedKey]);
  const dirty = JSON.stringify(value) !== savedKey;
  const options = catalog.set_pieces;
  const save = useMutation({
    mutationFn: () => setCareerPlan({
      rules: season.match_plan?.rules ?? [], subs: season.match_plan?.subs ?? [],
      round_index: season.rounds_played, set_pieces: value,
    }),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  const squad = season.squad
    .filter((s) => s.owned && (s.card?.player.position ?? s.my_player?.position) !== "GK")
    .map((s) => ({
      id: s.card_id,
      label: s.card ? `${s.card.player.display_name} · ${s.card.player.position} · ${s.card.player.rating}`
        : s.my_player ? `${s.my_player.name} · ${s.my_player.position}` : `#${s.card_id}`,
    }));

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div>
        <p className="font-display text-base font-bold text-ink-chalk">Стандарты и пенальти</p>
        <p className="text-[11px] leading-snug text-ink-mist">
          Угловые бывают после заблокированных и отбитых ударов, штрафные — после фолов вне штрафной.
          Если исполнителя нет на поле, подаст лучший подходящий.
        </p>
      </div>
      <div className="flex flex-col gap-1.5">
        {TAKERS.map((t) => (
          <label key={t.key} className="flex items-center gap-2 rounded-xl bg-bg-raised px-3 py-2">
            <span className="w-24 shrink-0 text-[11px] font-semibold text-ink-chalk">{t.icon} {t.label}</span>
            <select
              aria-label={t.label}
              value={value[t.key] ?? ""}
              onChange={(e) => setValue({ ...value, [t.key]: e.target.value ? Number(e.target.value) : null })}
              className="min-w-0 flex-1 rounded-lg bg-bg-base/60 px-2 py-1.5 text-[11px] text-ink-chalk outline-none"
            >
              <option value="">Авто — лучший подходящий</option>
              {squad.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
          </label>
        ))}
      </div>
      {options && (
        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-accent-cyan">Подача углового</span>
            {options.routines.map((r) => (
              <button key={r.value} onClick={() => setValue({ ...value, corner_routine: r.value })}
                className={`rounded-xl px-2 py-2 text-[11px] font-semibold ${value.corner_routine === r.value ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-mist"}`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-accent-cyan">Защита на стандартах</span>
            {options.defences.map((d) => (
              <button key={d.value} onClick={() => setValue({ ...value, corner_defence: d.value })}
                className={`rounded-xl px-2 py-2 text-[11px] font-semibold ${value.corner_defence === d.value ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-mist"}`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
      )}
      {options && (
        <p className="text-[10px] leading-snug text-ink-mist-dim">
          {options.routines.map((r) => `${r.label.toLowerCase()} опаснее против «${(options.defences.find((d) => d.value === options.beats[r.value])?.label ?? "").toLowerCase()}»`).join(", ")}.
        </p>
      )}
      <button
        onClick={() => save.mutate()}
        disabled={!dirty || save.isPending}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {save.isPending ? "Сохраняем..." : dirty ? "Сохранить стандарты" : "Стандарты сохранены"}
      </button>
    </section>
  );
}

/** Holes / thin lines in the squad for the next round (server-computed). */
export function SquadWarnings({ warnings }: { warnings: CareerSquadWarning[] | undefined }) {
  if (!warnings?.length) return null;
  return (
    <div className="flex flex-col gap-1.5" role="alert">
      {warnings.map((w, i) => (
        <p key={i} className={`rounded-2xl px-3 py-2 text-[11px] leading-snug ${
          w.level === "critical" ? "bg-red-500/15 text-red-300" : "bg-amber-400/10 text-amber-200"}`}
        >
          {w.level === "critical" ? "⚠️ " : "ℹ️ "}{w.text}
        </p>
      ))}
    </div>
  );
}
