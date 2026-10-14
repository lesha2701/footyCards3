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
import { TournamentMatchReplay } from "@/components/clubs/TournamentMatchReplay";
import { MENTALITIES } from "@/lib/clubTactics";
import { haptic } from "@/lib/telegram";
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

function FatigueBar({ value }: { value: number }) {
  const tone = value >= 70 ? "bg-red-400" : value >= 45 ? "bg-amber-300" : "bg-accent-lime";
  return (
    <span className="block h-1 w-12 overflow-hidden rounded-full bg-white/10" aria-label={`Усталость ${value}%`}>
      <span className={`block h-full ${tone}`} style={{ width: `${Math.min(100, value)}%` }} />
    </span>
  );
}

function PlayerRow({ p, selected, onClick, disabled }: {
  p: CareerLivePlayer; selected: boolean; onClick: () => void; disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex w-full items-center gap-2 rounded-xl px-2 py-1.5 text-left text-xs transition-colors disabled:opacity-40 ${
        selected ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk active:bg-white/5"}`}
    >
      <span className="w-9 shrink-0 font-mono text-[10px] opacity-70">{p.position ?? ""}</span>
      <span className="min-w-0 flex-1 truncate">{p.name}</span>
      <span className="font-mono text-[11px]">{p.rating ?? ""}</span>
      <FatigueBar value={p.fatigue} />
    </button>
  );
}

/** Live match centre: the first half of my match is played at kick-off;
 * during the break (until second_half_at) the coach can change mentality,
 * tactical axes and make substitutions for the second half. */
export function LiveMatchCenter({ live, catalog, onView, onError }: {
  live: CareerLive; catalog: TacticsCatalog | null;
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
  const [subs, setSubs] = useState<{ out: number; in: number }[]>(saved?.subs ?? []);
  const [pickOut, setPickOut] = useState<number | null>(null);

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
  const usedIn = new Set(subs.map((s) => s.in));
  const usedOut = new Set(subs.map((s) => s.out));
  const full = subs.length >= live.subs_left;
  const name = (list: CareerLivePlayer[], id: number) => list.find((p) => p.card_id === id)?.name ?? `#${id}`;
  const mm = Math.floor(left / 60_000);
  const ss = Math.floor((left % 60_000) / 1000);
  const stats = useMemo(() => {
    const count = (side: string, types: string[]) => live.events.filter((e) => e.team === side && types.includes(String(e.event_type))).length;
    return (["a", "b"] as const).map((side) => ({
      shots: count(side, ["goal", "shot", "save", "blocked", "miss", "post"]),
      tackles: count(side, ["tackle_won"]),
    }));
  }, [live.events]);

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-gradient-to-br from-bg-surface to-bg-raised p-4 ring-1 ring-red-400/30">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-red-300">
          <span className="h-2 w-2 animate-pulse rounded-full bg-red-400" /> Live · тур {live.round + 1} · перерыв
        </span>
        <span className="font-mono text-xs text-ink-chalk" aria-live="polite">
          {over ? "Второй тайм начался" : `2-й тайм через ${mm}:${String(ss).padStart(2, "0")}`}
        </span>
      </div>
      <div className="flex items-center justify-center gap-3 text-center">
        <p className="min-w-0 flex-1 truncate text-right text-sm font-semibold text-ink-chalk">{live.home_name}</p>
        <p className="font-mono text-2xl font-bold text-ink-chalk">{live.hs}:{live.as}</p>
        <p className="min-w-0 flex-1 truncate text-left text-sm font-semibold text-ink-chalk">{live.away_name}</p>
      </div>
      <div className="grid grid-cols-3 gap-1 text-center text-[11px] text-ink-mist">
        <span className="font-mono text-ink-chalk">{stats[0].shots}</span><span>удары</span><span className="font-mono text-ink-chalk">{stats[1].shots}</span>
        <span className="font-mono text-ink-chalk">{stats[0].tackles}</span><span>отборы</span><span className="font-mono text-ink-chalk">{stats[1].tackles}</span>
      </div>

      <TournamentMatchReplay
        events={live.events as unknown as MatchEvent[]}
        clubAName={live.home_name}
        clubBName={live.away_name}
        scoreA={live.hs}
        scoreB={live.as}
        finishedLabel="Перерыв"
        scoreLabel="После первого тайма"
      />

      {!over && (
        <div className="flex flex-col gap-3 rounded-2xl bg-bg-base/40 p-3">
          <p className="font-display text-sm font-bold text-ink-chalk">
            Указания на второй тайм{ownScore < oppScore ? " — нужно отыгрываться" : ownScore > oppScore ? " — удержать счёт" : ""}
          </p>
          <div className="flex flex-col gap-1">
            <p className="text-[11px] text-ink-mist">Настрой</p>
            <Segmented label="Настрой" value={mentality} options={MENTALITIES.map((m) => ({ value: m.value, label: m.label }))}
              onChange={setMentality} />
          </div>
          {catalog?.axes.map((axis) => (
            <div key={axis.key} className="flex flex-col gap-1">
              <p className="text-[11px] text-ink-mist">{axis.label}</p>
              <Segmented label={axis.label} value={tactic[axis.key] ?? ""}
                options={axis.values.map((v) => ({ value: v.value, label: v.label }))}
                onChange={(v) => setTactic({ ...tactic, [axis.key]: v })} />
            </div>
          ))}

          <div className="flex flex-col gap-1.5">
            <p className="text-[11px] text-ink-mist">Замены · осталось {Math.max(0, live.subs_left - subs.length)} из {live.subs_left}</p>
            {subs.map((s) => (
              <div key={s.out} className="flex items-center gap-2 rounded-xl bg-bg-raised px-2 py-1.5 text-xs text-ink-chalk">
                <span className="text-red-300">↓ {name(live.on, s.out)}</span>
                <span className="text-accent-lime">↑ {name(live.bench, s.in)}</span>
                <button onClick={() => setSubs(subs.filter((x) => x.out !== s.out))} className="ml-auto text-ink-mist" aria-label="Отменить замену">✕</button>
              </div>
            ))}
            {!full && (
              <div className="grid grid-cols-2 gap-2">
                <div className="flex flex-col gap-1">
                  <p className="text-[10px] text-ink-mist-dim">Уходит</p>
                  {live.on.filter((p) => !usedOut.has(p.card_id)).map((p) => (
                    <PlayerRow key={p.card_id} p={p} selected={pickOut === p.card_id} onClick={() => setPickOut(p.card_id)} />
                  ))}
                </div>
                <div className="flex flex-col gap-1">
                  <p className="text-[10px] text-ink-mist-dim">{pickOut ? "Выходит" : "Сначала выбери, кто уходит"}</p>
                  {live.bench.filter((p) => !usedIn.has(p.card_id)).map((p) => (
                    <PlayerRow key={p.card_id} p={p} selected={false} disabled={!pickOut}
                      onClick={() => { if (pickOut) { setSubs([...subs, { out: pickOut, in: p.card_id }]); setPickOut(null); } }} />
                  ))}
                  {!live.bench.length && <p className="text-[10px] text-ink-mist-dim">Скамейка пуста</p>}
                </div>
              </div>
            )}
          </div>

          <button
            onClick={() => send.mutate()}
            disabled={send.isPending}
            className="rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-50"
          >
            {saved ? "Обновить указания" : "Отдать указания"}
          </button>
          {saved && <p className="text-center text-[11px] text-accent-lime">Указания приняты — применятся с 46-й минуты</p>}
        </div>
      )}
    </section>
  );
}
