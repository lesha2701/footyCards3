import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  answerPlayerCareerEvent,
  buyPlayerCareerWithCoins,
  claimPlayerCareerWeekly,
  fetchPlayerCareerRankings,
  openPlayerCareerChest,
  type PlayerCareerRankingEntry,
  type PlayerCareerView,
} from "@/api/playerCareer";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCoin } from "@/components/icons";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useCareerStars } from "@/lib/useCareerStars";
import { useAuthStore } from "@/store/authStore";

type OnView = (v: PlayerCareerView) => void;
type OnError = (e: unknown) => void;

const ROLE_STYLE: Record<string, string> = {
  bench: "bg-white/10 text-ink-mist", starter: "bg-accent-cyan/20 text-accent-cyan", captain: "bg-amber-400/20 text-amber-300",
};

/** Role for the next match, the coach's trust and an injury (with healing). */
export function CareerStatus({ view, onView, onError }: { view: PlayerCareerView; onView: OnView; onError: OnError }) {
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const stars = useCareerStars(onError);
  const heal = useMutation({
    mutationFn: () => buyPlayerCareerWithCoins("heal"),
    onSuccess: (v) => { hapticNotify("success"); onView(v); if (v.balance != null) updateBalance(v.balance); },
    onError,
  });
  if (!view.club) return null;
  const shop = view.shop;
  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4" data-testid="career-status">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-ink-chalk">Роль в «{view.club.name}»</span>
        {view.role && (
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${ROLE_STYLE[view.role]}`}>
            {view.role === "captain" ? "©️ " : ""}{view.role_label}
          </span>
        )}
      </div>
      <div>
        <div className="flex justify-between text-caption text-ink-mist">
          <span>Доверие тренера</span>
          <span><b className="text-ink-chalk">{view.trust}</b> · основа с {view.trust_starter}, капитан с {view.trust_captain}</span>
        </div>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-bg-raised">
          <div className="h-full rounded-full bg-gradient-to-r from-accent-cyan to-accent-lime" style={{ width: `${view.trust}%` }} />
        </div>
      </div>
      {view.role === "bench" && (
        <p className="text-caption text-ink-mist">
          На скамейке выходишь на замену не каждый матч. Хорошие оценки и выполненные цели поднимают доверие — или вырасти в рейтинге.
        </p>
      )}
      {view.injury_rounds > 0 && shop && (
        <div className="rounded-xl bg-red-500/10 p-3" data-testid="injury">
          <p className="text-sm font-semibold text-red-300">🤕 Травма: пропустит ещё {view.injury_rounds} {view.injury_rounds === 1 ? "тур" : "тура"}</p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {shop.heal_coins > 0 && (
              <button disabled={heal.isPending} onClick={() => heal.mutate()} className="flex items-center justify-center gap-1 rounded-lg bg-floodlight py-2 text-xs font-bold text-bg-base disabled:opacity-40">
                Вылечить <IconCoin size={12} /> {shop.heal_coins}
              </button>
            )}
            {shop.heal_stars > 0 && (
              <button disabled={!!stars.busy} onClick={() => stars.buy("heal")} className="rounded-lg bg-amber-400 py-2 text-xs font-bold text-bg-base disabled:opacity-40">
                Вылечить ⭐ {shop.heal_stars}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

const EFFECT_LABELS: Record<string, string> = { prestige: "престиж", trust: "доверие", coins: "монет", freshness: "свежесть", xp: "опыта" };

export function StoryEvent({ view, onView, onError }: { view: PlayerCareerView; onView: OnView; onError: OnError }) {
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const answer = useMutation({
    mutationFn: ({ id, choice }: { id: number; choice: string }) => answerPlayerCareerEvent(id, choice),
    onSuccess: (v) => { hapticNotify("success"); onView(v); if (v.balance != null) updateBalance(v.balance); },
    onError,
  });
  const event = view.event;
  if (!event) return null;
  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-gradient-to-br from-fuchsia-500/20 to-bg-surface p-4" data-testid="story-event">
      <p className="text-micro font-bold uppercase tracking-wider text-fuchsia-300">Событие</p>
      <h2 className="font-display text-base font-bold text-ink-chalk">{event.title}</h2>
      <p className="text-sm text-ink-mist">{event.text}</p>
      {event.choices.map((c) => (
        <button
          key={c.key}
          disabled={answer.isPending}
          onClick={() => { haptic("light"); answer.mutate({ id: event.id, choice: c.key }); }}
          className="rounded-xl bg-bg-raised p-3 text-left active:scale-[0.99] disabled:opacity-50"
        >
          <span className="block text-sm font-semibold text-ink-chalk">{c.label}</span>
          <span className="mt-0.5 block text-caption text-ink-mist">
            {Object.entries(c.effects).map(([k, v]) => `${v! > 0 ? "+" : ""}${v} ${EFFECT_LABELS[k] ?? k}`).join(" · ")}
          </span>
        </button>
      ))}
    </section>
  );
}

export function NewsFeed({ news }: { news: PlayerCareerView["news"] }) {
  if (!news.length) return null;
  return (
    <section className="rounded-2xl bg-bg-surface p-4" data-testid="news">
      <h2 className="font-display text-base font-bold text-ink-chalk">📰 Газета</h2>
      <div className="mt-2 flex flex-col divide-y divide-white/5">
        {news.map((n) => (
          <p key={n.round} className="py-2 text-sm text-ink-chalk">
            <span className="mr-2 font-mono text-micro text-ink-mist">Тур {n.round + 1}</span>{n.headline}
          </p>
        ))}
      </div>
    </section>
  );
}

export function HallOfFame({ view }: { view: PlayerCareerView }) {
  if (!view.club || !view.legends.length) return null;
  return (
    <section className="rounded-2xl bg-gradient-to-b from-amber-400/10 to-bg-surface p-4" data-testid="hall-of-fame">
      <h2 className="font-display text-base font-bold text-ink-chalk">🏛 Зал славы «{view.club.name}»</h2>
      <div className="mt-2 flex flex-col gap-1">
        {view.legends.map((l) => (
          <div key={l.place} className={`flex items-center gap-2 text-sm ${l.is_me ? "font-bold text-accent-lime" : "text-ink-chalk"}`}>
            <span className="w-5 font-mono text-xs text-ink-mist">{l.place}</span>
            <span className="min-w-0 flex-1 truncate">{l.player_name} <span className="text-ink-mist">· {l.user_name}</span></span>
            <span className="text-caption text-ink-mist">{l.seasons} сез. · ⚽ {l.goals}{l.titles ? ` · 🏆 ${l.titles}` : ""}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function RankList({ title, rows, unit }: { title: string; rows: PlayerCareerRankingEntry[]; unit: string }) {
  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <h2 className="font-display text-base font-bold text-ink-chalk">{title}</h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-ink-mist">Пока пусто</p>
      ) : (
        <div className="mt-2 flex flex-col divide-y divide-white/5">
          {rows.map((r) => (
            <div key={`${r.user_id}-${r.place}`} className={`flex items-center gap-3 py-2 text-sm ${r.is_me ? "font-bold text-accent-lime" : "text-ink-chalk"}`}>
              <span className="w-6 font-mono text-xs text-ink-mist">{r.place}</span>
              <span className="min-w-0 flex-1 truncate">{r.player_name ?? r.user_name}{r.player_name && <span className="text-ink-mist"> · {r.user_name}</span>}</span>
              <span className="font-mono font-bold">{r.value}</span>
              <span className="w-10 text-caption text-ink-mist">{unit}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function RankingsTab() {
  const { data, isLoading } = useQuery({ queryKey: ["player-career", "rankings"], queryFn: fetchPlayerCareerRankings });
  if (isLoading || !data) return <ListSkeleton />;
  return (
    <div className="flex flex-col gap-4" data-testid="rankings">
      <p className="text-caption text-ink-mist">Неделя {data.week.split("-W")[1]} — все матчи «Карьеры игрока»: лига, кубки, лига друзей.</p>
      <RankList title="⚽ Бомбардиры недели" rows={data.scorers} unit="гол." />
      <RankList title="🅰️ Ассистенты недели" rows={data.assists ?? []} unit="пас." />
      <RankList title="⭐ Лучшая оценка недели (от 4 матчей)" rows={data.ratings} unit="" />
      <RankList title="👑 Престиж" rows={data.prestige} unit="" />
    </div>
  );
}

/** «Бонусы»: the daily chest, weekly tasks, «Карьера Pro» and the paid extras. */
export function BonusTab({ view, onView, onError }: { view: PlayerCareerView; onView: OnView; onError: OnError }) {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const stars = useCareerStars(onError);
  const [chestResult, setChestResult] = useState<string | null>(null);
  const chest = useMutation({
    mutationFn: openPlayerCareerChest,
    onSuccess: (r) => {
      hapticNotify("success");
      updateBalance(r.balance);
      setChestResult(`+${r.coins} монет${r.token ? ` и жетон «${r.token.icon} ${r.token.name}»` : ""}`);
      void queryClient.invalidateQueries({ queryKey: ["player-career"] });
    },
    onError,
  });
  const claim = useMutation({
    mutationFn: (code: string) => claimPlayerCareerWeekly(code),
    onSuccess: (v) => { hapticNotify("success"); onView(v); if (v.balance != null) updateBalance(v.balance); },
    onError,
  });
  const refresh = useMutation({
    mutationFn: () => buyPlayerCareerWithCoins("refresh"),
    onSuccess: (v) => { hapticNotify("success"); onView(v); if (v.balance != null) updateBalance(v.balance); },
    onError,
  });
  const shop = view.shop;
  return (
    <div className="flex flex-col gap-4" data-testid="bonus-tab">
      {view.chest && (
        <section className="flex items-center gap-3 rounded-2xl bg-gradient-to-r from-amber-400/25 to-bg-surface p-4">
          <span className="text-4xl">🎁</span>
          <span className="min-w-0 flex-1">
            <span className="block font-display text-base font-bold text-ink-chalk">Сундук дня</span>
            <span className="block text-caption text-ink-mist">
              {chestResult ?? `${view.chest.coins_min}–${view.chest.coins_max} монет, ${view.chest.token_pct}% шанс жетона навыка`}
            </span>
          </span>
          <button
            disabled={!view.chest.available || chest.isPending}
            onClick={() => { haptic("medium"); chest.mutate(); }}
            className="shrink-0 rounded-xl bg-floodlight px-4 py-2 text-sm font-bold text-bg-base disabled:opacity-40"
          >
            {view.chest.available ? "Открыть" : "Завтра"}
          </button>
        </section>
      )}

      {view.weekly && (
        <section className="rounded-2xl bg-bg-surface p-4" data-testid="weekly-tasks">
          <h2 className="font-display text-base font-bold text-ink-chalk">Задания недели</h2>
          <div className="mt-2 flex flex-col gap-2">
            {view.weekly.tasks.map((t) => (
              <div key={t.code} className="flex items-center gap-3 rounded-xl bg-bg-raised p-3">
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-ink-chalk">{t.label}</span>
                  <span className="block text-caption text-ink-mist">{t.value} / {t.target} · +{t.coins} монет</span>
                </span>
                {t.claimed ? (
                  <span className="text-xs font-bold text-accent-lime">✓</span>
                ) : (
                  <button
                    disabled={!t.done || claim.isPending}
                    onClick={() => claim.mutate(t.code)}
                    className="shrink-0 rounded-lg bg-floodlight px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-30"
                  >
                    Забрать
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {shop && (
        <>
          <section className="rounded-2xl bg-gradient-to-br from-violet-500/30 via-fuchsia-500/15 to-bg-surface p-4 ring-1 ring-violet-400/40" data-testid="career-pro">
            <p className="font-display text-lg font-black text-ink-chalk">Карьера <span className="text-violet-300">PRO</span></p>
            <ul className="mt-2 flex flex-col gap-1 text-sm text-ink-chalk">
              <li>⚡ ещё один ключевой момент в каждом матче</li>
              <li>📈 +{shop.pro_xp_pct}% опыта за матчи карьеры</li>
              <li>🏋️ +1 тренировка каждый день</li>
              <li>🎨 фон «Pro» и значок PRO</li>
            </ul>
            {shop.pro && shop.pro_until && (
              <p className="mt-2 text-xs font-semibold text-violet-200">Активна до {new Date(shop.pro_until).toLocaleDateString("ru-RU")}</p>
            )}
            {shop.pro_stars > 0 && (
              <button
                disabled={!!stars.busy}
                onClick={() => stars.buy("pro")}
                className="mt-3 w-full rounded-xl bg-amber-400 py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
              >
                {shop.pro ? "Продлить" : "Подключить"} на {shop.pro_days} дней · ⭐ {shop.pro_stars}
              </button>
            )}
          </section>

          <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
            <h2 className="font-display text-base font-bold text-ink-chalk">Услуги</h2>
            <ShopRow
              icon="🤝" title="Агент на трансферное окно"
              text={`Ещё одно предложение и +${shop.agent_haggle_bonus}% к шансу в торге${shop.agent_credits ? ` · нанят: ${shop.agent_credits}` : ""}`}
              stars={shop.agent_stars} busy={!!stars.busy} onStars={() => stars.buy("agent")}
            />
            <ShopRow
              icon="💪" title="Полная свежесть" text={`Сейчас ${view.freshness?.value ?? 100}%`}
              coins={shop.refresh_coins} stars={shop.refresh_stars} busy={!!stars.busy || refresh.isPending}
              disabled={(view.freshness?.value ?? 100) >= 100}
              onCoins={() => refresh.mutate()} onStars={() => stars.buy("refresh")}
            />
            {shop.fast_enabled && <ShopRow
              icon="⏩" title="Ускоренный сезон"
              text={`Туры каждые ${Math.round(shop.fast_round_minutes / 60 * 10) / 10} ч${shop.fast_season_credits ? ` · куплено: ${shop.fast_season_credits}` : ""}`}
              stars={shop.fast_stars} busy={!!stars.busy} onStars={() => stars.buy("fast")}
            />}
          </section>
        </>
      )}
    </div>
  );
}

function ShopRow({
  icon, title, text, coins = 0, stars = 0, busy, disabled, onCoins, onStars,
}: {
  icon: string; title: string; text: string; coins?: number; stars?: number; busy: boolean; disabled?: boolean;
  onCoins?: () => void; onStars?: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl bg-bg-raised p-3">
      <span className="text-2xl">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-ink-chalk">{title}</span>
        <span className="block text-caption text-ink-mist">{text}</span>
      </span>
      <span className="flex shrink-0 flex-col gap-1">
        {coins > 0 && onCoins && (
          <button disabled={busy || disabled} onClick={onCoins} className="flex items-center justify-center gap-1 rounded-lg bg-floodlight px-2.5 py-1.5 text-xs font-bold text-bg-base disabled:opacity-30">
            <IconCoin size={11} /> {coins}
          </button>
        )}
        {stars > 0 && onStars && (
          <button disabled={busy || disabled} onClick={onStars} className="rounded-lg bg-amber-400 px-2.5 py-1.5 text-xs font-bold text-bg-base disabled:opacity-30">
            ⭐ {stars}
          </button>
        )}
      </span>
    </div>
  );
}
