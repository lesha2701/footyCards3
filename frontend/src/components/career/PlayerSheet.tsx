/** A player's card in «Карьера тренера» (a bottom sheet): who he is, his
 * energy and form, and what he does in the team — the role of his line,
 * marking the opponent's star, set pieces. Each change is saved right away
 * through the same endpoints as the cards of the prep screen. */
import { useMutation } from "@tanstack/react-query";
import type { ReactNode } from "react";

import {
  setCareerMarking,
  setCareerPlan,
  setCareerRoles,
  type CareerSeason,
  type CareerSetPieces,
  type CareerSquadCard,
  type CareerView,
  type TacticsCatalog,
} from "@/api/career";
import { EnergyBar } from "@/components/career/EnergyBar";
import { TAKERS, playerInfo } from "@/lib/careerRoles";
import { haptic } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

/** A bottom sheet over the page. */
function Sheet({ title, onClose, children }: { title: ReactNode; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/55" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="flex max-h-[80vh] w-full max-w-lg flex-col gap-3 overflow-y-auto rounded-t-3xl bg-bg-surface p-4 pb-[max(16px,env(safe-area-inset-bottom))]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">{title}</div>
          <button type="button" onClick={onClose} className="px-1 text-lg text-ink-mist" aria-label="Закрыть">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

const SET_PIECE_DEFAULTS: CareerSetPieces = {
  corner_taker: null, free_kick_taker: null, penalty_taker: null, corner_routine: "far", corner_defence: "zonal",
};

/** A player's card: who he is, his energy and form, and what he does —
 * the role of his line, marking the opponent's star, set pieces. Each
 * change is saved right away. */
export function PlayerSheet({ season, catalog, code, entry, onClose, onView, onError }: {
  season: CareerSeason; catalog: TacticsCatalog; code: string; entry: CareerSquadCard; onClose: () => void;
} & Handlers) {
  const info = playerInfo(entry)!;
  const slot = season.slots.find((s) => s.code === code);
  const keeper = slot?.category === "GK";
  const roles = season.roles ?? {};
  const group = (catalog.roles ?? []).find((g) => g.positions.includes(slot?.ideal_position ?? "") || g.positions.includes(info.position));
  const star = season.scouting?.star ?? null;
  const marker = season.scouting?.marking?.marker ?? null;
  const setPieces = { ...SET_PIECE_DEFAULTS, ...(season.set_pieces ?? {}) };
  const done = { onSuccess: (v: CareerView) => { haptic("light"); onView(v); }, onError };
  const saveRole = useMutation({ mutationFn: (value: string | null) => setCareerRoles({ ...roles, [group!.group]: value }, season.rounds_played), ...done });
  const saveMarking = useMutation({ mutationFn: (id: number | null) => setCareerMarking(id, season.rounds_played), ...done });
  const saveTaker = useMutation({
    mutationFn: (sp: CareerSetPieces) => setCareerPlan({
      rules: season.match_plan?.rules ?? [], subs: season.match_plan?.subs ?? [], round_index: season.rounds_played, set_pieces: sp,
    }),
    ...done,
  });
  const busy = saveRole.isPending || saveMarking.isPending || saveTaker.isPending;
  const role = group ? roles[group.group] ?? "" : "";

  return (
    <Sheet
      onClose={onClose}
      title={
        <div className="flex items-center gap-3">
          <img src={info.image} alt="" className="h-14 w-14 shrink-0 rounded-2xl bg-bg-raised object-cover object-top" />
          <div className="min-w-0">
            <p className="truncate font-display text-base font-bold text-ink-chalk">{info.name}</p>
            <p className="flex items-center gap-2 text-caption text-ink-mist">
              <span className="font-mono">{info.position} · {info.rating}</span>
              {entry.form !== 0 && (
                <span className={entry.form > 0 ? "text-accent-lime" : "text-red-400"}>форма {entry.form > 0 ? `+${entry.form}` : entry.form}</span>
              )}
            </p>
            <div className="mt-1 flex items-center gap-2"><EnergyBar fatigue={entry.fatigue} /></div>
          </div>
        </div>
      }
    >
      {(entry.injured_rounds > 0 || entry.suspended_rounds > 0) && (
        <p className="rounded-xl bg-red-500/15 px-3 py-2 text-caption font-semibold text-red-300">
          {entry.injured_rounds > 0 ? `Травма — пропустит ${entry.injured_rounds} т.` : `Дисквалификация — ${entry.suspended_rounds} т.`}
        </p>
      )}

      {group && (
        <div className="flex flex-col gap-1.5">
          <p className="text-caption font-semibold text-ink-chalk">Роль · {group.label.toLowerCase()}</p>
          <div className="flex flex-col gap-1.5" role="radiogroup" aria-label={`Роль: ${group.label}`}>
            {[{ value: "", label: "Обычная", hint: "Без особой роли: без бонусов и без слабостей." }, ...group.values].map((v) => (
              <button
                key={v.value}
                type="button"
                role="radio"
                aria-checked={role === v.value}
                disabled={busy}
                onClick={() => saveRole.mutate(v.value || null)}
                className={`flex flex-col rounded-xl px-3 py-2 text-left ${role === v.value ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"}`}
              >
                <span className="text-caption font-bold">{v.label}</span>
                <span className={`text-micro leading-snug ${role === v.value ? "text-bg-base/80" : "text-ink-mist"}`}>{v.hint}</span>
              </button>
            ))}
          </div>
          <p className="text-micro text-ink-mist-dim">Роль одна на всю линию: {group.label.toLowerCase()}.</p>
        </div>
      )}

      {star && !keeper && (
        <div className="flex flex-col gap-1.5">
          <p className="text-caption font-semibold text-ink-chalk">Персональная опека</p>
          <button
            type="button"
            disabled={busy}
            onClick={() => saveMarking.mutate(marker === entry.card_id ? null : entry.card_id)}
            className={`rounded-xl px-3 py-2 text-left text-caption font-semibold ${marker === entry.card_id ? "bg-amber-300 text-bg-base" : "bg-bg-raised text-ink-chalk"}`}
          >
            {marker === entry.card_id ? `Опекает ${star.name} — снять` : `Опекать звезду: ${star.name} (${star.position}, ${star.rating})`}
          </button>
          <p className="text-micro leading-snug text-ink-mist-dim">Звезде труднее в единоборствах, но опекун меньше помогает в атаке. Один тур.</p>
        </div>
      )}

      {!keeper && entry.owned && (
        <div className="flex flex-col gap-1.5">
          <p className="text-caption font-semibold text-ink-chalk">Стандарты</p>
          <div className="grid grid-cols-3 gap-1.5">
            {TAKERS.map((t) => {
              const on = setPieces[t.key] === entry.card_id;
              return (
                <button
                  key={t.key}
                  type="button"
                  aria-pressed={on}
                  disabled={busy}
                  onClick={() => saveTaker.mutate({ ...setPieces, [t.key]: on ? null : entry.card_id })}
                  className={`rounded-xl px-2 py-2 text-caption font-semibold ${on ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-mist"}`}
                >
                  {t.icon} {t.label}
                </button>
              );
            })}
          </div>
          <p className="text-micro text-ink-mist-dim">Без выбора подаёт лучший подходящий.</p>
        </div>
      )}
    </Sheet>
  );
}

