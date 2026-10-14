import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { setCareerLineup, type CareerSeason, type CareerSlot, type CareerSquadCard, type CareerView } from "@/api/career";
import { ChemistryDiamonds, ChemistryLinksOverlay, ChemistrySummary } from "@/components/squad/Chemistry";
import PitchBackground from "@/components/squad/PitchBackground";
import { staticUrl } from "@/lib/api";
import { chemistryGain, computeChemistry } from "@/lib/chemistry";
import { CATEGORY_POSITIONS } from "@/lib/formation";
import { formationLabel, inRow, pitchRows, PITCH_STYLE } from "@/lib/formationLayout";
import { RARITY_GLOW, RARITY_GRADIENTS } from "@/lib/rarity";
import { haptic } from "@/lib/telegram";
import type { ChemistryOut, Rarity } from "@/types";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

const PLACEHOLDER = "players/placeholder/player_placeholder.webp";
const LINES: { category: "GK" | "DEF" | "MID" | "FWD"; label: string }[] = [
  { category: "GK", label: "Вратари" }, { category: "DEF", label: "Защита" },
  { category: "MID", label: "Полузащита" }, { category: "FWD", label: "Атака" },
];

interface Info {
  name: string;
  short: string;
  position: string;
  rating: number;
  club: string;
  country: string;
  image?: string;
  rarity: Rarity;
  mine: boolean;
}

function infoOf(entry: CareerSquadCard | undefined): Info | null {
  if (!entry) return null;
  if (entry.card) {
    const p = entry.card.player;
    return {
      name: p.display_name, short: p.display_name.split(" ").slice(-1)[0], position: p.position, rating: p.rating,
      club: p.club, country: p.country, image: staticUrl(p.image_path ?? PLACEHOLDER), rarity: p.rarity, mine: false,
    };
  }
  if (entry.my_player) {
    const m = entry.my_player;
    return { name: m.name, short: m.name.split(" ").slice(-1)[0], position: m.position, rating: m.rating,
      club: m.club ?? "", country: m.country ?? "", image: staticUrl(PLACEHOLDER), rarity: "epic", mine: true };
  }
  return null;
}

function lineOf(position: string): "GK" | "DEF" | "MID" | "FWD" {
  return (Object.keys(CATEGORY_POSITIONS) as ("GK" | "DEF" | "MID" | "FWD")[]).find((c) => CATEGORY_POSITIONS[c].includes(position)) ?? "MID";
}

function fatigueTone(value: number): string {
  return value > 70 ? "bg-red-400" : value > 40 ? "bg-amber-400" : "bg-accent-lime";
}

function isOut(entry: CareerSquadCard): boolean {
  return entry.injured_rounds > 0 || entry.suspended_rounds > 0;
}

function StatusBadge({ entry }: { entry: CareerSquadCard }) {
  if (entry.suspended_rounds > 0) {
    return <span className="rounded bg-red-500 px-1 text-[8px] font-bold leading-tight text-white">🟥 {entry.suspended_rounds}</span>;
  }
  if (entry.injured_rounds > 0) {
    return <span className="rounded bg-red-500 px-1 text-[8px] font-bold leading-tight text-white">✚ {entry.injured_rounds}</span>;
  }
  if (entry.form > 0) return <span className="rounded bg-accent-lime px-1 text-[8px] font-bold leading-tight text-bg-base">▲{entry.form}</span>;
  if (entry.form < 0) return <span className="rounded bg-red-400 px-1 text-[8px] font-bold leading-tight text-white">▼</span>;
  return null;
}

/** A player card in a rarity frame: photo, rating, position, name. */
function CardFace({ info, entry, width, children }: { info: Info; entry?: CareerSquadCard; width: string; children?: ReactNode }) {
  return (
    <div className={`${width} rounded-[11px] bg-gradient-to-b p-[1.5px] ${RARITY_GRADIENTS[info.rarity]} ${RARITY_GLOW[info.rarity]}`}>
      <div className="flex flex-col items-center gap-0.5 rounded-[10px] bg-bg-surface/95 p-1">
        <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-gradient-to-b from-white/10 to-black/40">
          <img src={info.image} alt="" className="h-full w-full object-cover" loading="lazy" />
          <span className="absolute left-0.5 top-0.5 rounded-md bg-black/75 px-1 font-mono text-[10px] font-bold leading-tight text-accent-lime">
            {info.rating}
          </span>
          {info.mine && <span className="absolute right-0.5 top-0.5 rounded bg-accent-lime px-0.5 text-[7px] font-black text-bg-base">Я</span>}
          {entry && <span className="absolute bottom-0.5 left-0.5"><StatusBadge entry={entry} /></span>}
        </div>
        <span className="w-full truncate text-center text-[9px] font-semibold leading-tight text-ink-chalk">{info.short}</span>
        {children}
      </div>
    </div>
  );
}

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
      className="relative flex min-w-0 flex-col items-center active:scale-95"
      aria-label={info ? `${slot.code}: ${info.name}` : `${slot.code}: пусто`}
    >
      {info ? (
        <CardFace info={info} entry={entry} width="w-[62px]">
          <span className={`rounded-full px-1.5 font-mono text-[8px] font-bold leading-tight ${off ? "bg-red-500/25 text-red-300" : "bg-white/10 text-accent-cyan"}`}>
            {info.position}
          </span>
          {chemPoints && <ChemistryDiamonds points={chemPoints.points} max={chemMax} onPosition={chemPoints.on_position} />}
          {entry && (
            <span className="block h-[3px] w-full overflow-hidden rounded-full bg-white/10" title={`Усталость ${entry.fatigue}%`}>
              <span className={`block h-full ${fatigueTone(entry.fatigue)}`} style={{ width: `${entry.fatigue}%` }} />
            </span>
          )}
        </CardFace>
      ) : (
        <div className="flex w-[62px] flex-col items-center gap-1 rounded-xl border border-dashed border-white/25 bg-black/30 p-2">
          <span className="text-lg leading-none text-ink-mist-dim">+</span>
          <span className="font-mono text-[9px] text-ink-mist-dim">{slot.ideal_position}</span>
        </div>
      )}
    </button>
  );
}

function BenchCard({ entry, onClick, gain, selected }: { entry: CareerSquadCard; onClick?: () => void; gain?: number | null; selected?: boolean }) {
  const info = infoOf(entry);
  if (!info) return null;
  const out = isOut(entry);
  return (
    <button onClick={onClick} disabled={!onClick || out}
      className={`relative flex min-w-0 flex-col items-center ${out ? "opacity-45 grayscale" : "active:scale-95"} ${selected ? "rounded-[12px] ring-2 ring-accent-lime" : ""}`}
    >
      <CardFace info={info} entry={entry} width="w-full">
        <span className="font-mono text-[8px] font-bold leading-tight text-accent-cyan">{info.position}</span>
        <span className="block h-[3px] w-full overflow-hidden rounded-full bg-white/10">
          <span className={`block h-full ${fatigueTone(entry.fatigue)}`} style={{ width: `${entry.fatigue}%` }} />
        </span>
        {gain != null && gain !== 0 && (
          <span className={`font-mono text-[9px] font-bold leading-tight ${gain > 0 ? "text-accent-green" : "text-red-400"}`}>
            {gain > 0 ? `+${gain}` : gain} хим.
          </span>
        )}
      </CardFace>
    </button>
  );
}

/** Career squad: the XI on a pitch (rows follow the formation) with photos,
 * rarity frames and live chemistry links; the bench as a grid grouped by
 * line so every player is visible; a picker with each candidate's chemistry
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
  const benchByLine = LINES.map((line) => ({
    ...line,
    entries: bench
      .filter((e) => lineOf(infoOf(e)?.position ?? "") === line.category)
      .sort((a, b) => Number(isOut(a)) - Number(isOut(b)) || (infoOf(b)?.rating ?? 0) - (infoOf(a)?.rating ?? 0)),
  })).filter((line) => line.entries.length > 0);
  const candidates = picking
    ? season.squad.filter((s) => {
      const pos = infoOf(s)?.position;
      return s.owned && !!pos && CATEGORY_POSITIONS[picking.category].includes(pos);
    })
    : [];
  const rows = pitchRows(season.formation, season.slots.map((s) => s.code));

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
      <div className="flex items-end justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-ink-mist">Состав на тур {season.rounds_played + 1}</p>
          <p className="font-display text-lg font-bold leading-tight text-ink-chalk">{formationLabel(season.formation)}</p>
        </div>
        <p className="text-[11px] text-ink-mist">заявка · {season.squad.length}</p>
      </div>
      {chemistry?.enabled && <ChemistrySummary chemistry={chemistry} />}

      <div
        ref={pitchRef}
        className="relative overflow-hidden rounded-[22px] px-1 py-4 ring-1 ring-white/10"
        style={PITCH_STYLE}
      >
        <PitchBackground />
        <ChemistryLinksOverlay containerRef={pitchRef} chemistry={chemistry} />
        <div className="relative flex flex-col gap-2.5">
          {rows.map((row) => (
            <div key={row.key} className="flex justify-evenly gap-1">
              {inRow(row, season.slots).map((slot) => (
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

      <div className="flex flex-col gap-2.5">
        <div className="flex items-center justify-between">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-accent-cyan">Запас · {bench.length}</p>
          <p className="text-[10px] text-ink-mist-dim">полоска — усталость</p>
        </div>
        {benchByLine.map((line) => (
          <div key={line.category}>
            <p className="mb-1 text-[10px] font-semibold text-ink-mist">{line.label} · {line.entries.length}</p>
            <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-5">
              {line.entries.map((entry) => <BenchCard key={entry.card_id} entry={entry} />)}
            </div>
          </div>
        ))}
      </div>

      <p className="text-[10px] leading-snug text-ink-mist-dim">
        Нажми на игрока на поле, чтобы заменить. Линии — химия соседей: зелёная — один клуб и страна, жёлтая — что-то
        одно, красная — ничего общего.
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
            className="max-h-[78vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-bg-surface p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/20" />
            <p className="font-display text-base font-bold text-ink-chalk">Позиция {picking.ideal_position}</p>
            <p className="mb-3 text-[11px] text-ink-mist">Цифра под карточкой — как изменится химия состава</p>
            <div className="grid grid-cols-4 gap-2">
              {candidates.map((entry) => {
                const info = infoOf(entry)!;
                const gain = chemistry?.enabled
                  ? chemistryGain(chemistry, slotLikes, picking.code, { club: info.club, country: info.country, position: info.position })
                  : null;
                return (
                  <BenchCard key={entry.card_id} entry={entry} gain={gain} selected={slots[picking.code] === entry.card_id}
                    onClick={() => put(picking, entry)} />
                );
              })}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
