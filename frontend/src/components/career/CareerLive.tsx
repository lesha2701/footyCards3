import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  setCareerHalftime,
  type CareerLive,
  type CareerLivePlayer,
  type CareerView,
  type Tactic,
  type TacticsCatalog,
} from "@/api/career";
import { Segmented } from "@/components/career/CareerTactics";
import { VALUE_ICONS } from "@/components/career/TacticIcons";
import { EnergyBar } from "@/components/career/EnergyBar";
import { CareerMatchViewer, type ReplayTab } from "@/components/career/MatchViewer";
import { TournamentMatchReplay } from "@/components/clubs/TournamentMatchReplay";
import { TIRED_AT, benchFor, byFatigue, suggestSubs, type Sub } from "@/lib/careerSubs";
import { MENTALITIES } from "@/lib/clubTactics";
import { haptic, hapticSelection } from "@/lib/telegram";
import type { MatchEvent } from "@/types";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

function useCountdown(iso: string): number {
  const target = useMemo(() => new Date(iso).getTime(), [iso]);
  const [left, setLeft] = useState(() => Math.max(0, target - Date.now()));
  useEffect(() => {
    const id = setInterval(() => setLeft(Math.max(0, target - Date.now())), 1000);
    return () => clearInterval(id);
  }, [target]);
  return left;
}

function PlayerRow({ p, selected, onClick, disabled, mark }: {
  p: CareerLivePlayer; selected: boolean; onClick: () => void; disabled?: boolean; mark?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-expanded={selected}
      className={`flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left text-xs transition-colors disabled:opacity-40 ${
        selected ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk active:bg-white/5"}`}
    >
      {mark && <span className="shrink-0">{mark}</span>}
      <span className="w-9 shrink-0 font-mono text-micro opacity-70">{p.position ?? ""}</span>
      <span className="min-w-0 flex-1 truncate">{p.name}</span>
      <span className="font-mono text-caption">{p.rating ?? ""}</span>
      <EnergyBar fatigue={p.fatigue} />
    </button>
  );
}

/** Substitutions in two taps: the players on the pitch, the most tired
 * first; tap one and the bench that suits him opens right under him (same
 * position, then line, then rating); tap a sub and it's planned. "Replace
 * the tired" plans all of them at once. */
function SubsPanel({ live, subs, setSubs }: {
  live: CareerLive; subs: Sub[]; setSubs: (s: Sub[]) => void;
}) {
  const [pickOut, setPickOut] = useState<number | null>(null);
  const left = Math.max(0, live.subs_left - subs.length);
  const outs = new Set(subs.map((s) => s.out));
  const name = (list: CareerLivePlayer[], id: number) => list.find((p) => p.card_id === id)?.name ?? `#${id}`;
  const proposal = suggestSubs(live.on, live.bench, subs, live.subs_left);
  const tired = live.on.filter((p) => p.fatigue >= TIRED_AT && !outs.has(p.card_id)).length;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-caption text-ink-mist">Замены · осталось {left} из {live.subs_left}</p>
        {proposal.length > subs.length && (
          <button
            type="button"
            onClick={() => { hapticSelection(); setSubs(proposal); setPickOut(null); }}
            className="rounded-full bg-amber-300/15 px-2.5 py-1 text-micro font-semibold text-amber-200 active:bg-amber-300/25"
          >
            Заменить уставших ({proposal.length - subs.length})
          </button>
        )}
      </div>
      {subs.map((s) => (
        <div key={s.out} className="flex items-center gap-2 rounded-xl bg-bg-raised px-2 py-1.5 text-xs text-ink-chalk">
          <span className="truncate text-red-300">↓ {name(live.on, s.out)}</span>
          <span className="truncate text-accent-lime">↑ {name(live.bench, s.in)}</span>
          <button type="button" onClick={() => setSubs(subs.filter((x) => x.out !== s.out))} className="ml-auto px-1 text-ink-mist" aria-label="Отменить замену">✕</button>
        </div>
      ))}
      {left === 0 && <p className="text-micro text-ink-mist-dim">Все замены запланированы</p>}
      {left > 0 && (
        <>
          <p className="text-micro text-ink-mist-dim">
            {tired > 0 ? `Устали: ${tired}. ` : ""}Нажми на игрока, чтобы выбрать замену
          </p>
          {byFatigue(live.on).filter((p) => !outs.has(p.card_id)).map((p) => (
            <div key={p.card_id} className="flex flex-col gap-1">
              <PlayerRow p={p} selected={pickOut === p.card_id} mark={p.fatigue >= TIRED_AT ? "⚠" : undefined}
                onClick={() => setPickOut(pickOut === p.card_id ? null : p.card_id)} />
              {pickOut === p.card_id && (
                <div className="ml-4 flex flex-col gap-1 border-l border-white/10 pl-2" aria-label={`Замена для ${p.name}`}>
                  {benchFor(p, live.bench, subs).map((b) => (
                    <PlayerRow key={b.card_id} p={b} selected={false} mark="↑"
                      onClick={() => { hapticSelection(); setSubs([...subs, { out: p.card_id, in: b.card_id }]); setPickOut(null); }} />
                  ))}
                  {benchFor(p, live.bench, subs).length === 0 && <p className="text-micro text-ink-mist-dim">Скамейка пуста</p>}
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function TacticsPanel({ catalog, mentality, setMentality, tactic, setTactic }: {
  catalog: TacticsCatalog | null; mentality: string; setMentality: (m: string) => void;
  tactic: Tactic; setTactic: (t: Tactic) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <p className="text-caption text-ink-mist">Настрой</p>
        <Segmented label="Настрой" value={mentality} options={MENTALITIES.map((m) => ({ value: m.value, label: m.label }))}
          onChange={setMentality} />
      </div>
      {catalog?.axes.map((axis) => (
        <div key={axis.key} className="flex flex-col gap-1">
          <p className="text-caption text-ink-mist">{axis.label}</p>
          <Segmented label={axis.label} value={tactic[axis.key] ?? ""} icons={VALUE_ICONS[axis.key]}
            options={axis.values.map((v) => ({ value: v.value, label: v.label }))}
            onChange={(v) => setTactic({ ...tactic, [axis.key]: v })} />
        </div>
      ))}
    </div>
  );
}

/** Live match centre: the first half of my match is played at kick-off;
 * during the break (until second_half_at) the coach can change mentality,
 * tactical axes and make substitutions for the second half. With the 2D
 * viewer they are its "Замены" / "Тактика" tabs, next to the feed. */
export function LiveMatchCenter({ live, catalog, seasonId, onView, onError }: {
  live: CareerLive; catalog: TacticsCatalog | null;
  /** With it (and live.match_index) the first half plays on the 2D pitch. */
  seasonId?: number;
} & Handlers) {
  const queryClient = useQueryClient();
  const left = useCountdown(live.second_half_at);
  const over = left <= 0;
  useEffect(() => {
    if (over) queryClient.invalidateQueries({ queryKey: ["career"] });
  }, [over, queryClient]);

  const saved = live.orders;
  const [mentality, setMentality] = useState<string>(saved?.mentality ?? live.mentality ?? "BALANCED");
  const [tactic, setTactic] = useState<Tactic>({ ...(live.tactic ?? {}), ...(saved?.tactic ?? {}) });
  const [subs, setSubs] = useState<Sub[]>(saved?.subs ?? []);
  const withViewer = seasonId !== undefined && live.match_index !== undefined;

  const send = useMutation({
    mutationFn: () => {
      const changed: Tactic = {};
      for (const [axis, value] of Object.entries(tactic)) {
        if (live.tactic?.[axis] !== value) changed[axis] = value;
      }
      return setCareerHalftime({ mentality: mentality !== live.mentality ? mentality : null, tactic: changed, subs });
    },
    onSuccess: (v) => { haptic("medium"); onView(v); },
    onError,
  });

  const mine = live.my_side;
  const [ownScore, oppScore] = mine === "a" ? [live.hs, live.as] : [live.as, live.hs];
  const mm = Math.floor(left / 60_000);
  const ss = Math.floor((left % 60_000) / 1000);
  const stats = useMemo(() => {
    const count = (side: string, types: string[]) => live.events.filter((e) => e.team === side && types.includes(String(e.event_type))).length;
    return (["a", "b"] as const).map((side) => ({
      shots: count(side, ["goal", "shot", "save", "blocked", "miss", "post"]),
      tackles: count(side, ["tackle_won"]),
    }));
  }, [live.events]);
  const tired = live.on.filter((p) => p.fatigue >= TIRED_AT && !subs.some((s) => s.out === p.card_id)).length;

  const sendBlock = (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={() => send.mutate()}
        disabled={send.isPending}
        className="rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-50"
      >
        {saved ? "Обновить указания" : "Отдать указания"}
      </button>
      {saved && <p className="text-center text-caption text-accent-lime">Указания приняты — применятся с 46-й минуты</p>}
    </div>
  );
  const heading = (
    <p className="font-display text-sm font-bold text-ink-chalk">
      Указания на второй тайм{ownScore < oppScore ? " — нужно отыгрываться" : ownScore > oppScore ? " — удержать счёт" : ""}
    </p>
  );
  const subsPanel = <SubsPanel live={live} subs={subs} setSubs={setSubs} />;
  const tacticsPanel = (
    <TacticsPanel catalog={catalog} mentality={mentality} setMentality={setMentality} tactic={tactic} setTactic={setTactic} />
  );
  const tabs: ReplayTab[] | undefined = over ? undefined : [
    {
      key: "subs", label: "Замены", badge: tired > 0 ? String(tired) : undefined,
      content: <div className="flex flex-col gap-3 rounded-2xl bg-bg-base/40 p-3">{heading}{subsPanel}{sendBlock}</div>,
    },
    {
      key: "tactics", label: "Тактика",
      content: <div className="flex flex-col gap-3 rounded-2xl bg-bg-base/40 p-3">{heading}{tacticsPanel}{sendBlock}</div>,
    },
  ];

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-gradient-to-br from-bg-surface to-bg-raised p-4 ring-1 ring-red-400/30">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-caption font-bold uppercase tracking-wider text-red-300">
          <span className="h-2 w-2 animate-pulse rounded-full bg-red-400" /> Live · тур {live.round + 1} · перерыв
        </span>
        <span className="font-mono text-xs text-ink-chalk" aria-live="polite">
          {over ? "Второй тайм начался" : `2-й тайм через ${mm}:${String(ss).padStart(2, "0")}`}
        </span>
      </div>
      {/* The 2D viewer has its own scoreboard. */}
      {!withViewer && (
        <>
          <div className="flex items-center justify-center gap-3 text-center">
            <p className="min-w-0 flex-1 truncate text-right text-sm font-semibold text-ink-chalk">{live.home_name}</p>
            <p className="font-mono text-2xl font-bold text-ink-chalk">{live.hs}:{live.as}</p>
            <p className="min-w-0 flex-1 truncate text-left text-sm font-semibold text-ink-chalk">{live.away_name}</p>
          </div>
          <div className="grid grid-cols-3 gap-1 text-center text-caption text-ink-mist">
            <span className="font-mono text-ink-chalk">{stats[0].shots}</span><span>удары</span><span className="font-mono text-ink-chalk">{stats[1].shots}</span>
            <span className="font-mono text-ink-chalk">{stats[0].tackles}</span><span>отборы</span><span className="font-mono text-ink-chalk">{stats[1].tackles}</span>
          </div>
        </>
      )}

      {(() => {
        const text = (
          <TournamentMatchReplay
            events={live.events as unknown as MatchEvent[]}
            clubAName={live.home_name}
            clubBName={live.away_name}
            scoreA={live.hs}
            scoreB={live.as}
            finishedLabel="Перерыв"
            scoreLabel="После первого тайма"
          />
        );
        // Without the 2D record the orders stay below the text replay.
        const orders = !over && (
          <div className="flex flex-col gap-3 rounded-2xl bg-bg-base/40 p-3">
            {heading}{tacticsPanel}{subsPanel}{sendBlock}
          </div>
        );
        if (!withViewer) return <>{text}{orders}</>;
        return (
          <CareerMatchViewer
            seasonId={seasonId} round={live.round} match={live.match_index!} extraTabs={tabs}
            fallback={<>{text}{orders}</>}
          />
        );
      })()}
    </section>
  );
}
