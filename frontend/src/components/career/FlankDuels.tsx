import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  fetchCareerDuels, setCareerLineup, type CareerSeason, type CareerView, type DuelHint, type FlankDuel,
  type HalftimeDuels, type PlayedDuel,
} from "@/api/career";
import { haptic } from "@/lib/telegram";

const VERDICT: Record<FlankDuel["verdict"], { emoji: string; label: string; tone: string }> = {
  easy: { emoji: "😎", label: "Легко", tone: "text-accent-lime" },
  even: { emoji: "⚔️", label: "На равных", tone: "text-ink-mist" },
  hard: { emoji: "😰", label: "Тяжело", tone: "text-red-400" },
};
const FLANK_LABEL: Record<FlankDuel["flank"], string> = { left: "Левый", right: "Правый", centre: "Центр" };

/** A footballer's duel style (players.duel_style): one field, read as an
 * attacker or a defender type in a duel (backend duel_service). */
const DUEL_STYLES: Record<string, { icon: string; label: string }> = {
  speed: { icon: "⚡", label: "Скорость" },
  technique: { icon: "🎩", label: "Техника" },
  power: { icon: "💪", label: "Сила" },
  reading: { icon: "🧠", label: "Чтение игры" },
};

export function DuelStyleBadge({ style, className = "" }: { style?: string | null; className?: string }) {
  const meta = style ? DUEL_STYLES[style] : undefined;
  if (!meta) return null;
  return (
    <span title={`Стиль в дуэлях: ${meta.label}`} aria-label={`Стиль в дуэлях: ${meta.label}`}
      className={`pointer-events-none rounded-full bg-black/60 px-[3px] text-[9px] leading-tight ${className}`}>
      {meta.icon}
    </span>
  );
}

/** The duel style with its name: the legend and the player's sheet. */
export function DuelStyleChip({ style }: { style: string }) {
  const meta = DUEL_STYLES[style];
  if (!meta) return null;
  return <span className="rounded-full bg-white/10 px-2 py-0.5 text-micro font-semibold text-ink-chalk">{meta.icon} {meta.label}</span>;
}

export const DUEL_STYLE_KEYS = Object.keys(DUEL_STYLES);

/** «Кто кого обыгрывает»: the rock-paper-scissors of duel_service.MATRIX. */
const GUIDE: { attacker: string; easy: string; hard: string }[] = [
  { attacker: "⚡ Скоростной", easy: "силового — тот не успевает", hard: "быстрого — догоняет" },
  { attacker: "🎩 Технарь", easy: "быстрого — рано бросается в отбор", hard: "читающего игру — не ведётся на финты" },
  { attacker: "💪 Силовой", easy: "читающего игру — проигрывает корпус", hard: "силового — «танк» на «танка»" },
];

function StyleGuide() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-2xl bg-bg-base/40 p-2.5">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex w-full items-center justify-between text-caption font-semibold text-ink-mist">
        Кто кого обыгрывает <span aria-hidden>{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <ul className="mt-2 flex flex-col gap-1.5">
          {GUIDE.map((g) => (
            <li key={g.attacker} className="text-micro leading-snug text-ink-mist">
              <span className="font-semibold text-ink-chalk">{g.attacker}</span>: легко против {g.easy}; тяжело
              против {g.hard}.
            </li>
          ))}
          <li className="text-micro leading-snug text-ink-mist-dim">
            🧠 Чтение игры у вингера работает как техника. Ещё дуэль сдвигают известные противостояния и история пары.
          </li>
        </ul>
      )}
    </div>
  );
}

const FLIP: Record<FlankDuel["verdict"], FlankDuel["verdict"]> = { easy: "hard", hard: "easy", even: "even" };

/** One duel, always from OUR point of view: in their attacks a duel easy
 * for their attacker is a hard one for our defender. */
function DuelRow({ duel, theirs = false }: { duel: FlankDuel; theirs?: boolean }) {
  const v = VERDICT[theirs ? FLIP[duel.verdict] : duel.verdict];
  const pp = theirs ? -duel.pp : duel.pp;
  // Their left winger attacks down OUR right flank.
  const flank = theirs && duel.flank !== "centre" ? (duel.flank === "left" ? "right" : "left") : duel.flank;
  return (
    <li className="flex flex-col gap-0.5 rounded-xl bg-bg-raised px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="shrink-0 rounded-md bg-white/5 px-1.5 py-0.5 text-micro font-semibold text-ink-mist">
          {FLANK_LABEL[flank]}
        </span>
        <span className="min-w-0 flex-1 truncate text-caption font-semibold text-ink-chalk">
          {duel.attacker} <span className="text-ink-mist-dim">⟷</span> {duel.defender}
        </span>
        <span className={`shrink-0 text-caption font-bold ${v.tone}`} title={v.label}>
          {v.emoji} {pp > 0 ? "+" : ""}{pp}
        </span>
      </div>
      {duel.reasons.length > 0 && (
        <p className="text-micro leading-snug text-ink-mist">
          {theirs ? "Их атака: " : ""}{duel.reasons.join(" · ")}
        </p>
      )}
    </li>
  );
}

/** «Дуэли на флангах» before the next match: our wide attackers against the
 * full-backs they will meet and theirs against ours, our strikers against
 * their centre-backs, with what to do about it — in one tap where it can be
 * (switch the flank, open the squad or the man-marking). Hidden while the
 * season has no flank duels. */
export function FlankDuelsCard({ season, onView, onError, onSquad }: {
  season: CareerSeason;
  onView?: (v: CareerView) => void;
  onError?: (e: unknown) => void;
  /** «Сменить игрока»: the squad screen. */
  onSquad?: () => void;
}) {
  const { data } = useQuery({
    queryKey: ["career", "duels", season.id, season.rounds_played, JSON.stringify(season.lineup), season.formation,
      JSON.stringify(season.tactic ?? {})],
    queryFn: fetchCareerDuels,
  });
  const flank = useMutation({
    mutationFn: ({ axis, value }: { axis: "flank" | "direction"; value: string }) => setCareerLineup({
      slots: season.lineup, formation: season.formation, mentality: season.mentality, playstyle: season.playstyle,
      tactic: { ...(season.tactic ?? {}), [axis]: value }, round_index: season.rounds_played,
    }),
    onSuccess: (v) => { haptic("light"); onView?.(v); },
    onError: (e) => onError?.(e),
  });
  if (!data?.enabled) return null;
  const attack = data.attack ?? [];
  const defence = data.defence ?? [];
  const centre = data.centre ?? [];
  if (!attack.length && !defence.length && !centre.length) return null;
  type Action = DuelHint["actions"][number];
  const usable = (a: Action) =>
    ((a.kind === "flank" || a.kind === "direction") && !!onView) || (a.kind === "squad" && !!onSquad) || a.kind === "marking";
  const act = (a: Action) => {
    if ((a.kind === "flank" || a.kind === "direction") && a.value) flank.mutate({ axis: a.kind, value: a.value });
    else if (a.kind === "squad") onSquad?.();
    else document.getElementById("career-marking")?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div>
        <p className="font-display text-base font-bold text-ink-chalk">Дуэли на флангах</p>
        <p className="text-micro text-ink-mist">
          Кто кому неудобен: стиль игрока, известные противостояния и история их дуэлей. Число — насколько нашему игроку
          легче (+) или тяжелее (−) выиграть стык, в п.п.
        </p>
      </div>
      {attack.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">Наши атаки</p>
          <ul className="flex flex-col gap-1.5">{attack.map((d, i) => <DuelRow key={`a${i}`} duel={d} />)}</ul>
        </div>
      )}
      {defence.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">Их атаки</p>
          <ul className="flex flex-col gap-1.5">{defence.map((d, i) => <DuelRow key={`d${i}`} duel={d} theirs />)}</ul>
        </div>
      )}
      {centre.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">В центре</p>
          <ul className="flex flex-col gap-1.5">{centre.map((d, i) => <DuelRow key={`c${i}`} duel={d} />)}</ul>
        </div>
      )}
      {(data.hints ?? []).length > 0 && (
        <ul className="flex flex-col gap-2 rounded-2xl bg-amber-400/10 p-3">
          {(data.hints ?? []).map((h) => {
            const actions = h.actions.filter(usable);
            return (
              <li key={h.text} className="flex flex-col gap-1.5">
                <p className="text-caption text-amber-200">💡 {h.text}</p>
                {actions.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {actions.map((a) => (
                      <button key={a.kind + (a.value ?? "")} type="button" onClick={() => act(a)} disabled={flank.isPending}
                        className="rounded-full bg-amber-300/20 px-2.5 py-1 text-micro font-semibold text-amber-100 active:scale-95 disabled:opacity-50">
                        {a.label}
                      </button>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <StyleGuide />
      <p className="text-micro text-ink-mist-dim">Фланг атак выбирается в тактике, «Фланг атак».</p>
    </section>
  );
}

function PlayedRows({ duels }: { duels: PlayedDuel[] }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {duels.map((d) => {
        const total = d.attacker_wins + d.defender_wins;
        const mineWon = d.mine === "attack" ? d.attacker_wins : d.defender_wins;
        const tone = mineWon * 2 > total ? "text-accent-lime" : mineWon * 2 < total ? "text-red-400" : "text-ink-mist";
        return (
          <li key={`${d.attacker}-${d.defender}`} className="flex items-center gap-2 rounded-xl bg-bg-raised px-3 py-2">
            <span className="min-w-0 flex-1 truncate text-caption text-ink-chalk">
              {d.attacker} <span className="text-ink-mist-dim">⟷</span> {d.defender}
            </span>
            <span className={`shrink-0 font-mono text-caption font-bold ${tone}`}>
              {d.attacker_wins}:{d.defender_wins}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** «Дуэли первого тайма» at the break of a live match: who won how many,
 * and a one-tap flank switch put into the second-half orders. */
export function HalftimeDuelsPanel({ duels, flank, onFlank }: {
  duels: HalftimeDuels | null | undefined;
  /** The flank in the orders being prepared. */
  flank?: string;
  onFlank: (flank: "left" | "right") => void;
}) {
  if (!duels?.duels.length) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">Дуэли первого тайма</p>
      <PlayedRows duels={duels.duels} />
      {duels.hints.map((h) => (
        <div key={h.text} className="flex flex-col gap-1 rounded-xl bg-amber-400/10 p-2">
          <p className="text-caption text-amber-200">💡 {h.text}</p>
          {h.flank && (
            <button type="button" onClick={() => onFlank(h.flank!)} disabled={flank === h.flank}
              className="self-start rounded-full bg-amber-300/20 px-2.5 py-1 text-micro font-semibold text-amber-100 disabled:opacity-60">
              {flank === h.flank ? "Фланг выбран — отдай указания" : `Атаковать: ${h.flank === "left" ? "левый" : "правый"}`}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

/** «Ключевые дуэли» after a match: who won the flank duels my players were
 * in, and the stories they made (a rival beaten, fear born or gone). */
export function PlayedDuels({ duels, stories }: { duels: PlayedDuel[] | null | undefined; stories?: string[] | null }) {
  if (!duels?.length && !stories?.length) return null;
  return (
    <section className="flex flex-col gap-2 rounded-3xl bg-bg-surface p-4">
      <p className="font-display text-base font-bold text-ink-chalk">Ключевые дуэли</p>
      {(stories ?? []).map((story) => (
        <p key={story} className="rounded-xl bg-accent-cyan/10 px-3 py-2 text-caption text-ink-chalk">📰 {story}</p>
      ))}
      {!!duels?.length && <PlayedRows duels={duels} />}
      <p className="text-micro text-ink-mist-dim">Выигранные стыки атакующего : защитника.</p>
    </section>
  );
}
