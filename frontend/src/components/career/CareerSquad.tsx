import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { setCareerLineup, type CareerSeason, type CareerSlot, type CareerSquadCard, type CareerView, type TacticsCatalog } from "@/api/career";
import { ChemistryDiamonds, ChemistryLinksOverlay, ChemistrySummary } from "@/components/squad/Chemistry";
import { SquadBuilder } from "@/components/career/Offseason";
import { EnergyBar } from "@/components/career/EnergyBar";
import { PlayerTile } from "@/components/career/PlayerTile";
import { SquadTacticLayer } from "@/components/career/SquadTacticLayer";
import { VALUE_ICONS } from "@/components/career/TacticIcons";
import { isOut, lineOf, playerInfo } from "@/lib/careerPlayer";
import { axisValueLabel } from "@/lib/careerTactics";
import { chemistryGain, computeChemistry } from "@/lib/chemistry";
import { CATEGORY_POSITIONS, onIdealPosition } from "@/lib/formation";
import { formationLabel, inRow, pitchRows } from "@/lib/formationLayout";
import { haptic } from "@/lib/telegram";
import type { ChemistryOut } from "@/types";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

const LINES: { category: "GK" | "DEF" | "MID" | "FWD"; label: string }[] = [
  { category: "GK", label: "Вратари" }, { category: "DEF", label: "Защита" },
  { category: "MID", label: "Полузащита" }, { category: "FWD", label: "Атака" },
];

function PitchCard({ slot, entry, chemPoints, chemMax, onClick, target = false, dimmed = false }: {
  slot: CareerSlot; entry?: CareerSquadCard; chemPoints?: { points: number; on_position: boolean }; chemMax: number;
  onClick: () => void;
  /** A bench player is picked and can go here: the slot pulses. */
  target?: boolean;
  dimmed?: boolean;
}) {
  const info = playerInfo(entry);
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
        <PlayerTile info={info} entry={entry} width="w-[42px] min-[400px]:w-[47px]" offPosition={!!off}>
          {chemPoints && <ChemistryDiamonds points={chemPoints.points} max={chemMax} onPosition={chemPoints.on_position} />}
          {entry && (
            <EnergyBar fatigue={entry.fatigue} thin />
          )}
        </PlayerTile>
      ) : (
        <div className="flex w-[42px] flex-col items-center gap-1 rounded-xl border border-dashed border-white/25 bg-black/30 p-2 min-[400px]:w-[47px]">
          <span className="text-lg leading-none text-ink-mist-dim">+</span>
          <span className="font-mono text-micro text-ink-mist-dim">{slot.ideal_position}</span>
        </div>
      )}
    </button>
  );
}

function BenchCard({ entry, onClick, gain, selected }: { entry: CareerSquadCard; onClick?: () => void; gain?: number | null; selected?: boolean }) {
  const info = playerInfo(entry);
  if (!info) return null;
  const out = isOut(entry);
  return (
    <button onClick={onClick} disabled={!onClick || out}
      className={`relative flex min-w-0 flex-col items-center ${out ? "opacity-45 grayscale" : "active:scale-95"} ${selected ? "rounded-[12px] ring-2 ring-accent-lime" : ""}`}
    >
      <PlayerTile info={info} entry={entry}>
        <EnergyBar fatigue={entry.fatigue} thin />
        {gain != null && gain !== 0 && (
          <span className={`font-mono text-micro font-bold leading-tight ${gain > 0 ? "text-accent-green" : "text-red-400"}`}>
            {gain > 0 ? `+${gain}` : gain} хим.
          </span>
        )}
      </PlayerTile>
    </button>
  );
}

/** A small bench tile for the sideways strip: photo, rating, position, surname. */
function BenchTile({ entry, onClick, selected }: { entry: CareerSquadCard; onClick: () => void; selected: boolean }) {
  const info = playerInfo(entry);
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
      <PlayerTile info={info} entry={entry}>
        <EnergyBar fatigue={entry.fatigue} thin />
      </PlayerTile>
    </button>
  );
}

/** What the faint drawing under the cards means: the tactic's main
 * settings with their pictograms (changed on the «Тактика» card). */
function TacticLegend({ tactic, catalog }: { tactic: NonNullable<CareerSeason["tactic"]>; catalog: TacticsCatalog }) {
  const items = ([["direction", "Атака"], ["buildup", "Розыгрыш"], ["block", "Линия обороны"], ["on_loss", "После потери"]] as const)
    .map(([axis, label]) => ({ axis, label, value: tactic[axis] }))
    .filter((x) => x.value);
  if (!items.length) return null;
  return (
    <ul className="grid grid-cols-2 gap-1" aria-label="Тактика на поле">
      {items.map((x) => (
        <li key={x.axis} className="flex min-w-0 items-center gap-1.5 rounded-xl bg-bg-raised px-2 py-1">
          <span aria-hidden="true" className="shrink-0 text-ink-mist">{VALUE_ICONS[x.axis]?.[x.value!]}</span>
          <span className="min-w-0">
            <span className="block truncate text-[9px] uppercase tracking-wider text-ink-mist-dim">{x.label}</span>
            <span className="block truncate text-micro font-semibold text-ink-chalk">{axisValueLabel(catalog, x.axis, x.value)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Career squad: the XI on a pitch (rows follow the formation) with photos,
 * rarity frames and live chemistry links; the bench as a grid grouped by
 * line so every player is visible; a picker with each candidate's chemistry
 * gain. Unsaved swaps recompute chemistry client-side (lib/chemistry, the
 * server's rules and adjacency); what plays is what the server saves. */
export default function CareerSquad({ season, catalog = null, onView, onError }: { season: CareerSeason; catalog?: TacticsCatalog | null } & Handlers) {
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
    const info = playerInfo(byId.get(slots[s.code]));
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
      .filter((e) => lineOf(playerInfo(e)?.position ?? "") === line.category)
      .sort((a, b) => Number(isOut(a)) - Number(isOut(b)) || (playerInfo(b)?.rating ?? 0) - (playerInfo(a)?.rating ?? 0)),
  })).filter((line) => line.entries.length > 0);
  const candidates = picking
    ? season.squad.filter((s) => {
      const pos = playerInfo(s)?.position;
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
    CATEGORY_POSITIONS[slot.category as keyof typeof CATEGORY_POSITIONS]?.includes(playerInfo(entry)?.position ?? "") ?? false;
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
        className="relative overflow-hidden rounded-[22px] bg-gradient-to-b from-[#17633a] via-[#12512f] to-[#0e4026] px-1 pb-3 pt-7 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]"
      >
        <SquadTacticLayer containerRef={pitchRef} tactic={season.tactic} layoutKey={season.formation} />
        <ChemistryLinksOverlay containerRef={pitchRef} chemistry={chemistry} />
        {/* Room between the lines for the tactic drawn under them. */}
        <div className="relative flex flex-col gap-6">
          {rows.map((row) => (
            <div key={row.key} data-row={row.category} className="flex justify-evenly gap-0.5">
              {inRow(row, season.slots).map((slot) => {
                const entry = byId.get(slots[slot.code]);
                return (
                  <PitchCard
                    key={slot.code}
                    slot={slot}
                    entry={entry}
                    chemPoints={chemBySlot.get(slot.code)}
                    chemMax={chemMax}
                    target={!!benchPick && fitsSlot(slot, benchPick)}
                    dimmed={!!benchPick && !fitsSlot(slot, benchPick)}
                    onClick={() => (benchPick ? fitsSlot(slot, benchPick) && put(slot, benchPick) : setPicking(slot))}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {season.tactic && catalog && <TacticLegend tactic={season.tactic} catalog={catalog} />}


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
            <span>Нажми на поле, кого заменит {playerInfo(benchPick)?.short}</span>
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
                const info = playerInfo(entry)!;
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
