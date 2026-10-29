/** The tactics board of «Карьера тренера»: the team on a pitch with the
 * tactic drawn over it (attack arrows, the defensive line at its height,
 * the pressing zone), tactic chips that open a choice with hints, the
 * mentality as a thermometer, and a player card on a tap — role, marking
 * of the opponent's star and set-piece duties, saved through the same
 * endpoints as before. Purely a view of the existing settings: the match
 * engine and its numbers are unchanged. */
import { useMutation } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import {
  setCareerMarking,
  setCareerPlan,
  setCareerRoles,
  type CareerSeason,
  type CareerSetPieces,
  type CareerView,
  type Tactic,
  type TacticsCatalog,
} from "@/api/career";
import { EnergyBar } from "@/components/career/EnergyBar";
import { BOARD_AXES, LINE_Y, boardLayout, playerInfo, type BoardPlayer } from "@/lib/careerBoard";
import { energyLevel, energyOf } from "@/lib/careerEnergy";
import { MENTALITIES } from "@/lib/clubTactics";
import { haptic, hapticSelection } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

/** The board's grass: a photo texture (the 3D free kick's), mowing stripes
 * and a light shade over it so the drawing on top reads. */
const GRASS = {
  backgroundImage: [
    "linear-gradient(rgba(6,20,12,0.28), rgba(6,20,12,0.38))",
    "repeating-linear-gradient(180deg, rgba(255,255,255,0.07) 0 7.14%, rgba(0,0,0,0.06) 7.14% 14.28%)",
    "url(/career/grass.webp)",
  ].join(", "),
  backgroundSize: "100% 100%, 100% 100%, 35% auto",
};
const MENTALITY_TONE: Record<string, string> = {
  PARK_THE_BUS: "#38bdf8", DEFENSIVE: "#22d3c4", BALANCED: "#c6e63a", ATTACKING: "#f87171",
};

const ENERGY_FILL = { fresh: "#c6e63a", tired: "#fcd34d", spent: "#f87171" };

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

/** The pitch with the team and the tactic drawn on it. */
export function TacticBoard({ season, catalog, formation, tactic, setTactic, mentality, setMentality, onView, onError }: {
  season: CareerSeason; catalog: TacticsCatalog; formation: string;
  tactic: Tactic; setTactic: (t: Tactic) => void;
  mentality: string; setMentality: (m: string) => void;
} & Handlers) {
  const [axisOpen, setAxisOpen] = useState<string | null>(null);
  const [playerOpen, setPlayerOpen] = useState<BoardPlayer | null>(null);
  const block = tactic.block ?? "mid";
  const y = LINE_Y[block] ?? LINE_Y.mid;
  const lineup = formation === season.formation ? season.lineup : {};
  const players = boardLayout(formation, block, lineup, season.squad);
  const wings = tactic.direction !== "center";
  const center = tactic.direction !== "wings";
  const arrowW = tactic.direction === "mixed" ? 1.6 : 2.4;
  const lit = (axis: string) => (axisOpen === axis ? 1 : axisOpen ? 0.25 : 0.9);
  const axisDef = (key: string) => catalog.axes.find((a) => a.key === key);
  const valueLabel = (key: string) => axisDef(key)?.values.find((v) => v.value === tactic[key])?.label ?? "—";

  return (
    <div className="flex flex-col gap-2">
      <div className="relative overflow-hidden rounded-2xl" style={GRASS}>
        <svg viewBox="0 0 100 140" className="block h-auto w-full touch-manipulation select-none" role="img" aria-label="Тактическая доска">
          <defs>
            <marker id="tb-arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="#c6e63a" />
            </marker>
            {players.map((p) => (
              <clipPath key={p.code} id={`tb-clip-${p.code}`}><circle cx={p.x} cy={p.y} r="4.6" /></clipPath>
            ))}
          </defs>
          <g fill="none" stroke="#ffffff" strokeOpacity="0.55" strokeWidth="0.5">
            <rect x="3" y="3" width="94" height="134" rx="1.5" />
            <line x1="3" y1="70" x2="97" y2="70" />
            <circle cx="50" cy="70" r="9" />
            <rect x="24" y="3" width="52" height="17" />
            <rect x="37" y="3" width="26" height="6" />
            <rect x="24" y="120" width="52" height="17" />
            <rect x="37" y="131" width="26" height="6" />
          </g>

          {/* Pressing zone: up the pitch for a high block, deep for a low one. */}
          <g opacity={lit("block")} onClick={() => setAxisOpen("block")} className="cursor-pointer">
            {block === "high" && <rect x="3" y="3" width="94" height={y.FWD - 3} fill="#22d3c4" opacity="0.1" />}
            {block === "low" && <rect x="3" y={y.MID - 6} width="94" height={137 - (y.MID - 6)} fill="#22d3c4" opacity="0.09" />}
            <line x1="5" y1={y.DEF + 7} x2="95" y2={y.DEF + 7} stroke="#22d3c4" strokeWidth="0.9" strokeDasharray="2.2 1.6" />
            <rect x="3" y={y.DEF + 3} width="94" height="8" fill="transparent" />
          </g>
          {/* After losing the ball: closing in (arrows inwards) or dropping (arrows back). */}
          <g opacity={lit("on_loss")} stroke="#22d3c4" strokeWidth="0.8" fill="none" markerEnd="url(#tb-arrow)">
            {tactic.on_loss === "counterpress" ? (
              <>
                <path d={`M30 ${y.MID - 2} L38 ${y.MID - 8}`} />
                <path d={`M70 ${y.MID - 2} L62 ${y.MID - 8}`} />
              </>
            ) : (
              <>
                <path d={`M30 ${y.MID - 6} L30 ${y.MID + 3}`} />
                <path d={`M70 ${y.MID - 6} L70 ${y.MID + 3}`} />
              </>
            )}
          </g>
          {/* Attack: down the wings and/or through the middle; passing pattern. */}
          <g opacity={lit("direction")} stroke="#c6e63a" fill="none" strokeLinecap="round" markerEnd="url(#tb-arrow)"
            onClick={() => setAxisOpen("direction")} className="cursor-pointer">
            {wings && (
              <>
                <path d={`M14 ${y.MID} C 6 ${y.FWD}, 8 28, 26 14`} strokeWidth={arrowW} />
                <path d={`M86 ${y.MID} C 94 ${y.FWD}, 92 28, 74 14`} strokeWidth={arrowW} />
              </>
            )}
            {center && <path d={`M50 ${y.MID - 6} L50 16`} strokeWidth={arrowW} />}
          </g>
          <g opacity={lit("buildup")} fill="none" stroke="#8fe3b8" strokeWidth="0.8">
            {tactic.buildup === "direct" && <path d={`M40 ${y.DEF - 2} L46 22`} strokeDasharray="3 2" markerEnd="url(#tb-arrow)" />}
            {tactic.buildup !== "direct" && (
              <polyline points={`36,${y.DEF - 6} 42,${y.MID + 6} 48,${y.MID + 12} 54,${y.MID + 4} 60,${y.MID + 10}`} strokeDasharray="1.5 1.5" />
            )}
          </g>
          {tactic.on_win === "fast" && (
            <g opacity={lit("on_win")} stroke="#fcd34d" strokeWidth="0.8" fill="none" markerEnd="url(#tb-arrow)">
              <path d={`M58 ${y.DEF - 4} L66 ${y.FWD + 4}`} strokeDasharray="0.5 1.6" strokeLinecap="round" />
            </g>
          )}

          {/* The team: photo, rating, energy. */}
          {players.map((p) => {
            const info = playerInfo(p.entry);
            const energy = p.entry ? energyOf(p.entry.fatigue) : 100;
            const out = p.entry && (p.entry.injured_rounds > 0 || p.entry.suspended_rounds > 0);
            return (
              <g key={p.code} onClick={() => { if (info) { hapticSelection(); setPlayerOpen(p); } }}
                className={info ? "cursor-pointer" : ""} role={info ? "button" : undefined} aria-label={info ? `${info.name}, ${info.position}` : `${p.code}: пусто`}>
                <circle cx={p.x} cy={p.y} r="5.2" fill="#0b1a12" stroke={out ? "#f87171" : "#ffffff"} strokeOpacity={out ? 1 : 0.7} strokeWidth="0.5" />
                {info ? (
                  <image href={info.image} x={p.x - 4.6} y={p.y - 4.6} width="9.2" height="9.2" clipPath={`url(#tb-clip-${p.code})`} preserveAspectRatio="xMidYMin slice" />
                ) : (
                  <text x={p.x} y={p.y + 1.3} textAnchor="middle" fontSize="3.6" fill="#ffffff" opacity="0.5">+</text>
                )}
                {info && (
                  <>
                    <rect x={p.x + 2.4} y={p.y - 6.4} width="5" height="3.2" rx="0.8" fill="#0b1a12" />
                    <text x={p.x + 4.9} y={p.y - 4} textAnchor="middle" fontSize="2.4" fontWeight="700" fill="#ffffff" style={{ fontFamily: "ui-monospace, monospace" }}>{info.rating}</text>
                    <rect x={p.x - 4.5} y={p.y + 5.6} width="9" height="1" rx="0.5" fill="#ffffff" opacity="0.15" />
                    <rect x={p.x - 4.5} y={p.y + 5.6} width={(9 * energy) / 100} height="1" rx="0.5" fill={ENERGY_FILL[energyLevel(energy)]} />
                    <text x={p.x} y={p.y + 9.4} textAnchor="middle" fontSize="2.5" fill="#ffffff" style={{ paintOrder: "stroke" }} stroke="#0b1a12" strokeWidth="0.6">
                      {info.short.length > 11 ? `${info.short.slice(0, 10)}…` : info.short}
                    </text>
                  </>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Mentality: a thermometer from parking the bus to all-out attack. */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between text-micro text-ink-mist">
          <span>Настрой</span>
          <span className="font-semibold text-ink-chalk">{MENTALITIES.find((m) => m.value === mentality)?.label}</span>
        </div>
        <div className="grid grid-cols-4 gap-1" role="radiogroup" aria-label="Настрой">
          {MENTALITIES.map((m) => (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={mentality === m.value}
              aria-label={m.label}
              onClick={() => { hapticSelection(); setMentality(m.value); }}
              className="h-2.5 rounded-full transition-opacity"
              style={{ background: MENTALITY_TONE[m.value], opacity: mentality === m.value ? 1 : 0.25 }}
            />
          ))}
        </div>
        <div className="flex justify-between text-micro text-ink-mist-dim"><span>Автобус</span><span>Атака</span></div>
      </div>

      {/* The tactic, in two groups; a tap opens the choice with hints. */}
      {(["attack", "defence"] as const).map((group) => (
        <div key={group} className="flex flex-col gap-1">
          <p className={`text-micro font-bold uppercase tracking-[0.12em] ${group === "attack" ? "text-accent-lime" : "text-accent-cyan"}`}>
            {group === "attack" ? "Атака" : "Оборона"}
          </p>
          <div className="grid grid-cols-3 gap-1.5">
            {BOARD_AXES.filter((a) => a.group === group).map((a) => {
              const def = axisDef(a.key);
              if (!def) return null;
              return (
                <button
                  key={a.key}
                  type="button"
                  onClick={() => setAxisOpen(a.key)}
                  className="flex min-w-0 flex-col items-start rounded-xl bg-bg-raised px-2 py-1.5 text-left active:bg-white/5"
                  aria-label={`${def.label}: ${valueLabel(a.key)}`}
                >
                  <span className="w-full truncate text-micro text-ink-mist">{a.icon} {def.label}</span>
                  <span className="w-full truncate text-caption font-semibold text-ink-chalk">{valueLabel(a.key)}</span>
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {axisOpen && axisDef(axisOpen) && (
        <Sheet title={<p className="font-display text-base font-bold text-ink-chalk">{axisDef(axisOpen)!.label}</p>} onClose={() => setAxisOpen(null)}>
          <div className="flex flex-col gap-2" role="radiogroup" aria-label={axisDef(axisOpen)!.label}>
            {axisDef(axisOpen)!.values.map((v) => {
              const on = tactic[axisOpen] === v.value;
              return (
                <button
                  key={v.value}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => { hapticSelection(); setTactic({ ...tactic, [axisOpen]: v.value }); }}
                  className={`flex flex-col gap-0.5 rounded-2xl px-3 py-2.5 text-left ${on ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk active:bg-white/5"}`}
                >
                  <span className="text-sm font-bold">{v.label}</span>
                  <span className={`text-caption leading-snug ${on ? "text-bg-base/80" : "text-ink-mist"}`}>{v.hint}</span>
                </button>
              );
            })}
          </div>
          <p className="text-micro text-ink-mist-dim">Изменение применится после «Сохранить тактику».</p>
        </Sheet>
      )}

      {playerOpen && (
        <PlayerSheet season={season} catalog={catalog} player={playerOpen} onClose={() => setPlayerOpen(null)} onView={onView} onError={onError} />
      )}
    </div>
  );
}

const TAKERS: { key: "corner_taker" | "free_kick_taker" | "penalty_taker"; label: string; icon: string }[] = [
  { key: "corner_taker", label: "Угловые", icon: "🚩" },
  { key: "free_kick_taker", label: "Штрафные", icon: "🎯" },
  { key: "penalty_taker", label: "Пенальти", icon: "⚽" },
];
const SET_PIECE_DEFAULTS: CareerSetPieces = {
  corner_taker: null, free_kick_taker: null, penalty_taker: null, corner_routine: "far", corner_defence: "zonal",
};

/** A player's card: who he is, his energy and form, and what he does —
 * the role of his line, marking the opponent's star, set pieces. Each
 * change is saved right away. */
function PlayerSheet({ season, catalog, player, onClose, onView, onError }: {
  season: CareerSeason; catalog: TacticsCatalog; player: BoardPlayer; onClose: () => void;
} & Handlers) {
  const entry = player.entry!;
  const info = playerInfo(entry)!;
  const slot = season.slots.find((s) => s.code === player.code);
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
