import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { setCareerLineup, type CareerSeason, type CareerSlot, type CareerSquadCard, type CareerView } from "@/api/career";
import { ChemistryDiamonds, ChemistryLinksOverlay, ChemistrySummary } from "@/components/squad/Chemistry";
import { staticUrl } from "@/lib/api";
import { chemistryGain, computeChemistry } from "@/lib/chemistry";
import { CATEGORY_POSITIONS } from "@/lib/formation";
import { haptic } from "@/lib/telegram";
import type { ChemistryOut } from "@/types";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

const PLACEHOLDER = "players/placeholder/player_placeholder.webp";
const ROWS = ["FWD", "MID", "DEF", "GK"] as const;
const CATEGORY_LABEL: Record<string, string> = { GK: "Вратарь", DEF: "Защита", MID: "Полузащита", FWD: "Атака" };

interface Info {
  name: string;
  short: string;
  position: string;
  rating: number;
  club: string;
  country: string;
  image?: string;
  mine: boolean;
}

function infoOf(entry: CareerSquadCard | undefined): Info | null {
  if (!entry) return null;
  if (entry.card) {
    const p = entry.card.player;
    return {
      name: p.display_name, short: p.display_name.split(" ").slice(-1)[0], position: p.position, rating: p.rating,
      club: p.club, country: p.country, image: staticUrl(p.image_path ?? PLACEHOLDER), mine: false,
    };
  }
  if (entry.my_player) {
    const m = entry.my_player;
    return { name: m.name, short: m.name.split(" ").slice(-1)[0], position: m.position, rating: m.rating,
      club: m.club ?? "", country: m.country ?? "", image: staticUrl(PLACEHOLDER), mine: true };
  }
  return null;
}

function fatigueTone(value: number): string {
  return value > 70 ? "bg-red-400" : value > 40 ? "bg-amber-400" : "bg-accent-lime";
}

function StatusBadge({ entry }: { entry: CareerSquadCard }) {
  if (entry.suspended_rounds > 0) {
    return <span className="rounded bg-red-500/90 px-1 text-[8px] font-bold text-white">ДИСКВ · {entry.suspended_rounds}</span>;
  }
  if (entry.injured_rounds > 0) {
    return <span className="rounded bg-red-500/90 px-1 text-[8px] font-bold text-white">ТРАВМА · {entry.injured_rounds}</span>;
  }
  if (entry.form > 0) return <span className="rounded bg-accent-lime/90 px-1 text-[8px] font-bold text-bg-base">▲+{entry.form}</span>;
  if (entry.form < 0) return <span className="rounded bg-red-400/90 px-1 text-[8px] font-bold text-white">▼{entry.form}</span>;
  return null;
}

/** One card on the pitch: photo, rating, position (red when off the slot's
 * position), chemistry diamonds, fatigue and availability. */
function PitchCard({ slot, entry, chemPoints, chemMax, onClick }: {
  slot: CareerSlot; entry?: CareerSquadCard; chemPoints?: { points: number; on_position: boolean }; chemMax: number;
  onClick: () => void;
}) {
  const info = infoOf(entry);
  const off = info && info.position !== slot.ideal_position;
  return (
    <button
      data-chem-slot={slot.code}
      onClick={onClick}
      className="relative flex w-[68px] min-w-0 flex-col items-center gap-0.5 rounded-xl bg-black/35 p-1 backdrop-blur-sm active:scale-95"
      aria-label={info ? `${slot.code}: ${info.name}` : `${slot.code}: пусто`}
    >
      {info ? (
        <>
          <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-black/40">
            <img src={info.image} alt="" className="h-full w-full object-cover" loading="lazy" />
            <span className="absolute left-0.5 top-0.5 rounded bg-black/70 px-1 font-mono text-[10px] font-bold leading-tight text-accent-lime">
              {info.rating}
            </span>
            {entry && <span className="absolute bottom-0.5 left-0.5"><StatusBadge entry={entry} /></span>}
          </div>
          <span className="w-full truncate text-center text-[9px] font-semibold leading-tight text-ink-chalk">{info.short}</span>
          <span className={`rounded-full px-1.5 font-mono text-[8px] font-bold leading-tight ${off ? "bg-red-500/25 text-red-300" : "bg-black/50 text-accent-cyan"}`}>
            {info.position}
          </span>
          {chemPoints && <ChemistryDiamonds points={chemPoints.points} max={chemMax} onPosition={chemPoints.on_position} />}
          {entry && (
            <span className="block h-1 w-10 overflow-hidden rounded-full bg-white/10" title={`Усталость ${entry.fatigue}%`}>
              <span className={`block h-full ${fatigueTone(entry.fatigue)}`} style={{ width: `${entry.fatigue}%` }} />
            </span>
          )}
        </>
      ) : (
        <>
          <div className="flex aspect-square w-full items-center justify-center rounded-lg border border-dashed border-white/20 text-lg text-ink-mist-dim">
            +
          </div>
          <span className="text-[9px] text-ink-mist-dim">{slot.code}</span>
        </>
      )}
    </button>
  );
}

function BenchCard({ entry, onClick, gain }: { entry: CareerSquadCard; onClick?: () => void; gain?: number | null }) {
  const info = infoOf(entry);
  if (!info) return null;
  const out = entry.injured_rounds > 0 || entry.suspended_rounds > 0;
  return (
    <button onClick={onClick} disabled={!onClick || out}
      className={`flex w-[76px] shrink-0 flex-col items-center gap-0.5 rounded-xl bg-bg-raised p-1.5 ${out ? "opacity-50" : "active:scale-95"}`}
    >
      <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-black/40">
        <img src={info.image} alt="" className="h-full w-full object-cover" loading="lazy" />
        <span className="absolute left-0.5 top-0.5 rounded bg-black/70 px-1 font-mono text-[10px] font-bold text-accent-lime">{info.rating}</span>
        <span className="absolute bottom-0.5 left-0.5"><StatusBadge entry={entry} /></span>
      </div>
      <span className="w-full truncate text-center text-[9px] font-semibold text-ink-chalk">{info.short}</span>
      <span className="font-mono text-[8px] text-accent-cyan">{info.position}</span>
      <span className="block h-1 w-12 overflow-hidden rounded-full bg-white/10">
        <span className={`block h-full ${fatigueTone(entry.fatigue)}`} style={{ width: `${entry.fatigue}%` }} />
      </span>
      {gain != null && gain !== 0 && (
        <span className={`font-mono text-[9px] font-bold ${gain > 0 ? "text-accent-green" : "text-red-400"}`}>
          {gain > 0 ? `+${gain}` : gain} хим.
        </span>
      )}
    </button>
  );
}

/** Career squad: the XI on a pitch with photos and live chemistry links,
 * the bench as a strip, a picker that shows each candidate's chemistry
 * gain. Unsaved swaps recompute chemistry client-side (lib/chemistry, the
 * server's rules and adjacency); what plays is what the server saves. */
export default function CareerSquad({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const [slots, setSlots] = useState<Record<string, number>>(season.lineup);
  const [picking, setPicking] = useState<CareerSlot | null>(null);
  const savedKey = JSON.stringify(season.lineup);
  useEffect(() => setSlots(JSON.parse(savedKey)), [savedKey]);
  const pitchRef = useRef<HTMLDivElement>(null);
  const byId = useMemo(() => new Map(season.squad.map((s) => [s.card_id, s])), [season.squad]);
  const dirty = JSON.stringify(slots) !== savedKey;

  const slotLikes = useMemo(() => season.slots.map((s) => {
    const info = infoOf(byId.get(slots[s.code]));
    return {
      slot_code: s.code, ideal_position: s.ideal_position,
      player: info ? { id: slots[s.code], display_name: info.name, club: info.club, country: info.country, position: info.position } : null,
    };
  }), [season.slots, slots, byId]);

  const server = season.chemistry ?? undefined;
  const chemistry: ChemistryOut | undefined = useMemo(() => {
    if (!server?.enabled || !server.rules) return server;
    const result = computeChemistry(
      slotLikes.filter((s) => s.player).map((s) => ({
        slot: s.slot_code, club: s.player!.club, country: s.player!.country, position: s.player!.position, idealPosition: s.ideal_position,
      })),
      (server.adjacency ?? []) as [string, string][], server.rules, season.slots.length,
    );
    return { ...server, links: result.links, players: Object.values(result.players), team: result.team, team_max: result.teamMax };
  }, [server, slotLikes, season.slots.length]);
  const chemBySlot = new Map((chemistry?.enabled ? chemistry.players : []).map((p) => [p.slot_code, p]));
  const chemMax = chemistry?.rules?.player_max ?? 3;

  const save = useMutation({
    mutationFn: () => setCareerLineup({
      slots, formation: season.formation, mentality: season.mentality, playstyle: season.playstyle,
      round_index: season.rounds_played, ...(season.tactic ? { tactic: season.tactic } : {}),
    }),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });

  const inLineup = new Set(Object.values(slots));
  const bench = season.squad.filter((s) => !inLineup.has(s.card_id) && s.owned);
  const candidates = picking
    ? season.squad.filter((s) => {
      const pos = infoOf(s)?.position;
      return s.owned && !!pos && CATEGORY_POSITIONS[picking.category].includes(pos);
    })
    : [];

  const put = (slot: CareerSlot, entry: CareerSquadCard) => {
    const next = { ...slots };
    const from = Object.entries(next).find(([, id]) => id === entry.card_id)?.[0];
    const current = next[slot.code];
    if (from && current !== undefined) next[from] = current; // swap two starters
    else if (from) delete next[from];
    next[slot.code] = entry.card_id;
    setSlots(next);
    setPicking(null);
    haptic("light");
  };

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-ink-mist">Состав на тур {season.rounds_played + 1}</p>
          <p className="font-display text-base font-bold text-ink-chalk">{season.formation} · заявка {season.squad.length}</p>
        </div>
      </div>
      {chemistry?.enabled && <ChemistrySummary chemistry={chemistry} />}

      <div ref={pitchRef} className="relative overflow-hidden rounded-2xl bg-gradient-to-b from-[#134a32] to-[#0c2f20] px-1 py-3">
        <ChemistryLinksOverlay containerRef={pitchRef} chemistry={chemistry} />
        <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 140" preserveAspectRatio="none" aria-hidden>
          <g fill="none" stroke="#ffffff" strokeOpacity="0.12" strokeWidth="0.5">
            <rect x="3" y="2" width="94" height="136" rx="2" />
            <line x1="3" y1="70" x2="97" y2="70" />
            <circle cx="50" cy="70" r="9" />
            <rect x="27" y="2" width="46" height="16" />
            <rect x="27" y="122" width="46" height="16" />
          </g>
        </svg>
        <div className="relative flex flex-col gap-3">
          {ROWS.map((cat) => (
            <div key={cat} className="flex justify-evenly gap-1">
              {season.slots.filter((s) => s.category === cat).map((slot) => (
                <PitchCard
                  key={slot.code}
                  slot={slot}
                  entry={byId.get(slots[slot.code])}
                  chemPoints={chemBySlot.get(slot.code)}
                  chemMax={chemMax}
                  onClick={() => setPicking(slot)}
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-accent-cyan">Запас · {bench.length}</p>
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" style={{ scrollbarWidth: "none" }}>
          {bench.map((entry) => <BenchCard key={entry.card_id} entry={entry} />)}
        </div>
      </div>
      <p className="text-[10px] leading-snug text-ink-mist-dim">
        Нажми на позицию, чтобы поставить другого игрока. Линии — химия соседей: зелёная — один клуб и страна, жёлтая — что-то одно,
        красная — ничего общего. Травмированных и дисквалифицированных автоматически заменит лучший свежий игрок заявки.
      </p>
      <button
        onClick={() => save.mutate()}
        disabled={!dirty || save.isPending}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {save.isPending ? "Сохраняем..." : dirty ? "Сохранить состав" : "Состав сохранён"}
      </button>

      {picking && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60" onClick={() => setPicking(null)}>
          <div
            className="max-h-[75vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-bg-surface p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="font-display text-base font-bold text-ink-chalk">{picking.code} · {CATEGORY_LABEL[picking.category]}</p>
            <p className="mb-3 text-[11px] text-ink-mist">Идеальная позиция: {picking.ideal_position}</p>
            <div className="grid grid-cols-4 gap-2">
              {candidates.map((entry) => {
                const info = infoOf(entry)!;
                const gain = chemistry?.enabled
                  ? chemistryGain(chemistry, slotLikes, picking.code, { club: info.club, country: info.country, position: info.position })
                  : null;
                return (
                  <div key={entry.card_id} className={slots[picking.code] === entry.card_id ? "rounded-xl ring-2 ring-accent-lime" : ""}>
                    <BenchCard entry={entry} gain={gain} onClick={() => put(picking, entry)} />
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
