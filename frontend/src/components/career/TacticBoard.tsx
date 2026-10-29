/** The tactics board of «Карьера тренера», two views of one drawn pitch:
 * «Тактика» — the team's settings placed on the pitch where they act (a
 * tap opens the options right there) with the tactic drawn over it and
 * the mentality as a thermometer beside it; «Роли игроков» — the line-up
 * with roles and duties, a tap opens the player's card (role, marking of
 * the opponent's star, set pieces; saved through the same endpoints as
 * before). Only a view of the existing settings: the match engine and its
 * numbers are unchanged. */
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

/** The board's pitch, drawn for it (crisp at any size): bright grass in
 * wide mowing bands with a fine texture, a soft light from the middle and a
 * vignette, clean white markings with a faint shadow. `id` keeps the SVG
 * defs of two boards on a page apart. */
function PitchMarkings({ id = "p" }: { id?: string }) {
  const bands = 12;
  return (
    <g>
      <defs>
        <radialGradient id={`${id}-light`} cx="50%" cy="45%" r="70%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.18" />
          <stop offset="60%" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="100%" stopColor="#0b2a12" stopOpacity="0.35" />
        </radialGradient>
        <filter id={`${id}-grain`} x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="2" seed="7" result="n" />
          <feColorMatrix in="n" type="matrix" values="0 0 0 0 0.08  0 0 0 0 0.25  0 0 0 0 0.06  0 0 0 0.35 0" />
        </filter>
        <filter id={`${id}-shadow`} x="-5%" y="-5%" width="110%" height="110%">
          <feDropShadow dx="0" dy="0.25" stdDeviation="0.25" floodColor="#0b2a12" floodOpacity="0.45" />
        </filter>
      </defs>
      <rect x="0" y="0" width="100" height="140" fill="#4f9a3a" />
      {Array.from({ length: bands }, (_, i) => (
        <rect key={i} x="0" y={(140 / bands) * i} width="100" height={140 / bands} fill={i % 2 ? "#5aa843" : "#4c9437"} />
      ))}
      <rect x="0" y="0" width="100" height="140" filter={`url(#${id}-grain)`} />
      <rect x="0" y="0" width="100" height="140" fill={`url(#${id}-light)`} />
      <g fill="none" stroke="#ffffff" strokeOpacity="0.92" strokeWidth="0.55" filter={`url(#${id}-shadow)`}>
        <rect x="4" y="4" width="92" height="132" />
        <line x1="4" y1="70" x2="96" y2="70" />
        <circle cx="50" cy="70" r="9" />
        <rect x="25" y="4" width="50" height="16" />
        <rect x="37.5" y="4" width="25" height="5.5" />
        <path d="M 42 20 A 9 9 0 0 0 58 20" />
        <rect x="25" y="120" width="50" height="16" />
        <rect x="37.5" y="130.5" width="25" height="5.5" />
        <path d="M 42 120 A 9 9 0 0 1 58 120" />
        <rect x="44" y="2" width="12" height="2" strokeOpacity="0.7" />
        <rect x="44" y="136" width="12" height="2" strokeOpacity="0.7" />
      </g>
      <g fill="#ffffff" fillOpacity="0.92">
        <circle cx="50" cy="70" r="0.6" />
        <circle cx="50" cy="15" r="0.5" />
        <circle cx="50" cy="125" r="0.5" />
      </g>
    </g>
  );
}

/** Where each control sits on the tactics pitch (% of its box), by line height. */
function controlSpots(y: { DEF: number; MID: number; FWD: number }): Record<string, { left: number; top: number; up?: boolean }> {
  const pct = (v: number) => (v / 140) * 100;
  return {
    direction: { left: 27, top: 3 },
    on_win: { left: 52, top: pct(y.FWD) - 4 },
    buildup: { left: 3, top: pct(y.MID) - 12 },
    on_loss: { left: 52, top: pct(y.MID) + 1 },
    block: { left: 3, top: pct(y.DEF) + 6, up: true },
    tackling: { left: 52, top: 86, up: true },
  };
}

/** A setting placed on the pitch: its name and value; a tap opens the
 * options right there (with the chosen one's hint). */
function PitchControl({ axis, label, values, value, open, onOpen, onPick, spot }: {
  axis: string; label: string; values: { value: string; label: string; hint: string }[]; value: string | undefined;
  open: boolean; onOpen: () => void; onPick: (v: string) => void; spot: { left: number; top: number; up?: boolean };
}) {
  const current = values.find((v) => v.value === value);
  const meta = BOARD_AXES.find((a) => a.key === axis);
  return (
    <div className="absolute w-[45%]" style={{ left: `${spot.left}%`, top: `${spot.top}%`, zIndex: open ? 20 : 10 }}>
      <button
        type="button"
        onClick={onOpen}
        aria-expanded={open}
        aria-label={`${label}: ${current?.label ?? "—"}`}
        className={`flex w-full flex-col items-start rounded-lg px-2 py-1 text-left shadow-md backdrop-blur-sm ${
          open ? "bg-floodlight text-bg-base" : "bg-black/60 text-white active:bg-black/75"}`}
      >
        <span className={`w-full truncate text-[9px] uppercase tracking-wider ${open ? "text-bg-base/70" : "text-white/65"}`}>{meta?.icon} {meta?.short ?? label}</span>
        <span className="flex w-full items-center gap-1 text-caption font-bold">
          <span className="min-w-0 flex-1 truncate">{current?.label ?? "—"}</span>
          <span className="text-micro opacity-70">▾</span>
        </span>
      </button>
      {open && (
        <div className={`absolute inset-x-0 flex flex-col gap-1 rounded-xl bg-bg-surface p-1.5 shadow-xl ring-1 ring-white/10 ${spot.up ? "bottom-full mb-1" : "top-full mt-1"}`}
          role="radiogroup" aria-label={label}>
          {values.map((v) => (
            <button
              key={v.value}
              type="button"
              role="radio"
              aria-checked={v.value === value}
              aria-label={v.label}
              onClick={() => onPick(v.value)}
              className={`rounded-lg px-2 py-1.5 text-left text-caption font-semibold ${
                v.value === value ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk active:bg-white/5"}`}
            >
              {v.label}
            </button>
          ))}
          {current && <p className="px-1 pt-0.5 text-micro leading-snug text-ink-mist">{current.hint}</p>}
        </div>
      )}
    </div>
  );
}

const VIEWS = [
  { key: "tactic", label: "Тактика" },
  { key: "roles", label: "Роли игроков" },
] as const;

/** Two views of one pitch: «Тактика» — the team's settings placed on the
 * pitch where they act, the mentality as a thermometer beside it; «Роли
 * игроков» — the line-up with each player's role and duties, a tap opens
 * his card. */
export function TacticBoard({ season, catalog, formation, tactic, setTactic, mentality, setMentality, onView, onError }: {
  season: CareerSeason; catalog: TacticsCatalog; formation: string;
  tactic: Tactic; setTactic: (t: Tactic) => void;
  mentality: string; setMentality: (m: string) => void;
} & Handlers) {
  const [view, setView] = useState<"tactic" | "roles">("tactic");
  const [axisOpen, setAxisOpen] = useState<string | null>(null);
  const [playerOpen, setPlayerOpen] = useState<BoardPlayer | null>(null);
  const block = tactic.block ?? "mid";
  const y = LINE_Y[block] ?? LINE_Y.mid;
  const wings = tactic.direction !== "center";
  const center = tactic.direction !== "wings";
  const arrowW = tactic.direction === "mixed" ? 1.6 : 2.4;
  const lit = (axis: string) => (axisOpen === axis ? 1 : axisOpen ? 0.25 : 0.9);
  const spots = controlSpots(y);

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-1 rounded-2xl bg-bg-base/40 p-1" role="tablist" aria-label="Доска">
        {VIEWS.map((v) => (
          <button key={v.key} type="button" role="tab" aria-selected={view === v.key}
            onClick={() => { setView(v.key); setAxisOpen(null); }}
            className={`rounded-xl py-1.5 text-caption font-semibold ${view === v.key ? "bg-bg-raised text-ink-chalk" : "text-ink-mist"}`}>
            {v.label}
          </button>
        ))}
      </div>

      {view === "tactic" && (
        <div className="flex items-stretch gap-2">
          <div className="relative min-w-0 flex-1 overflow-hidden rounded-2xl ring-1 ring-black/30">
            <svg viewBox="0 0 100 140" className="block h-auto w-full select-none" role="img" aria-label="Тактическая доска"
              onClick={() => setAxisOpen(null)}>
              <defs>
                <marker id="tb-arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
                  <path d="M0 0 L10 5 L0 10 z" fill="#ffffff" />
                </marker>
              </defs>
              <PitchMarkings id="tb-t" />
              {/* Pressing zone and the defensive line at its height. */}
              <g opacity={lit("block")}>
                {block === "high" && <rect x="4" y="4" width="92" height={y.FWD - 4} fill="#38bdf8" opacity="0.22" />}
                {block === "low" && <rect x="4" y={y.MID - 6} width="92" height={136 - (y.MID - 6)} fill="#38bdf8" opacity="0.2" />}
                <line x1="5" y1={y.DEF + 4} x2="95" y2={y.DEF + 4} stroke="#facc15" strokeWidth="1.1" strokeDasharray="2.2 1.6" />
              </g>
              <g opacity={lit("on_loss")} stroke="#7dd3fc" strokeWidth="1" fill="none" markerEnd="url(#tb-arrow)">
                {tactic.on_loss === "counterpress" ? (
                  <>
                    <path d={`M28 ${y.MID + 10} L37 ${y.MID + 3}`} />
                    <path d={`M72 ${y.MID + 10} L63 ${y.MID + 3}`} />
                  </>
                ) : (
                  <>
                    <path d={`M30 ${y.MID + 2} L30 ${y.MID + 12}`} />
                    <path d={`M70 ${y.MID + 2} L70 ${y.MID + 12}`} />
                  </>
                )}
              </g>
              <g opacity={lit("direction")} stroke="#ffffff" fill="none" strokeLinecap="round" markerEnd="url(#tb-arrow)">
                {wings && (
                  <>
                    <path d={`M14 ${y.MID} C 6 ${y.FWD}, 8 30, 24 18`} strokeWidth={arrowW} />
                    <path d={`M86 ${y.MID} C 94 ${y.FWD}, 92 30, 76 18`} strokeWidth={arrowW} />
                  </>
                )}
                {center && <path d={`M50 ${y.MID - 2} L50 20`} strokeWidth={arrowW} />}
              </g>
              <g opacity={lit("buildup")} fill="none" stroke="#fef08a" strokeWidth="1">
                {tactic.buildup === "direct" && <path d={`M40 ${y.DEF - 2} L46 24`} strokeDasharray="3 2" markerEnd="url(#tb-arrow)" />}
                {tactic.buildup !== "direct" && (
                  <polyline points={`36,${y.DEF - 4} 42,${y.MID + 8} 48,${y.MID + 14} 54,${y.MID + 6} 60,${y.MID + 12}`} strokeDasharray="1.5 1.5" />
                )}
              </g>
              {tactic.on_win === "fast" && (
                <g opacity={lit("on_win")} stroke="#fde047" strokeWidth="1" fill="none" markerEnd="url(#tb-arrow)">
                  <path d={`M60 ${y.DEF - 4} L68 ${y.FWD + 6}`} strokeDasharray="0.5 1.6" strokeLinecap="round" />
                </g>
              )}
              {tactic.tackling && tactic.tackling !== "normal" && (
                <g opacity={lit("tackling")}>
                  <circle cx="50" cy={y.DEF - 10} r="5" fill={tactic.tackling === "hard" ? "#f87171" : "#8fe3b8"} opacity="0.25" />
                </g>
              )}
            </svg>
            {BOARD_AXES.map((a) => {
              const def = catalog.axes.find((x) => x.key === a.key);
              if (!def) return null;
              return (
                <PitchControl
                  key={a.key} axis={a.key} label={def.label} values={def.values} value={tactic[a.key]}
                  open={axisOpen === a.key} spot={spots[a.key]}
                  onOpen={() => setAxisOpen(axisOpen === a.key ? null : a.key)}
                  onPick={(v) => { hapticSelection(); setTactic({ ...tactic, [a.key]: v }); setAxisOpen(null); }}
                />
              );
            })}
          </div>

          {/* Mentality: a thermometer from attack (top) to parking the bus. */}
          <div className="flex w-9 shrink-0 flex-col items-center gap-1">
            <span className="text-[9px] font-bold uppercase text-red-300">Атака</span>
            <div className="flex w-4 flex-1 flex-col-reverse gap-1" role="radiogroup" aria-label="Настрой">
              {MENTALITIES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  role="radio"
                  aria-checked={mentality === m.value}
                  aria-label={m.label}
                  title={m.label}
                  onClick={() => { hapticSelection(); setMentality(m.value); }}
                  className={`flex-1 rounded-full transition-all ${mentality === m.value ? "ring-2 ring-white" : ""}`}
                  style={{ background: MENTALITY_TONE[m.value], opacity: mentality === m.value ? 1 : 0.3 }}
                />
              ))}
            </div>
            <span className="text-[9px] font-bold uppercase text-sky-300">Защита</span>
          </div>
        </div>
      )}
      {view === "tactic" && (
        <p className="text-center text-micro text-ink-mist">
          Настрой: <span className="font-semibold text-ink-chalk">{MENTALITIES.find((m) => m.value === mentality)?.label}</span>
          {" · "}нажми на настройку на поле, чтобы изменить
        </p>
      )}

      {view === "roles" && <RolesPitch season={season} catalog={catalog} formation={formation} block={block} onPick={setPlayerOpen} />}

      {playerOpen && (
        <PlayerSheet season={season} catalog={catalog} player={playerOpen} onClose={() => setPlayerOpen(null)} onView={onView} onError={onError} />
      )}
    </div>
  );
}

/** The line-up on the pitch with each player's role and duties under him. */
function RolesPitch({ season, catalog, formation, block, onPick }: {
  season: CareerSeason; catalog: TacticsCatalog; formation: string; block: string; onPick: (p: BoardPlayer) => void;
}) {
  const lineup = formation === season.formation ? season.lineup : {};
  const players = boardLayout(formation, block, lineup, season.squad);
  const roles = season.roles ?? {};
  const marker = season.scouting?.marking?.marker ?? null;
  const sp = season.set_pieces ?? null;
  const roleOf = (code: string, position: string) => {
    const slot = season.slots.find((s) => s.code === code);
    const group = (catalog.roles ?? []).find((g) => g.positions.includes(slot?.ideal_position ?? "") || g.positions.includes(position));
    const value = group ? roles[group.group] : undefined;
    return group && value ? group.values.find((v) => v.value === value)?.label ?? null : null;
  };
  return (
    <div className="flex flex-col gap-1.5">
      <div className="relative overflow-hidden rounded-2xl ring-1 ring-black/30">
        <svg viewBox="0 0 100 140" className="block h-auto w-full touch-manipulation select-none" role="img" aria-label="Роли игроков на поле">
          <defs>
            {players.map((p) => (
              <clipPath key={p.code} id={`tb-clip-${p.code}`}><circle cx={p.x} cy={p.y} r="4.6" /></clipPath>
            ))}
          </defs>
          <PitchMarkings id="tb-r" />
          {players.map((p) => {
            const info = playerInfo(p.entry);
            const energy = p.entry ? energyOf(p.entry.fatigue) : 100;
            const out = p.entry && (p.entry.injured_rounds > 0 || p.entry.suspended_rounds > 0);
            const role = info ? roleOf(p.code, info.position) : null;
            const duties = p.entry ? [
              marker === p.entry.card_id ? "👁" : "",
              sp?.corner_taker === p.entry.card_id ? "🚩" : "",
              sp?.free_kick_taker === p.entry.card_id ? "🎯" : "",
              sp?.penalty_taker === p.entry.card_id ? "⚽" : "",
            ].join("") : "";
            return (
              <g key={p.code} onClick={() => { if (info) { hapticSelection(); onPick(p); } }}
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
                    {duties && <text x={p.x - 6.6} y={p.y - 3.6} fontSize="2.6">{duties}</text>}
                    <rect x={p.x - 4.5} y={p.y + 5.6} width="9" height="1" rx="0.5" fill="#ffffff" opacity="0.15" />
                    <rect x={p.x - 4.5} y={p.y + 5.6} width={(9 * energy) / 100} height="1" rx="0.5" fill={ENERGY_FILL[energyLevel(energy)]} />
                    <text x={p.x} y={p.y + 9.4} textAnchor="middle" fontSize="2.5" fill="#ffffff" style={{ paintOrder: "stroke" }} stroke="#0b1a12" strokeWidth="0.6">
                      {info.short.length > 11 ? `${info.short.slice(0, 10)}…` : info.short}
                    </text>
                    {role && (
                      <g>
                        <rect x={p.x - 7} y={p.y + 10.6} width="14" height="3.4" rx="1.2" fill="#c6e63a" />
                        <text x={p.x} y={p.y + 13.1} textAnchor="middle" fontSize="2.3" fontWeight="700" fill="#0b1a12">
                          {role.length > 12 ? `${role.slice(0, 11)}…` : role}
                        </text>
                      </g>
                    )}
                  </>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      <p className="text-center text-micro text-ink-mist">Нажми на игрока: роль, опека звезды, стандарты · 👁 опека · 🚩🎯⚽ стандарты</p>
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
