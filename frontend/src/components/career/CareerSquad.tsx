import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { setCareerLineup, type CareerSeason, type CareerSlot, type CareerSquadCard, type CareerView } from "@/api/career";
import { ChemistryDiamonds, ChemistryLinksOverlay, ChemistrySummary } from "@/components/squad/Chemistry";
import { SquadBuilder } from "@/components/career/Offseason";
import PitchBackground from "@/components/squad/PitchBackground";
import { staticUrl } from "@/lib/api";
import { chemistryGain, computeChemistry } from "@/lib/chemistry";
import { CATEGORY_POSITIONS, onIdealPosition } from "@/lib/formation";
import { formationLabel, inRow, pitchRows, PITCH_STYLE } from "@/lib/formationLayout";
import { RARITY_GLOW_STATIC, RARITY_GRADIENTS } from "@/lib/rarity";
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

/** Short label for a tile: the last word of the name (surname), never empty
 * — trailing spaces or a one-word name fall back to the whole name. */
function shortName(...names: (string | null | undefined)[]): string {
  for (const n of names) {
    const words = (n ?? "").trim().split(/\s+/).filter(Boolean);
    if (words.length) return words[words.length - 1];
  }
  return "";
}

function infoOf(entry: CareerSquadCard | undefined): Info | null {
  if (!entry) return null;
  if (entry.card) {
    const p = entry.card.player;
    return {
      name: p.display_name, short: shortName(p.display_name, p.last_name, p.first_name), position: p.position, rating: p.rating,
      club: p.club, country: p.country, image: staticUrl(p.image_path ?? PLACEHOLDER), rarity: p.rarity, mine: false,
    };
  }
  if (entry.my_player) {
    const m = entry.my_player;
    return { name: m.name, short: shortName(m.name), position: m.position, rating: m.rating,
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
    return <span className="rounded bg-red-500 px-1 text-micro font-bold leading-tight text-white">🟥 {entry.suspended_rounds}</span>;
  }
  if (entry.injured_rounds > 0) {
    return <span className="rounded bg-red-500 px-1 text-micro font-bold leading-tight text-white">✚ {entry.injured_rounds}</span>;
  }
  if (entry.form > 0) return <span className="rounded bg-accent-lime px-1 text-micro font-bold leading-tight text-bg-base">▲{entry.form}</span>;
  if (entry.form < 0) return <span className="rounded bg-red-400 px-1 text-micro font-bold leading-tight text-white">▼</span>;
  return null;
}

/** A player card in a rarity frame: photo, rating, position, name.
 * `compact` (the pitch): a shorter photo with the position on it, so the
 * whole XI fits on one phone screen. */
function CardFace({ info, entry, width, children, compact = false, position, offPosition = false }: {
  info: Info; entry?: CareerSquadCard; width: string; children?: ReactNode;
  compact?: boolean; position?: string; offPosition?: boolean;
}) {
  return (
    <div className={`${width} rounded-[11px] bg-gradient-to-b p-[1.5px] ${RARITY_GRADIENTS[info.rarity]} ${RARITY_GLOW_STATIC[info.rarity]}`}>
      <div className={`flex flex-col items-center gap-0.5 rounded-[10px] bg-bg-surface/95 ${compact ? "p-0.5" : "p-1"}`}>
        <div className={`relative w-full overflow-hidden rounded-lg bg-gradient-to-b from-white/10 to-black/40 ${compact ? "aspect-[5/4]" : "aspect-square"}`}>
          <img decoding="async" src={info.image} alt="" className="h-full w-full object-cover" loading="lazy" />
          <span className="absolute left-0.5 top-0.5 rounded-md bg-black/75 px-1 font-mono text-micro font-bold leading-tight text-accent-lime">
            {info.rating}
          </span>
          {info.mine && <span className="absolute right-0.5 top-0.5 rounded bg-accent-lime px-0.5 text-micro font-black text-bg-base">Я</span>}
          {entry && <span className="absolute bottom-0.5 left-0.5"><StatusBadge entry={entry} /></span>}
          {position && (
            <span className={`absolute bottom-0.5 right-0.5 rounded px-0.5 font-mono text-micro font-bold leading-tight ${
              offPosition ? "bg-red-500/90 text-white" : "bg-black/75 text-accent-cyan"
            }`}>
              {position}
            </span>
          )}
        </div>
        <span className="w-full truncate text-center text-micro font-semibold leading-tight text-ink-chalk">{info.short}</span>
        {children}
      </div>
    </div>
  );
}

function PitchCard({ slot, entry, chemPoints, chemMax, onClick, target = false, dimmed = false }: {
  slot: CareerSlot; entry?: CareerSquadCard; chemPoints?: { points: number; on_position: boolean }; chemMax: number;
  onClick: () => void;
  /** A bench player is picked and can go here: the slot pulses. */
  target?: boolean;
  dimmed?: boolean;
}) {
  const info = infoOf(entry);
  const off = info && !onIdealPosition(info.position, slot.ideal_position);
  return (
    <button
      data-chem-slot={slot.code}
      onClick={onClick}
      className={`relative flex min-w-0 flex-col items-center rounded-[12px] transition active:scale-95 ${
        target ? "animate-pulse ring-2 ring-accent-lime ring-offset-1 ring-offset-transparent" : ""
      } ${dimmed ? "opacity-35" : ""}`}
      aria-label={info ? `${slot.code}: ${info.name}` : `${slot.code}: пусто`}
    >
      {info ? (
        <CardFace info={info} entry={entry} width="w-[54px] min-[400px]:w-[60px]" compact position={info.position} offPosition={!!off}>
          {chemPoints && <ChemistryDiamonds points={chemPoints.points} max={chemMax} onPosition={chemPoints.on_position} />}
          {entry && (
            <span className="block h-[3px] w-full overflow-hidden rounded-full bg-white/10" title={`Усталость ${entry.fatigue}%`}>
              <span className={`block h-full ${fatigueTone(entry.fatigue)}`} style={{ width: `${entry.fatigue}%` }} />
            </span>
          )}
        </CardFace>
      ) : (
        <div className="flex w-[54px] flex-col items-center gap-1 rounded-xl border border-dashed border-white/25 bg-black/30 p-2 min-[400px]:w-[60px]">
          <span className="text-lg leading-none text-ink-mist-dim">+</span>
          <span className="font-mono text-micro text-ink-mist-dim">{slot.ideal_position}</span>
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
      <CardFace info={info} entry={entry} width="w-full" compact position={info.position}>
        <span className="block h-[3px] w-full overflow-hidden rounded-full bg-white/10">
          <span className={`block h-full ${fatigueTone(entry.fatigue)}`} style={{ width: `${entry.fatigue}%` }} />
        </span>
        {gain != null && gain !== 0 && (
          <span className={`font-mono text-micro font-bold leading-tight ${gain > 0 ? "text-accent-green" : "text-red-400"}`}>
            {gain > 0 ? `+${gain}` : gain} хим.
          </span>
        )}
      </CardFace>
    </button>
  );
}

/** A small bench tile for the sideways strip: photo, rating, position, surname. */
function BenchTile({ entry, onClick, selected }: { entry: CareerSquadCard; onClick: () => void; selected: boolean }) {
  const info = infoOf(entry);
  if (!info) return null;
  const out = isOut(entry);
  return (
    <button
      onClick={onClick}
      disabled={out}
      aria-pressed={selected}
      aria-label={`${info.name}, ${info.position}, ${info.rating}`}
      className={`w-[52px] shrink-0 snap-start rounded-[12px] ${out ? "opacity-45 grayscale" : "active:scale-95"} ${
        selected ? "ring-2 ring-accent-lime" : ""
      }`}
    >
      <CardFace info={info} entry={entry} width="w-full" compact position={info.position}>
        <span className="block h-[3px] w-full overflow-hidden rounded-full bg-white/10">
          <span className={`block h-full ${fatigueTone(entry.fatigue)}`} style={{ width: `${entry.fatigue}%` }} />
        </span>
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
  // Bench strip: line filter and a picked bench player waiting for a slot.
  const [benchLine, setBenchLine] = useState<"ALL" | "GK" | "DEF" | "MID" | "FWD">("ALL");
  const [benchPick, setBenchPick] = useState<CareerSquadCard | null>(null);
  const [building, setBuilding] = useState(false);
  // The season squad (заявка) can be rebuilt until round 1 kicks off.
  const squadEditable = season.rounds_played === 0 && (season.tactics_version ?? 0) > 0 && season.status === "active";
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
    setBenchPick(null);
    haptic("light");
  };
  const fitsSlot = (slot: CareerSlot, entry: CareerSquadCard) =>
    CATEGORY_POSITIONS[slot.category as keyof typeof CATEGORY_POSITIONS]?.includes(infoOf(entry)?.position ?? "") ?? false;
  const benchShown = benchByLine
    .filter((line) => benchLine === "ALL" || line.category === benchLine)
    .flatMap((line) => line.entries);

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-micro uppercase tracking-wider text-ink-mist">Состав на тур {season.rounds_played + 1}</p>
          <p className="font-display text-lg font-bold leading-tight text-ink-chalk">{formationLabel(season.formation)}</p>
        </div>
        {squadEditable ? (
          <button onClick={() => setBuilding(true)}
            className="rounded-xl bg-white/10 px-3 py-1.5 text-caption font-semibold text-ink-chalk active:scale-95">
            Изменить заявку · {season.squad.length}
          </button>
        ) : (
          <p className="text-caption text-ink-mist">заявка · {season.squad.length}</p>
        )}
      </div>
      {squadEditable && (
        <p className="-mt-1 text-micro text-ink-mist-dim">Заявку можно менять до первого тура, состав — перед каждым туром.</p>
      )}
      {chemistry?.enabled && <ChemistrySummary chemistry={chemistry} />}

      <div
        ref={pitchRef}
        className="relative overflow-hidden rounded-[22px] px-1 py-3 ring-1 ring-white/10"
        style={PITCH_STYLE}
      >
        <PitchBackground />
        <ChemistryLinksOverlay containerRef={pitchRef} chemistry={chemistry} />
        <div className="relative flex flex-col gap-1.5">
          {rows.map((row) => (
            <div key={row.key} className="flex justify-evenly gap-0.5">
              {inRow(row, season.slots).map((slot) => (
                <PitchCard
                  key={slot.code}
                  slot={slot}
                  entry={byId.get(slots[slot.code])}
                  chemPoints={chemBySlot.get(slot.code)}
                  chemMax={chemMax}
                  target={!!benchPick && fitsSlot(slot, benchPick)}
                  dimmed={!!benchPick && !fitsSlot(slot, benchPick)}
                  onClick={() => (benchPick ? fitsSlot(slot, benchPick) && put(slot, benchPick) : setPicking(slot))}
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">Запас · {bench.length}</p>
          <div className="flex gap-1" role="tablist" aria-label="Линия запаса">
            {([["ALL", "Все"], ["GK", "ВР"], ["DEF", "ЗЩ"], ["MID", "ПЗ"], ["FWD", "НП"]] as const).map(([key, label]) => {
              const count = key === "ALL" ? bench.length : benchByLine.find((l) => l.category === key)?.entries.length ?? 0;
              if (key !== "ALL" && count === 0) return null;
              return (
                <button
                  key={key}
                  role="tab"
                  aria-selected={benchLine === key}
                  onClick={() => setBenchLine(key)}
                  className={`rounded-full px-2 py-0.5 text-micro font-semibold ${
                    benchLine === key ? "bg-accent-cyan/20 text-accent-cyan" : "bg-white/5 text-ink-mist"
                  }`}
                >
                  {label}{key !== "ALL" ? ` ${count}` : ""}
                </button>
              );
            })}
          </div>
        </div>
        {benchPick ? (
          <p className="flex items-center justify-between gap-2 rounded-xl bg-accent-lime/10 px-3 py-1.5 text-caption text-accent-lime">
            <span>Нажми на поле, кого заменит {infoOf(benchPick)?.short}</span>
            <button onClick={() => setBenchPick(null)} className="font-semibold text-ink-mist">Отмена</button>
          </p>
        ) : (
          <p className="text-micro text-ink-mist-dim">Нажми на игрока запаса, потом на позицию на поле · полоска — усталость</p>
        )}
        <div className="-mx-1 flex snap-x gap-1.5 overflow-x-auto px-1 pb-1">
          {benchShown.map((entry) => (
            <BenchTile
              key={entry.card_id}
              entry={entry}
              selected={benchPick?.card_id === entry.card_id}
              onClick={() => { haptic("light"); setBenchPick(benchPick?.card_id === entry.card_id ? null : entry); }}
            />
          ))}
          {benchShown.length === 0 && <p className="py-3 text-caption text-ink-mist-dim">В этой линии запасных нет</p>}
        </div>
      </div>

      <p className="text-micro leading-snug text-ink-mist-dim">
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

      {building && <SquadBuilder onClose={() => setBuilding(false)} onView={onView} onError={onError} />}

      {picking && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60" onClick={() => setPicking(null)}>
          <div
            className="max-h-[78vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-bg-surface p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/20" />
            <p className="font-display text-base font-bold text-ink-chalk">Позиция {picking.ideal_position}</p>
            <p className="mb-3 text-caption text-ink-mist">Цифра под карточкой — как изменится химия состава</p>
            <div className="grid grid-cols-5 gap-1.5">
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
