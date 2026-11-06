/** The round around my match in «Карьера тренера»: «До матча» — the
 * opponent, his form, my chances and who of my starters is tired or out,
 * with a jump to the squad when something is wrong; «Итог тура» — the score, the
 * coins, my place in the table and what happened to my players, until the
 * coach has seen it. Read-only: everything comes from the season view. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { CareerSeason, CareerSquadCard } from "@/api/career";
import { EnergyBar } from "@/components/career/EnergyBar";
import { IconCoin, IconShirt } from "@/components/icons";
import { TIRED_AT } from "@/lib/careerSubs";

const FORM: Record<string, { label: string; tone: string }> = {
  W: { label: "В", tone: "bg-accent-lime" },
  D: { label: "Н", tone: "bg-amber-300" },
  L: { label: "П", tone: "bg-red-400" },
};

const surname = (full: string) => full.trim().split(/\s+/).slice(-1)[0] ?? full;

function nameOf(e: CareerSquadCard): string {
  return surname(e.card?.player.display_name ?? e.my_player?.name ?? "");
}

/** My match of a round: its index in the round and whether I'm at home. */
function myMatchOf(season: CareerSeason, round: number) {
  const matches = season.rounds[round]?.matches ?? [];
  const index = matches.findIndex((m) => m.home === season.my_team_index || m.away === season.my_team_index);
  if (index < 0) return null;
  const m = matches[index];
  const home = m.home === season.my_team_index;
  return { index, home, match: m, opponent: season.teams[home ? m.away : m.home] };
}

/** Starters of the saved line-up who are tired (most tired first) or out. */
export function readiness(season: CareerSeason) {
  const byId = new Map(season.squad.map((s) => [s.card_id, s]));
  const starters = Object.values(season.lineup ?? {}).map((id) => byId.get(id)).filter((e): e is CareerSquadCard => !!e);
  return {
    tired: starters.filter((e) => e.fatigue >= TIRED_AT).sort((a, b) => b.fatigue - a.fatigue),
    out: starters.filter((e) => e.injured_rounds > 0 || e.suspended_rounds > 0),
  };
}

const plural = (n: number, one: string, few: string, many: string) => {
  const d = n % 10, h = n % 100;
  return d === 1 && h !== 11 ? one : d >= 2 && d <= 4 && (h < 12 || h > 14) ? few : many;
};

function FormRow({ form, right }: { form: string[]; right?: boolean }) {
  if (form.length === 0) return <span className="text-micro text-ink-mist-dim">ещё не играл</span>;
  return (
    <span className={`flex gap-0.5 ${right ? "justify-end" : ""}`}>
      {form.map((r, i) => (
        <span key={i} className={`flex h-4 w-4 items-center justify-center rounded text-[9px] font-bold text-bg-base ${FORM[r]?.tone ?? "bg-white/20"}`}>
          {FORM[r]?.label ?? r}
        </span>
      ))}
    </span>
  );
}

/** The next match, once: where and when, me against them, and my XI. */
export function PreMatchCard({ season, when, league, onSquad }: {
  season: CareerSeason; when: string; league: string; onSquad: () => void;
}) {
  const scouting = season.scouting;
  const mine = myMatchOf(season, season.rounds_played);
  if (!scouting || !mine) return null;
  const compare = scouting.compare;
  const { tired, out } = readiness(season);
  const critical = (season.squad_warnings ?? []).filter((w) => w.level === "critical").length;
  const ok = tired.length === 0 && out.length === 0 && critical === 0;
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-gradient-to-br from-bg-surface to-bg-raised p-4 ring-1 ring-white/5" aria-label="Следующий матч">
      <p className="text-micro uppercase tracking-wider text-ink-mist">{league}</p>
      <div className="-mt-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="break-words font-display text-lg font-bold leading-tight text-ink-chalk">
            {mine.home ? "Дома" : "В гостях"}: {scouting.opponent_name}
          </p>
          {when && <p className="text-caption text-ink-mist">{when}</p>}
        </div>
        {scouting.win_pct !== null && (
          <span className="shrink-0 rounded-xl bg-bg-base/60 px-2 py-1 text-center">
            <span className="block font-mono text-sm font-bold text-accent-lime">{Math.round(scouting.win_pct)}%</span>
            <span className="block text-micro text-ink-mist">побед тактикой</span>
          </span>
        )}
      </div>

      {scouting.rivalry && (
        <p className={`rounded-xl px-3 py-1.5 text-caption font-semibold ${scouting.rivalry.kind === "nemesis" ? "bg-red-500/10 text-red-300" : "bg-floodlight/10 text-floodlight"}`}>
          {scouting.rivalry.kind === "nemesis" ? "🔥" : "⚔️"} {scouting.rivalry.text}
        </p>
      )}

      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-x-2 gap-y-1.5 rounded-2xl bg-bg-base/50 px-3 py-2.5 text-caption">
        <span className="text-micro font-semibold uppercase tracking-wider text-accent-lime">Ты</span>
        <span />
        <span className="text-right text-micro font-semibold uppercase tracking-wider text-ink-mist">Соперник</span>
        <span className="font-mono text-sm font-bold text-ink-chalk">{compare?.my_strength ?? "—"}</span>
        <span className="text-center text-micro text-ink-mist">сила</span>
        <span className="text-right font-mono text-sm font-bold text-ink-chalk">{scouting.strength ?? "?"}</span>
        <FormRow form={compare?.my_form ?? []} />
        <span className="text-center text-micro text-ink-mist">форма</span>
        <FormRow form={scouting.form} right />
        {scouting.star && compare?.duel_mine && (
          <>
            <span className="truncate text-ink-chalk">{surname(compare.duel_mine.name)} <span className="font-mono font-bold">{compare.duel_mine.rating}</span></span>
            <span className="text-center text-micro text-ink-mist">дуэль</span>
            <span className="truncate text-right text-ink-chalk"><span className="font-mono font-bold">{scouting.star.rating}</span> {surname(scouting.star.name)}</span>
          </>
        )}
        {scouting.head_to_head && scouting.head_to_head.meetings > 0 && (
          <p className="col-span-3 text-center text-micro text-ink-mist">
            Встречи: В{scouting.head_to_head.w} Н{scouting.head_to_head.d} П{scouting.head_to_head.l}
            {!!scouting.head_to_head.scores?.length && ` · ${scouting.head_to_head.scores.join(", ")}`}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5 rounded-2xl bg-bg-base/50 p-3">
        {ok && <p className="text-caption font-semibold text-accent-lime">Состав готов: все свежие и здоровы</p>}
        {out.length > 0 && (
          <p className="text-caption font-semibold text-red-300">
            Не сыграют {out.length} {plural(out.length, "игрок", "игрока", "игроков")} из стартового состава: {out.map(nameOf).join(", ")}
          </p>
        )}
        {critical > 0 && out.length === 0 && (
          <p className="text-caption font-semibold text-red-300">В составе есть игрок не по амплуа</p>
        )}
        {tired.length > 0 && (
          <>
            <p className="text-caption font-semibold text-amber-300">
              У тебя {tired.length} {plural(tired.length, "уставший", "уставших", "уставших")} в старте
            </p>
            <ul className="flex flex-col gap-1">
              {tired.slice(0, 4).map((e) => (
                <li key={e.card_id} className="flex items-center justify-between gap-2 text-caption text-ink-chalk">
                  <span className="truncate">{nameOf(e)}</span>
                  <EnergyBar fatigue={e.fatigue} />
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {!ok && (
        <button type="button" onClick={onSquad}
          className="flex items-center justify-center gap-1.5 rounded-2xl bg-floodlight py-2.5 text-caption font-bold text-bg-base active:scale-95">
          <IconShirt size={16} aria-hidden="true" />Поправить состав
        </button>
      )}
    </section>
  );
}

const seenKey = (season: number, round: number) => `fc_career_round_seen_${season}_${round}`;

function wasSeen(season: number, round: number): boolean {
  try {
    return localStorage.getItem(seenKey(season, round)) === "1";
  } catch {
    return false;
  }
}

/** «Итог тура» for the last round played, until the coach closes it. */
export function PostMatchCard({ season }: { season: CareerSeason }) {
  const navigate = useNavigate();
  const round = season.rounds_played - 1;
  const [hidden, setHidden] = useState(() => round < 0 || wasSeen(season.id, round));
  const mine = round >= 0 ? myMatchOf(season, round) : null;
  const report = round >= 0 ? season.rounds[round]?.report ?? null : null;
  if (hidden || !mine || mine.match.hs === null || mine.match.as === null) return null;
  const own = mine.home ? mine.match.hs : mine.match.as;
  const opp = mine.home ? mine.match.as : mine.match.hs;
  const result = own > opp ? { label: "Победа", tone: "text-accent-lime", ring: "ring-accent-lime/40" }
    : own === opp ? { label: "Ничья", tone: "text-amber-300", ring: "ring-amber-300/40" }
      : { label: "Поражение", tone: "text-red-400", ring: "ring-red-400/40" };
  const before = round > 0 ? season.rounds[round - 1]?.report?.place ?? null : null;
  // Rounds played before the place was recorded: the table is as of now,
  // i.e. after this (the last played) round.
  const tableIndex = season.table.findIndex((r) => r.team_index === season.my_team_index);
  const place = report?.place ?? (tableIndex >= 0 ? tableIndex + 1 : null);
  const move = place !== null && before !== null ? before - place : 0;
  const close = () => {
    try {
      localStorage.setItem(seenKey(season.id, round), "1");
    } catch {
      // Private mode: it just shows again next time.
    }
    setHidden(true);
  };
  const news: { icon: string; text: string; tone: string }[] = report ? [
    ...report.red.map((n) => ({ icon: "🟥", text: `${n} — удалён`, tone: "text-red-300" })),
    ...report.suspended.map((n) => ({ icon: "⛔", text: `${n} пропустит тур (жёлтые)`, tone: "text-red-300" })),
    ...report.injured.map((n) => ({ icon: "✚", text: `${n} — травма`, tone: "text-red-300" })),
    ...(report.auto_subs ?? []).map((n) => ({ icon: "⇄", text: `Автозамена: ${n}`, tone: "text-ink-chalk" })),
    ...report.yellow.map((n) => ({ icon: "🟨", text: `${n} — жёлтая`, tone: "text-amber-300" })),
    ...report.form_up.map((n) => ({ icon: "▲", text: `${n} в форме`, tone: "text-accent-lime" })),
    ...report.form_down.map((n) => ({ icon: "▼", text: `${n} теряет форму`, tone: "text-ink-mist" })),
  ] : [];

  return (
    <section className={`flex flex-col gap-3 rounded-3xl bg-bg-surface p-4 ring-1 ${result.ring}`} aria-label="Итог тура">
      <div className="flex items-center justify-between gap-2">
        <p className="text-micro uppercase tracking-wider text-ink-mist">Итог тура {round + 1}</p>
        <button type="button" onClick={close} className="px-1 text-ink-mist" aria-label="Закрыть итог тура">✕</button>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className={`font-display text-xl font-black leading-none ${result.tone}`}>{result.label}</p>
          <p className="mt-1 truncate text-caption text-ink-mist">{mine.home ? "дома" : "в гостях"} · {mine.opponent?.name}</p>
        </div>
        <p className="shrink-0 font-mono text-3xl font-black text-ink-chalk">{own}:{opp}</p>
      </div>

      <div className={`grid ${report?.coins != null ? "grid-cols-2" : "grid-cols-1"} gap-2`}>
        {report?.coins != null && (
          <div className="rounded-2xl bg-bg-raised px-3 py-2">
            <p className="text-micro uppercase tracking-wider text-ink-mist">Награда</p>
            <p className="flex items-center gap-1 font-mono text-base font-bold text-ink-chalk">
              <IconCoin size={15} aria-hidden="true" className="text-floodlight" />+{report.coins}
            </p>
          </div>
        )}
        <div className="rounded-2xl bg-bg-raised px-3 py-2">
          <p className="text-micro uppercase tracking-wider text-ink-mist">Место в таблице</p>
          <p className="font-mono text-base font-bold text-ink-chalk">
            {place ?? "—"}
            {move !== 0 && (
              <span className={`ml-1.5 text-caption ${move > 0 ? "text-accent-lime" : "text-red-400"}`}>
                {move > 0 ? `▲${move}` : `▼${-move}`}
              </span>
            )}
          </p>
        </div>
      </div>

      {news.length > 0 && (
        <ul className="flex flex-col gap-1">
          {news.map((n, i) => (
            <li key={i} className={`flex items-center gap-2 text-caption ${n.tone}`}>
              <span className="w-4 text-center" aria-hidden="true">{n.icon}</span>{n.text}
            </li>
          ))}
        </ul>
      )}

      <div className="grid grid-cols-2 gap-2">
        {mine.match.has_events ? (
          <button type="button" onClick={() => navigate(`/play/career/seasons/${season.id}/rounds/${round}/matches/${mine.index}`)}
            className="rounded-2xl bg-floodlight py-2.5 text-caption font-bold text-bg-base active:scale-95">
            Смотреть матч
          </button>
        ) : <span />}
        <button type="button" onClick={close} className="rounded-2xl bg-white/10 py-2.5 text-caption font-bold text-ink-chalk active:scale-95">
          Понятно
        </button>
      </div>
    </section>
  );
}

const AWAY_KEY = "fc_career_last_seen";

function readAway(): { season: number; round: number } | null {
  try {
    return JSON.parse(localStorage.getItem(AWAY_KEY) ?? "null");
  } catch {
    return null;
  }
}

/** Rounds played since the coach last closed the career screen: from which
 * round to sum up, and how to mark everything as seen. */
export function useAwaySummary(season: CareerSeason) {
  const [seen] = useState(readAway);
  const from = !seen ? season.rounds_played : seen.season === season.id ? seen.round : 0;
  const [closed, setClosed] = useState(false);
  const count = closed || season.second_half ? 0 : season.rounds_played - from;
  const mark = () => {
    try {
      localStorage.setItem(AWAY_KEY, JSON.stringify({ season: season.id, round: season.rounds_played }));
    } catch {
      // Private mode: the summary just shows again.
    }
  };
  useEffect(() => {
    if (count < 2 && !season.second_half) mark();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season.id, season.rounds_played, count]);
  return { from, count: count >= 2 ? count : 0, close: () => { mark(); setClosed(true); } };
}

/** «Пока тебя не было»: what the coach missed, in one card. */
export function AwaySummaryCard({ season, from, onClose }: { season: CareerSeason; from: number; onClose: () => void }) {
  const rows = season.rounds.slice(from, season.rounds_played).flatMap((round) => {
    const mine = myMatchOf(season, round.index);
    if (!mine || mine.match.hs === null || mine.match.as === null) return [];
    const own = mine.home ? mine.match.hs : mine.match.as;
    const opp = mine.home ? mine.match.as : mine.match.hs;
    return [{ round, own, opp, name: mine.opponent?.name ?? "", code: own > opp ? "W" : own === opp ? "D" : "L" }];
  });
  const coins = rows.reduce((sum, r) => sum + (r.round.report?.coins ?? 0), 0);
  const count = (code: string) => rows.filter((r) => r.code === code).length;
  const before = from > 0 ? season.rounds[from - 1]?.report?.place ?? null : null;
  const index = season.table.findIndex((r) => r.team_index === season.my_team_index);
  const place = index >= 0 ? index + 1 : null;
  const news = rows.flatMap(({ round: { report } }) => (report ? [
    ...report.injured.map((n) => `✚ ${n} — травма`),
    ...report.red.map((n) => `🟥 ${n} — удалён`),
    ...report.suspended.map((n) => `⛔ ${n} — дисквалификация`),
    ...(report.auto_subs ?? []).map((n) => `⇄ ${n}`),
  ] : []));
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4 ring-1 ring-accent-lime/30" aria-label="Пока тебя не было">
      <div>
        <p className="text-micro uppercase tracking-wider text-ink-mist">Пока тебя не было</p>
        <p className="font-display text-lg font-bold text-ink-chalk">
          {rows.length} {plural(rows.length, "тур", "тура", "туров")}: В{count("W")} Н{count("D")} П{count("L")}
        </p>
      </div>
      <ul className="flex flex-col gap-1">
        {rows.map(({ round, own, opp, name, code }) => (
          <li key={round.index} className="flex items-center gap-2 text-caption">
            <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-micro font-bold text-bg-base ${FORM[code].tone}`}>{FORM[code].label}</span>
            <span className="min-w-0 flex-1 truncate text-ink-chalk">{name}</span>
            <span className="font-mono font-bold text-ink-chalk">{own}:{opp}</span>
          </li>
        ))}
      </ul>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-2xl bg-bg-raised px-3 py-2">
          <p className="text-micro uppercase tracking-wider text-ink-mist">Заработано</p>
          <p className="flex items-center gap-1 font-mono text-base font-bold text-ink-chalk">
            <IconCoin size={15} aria-hidden="true" className="text-floodlight" />+{coins}
          </p>
        </div>
        <div className="rounded-2xl bg-bg-raised px-3 py-2">
          <p className="text-micro uppercase tracking-wider text-ink-mist">Место</p>
          <p className="font-mono text-base font-bold text-ink-chalk">
            {before !== null && before !== place ? `${before} → ` : ""}{place ?? "—"}
          </p>
        </div>
      </div>
      {news.length > 0 && (
        <ul className="flex flex-col gap-1 text-caption text-ink-mist">
          {news.slice(0, 6).map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
      <button type="button" onClick={onClose} className="rounded-2xl bg-white/10 py-2.5 text-caption font-bold text-ink-chalk active:scale-95">
        Понятно
      </button>
    </section>
  );
}
