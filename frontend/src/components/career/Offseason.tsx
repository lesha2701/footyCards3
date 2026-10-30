import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import {
  fetchCareerCollection,
  playCareerFriendly,
  setCareerCamp,
  setCareerSquad,
  type CareerCollectionCard,
  type CareerSeason,
  type CareerSeasonSummary,
  type CareerView,
  type TacticsCatalog,
} from "@/api/career";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { PlayerTile } from "@/components/career/PlayerTile";
import { IconCard, IconCoin } from "@/components/icons";
import { lineOf, playerInfo } from "@/lib/careerPlayer";
import { haptic } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

const CAMP_ICON: Record<string, string> = { physical: "🏃", tactical: "📐", cohesion: "🤝" };
const LINES: { cat: "GK" | "DEF" | "MID" | "FWD"; label: string }[] = [
  { cat: "GK", label: "Вратари" }, { cat: "DEF", label: "Защита" }, { cat: "MID", label: "Полузащита" }, { cat: "FWD", label: "Атака" },
];

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })} в ${d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-floodlight font-mono text-caption font-bold text-bg-base">{n}</span>
        <span className="mt-1 w-px flex-1 bg-white/10" />
      </div>
      <div className="min-w-0 flex-1 pb-4">
        <p className="mb-2 font-display text-sm font-bold text-ink-chalk">{title}</p>
        {children}
      </div>
    </div>
  );
}

/** Facts of a finished season: points by tactic, the interactions that
 * worked for and against, top scorer, workhorse, most rounds missed. */
export function SeasonSummaryView({ summary, catalog }: { summary: CareerSeasonSummary; catalog: TacticsCatalog | null }) {
  const presetLabel = (code: string) => catalog?.presets.find((p) => p.code === code)?.label ?? (code === "CUSTOM" ? "Своя тактика" : code);
  const best = summary.tactics[0];
  return (
    <div className="flex flex-col gap-2">
      {best && (
        <div className="rounded-2xl bg-bg-raised p-3">
          <p className="text-micro uppercase tracking-wider text-ink-mist">Лучшая тактика сезона</p>
          <p className="text-sm font-semibold text-ink-chalk">{presetLabel(best.preset)} — {best.points} очк. за {best.played} матч.</p>
          {summary.tactics.length > 1 && (
            <p className="mt-0.5 text-micro text-ink-mist">
              {summary.tactics.slice(1).map((t) => `${presetLabel(t.preset)}: ${t.points} за ${t.played}`).join(" · ")}
            </p>
          )}
        </div>
      )}
      <div className="grid grid-cols-3 gap-1.5 text-center">
        {([
          ["⚽ Бомбардир", summary.top_scorer ? `${summary.top_scorer.name} · ${summary.top_scorer.goals}` : "—"],
          ["⏱ Больше всех играл", summary.most_minutes ? `${summary.most_minutes.name} · ${summary.most_minutes.minutes}'` : "—"],
          ["🩹 Больше пропустил", summary.most_missed ? `${summary.most_missed.name} · ${summary.most_missed.rounds} т.` : "—"],
        ] as const).map(([label, value]) => (
          <div key={label} className="rounded-xl bg-bg-raised px-1.5 py-2">
            <p className="text-micro text-ink-mist">{label}</p>
            <p className="mt-0.5 text-micro font-semibold leading-tight text-ink-chalk">{value}</p>
          </div>
        ))}
      </div>
      {summary.duels.length > 0 && (
        <ul className="flex flex-col gap-1">
          {summary.duels.map((d) => (
            <li key={`${d.id}-${d.attacker}`} className="flex items-center justify-between gap-2 rounded-xl bg-bg-raised px-3 py-1.5 text-caption">
              <span className="min-w-0">
                <span className={`block truncate ${d.attacker === "me" ? "text-accent-lime" : "text-red-300"}`}>{d.label}</span>
                <span className="block text-micro text-ink-mist-dim">{d.attacker === "me" ? "ваши атаки" : "атаки соперника"} · прорывов {d.attacker_won} из {d.applied}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Bottom sheet: pick the season squad from the collection (before round 1). */
export function SquadBuilder({ onClose, onView, onError }: { onClose: () => void } & Handlers) {
  const { data, isLoading } = useQuery({ queryKey: ["career", "collection"], queryFn: fetchCareerCollection });
  const [picked, setPicked] = useState<Set<number> | null>(null);
  const selected = picked ?? new Set((data?.cards ?? []).filter((c) => c.in_squad).map((c) => c.card_id));
  const size = data?.squad_size ?? 22;
  const save = useMutation({
    mutationFn: () => setCareerSquad([...selected]),
    onSuccess: (v) => { haptic("medium"); onView(v); onClose(); },
    onError,
  });
  const byLine = useMemo(() => LINES.map((line) => ({
    ...line,
    cards: (data?.cards ?? []).filter((c) => lineOf(c.card?.player.position ?? c.my_player?.position ?? "") === line.cat)
      .sort((a, b) => (b.card?.player.rating ?? b.my_player?.rating ?? 0) - (a.card?.player.rating ?? a.my_player?.rating ?? 0)),
  })), [data]);
  // At least two keepers (or every keeper owned, when fewer): the server checks too.
  const keepers = byLine[0].cards;
  const keepersNeeded = Math.min(2, keepers.length);
  const keepersIn = keepers.filter((c) => selected.has(c.card_id)).length;
  const toggle = (c: CareerCollectionCard) => {
    const next = new Set(selected);
    if (next.has(c.card_id)) next.delete(c.card_id);
    else if (next.size < size) next.add(c.card_id);
    setPicked(next);
  };
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60" onClick={onClose}>
      <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-t-3xl bg-bg-surface" onClick={(e) => e.stopPropagation()}>
        <div className="p-4 pb-2">
          <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/20" />
          <div className="flex items-center justify-between">
            <p className="font-display text-base font-bold text-ink-chalk">Заявка на сезон</p>
            <span className={`font-mono text-sm font-bold ${selected.size === size ? "text-accent-lime" : "text-ink-chalk"}`}>{selected.size}/{size}</span>
          </div>
          <p className="text-caption text-ink-mist">Отмеченные — в заявке. Кто был в прошлом сезоне, тот ядро команды.</p>
        </div>
        <div className="flex-1 overflow-y-auto px-4">
          {isLoading && <ListSkeleton count={3} />}
          {data && data.cards.length === 0 && (
            <EmptyState compact icon={IconCard} title="Пока некого заявить"
              description="Открой паки — футболисты из коллекции попадут в список для заявки." />
          )}
          {byLine.map((line) => (
            <div key={line.cat} className="mb-3">
              <p className="mb-1 text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">
                {line.label} · {line.cards.filter((c) => selected.has(c.card_id)).length}
              </p>
              <div className="grid grid-cols-4 gap-1.5">
                {line.cards.map((c) => {
                  const on = selected.has(c.card_id);
                  const info = playerInfo(c);
                  if (!info) return null;
                  return (
                    <button key={c.card_id} type="button" onClick={() => toggle(c)} aria-pressed={on}
                      aria-label={`${info.name}, ${info.position}, ${info.rating}`}
                      className={`rounded-[12px] active:scale-95 ${on ? "" : "opacity-40 grayscale"}`}
                    >
                      <PlayerTile info={info}
                        corner={on ? <span className="absolute right-0.5 top-0.5 rounded-full bg-accent-lime px-1 text-micro font-black text-bg-base">✓</span> : undefined} />
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
        <div className="p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
          {keepersIn < keepersNeeded && (
            <p className="mb-2 rounded-xl bg-amber-300/15 px-3 py-2 text-caption font-semibold text-amber-300">
              В заявке нужно минимум два вратаря — сейчас {keepersIn}
            </p>
          )}
          <button onClick={() => save.mutate()} disabled={save.isPending || selected.size < 11 || keepersIn < keepersNeeded}
            className="w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            {save.isPending ? "Сохраняем..." : "Сохранить заявку"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** «Предсезонка»: steps top-down before round 1 of the new season — the
 * old season's result and summary, the core and squad, the camp, the
 * friendly. Every step is optional; the season starts on its own. */
export function OffseasonPanel({ season, catalog, onView, onError }: {
  season: CareerSeason; catalog: TacticsCatalog | null;
} & Handlers) {
  const navigate = useNavigate();
  const [building, setBuilding] = useState(false);
  const off = season.offseason;
  const camp = useMutation({ mutationFn: (code: string | null) => setCareerCamp(code), onSuccess: (v) => { haptic("light"); onView(v); }, onError });
  const friendly = useMutation({ mutationFn: playCareerFriendly, onSuccess: (v) => { haptic("medium"); onView(v); }, onError });
  if (!off) return null;
  const moved = off.prev_division && season.division ? season.division.division - off.prev_division.division : 0;
  const coreOk = off.core_count >= off.core_min;
  // Step numbers: the first season has no «Итоги сезона».
  const first = off.first_season ? 0 : 1;

  return (
    <section className="flex flex-col rounded-3xl bg-gradient-to-b from-bg-surface to-bg-raised p-4 ring-1 ring-accent-lime/20">
      <p className="text-micro uppercase tracking-wider text-accent-lime">Предсезонка</p>
      <p className="font-display text-lg font-bold text-ink-chalk">
        {off.first_season ? "Первый сезон" : "Новый сезон"} — {formatWhen(off.starts_at)}
      </p>
      <p className="mb-4 text-caption text-ink-mist">Любой шаг можно пропустить: сезон начнётся сам с текущими настройками.</p>
      {off.friend_league && (
        <p className="-mt-2 mb-4 rounded-xl bg-accent-cyan/10 px-3 py-2 text-caption text-accent-cyan">
          Лига с другом продолжается: вы снова в одном дивизионе.
        </p>
      )}

      {!off.first_season && <Step n={1} title="Итоги сезона">
        <div className="mb-2 flex flex-wrap items-center gap-2 text-caption">
          {off.prev_place && <span className="rounded-full bg-bg-base/60 px-2.5 py-1 font-semibold text-ink-chalk">{off.prev_place} место</span>}
          {moved !== 0 && (
            <span className={`rounded-full px-2.5 py-1 font-semibold ${moved < 0 ? "bg-accent-lime/15 text-accent-lime" : "bg-red-500/15 text-red-300"}`}>
              {moved < 0 ? "▲ Повышение" : "▼ Вылет"} · {season.division?.name}
            </span>
          )}
          <span className="flex items-center gap-1 rounded-full bg-bg-base/60 px-2.5 py-1 text-ink-chalk">
            +{off.prev_coins} <IconCoin size={11} className="text-accent-lime" />
          </span>
        </div>
        {off.summary ? <SeasonSummaryView summary={off.summary} catalog={catalog} /> : null}
      </Step>}

      <Step n={first + 1} title={off.first_season ? "Заявка на сезон" : "Ядро команды и заявка"}>
        {off.first_season ? (
          <div className="rounded-2xl bg-bg-base/50 p-3">
            <p className="text-caption leading-snug text-ink-mist">
              Заявка собрана автоматически из лучших карточек. Её можно поменять до первого тура — потом она станет ядром команды.
            </p>
            <button onClick={() => setBuilding(true)} className="mt-2 w-full rounded-xl bg-white/10 py-2 text-xs font-semibold text-ink-chalk active:scale-95">
              Изменить заявку · {season.squad.length}
            </button>
          </div>
        ) : (
        <div className="rounded-2xl bg-bg-base/50 p-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-ink-mist">Осталось с прошлого сезона</span>
            <span className={`font-mono font-bold ${coreOk ? "text-accent-lime" : "text-amber-300"}`}>{off.core_count} / {off.core_min}+</span>
          </div>
          <p className="mt-1 text-caption leading-snug text-ink-mist">
            {off.carried_pct > 0
              ? `Ядро сохранено — переходит ${off.carried_pct}% сыгранности (${off.keep_pct}% от прошлой).`
              : off.prev_formation && season.formation !== off.prev_formation
                ? "Схема сменилась — сыгранность начинается с нуля."
                : `Ядро меньше ${off.core_min} — сыгранность начинается с нуля (сборы «Сплочение» это исправят).`}
          </p>
          <button onClick={() => setBuilding(true)} className="mt-2 w-full rounded-xl bg-white/10 py-2 text-xs font-semibold text-ink-chalk active:scale-95">
            Изменить заявку · {season.squad.length}
          </button>
        </div>
        )}
      </Step>

      <Step n={first + 2} title="Предсезонные сборы">
        <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Сборы">
          {off.camps.map((c) => {
            const on = off.camp === c.code;
            return (
              <button key={c.code} role="radio" aria-checked={on} disabled={camp.isPending} onClick={() => camp.mutate(on ? null : c.code)}
                className={`flex flex-col items-center gap-1 rounded-2xl p-2.5 text-center ${on ? "bg-floodlight text-bg-base" : "bg-bg-base/50 text-ink-chalk"}`}
              >
                <span className="text-lg">{CAMP_ICON[c.code] ?? "•"}</span>
                <span className="text-caption font-bold">{c.label}</span>
              </button>
            );
          })}
        </div>
        <p className="mt-1.5 text-caption leading-snug text-ink-mist">
          {off.camps.find((c) => c.code === off.camp)?.hint ?? "Выбери фокус сборов на старт сезона."}
        </p>
      </Step>

      <Step n={first + 3} title="Товарищеский матч">
        {off.friendly ? (
          <button onClick={() => navigate(`/play/career/seasons/${season.id}/friendly`)}
            className="flex w-full items-center justify-between rounded-2xl bg-bg-base/50 px-3 py-2.5 text-left"
          >
            <span className="text-xs text-ink-chalk">против «{off.friendly.opponent}»</span>
            <span className="font-mono text-sm font-bold text-ink-chalk">{off.friendly.home_score}:{off.friendly.away_score} ›</span>
          </button>
        ) : (
          <>
            <button onClick={() => friendly.mutate()} disabled={friendly.isPending}
              className="w-full rounded-2xl bg-white/10 py-2.5 text-xs font-semibold text-ink-chalk active:scale-95 disabled:opacity-50"
            >
              {friendly.isPending ? "Играем..." : "Сыграть товарищеский"}
            </button>
            <p className="mt-1 text-micro text-ink-mist-dim">Без наград, усталости и сыгранности — проверка тактики и состава.</p>
          </>
        )}
      </Step>

      {building && <SquadBuilder onClose={() => setBuilding(false)} onView={onView} onError={onError} />}
    </section>
  );
}
