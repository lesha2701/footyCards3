/** The club around the matches: the coach's word after a round, the news
 * feed, the stands, the legends and the board's hot seat. Everything is
 * decided on the backend (career_story_service). */
import { useMutation } from "@tanstack/react-query";

import { answerCareerMoment, type CareerSeason, type CareerView } from "@/api/career";
import { haptic } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

const TONE: Record<string, string> = { good: "text-accent-lime", bad: "text-red-300", plain: "text-ink-chalk" };

const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`);

/** A press question or a player at the door: one word, it counts. */
export function MomentCard({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const answer = useMutation({
    mutationFn: (code: string) => answerCareerMoment(code, season.rounds_played),
    onSuccess: (v) => { haptic("medium"); onView(v); },
    onError,
  });
  const moment = season.moment;
  if (!moment) return null;
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4 ring-1 ring-floodlight/30" aria-label="Слово тренера">
      <div>
        <p className="text-micro uppercase tracking-wider text-ink-mist">{moment.kind === "press" ? "🎙 Пресс-конференция" : "💬 Разговор в раздевалке"}</p>
        <p className="mt-1 text-sm font-semibold text-ink-chalk">{moment.text}</p>
      </div>
      <div className="flex flex-col gap-1.5">
        {moment.answers.map((a) => (
          <button key={a.code} type="button" disabled={answer.isPending} onClick={() => answer.mutate(a.code)}
            className="flex items-center justify-between gap-2 rounded-2xl bg-bg-raised px-3 py-2.5 text-left text-caption font-semibold text-ink-chalk active:scale-[0.99] disabled:opacity-60">
            <span className="min-w-0">{a.text}</span>
            <span className="flex shrink-0 gap-1.5 font-mono text-micro text-ink-mist">
              {a.morale !== 0 && <span className={a.morale > 0 ? "text-accent-lime" : "text-red-300"}>мораль {signed(a.morale)}</span>}
              {a.fans !== 0 && <span className={a.fans > 0 ? "text-accent-lime" : "text-red-300"}>трибуны {signed(a.fans)}</span>}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

export function NewsFeed({ season }: { season: CareerSeason }) {
  const news = season.news ?? [];
  return (
    <section className="flex flex-col gap-2 rounded-3xl bg-bg-surface p-4" aria-label="Новости клуба">
      <p className="font-display text-base font-bold text-ink-chalk">Новости клуба</p>
      {news.length === 0 && <p className="text-caption text-ink-mist">Лента оживёт после первого тура.</p>}
      <ul className="flex flex-col gap-1.5">
        {news.slice(0, 14).map((n, i) => (
          <li key={i} className="flex items-start gap-2 text-caption">
            <span className="w-5 shrink-0 text-center" aria-hidden="true">{n.icon}</span>
            <span className={`min-w-0 flex-1 ${TONE[n.tone] ?? TONE.plain}`}>{n.text}</span>
            <span className="shrink-0 font-mono text-micro text-ink-mist-dim">т{n.round + 1}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function FansCard({ season }: { season: CareerSeason }) {
  const fans = season.fans;
  if (!fans) return null;
  return (
    <section className="flex flex-col gap-2 rounded-3xl bg-bg-surface p-4" aria-label="Трибуны">
      <div className="flex items-baseline justify-between gap-2">
        <p className="font-display text-base font-bold text-ink-chalk">Трибуны</p>
        <p className="text-caption font-semibold text-accent-lime">{fans.label}</p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-bg-raised" role="meter" aria-label="Настроение трибун"
        aria-valuenow={fans.mood} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded-full bg-accent-lime" style={{ width: `${fans.mood}%` }} />
      </div>
      <p className="text-caption text-ink-mist">
        Придёт {fans.attendance.toLocaleString("ru-RU")} из {fans.capacity.toLocaleString("ru-RU")}. Доход стадиона: {fans.income_pct}%.
        Побольше мест и денег — в «Клубной базе».
      </p>
    </section>
  );
}

export function LegendsCard({ season }: { season: CareerSeason }) {
  const legends = season.legends;
  if (!legends || legends.players.length === 0) return null;
  return (
    <section className="flex flex-col gap-2 rounded-3xl bg-bg-surface p-4" aria-label="Легенды клуба">
      <p className="font-display text-base font-bold text-ink-chalk">Легенды клуба</p>
      <table className="w-full text-caption">
        <thead>
          <tr className="text-micro text-ink-mist">
            <th className="text-left font-normal">Игрок</th>
            <th className="w-9 text-right font-normal">Сез.</th>
            <th className="w-9 text-right font-normal">Игр</th>
            <th className="w-9 text-right font-normal">Гол.</th>
            <th className="w-9 text-right font-normal">Пас</th>
          </tr>
        </thead>
        <tbody>
          {legends.players.map((p) => (
            <tr key={p.name} className="text-ink-chalk">
              <td className="max-w-0 truncate py-0.5">{p.name}</td>
              <td className="text-right font-mono">{p.seasons}</td>
              <td className="text-right font-mono">{p.apps}</td>
              <td className="text-right font-mono font-bold">{p.goals}</td>
              <td className="text-right font-mono">{p.assists}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-micro text-ink-mist">
        {legends.biggest_win && <span>Крупнейшая победа: {legends.biggest_win.score}, «{legends.biggest_win.opponent}»</span>}
        {legends.best_streak > 1 && <span>Лучшая серия: {legends.best_streak}</span>}
      </div>
    </section>
  );
}

export function HotSeatBanner({ season }: { season: CareerSeason }) {
  const seat = season.hot_seat;
  if (!seat) return null;
  return (
    <section className="rounded-3xl bg-red-500/10 p-4 ring-1 ring-red-400/40" aria-label="Горячее кресло">
      <p className="font-display text-base font-bold text-red-300">🔥 Горячее кресло{seat.level > 1 ? ` · уровень ${seat.level}` : ""}</p>
      <p className="mt-1 text-caption text-ink-chalk">{seat.text}</p>
    </section>
  );
}
