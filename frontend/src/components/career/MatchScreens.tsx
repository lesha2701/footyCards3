/** The round around my match in «Карьера тренера»: «До матча» — the
 * opponent, his form, my chances and who of my starters is tired or out,
 * with a jump to the squad or the tactic; «Итог тура» — the score, the
 * coins, my place in the table and what happened to my players, until the
 * coach has seen it. Read-only: everything comes from the season view. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { CareerSeason, CareerSquadCard } from "@/api/career";
import { EnergyBar } from "@/components/career/EnergyBar";
import { IconCoin } from "@/components/icons";
import { TIRED_AT } from "@/lib/careerSubs";

const FORM: Record<string, { label: string; tone: string }> = {
  W: { label: "В", tone: "bg-accent-lime" },
  D: { label: "Н", tone: "bg-amber-300" },
  L: { label: "П", tone: "bg-red-400" },
};

function nameOf(e: CareerSquadCard): string {
  const full = e.card?.player.display_name ?? e.my_player?.name ?? "";
  return full.trim().split(/\s+/).slice(-1)[0] ?? full;
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
function readiness(season: CareerSeason) {
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

export function PreMatchCard({ season, when, onSquad, onTactic }: {
  season: CareerSeason; when: string; onSquad: () => void; onTactic: () => void;
}) {
  const scouting = season.scouting;
  const mine = myMatchOf(season, season.rounds_played);
  if (!scouting || !mine) return null;
  const { tired, out } = readiness(season);
  const critical = (season.squad_warnings ?? []).filter((w) => w.level === "critical").length;
  const ok = tired.length === 0 && out.length === 0 && critical === 0;
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-gradient-to-br from-bg-surface to-bg-raised p-4 ring-1 ring-white/5" aria-label="До матча">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-micro uppercase tracking-wider text-ink-mist">До матча · тур {season.rounds_played + 1}{when ? ` · ${when}` : ""}</p>
          <p className="truncate font-display text-lg font-bold leading-tight text-ink-chalk">
            {mine.home ? "Дома" : "В гостях"}: {scouting.opponent_name}
          </p>
        </div>
        {scouting.win_pct !== null && (
          <span className="shrink-0 rounded-xl bg-bg-base/60 px-2 py-1 text-center">
            <span className="block font-mono text-sm font-bold text-accent-lime">{Math.round(scouting.win_pct)}%</span>
            <span className="block text-micro text-ink-mist">побед тактикой</span>
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-caption text-ink-mist">
        <span className="flex items-center gap-1">
          Форма
          {scouting.form.length === 0 ? <span className="text-ink-mist-dim">— ещё не играл</span> : scouting.form.map((r, i) => (
            <span key={i} className={`flex h-5 w-5 items-center justify-center rounded-md text-micro font-bold text-bg-base ${FORM[r]?.tone ?? "bg-white/20"}`}>
              {FORM[r]?.label ?? r}
            </span>
          ))}
        </span>
        {scouting.strength !== null && <span>сила {scouting.strength}</span>}
        {scouting.head_to_head && scouting.head_to_head.meetings > 0 && (
          <span>встречи В{scouting.head_to_head.w} Н{scouting.head_to_head.d} П{scouting.head_to_head.l}</span>
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

      <div className="grid grid-cols-2 gap-2">
        <button type="button" onClick={onSquad}
          className={`rounded-2xl py-2.5 text-caption font-bold active:scale-95 ${ok ? "bg-white/10 text-ink-chalk" : "bg-floodlight text-bg-base"}`}>
          {ok ? "Состав" : "Поправить состав"}
        </button>
        <button type="button" onClick={onTactic} className="rounded-2xl bg-white/10 py-2.5 text-caption font-bold text-ink-chalk active:scale-95">
          Тактика
        </button>
      </div>
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
