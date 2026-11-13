import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchTownWeek } from "@/api/town";
import { IconCoin } from "@/components/icons";

const fmt = (n: number) => n.toLocaleString("ru-RU");
const MEDAL = ["🥇", "🥈", "🥉"];
const medal = (place: number) => MEDAL[place - 1] ?? `${place}.`;
const endsOn = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });

/** «Город недели» (/town/week): towns ranked by guests' likes and visits plus
 * houses; the past week's top is paid on the first look after it ends
 * (every number comes from backend town_social_service). */
export default function TownWeekPage() {
  const { data, error } = useQuery({ queryKey: ["town-week"], queryFn: fetchTownWeek, refetchInterval: 60_000 });
  const last = data?.last_week;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 px-1">
        <span className="text-4xl" aria-hidden>🏆</span>
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-xl font-bold leading-tight text-ink-chalk">Город недели</h1>
          <p className="truncate text-xs text-ink-mist">{data ? `Итоги ${endsOn(data.ends_on)} в полночь` : "Загрузка…"}</p>
        </div>
        <Link to="/town/guests" className="shrink-0 rounded-full bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist">👋 Гости</Link>
      </div>
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">Рейтинг сейчас недоступен</p>}
      {last?.mine && (
        <p className="rounded-2xl border border-accent-lime/30 bg-accent-lime/10 px-3 py-2 text-xs text-accent-lime" data-testid="town-week-mine">
          Прошлая неделя: твой город на {last.mine.place} месте {medal(last.mine.place)}{last.mine.coins ? ` — +${fmt(last.mine.coins)} монет` : ""}
        </p>
      )}
      {data && (
        <p className="rounded-2xl border border-amber-300/25 bg-amber-400/5 px-3 py-2 text-xs text-ink-mist">
          Очки: ❤️ лайк гостя — {data.points.like}, 👋 гость — {data.points.guest}, 🏠 дом — {data.points.house}.
          Награды: {data.rewards.slice(0, 3).map((r) => `${medal(r.place)} ${fmt(r.coins)}`).join(" · ")}
          {data.rewards.length > 3 && ` · до ${data.rewards.length} места ${fmt(data.rewards[3].coins)}`} монет.
        </p>
      )}
      {data?.me && (
        <div className="flex items-center gap-3 rounded-2xl border border-floodlight/40 bg-floodlight/10 p-3">
          <span className="w-8 text-center font-display text-lg font-bold text-ink-chalk">{medal(data.me.place)}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold text-ink-chalk">Твой город · {fmt(data.me.score)} очк.</p>
            <p className="text-[11px] text-ink-mist">❤️ {data.me.likes} · 👋 {data.me.guests} · 🏠 {data.me.houses}</p>
          </div>
        </div>
      )}
      {data && data.top.length === 0 && (
        <p className="rounded-2xl bg-bg-surface px-3 py-6 text-center text-sm text-ink-mist">
          На этой неделе гостей ещё не было — сходи к соседям, и они придут к тебе.
        </p>
      )}
      <ol className="flex flex-col gap-2" aria-label="Рейтинг недели">
        {(data?.top ?? []).map((r) => (
          <li key={r.user_id}>
            <Link to={`/town/visit/${r.user_id}`} className="flex items-center gap-3 rounded-2xl border border-white/10 bg-bg-surface p-3">
              <span className="w-8 shrink-0 text-center font-display text-lg font-bold text-ink-chalk">{medal(r.place)}</span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-bold text-ink-chalk">{r.name}</p>
                <p className="truncate text-[11px] text-ink-mist">{r.owner} · ❤️ {r.likes} · 👋 {r.guests} · 🏠 {r.houses}</p>
              </div>
              <div className="flex shrink-0 flex-col items-end">
                <span className="text-sm font-bold text-ink-chalk">{fmt(r.score)}</span>
                {!!r.reward && <span className="flex items-center gap-0.5 text-[10px] text-amber-200"><IconCoin size={10} /> {fmt(r.reward)}</span>}
              </div>
            </Link>
          </li>
        ))}
      </ol>
      {last && last.winners.length > 0 && (
        <section className="rounded-2xl border border-white/10 bg-bg-surface p-3" aria-label="Победители прошлой недели">
          <p className="mb-1 text-xs font-bold text-ink-chalk">Прошлая неделя</p>
          {last.winners.map((w) => (
            <p key={w.place} className="text-xs text-ink-mist">{medal(w.place)} {w.owner} — {fmt(w.score)} очк.</p>
          ))}
        </section>
      )}
    </div>
  );
}
