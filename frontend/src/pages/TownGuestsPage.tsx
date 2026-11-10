import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchTownGuests } from "@/api/town";
import { IconCoin } from "@/components/icons";

const fmt = (n: number) => n.toLocaleString("ru-RU");

/** «В гости» (/town/guests): friends' towns first, then random ones. A like a
 * day per town, a gift costs the guest more than it brings the owner
 * (backend town_social_service — every number comes from there). */
export default function TownGuestsPage() {
  const { data, error } = useQuery({ queryKey: ["town-guests"], queryFn: fetchTownGuests });
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 px-1">
        <span className="text-4xl" aria-hidden>👋</span>
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-xl font-bold leading-tight text-ink-chalk">В гости</h1>
          <p className="truncate text-xs text-ink-mist">
            {data ? `Твоему городу лайков: сегодня ${fmt(data.likes_today)} · всего ${fmt(data.likes_total)}` : "Загрузка…"}
          </p>
        </div>
        <Link to="/town" className="shrink-0 rounded-full bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist">🗺️ Город</Link>
      </div>
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">Гости сейчас недоступны</p>}
      {data && (
        <p className="rounded-2xl border border-cyan-300/25 bg-cyan-400/5 px-3 py-2 text-xs text-ink-mist">
          Загляни к соседям, поставь лайк и оставь подарок: он стоит тебе{" "}
          <span className="inline-flex items-center gap-0.5 font-bold text-ink-chalk"><IconCoin size={11} /> {fmt(data.gift_price)}</span>,
          хозяин получит +{fmt(data.gift_rent)} к ренте. Подарков сегодня: {data.gifts_left}.
        </p>
      )}
      {data && data.towns.length === 0 && (
        <p className="rounded-2xl bg-bg-surface px-3 py-6 text-center text-sm text-ink-mist">Пока некому ходить в гости — города соседей ещё строятся.</p>
      )}
      <ul className="flex flex-col gap-2">
        {(data?.towns ?? []).map((t) => (
          <li key={t.user_id}>
            <Link
              to={`/town/visit/${t.user_id}`}
              className="flex items-center gap-3 rounded-2xl border border-white/10 bg-bg-surface p-3"
              aria-label={`В гости: ${t.name}`}
            >
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white/5 text-2xl" aria-hidden>🏘️</span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-bold text-ink-chalk">
                  {t.name} {t.friend && <span className="ml-1 rounded-full bg-accent-lime/15 px-1.5 text-[10px] text-accent-lime">друг</span>}
                </p>
                <p className="truncate text-[11px] text-ink-mist">{t.owner} · 🏠 {fmt(t.houses)} · ❤️ {fmt(t.likes)}</p>
              </div>
              <span className="shrink-0 text-sm" aria-label="Сегодня">
                {t.gifted ? "🎁" : ""}{t.liked ? "❤️" : ""}{t.visited ? "" : "›"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
