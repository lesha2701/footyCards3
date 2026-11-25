import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchPlayerSources } from "@/api/trades";
import PlayerCard from "@/components/cards/PlayerCard";
import { UserBadge } from "@/components/common/UserBadge";
import { IconCoin } from "@/components/icons";

/** «Где взять»: a footballer missing from the album — the themed packs on
 * sale, his lots on the market and friends holding a spare copy. */
export default function PlayerSourcesSheet({ playerId, onClose }: { playerId: number; onClose: () => void }) {
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["player-sources", playerId], queryFn: () => fetchPlayerSources(playerId) });
  const nothing = data && !data.packs.length && !data.market_lots && !data.friends.length;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 sm:items-center" onClick={onClose}>
      <div
        className="flex max-h-[85vh] w-full max-w-sm flex-col gap-3 overflow-y-auto rounded-t-3xl bg-bg-surface p-5 sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="player-sources"
      >
        <p className="font-display text-base font-bold text-ink-chalk">🔎 Где взять</p>
        {!data ? (
          <p className="text-sm text-ink-mist">Загрузка…</p>
        ) : (
          <>
            <div className="flex items-center gap-3">
              <div className="w-20 shrink-0"><PlayerCard player={data.player} size="sm" /></div>
              <p className="text-sm text-ink-mist">
                Этого футболиста нет в твоём альбоме. Вот где его можно добыть прямо сейчас:
              </p>
            </div>
            {data.friends.length > 0 && (
              <section className="flex flex-col gap-1.5">
                <p className="text-xs font-semibold text-accent-lime">🤝 Лишняя копия у друзей</p>
                {data.friends.map((f) => (
                  <button
                    key={f.user.id}
                    onClick={() => navigate("/trades/new", { state: { target: f.user, requestedIds: [f.card_id] } })}
                    className="flex items-center justify-between rounded-xl bg-black/20 px-3 py-2.5 text-left active:scale-[0.99]"
                  >
                    <span className="flex items-center gap-1 text-sm text-ink-chalk">
                      {f.user.username ?? f.user.first_name ?? `Игрок #${f.user.id}`}
                      <UserBadge badge={f.user.active_badge} />
                    </span>
                    <span className="text-xs font-bold text-accent-lime">Предложить обмен →</span>
                  </button>
                ))}
              </section>
            )}
            {data.market_lots > 0 && (
              <button
                onClick={() => navigate("/market")}
                className="flex items-center justify-between rounded-xl bg-black/20 px-3 py-2.5 text-left active:scale-[0.99]"
              >
                <span className="text-sm text-ink-chalk">🏷 На рынке: {data.market_lots} лот(ов)</span>
                {data.market_from != null && (
                  <span className="flex items-center gap-1 text-xs font-bold text-amber-200">
                    от {data.market_from.toLocaleString("ru-RU")} <IconCoin size={12} />
                  </span>
                )}
              </button>
            )}
            {data.packs.map((p) => (
              <button
                key={p.id}
                onClick={() => navigate("/packs")}
                className="flex items-center justify-between rounded-xl bg-black/20 px-3 py-2.5 text-left active:scale-[0.99]"
              >
                <span className="text-sm text-ink-chalk">🎁 Выпадает в паке «{p.name}»</span>
                <span className="text-xs font-bold text-accent-lime">В магазин →</span>
              </button>
            ))}
            {nothing && (
              <p className="rounded-xl bg-black/20 px-3 py-3 text-sm text-ink-mist">
                Сейчас его нет ни у друзей, ни на рынке. Добавь его в «Ищу» — мы сообщим, когда карточка появится у кого-то.
              </p>
            )}
          </>
        )}
        <button onClick={onClose} className="rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
          Закрыть
        </button>
      </div>
    </div>
  );
}
