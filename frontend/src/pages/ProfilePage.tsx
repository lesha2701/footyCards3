import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimDailyReward, fetchDailyRewardCalendar } from "@/api/dailyRewards";
import { fetchMyProfile, fetchMyTransactions, updateMySettings } from "@/api/profile";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const TX_TYPE_LABELS: Record<string, string> = {
  starting_balance: "Стартовый бонус",
  daily_reward: "Ежедневная награда",
  pack_purchase: "Покупка пака",
  card_sale: "Продажа карточки",
  game_reward: "Награда за игру",
  match_reward: "Награда за матч",
  achievement_reward: "Достижение",
  task_reward: "Задание",
  trade_coins_sent: "Обмен: отправлено",
  trade_coins_received: "Обмен: получено",
  admin_adjustment: "Корректировка администратором",
};

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [showTx, setShowTx] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);

  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: calendar } = useQuery({ queryKey: ["daily-reward-calendar"], queryFn: fetchDailyRewardCalendar });
  const { data: transactions } = useQuery({
    queryKey: ["transactions"],
    queryFn: () => fetchMyTransactions(1),
    enabled: showTx,
  });

  const claimMutation = useMutation({
    mutationFn: claimDailyReward,
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimError(null);
      queryClient.invalidateQueries({ queryKey: ["daily-reward-calendar"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
    },
    onError: (err) => setClaimError(err instanceof ApiRequestError ? err.message : "Не удалось получить награду"),
  });

  const settingsMutation = useMutation({
    mutationFn: updateMySettings,
    onSuccess: (data) => queryClient.setQueryData(["profile", "me"], data),
  });

  if (!user || !profile) return null;

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col items-center gap-2 rounded-3xl border border-white/5 bg-bg-surface p-5 text-center">
        <img
          src={user.avatar_url ?? staticUrl("players/placeholder/player_placeholder.webp")}
          alt="avatar"
          className="h-20 w-20 rounded-full border-2 border-accent object-cover"
        />
        <p className="font-display text-xl font-bold text-slate-100">{user.first_name} {user.last_name}</p>
        {user.username && <p className="text-sm text-slate-400">@{user.username}</p>}
        <p className="text-xs text-slate-500">С нами с {new Date(user.created_at).toLocaleDateString("ru-RU")}</p>
      </section>

      <section className="grid grid-cols-2 gap-3">
        <Stat label="Баланс" value={`🪙 ${user.balance}`} />
        <Stat label="Уровень" value={`⭐ ${user.level}`} />
        <Stat label="Уникальных карточек" value={profile.unique_cards} />
        <Stat label="Всего карточек" value={profile.total_cards} />
        <Stat label="Паков открыто" value={profile.packs_opened} />
        <Stat label="Место в рейтинге" value={`#${profile.arena_rank}`} />
        <Stat label="Матчи П/Н/П" value={`${profile.matches_won}/${profile.matches_drawn}/${profile.matches_lost}`} />
        <Stat label="Рекорд Memory" value={profile.memory_best_score} />
      </section>

      {profile.rarest_card && (
        <section className="flex items-center gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
          <img
            src={staticUrl(profile.rarest_card.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
            alt={profile.rarest_card.display_name}
            className="h-16 w-16 rounded-xl object-cover"
          />
          <div>
            <p className="text-[11px] text-amber-400">Самая редкая карточка</p>
            <p className="font-display text-sm font-bold text-slate-100">{profile.rarest_card.display_name}</p>
          </div>
        </section>
      )}

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-display text-base font-bold text-slate-100">🎁 Ежедневная награда</p>
          <span className="text-xs text-slate-400">Серия: день {calendar?.current_streak ?? 1}</span>
        </div>
        <div className="grid grid-cols-7 gap-1.5">
          {calendar?.days.map((d) => (
            <div
              key={d.day}
              className={`flex flex-col items-center rounded-lg py-2 text-[10px] ${
                d.is_claimed ? "bg-emerald-500/20 text-emerald-400" : d.is_today ? "bg-accent/20 text-accent" : "bg-white/5 text-slate-500"
              }`}
            >
              <span>Д{d.day}</span>
              <span className="mt-0.5">{d.grants_random_card ? "🃏" : d.free_pack_name ? "📦" : "🪙"}</span>
              <span>{d.coins}</span>
            </div>
          ))}
        </div>
        {claimError && <p className="mt-2 text-xs text-red-400">{claimError}</p>}
        <button
          onClick={() => claimMutation.mutate()}
          disabled={calendar?.already_claimed_today || claimMutation.isPending}
          className="mt-3 w-full rounded-2xl bg-amber-500 py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {calendar?.already_claimed_today ? "Уже получено сегодня" : "Забрать награду"}
        </button>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="font-display text-base font-bold text-slate-100">👥 Пригласи друзей</p>
        <p className="mt-1 text-xs text-slate-400">Приглашено: {profile.referral_count}</p>
        <div className="mt-3 flex items-center gap-2 rounded-xl bg-black/20 px-3 py-2">
          <span className="flex-1 truncate text-xs text-slate-300">
            https://t.me/{profile.telegram_bot_username}?start=ref_{user.telegram_id}
          </span>
          <button
            onClick={() => {
              navigator.clipboard.writeText(`https://t.me/${profile.telegram_bot_username}?start=ref_${user.telegram_id}`);
              hapticNotify("success");
            }}
            className="shrink-0 rounded-lg bg-accent px-2 py-1 text-[11px] font-bold text-bg-base"
          >
            Копировать
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="font-display text-base font-bold text-slate-100">🔄 Настройки обменов</p>
        <label className="mt-3 flex items-center justify-between gap-3">
          <span className="text-sm text-slate-300">Принимать предложения обмена от других игроков</span>
          <input
            type="checkbox"
            checked={profile.accept_trades}
            disabled={settingsMutation.isPending}
            onChange={(e) => settingsMutation.mutate({ accept_trades: e.target.checked })}
            className="h-5 w-5 shrink-0 accent-accent"
          />
        </label>
        <p className="mt-1 text-[11px] text-slate-500">
          Если отключено, тебя не будет видно в поиске игроков и тебе не смогут предложить обмен. Сам ты по-прежнему сможешь предлагать обмены.
        </p>
      </section>

      <section>
        <button onClick={() => setShowTx((v) => !v)} className="w-full rounded-2xl bg-white/5 py-3 text-sm font-semibold text-slate-300">
          {showTx ? "Скрыть историю транзакций" : "История транзакций"}
        </button>
        {showTx && (
          <div className="mt-3 flex flex-col gap-2">
            {transactions?.items.map((tx) => (
              <div key={tx.id} className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-sm">
                <div>
                  <p className="text-slate-300">{TX_TYPE_LABELS[tx.type] ?? tx.type}</p>
                  <p className="text-[10px] text-slate-500">{new Date(tx.created_at).toLocaleString("ru-RU")}</p>
                </div>
                <span className={`font-bold ${tx.amount >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {tx.amount >= 0 ? "+" : ""}{tx.amount}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {user.is_admin && (
        <button onClick={() => navigate("/admin")} className="rounded-2xl bg-purple-600 py-3 text-sm font-bold text-white active:scale-95">
          🛠 Административная панель
        </button>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-bg-surface px-3 py-2.5">
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className="font-display text-base font-bold text-slate-100">{value}</p>
    </div>
  );
}
