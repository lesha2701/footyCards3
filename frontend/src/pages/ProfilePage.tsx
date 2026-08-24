import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimDailyReward, fetchDailyRewardCalendar } from "@/api/dailyRewards";
import { fetchFeatureFlags } from "@/api/featureFlags";
import { fetchLeagueStatus } from "@/api/leagues";
import { fetchMyGifts } from "@/api/gifts";
import { fetchMyBadges, fetchMyProfile, fetchMyTransactions, fetchMyTrophies, updateMySettings } from "@/api/profile";
import { createCoinInvoice, fetchCoinInvoiceStatus, fetchCoinPackages } from "@/api/wallet";
import { UserBadge } from "@/components/common/UserBadge";
import {
  IconChevronRight,
  IconCoin,
  IconCollection,
  IconFire,
  IconGift,
  IconPack,
  IconScroll,
  IconSwap,
  IconTag,
  IconTools,
  IconTrophy,
  IconUsers,
  type IconProps,
} from "@/components/icons";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { PRIVACY_POLICY_URL, USER_AGREEMENT_URL } from "@/lib/legalLinks";
import { RARITY_GLOW, RARITY_GRADIENTS, RARITY_LABELS } from "@/lib/rarity";
import { hapticNotify, openLink, openTelegramInvoice } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { CoinPackage, DailyRewardClaimResult, UserTrophy } from "@/types";

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
  referral_reward: "Реферальная награда",
  stars_coin_purchase: "Покупка монет за ⭐",
  stars_pack_bonus_coins: "Бонус монет за пак",
};

function dayStreakLabel(days: number): string {
  const mod10 = days % 10;
  const mod100 = days % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return "дня";
  return "дней";
}

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const setUser = useAuthStore((s) => s.setUser);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [showTx, setShowTx] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);
  const [claimResult, setClaimResult] = useState<DailyRewardClaimResult | null>(null);
  const [showBuyCoins, setShowBuyCoins] = useState(false);
  const [showDocuments, setShowDocuments] = useState(false);

  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: leagueStatus } = useQuery({ queryKey: ["league-status"], queryFn: fetchLeagueStatus });
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags });
  const { data: badges } = useQuery({ queryKey: ["profile", "badges"], queryFn: fetchMyBadges });
  const { data: trophies } = useQuery({ queryKey: ["profile", "trophies"], queryFn: fetchMyTrophies });
  const { data: myGifts } = useQuery({ queryKey: ["gifts", "mine"], queryFn: fetchMyGifts });
  const pinnedGifts = myGifts?.filter((g) => g.is_pinned) ?? [];
  const [selectedTrophy, setSelectedTrophy] = useState<UserTrophy | null>(null);
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
      setClaimResult(data);
      queryClient.invalidateQueries({ queryKey: ["daily-reward-calendar"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
    },
    onError: (err) => setClaimError(err instanceof ApiRequestError ? err.message : "Не удалось получить награду"),
  });

  const settingsMutation = useMutation({
    mutationFn: updateMySettings,
    onSuccess: (data) => {
      queryClient.setQueryData(["profile", "me"], data);
      queryClient.invalidateQueries({ queryKey: ["profile", "badges"] });
      const current = useAuthStore.getState().user;
      if (current) setUser({ ...current, active_badge: data.active_badge });
    },
  });

  if (!user || !profile) return null;

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col items-center gap-2 rounded-3xl bg-bg-surface p-5 text-center">
        <img
          src={user.avatar_url ?? staticUrl("players/placeholder/player_placeholder.webp")}
          alt="avatar"
          className="h-20 w-20 rounded-full ring-2 ring-accent-lime object-cover"
        />
        <p className="flex items-center gap-1.5 font-display text-xl font-bold text-ink-chalk">
          {user.first_name} {user.last_name}
          <UserBadge badge={user.active_badge} />
        </p>
        {user.username && <p className="text-sm text-ink-mist">@{user.username}</p>}
        <p className="text-xs text-ink-mist-dim">С нами с {new Date(user.created_at).toLocaleDateString("ru-RU")}</p>
        {profile.daily_login_streak > 0 && (
          <div className="mt-1 flex items-center gap-1.5 rounded-full bg-orange-500/10 px-3 py-1">
            <IconFire size={14} className="text-orange-400" />
            <span className="text-xs font-bold text-orange-400">
              {profile.daily_login_streak} {dayStreakLabel(profile.daily_login_streak)} подряд
            </span>
          </div>
        )}
      </section>

      {leagueStatus && (leagueStatus.current_league ?? leagueStatus.next_league) && flags?.leagues_enabled !== false && (
        <button
          onClick={() => navigate("/league")}
          className="flex items-center gap-3 rounded-2xl bg-bg-surface px-4 py-3 text-left active:scale-[0.98]"
        >
          <span
            className={`flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full bg-bg-raised ${
              leagueStatus.current_league ? "" : "opacity-40"
            }`}
          >
            {(() => {
              const tier = leagueStatus.current_league ?? leagueStatus.next_league!;
              return tier.image_path ? (
                <img src={staticUrl(tier.image_path) ?? undefined} className="h-full w-full object-cover" />
              ) : (
                <IconTrophy size={22} style={{ color: tier.color }} />
              );
            })()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-sm font-bold text-ink-chalk">
              {leagueStatus.current_league ? leagueStatus.current_league.name : "Пока вне лиги"}
            </p>
            {leagueStatus.current_league_percent !== null && (
              <p className="mt-0.5 text-[11px] text-ink-mist-dim">
                {leagueStatus.current_league_percent}% игроков в этой лиге
              </p>
            )}
          </div>
          <IconChevronRight size={16} className="shrink-0 text-ink-mist-dim" />
        </button>
      )}

      {badges && badges.length > 1 && (
        <section className="rounded-2xl bg-bg-surface p-4">
          <p className="mb-3 flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
            <IconTag size={16} className="text-amber-400" />
            Значок у имени
          </p>
          <div className="flex flex-wrap gap-2">
            {badges.map((ob) => (
              <button
                key={ob.badge.id}
                onClick={() => settingsMutation.mutate({ active_badge_id: ob.equipped ? null : ob.badge.id })}
                disabled={settingsMutation.isPending}
                className={`flex items-center gap-1.5 rounded-full px-3 py-2 text-xs font-semibold transition disabled:opacity-40 ${
                  ob.equipped ? "bg-amber-400 text-bg-base" : "bg-white/5 text-ink-mist"
                }`}
              >
                <UserBadge badge={ob.badge} className="h-4 w-4" />
                {ob.badge.name}
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-ink-mist-dim">
            Нажми на значок, чтобы показать его рядом со своим именем. Нажми ещё раз, чтобы снять.
          </p>
        </section>
      )}

      {!!trophies?.length && (
        <section className="rounded-2xl bg-bg-surface p-4">
          <p className="mb-3 flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
            <IconTrophy size={16} className="text-amber-400" />
            Трофеи
          </p>
          <div className="grid grid-cols-4 gap-2">
            {trophies.map((t) => (
              <button
                key={t.id}
                onClick={() => setSelectedTrophy(t)}
                className="flex flex-col items-center gap-1 rounded-xl bg-bg-raised p-2 active:scale-95"
              >
                <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-b from-amber-400/20 to-amber-600/5">
                  {t.trophy.image_path ? (
                    <img src={staticUrl(t.trophy.image_path) ?? undefined} className="h-full w-full object-cover" />
                  ) : (
                    <span className="text-2xl">{t.trophy.icon}</span>
                  )}
                </div>
                <span className="w-full truncate text-center text-[10px] text-ink-mist">{t.trophy.name}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <button
        onClick={() => navigate("/gifts")}
        className="flex items-center justify-between rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.99]"
      >
        <span className="flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
          <IconGift size={16} className="text-rarity-epic" />
          Подарки
        </span>
        <span className="flex items-center gap-2">
          {pinnedGifts.length > 0 ? (
            <span className="flex -space-x-2">
              {pinnedGifts.slice(0, 3).map((g) => (
                <span
                  key={g.id}
                  className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-full border-2 border-bg-surface bg-rarity-epic/10"
                >
                  {g.gift_set.image_path ? (
                    <img src={staticUrl(g.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
                  ) : (
                    <IconGift size={14} className="text-rarity-epic" />
                  )}
                </span>
              ))}
            </span>
          ) : (
            <span className="text-xs text-ink-mist-dim">Закрепи любимые подарки</span>
          )}
          <IconChevronRight size={16} className="text-ink-mist-dim" />
        </span>
      </button>

      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="grid grid-cols-2 gap-y-4">
          <Stat label="Баланс" value={user.balance} Icon={IconCoin} iconClass="text-accent-lime" />
          <Stat label="Уникальных карточек" value={profile.unique_cards} />
          <Stat label="Всего карточек" value={profile.total_cards} />
          <Stat label="Паков открыто" value={profile.packs_opened} />
          <Stat label="Место в рейтинге" value={`#${profile.league_rank}`} accentClass="bg-floodlight bg-clip-text text-transparent" />
          <Stat label="Матчи Arena П/Н/П" value={`${profile.matches_won}/${profile.matches_drawn}/${profile.matches_lost}`} />
          <Stat label="Матчи Тактико П/Н/П" value={`${profile.tactics_matches_won}/${profile.tactics_matches_drawn}/${profile.tactics_matches_lost}`} />
          <Stat label="Матчи Пенальти П/Н/П" value={`${profile.penalty_matches_won}/${profile.penalty_matches_drawn}/${profile.penalty_matches_lost}`} />
        </div>
      </section>

      {profile.rarest_card && (
        <section className="flex items-center gap-3 rounded-2xl bg-rarity-legendary/10 p-4">
          <img
            src={staticUrl(profile.rarest_card.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
            alt={profile.rarest_card.display_name}
            className="h-16 w-16 rounded-xl object-cover"
          />
          <div>
            <p className="text-[11px] text-rarity-legendary">Самая редкая карточка</p>
            <p className="font-display text-sm font-bold text-ink-chalk">{profile.rarest_card.display_name}</p>
          </div>
        </section>
      )}

      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
            <IconGift size={16} className="text-accent-lime" />
            Ежедневная награда
          </p>
          <span className="font-mono text-xs text-ink-mist">Серия: день {calendar?.current_streak ?? 1}</span>
        </div>
        <div className="grid grid-cols-7 gap-1.5">
          {calendar?.days.map((d) => {
            const DayIcon = d.grants_random_card ? IconCollection : d.free_pack_name ? IconPack : IconCoin;
            return (
              <div
                key={d.day}
                className={`flex flex-col items-center gap-0.5 rounded-lg py-2 text-[10px] ${
                  d.is_claimed
                    ? "bg-accent-green/15 text-accent-green"
                    : d.is_today
                      ? "bg-accent-lime/15 text-accent-lime"
                      : "bg-white/5 text-ink-mist-dim"
                }`}
              >
                <span className="font-mono">Д{d.day}</span>
                <DayIcon size={13} />
                <span className="font-mono">{d.coins}</span>
              </div>
            );
          })}
        </div>
        {claimError && <p className="mt-2 text-xs text-red-400">{claimError}</p>}
        <button
          onClick={() => claimMutation.mutate()}
          disabled={calendar?.already_claimed_today || claimMutation.isPending}
          className="mt-3 w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {calendar?.already_claimed_today ? "Уже получено сегодня" : "Забрать награду"}
        </button>
      </section>

      <section className="rounded-2xl bg-bg-surface p-4">
        <p className="flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
          <IconUsers size={16} className="text-accent-cyan" />
          Пригласи друзей
        </p>
        <p className="mt-1 text-xs text-ink-mist">Приглашено: {profile.referral_count}</p>
        {(profile.referral_referrer_reward > 0 || profile.referral_referred_reward > 0) && (
          <div className="mt-2 flex items-center gap-1.5 rounded-xl bg-accent-lime/10 px-3 py-2 text-xs text-accent-lime">
            <IconCoin size={13} />
            <span>
              Тебе +{profile.referral_referrer_reward}, другу +{profile.referral_referred_reward} за каждого приглашённого
            </span>
          </div>
        )}
        <div className="mt-3 flex items-center gap-2 rounded-xl bg-black/20 px-3 py-2">
          <span className="flex-1 truncate font-mono text-xs text-ink-mist">
            https://t.me/{profile.telegram_bot_username}?start=ref_{user.telegram_id}
          </span>
          <button
            onClick={() => {
              navigator.clipboard.writeText(`https://t.me/${profile.telegram_bot_username}?start=ref_${user.telegram_id}`);
              hapticNotify("success");
            }}
            className="shrink-0 rounded-lg bg-floodlight px-2 py-1 text-[11px] font-bold text-bg-base"
          >
            Копировать
          </button>
        </div>
      </section>

      <section className="rounded-2xl bg-bg-surface p-4">
        <button
          onClick={() => setShowBuyCoins(true)}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-amber-400 py-3 text-sm font-bold text-bg-base active:scale-95"
        >
          <IconCoin size={16} />
          Купить монеты за ⭐
        </button>
      </section>

      <section className="rounded-2xl bg-bg-surface p-4">
        <p className="flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
          <IconSwap size={16} className="text-accent-cyan" />
          Настройки обменов
        </p>
        <label className="mt-3 flex items-center justify-between gap-3">
          <span className="text-sm text-ink-mist">Принимать предложения обмена от других игроков</span>
          <input
            type="checkbox"
            checked={profile.accept_trades}
            disabled={settingsMutation.isPending}
            onChange={(e) => settingsMutation.mutate({ accept_trades: e.target.checked })}
            className="h-5 w-5 shrink-0 accent-accent-lime"
          />
        </label>
        <p className="mt-1 text-[11px] text-ink-mist-dim">
          Если отключено, тебя не будет видно в поиске игроков и тебе не смогут предложить обмен. Сам ты по-прежнему сможешь предлагать обмены.
        </p>
      </section>

      <section>
        <button onClick={() => setShowTx((v) => !v)} className="w-full rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist">
          {showTx ? "Скрыть историю транзакций" : "История транзакций"}
        </button>
        {showTx && (
          <div className="mt-3 flex flex-col gap-2">
            {transactions?.items.map((tx) => (
              <div key={tx.id} className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-sm">
                <div>
                  <p className="text-ink-mist">{TX_TYPE_LABELS[tx.type] ?? tx.type}</p>
                  <p className="font-mono text-[10px] text-ink-mist-dim">{new Date(tx.created_at).toLocaleString("ru-RU")}</p>
                </div>
                <span className={`font-mono font-bold ${tx.amount >= 0 ? "text-accent-green" : "text-red-400"}`}>
                  {tx.amount >= 0 ? "+" : ""}{tx.amount}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {user.is_admin && (
        <button
          onClick={() => navigate("/admin")}
          className="flex items-center justify-center gap-2 rounded-2xl bg-rarity-epic py-3 text-sm font-bold text-white active:scale-95"
        >
          <IconTools size={16} />
          Административная панель
        </button>
      )}

      <button
        onClick={() => setShowDocuments(true)}
        className="flex items-center justify-center gap-2 rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95"
      >
        <IconScroll size={16} />
        Документы
      </button>

      {claimResult && <DailyRewardResultModal result={claimResult} onClose={() => setClaimResult(null)} />}
      {selectedTrophy && <TrophyDetailModal trophy={selectedTrophy} onClose={() => setSelectedTrophy(null)} />}
      {showBuyCoins && (
        <BuyCoinsModal
          onClose={() => setShowBuyCoins(false)}
          onPurchased={(newBalance) => {
            updateBalance(newBalance);
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
          }}
        />
      )}
      {showDocuments && <DocumentsModal onClose={() => setShowDocuments(false)} />}
    </div>
  );
}

function DocumentsModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm" onClick={onClose}>
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", damping: 20, stiffness: 300 }}
        className="w-full max-w-xs rounded-3xl bg-bg-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
          <IconScroll size={16} className="text-ink-mist" />
          Документы
        </p>
        <div className="mt-4 flex flex-col gap-2">
          <button
            onClick={() => openLink(PRIVACY_POLICY_URL)}
            className="rounded-xl bg-white/5 px-4 py-3 text-left text-sm text-ink-chalk active:scale-[0.98]"
          >
            Политика обработки персональных данных
          </button>
          <button
            onClick={() => openLink(USER_AGREEMENT_URL)}
            className="rounded-xl bg-white/5 px-4 py-3 text-left text-sm text-ink-chalk active:scale-[0.98]"
          >
            Пользовательское соглашение
          </button>
        </div>
        <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
          Закрыть
        </button>
      </motion.div>
    </div>
  );
}

function TrophyDetailModal({ trophy, onClose }: { trophy: UserTrophy; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm" onClick={onClose}>
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", damping: 20, stiffness: 300 }}
        className="w-full max-w-xs rounded-3xl bg-bg-surface p-5 text-center"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto flex h-20 w-20 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-b from-amber-400/25 to-amber-600/5">
          {trophy.trophy.image_path ? (
            <img src={staticUrl(trophy.trophy.image_path) ?? undefined} className="h-full w-full object-cover" />
          ) : (
            <span className="text-4xl">{trophy.trophy.icon}</span>
          )}
        </div>
        <p className="mt-3 font-display text-lg font-bold text-ink-chalk">{trophy.trophy.name}</p>
        {trophy.trophy.description && <p className="mt-1 text-xs text-ink-mist">{trophy.trophy.description}</p>}
        {trophy.message && (
          <p className="mt-3 rounded-xl bg-amber-400/10 px-3 py-2 text-xs italic text-amber-300">«{trophy.message}»</p>
        )}
        <p className="mt-2 text-[11px] text-ink-mist-dim">
          Вручено {new Date(trophy.granted_at).toLocaleDateString("ru-RU")}
        </p>
        <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
          Закрыть
        </button>
      </motion.div>
    </div>
  );
}

function DailyRewardResultModal({ result, onClose }: { result: DailyRewardClaimResult; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm" onClick={onClose}>
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", damping: 20, stiffness: 300 }}
        className="w-full max-w-xs rounded-3xl bg-bg-surface p-5 text-center"
        onClick={(e) => e.stopPropagation()}
      >
        <motion.div
          initial={{ scale: 0.6, rotate: -10 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: "spring", damping: 12, stiffness: 260, delay: 0.1 }}
          className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-accent-lime/15 text-accent-lime"
        >
          <IconGift size={30} />
        </motion.div>
        <p className="mt-3 font-display text-lg font-bold text-ink-chalk">Награда получена!</p>
        <p className="text-xs text-ink-mist">День {result.streak_day} серии</p>

        {result.coins_awarded > 0 && (
          <p className="mt-3 flex items-center justify-center gap-1.5 font-mono text-2xl font-bold text-accent-lime">
            +{result.coins_awarded}
            <IconCoin size={20} />
          </p>
        )}

        {result.granted_pack_name && (
          <p className="mt-2 flex items-center justify-center gap-1.5 text-sm text-ink-chalk">
            <IconPack size={16} className="text-accent-cyan" />
            Пак «{result.granted_pack_name}»
          </p>
        )}

        {result.granted_card && (
          <div
            className={`mx-auto mt-3 flex h-36 w-28 flex-col items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[result.granted_card.player.rarity]} p-[2px] ${RARITY_GLOW[result.granted_card.player.rarity]}`}
          >
            <div className="flex h-full w-full flex-col rounded-[14px] bg-bg-surface">
              <img
                src={staticUrl(result.granted_card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt={result.granted_card.player.display_name}
                className="aspect-square w-full object-cover"
              />
              <div className="p-1.5 text-center">
                <p className="truncate text-[10px] font-bold text-ink-chalk">{result.granted_card.player.display_name}</p>
                <p className="text-[9px] text-ink-mist">{RARITY_LABELS[result.granted_card.player.rarity]}</p>
              </div>
            </div>
          </div>
        )}

        <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
          Отлично!
        </button>
      </motion.div>
    </div>
  );
}

function BuyCoinsModal({ onClose, onPurchased }: { onClose: () => void; onPurchased: (newBalance: number) => void }) {
  const { data: packages } = useQuery({ queryKey: ["coin-packages"], queryFn: fetchCoinPackages });
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ coins: number; stars: number } | null>(null);

  const handleBuy = async (pkg: CoinPackage) => {
    setError(null);
    setBusyId(pkg.id);
    try {
      const invoice = await createCoinInvoice(pkg.id);
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") {
        setBusyId(null);
        return;
      }
      if (paymentStatus === "failed") {
        setError("Платёж не прошёл");
        setBusyId(null);
        return;
      }

      for (let attempt = 0; attempt < 20; attempt++) {
        const status = await fetchCoinInvoiceStatus(invoice.payload_token);
        if (status.status === "completed" && status.coin_result) {
          hapticNotify("success");
          onPurchased(status.coin_result.new_balance);
          setSuccess({ coins: status.coin_result.coins_credited, stars: pkg.stars_price });
          setBusyId(null);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Монеты ещё не начислены — проверь баланс через минуту");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : err instanceof Error ? err.message : "Не удалось купить монеты");
      setBusyId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" onClick={onClose}>
      <div
        className="w-full max-w-sm rounded-2xl bg-bg-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="font-display text-base font-bold text-ink-chalk">Купить монеты за ⭐</p>

        {success ? (
          <>
            <div className="mt-4 rounded-2xl bg-accent-green/10 px-4 py-4 text-center">
              <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
                +{success.coins} <IconCoin size={16} />
              </p>
              <p className="mt-1 text-xs text-ink-mist">За {success.stars} ⭐</p>
            </div>
            <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
              Отлично!
            </button>
          </>
        ) : (
          <>
            {error && <p className="mt-2 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="mt-4 flex flex-col gap-2">
              {(packages ?? []).map((pkg) => (
                <button
                  key={pkg.id}
                  onClick={() => handleBuy(pkg)}
                  disabled={busyId !== null}
                  className="flex items-center justify-between rounded-2xl bg-black/20 px-4 py-3 text-left disabled:opacity-40"
                >
                  <span className="font-mono text-sm font-semibold text-ink-chalk">{pkg.stars_price} ⭐</span>
                  <span className="flex items-center gap-1 font-mono text-sm font-bold text-accent-lime">
                    {busyId === pkg.id ? "..." : `+${pkg.coins_amount}`}
                    <IconCoin size={13} />
                  </span>
                </button>
              ))}
            </div>
            <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
              Отмена
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  Icon,
  iconClass,
  accentClass,
}: {
  label: string;
  value: string | number;
  Icon?: (props: IconProps) => JSX.Element;
  iconClass?: string;
  accentClass?: string;
}) {
  return (
    <div>
      <p className={`flex items-center gap-1.5 font-mono text-2xl font-bold ${accentClass ?? "text-ink-chalk"}`}>
        {Icon && <Icon size={16} className={iconClass} />}
        {value}
      </p>
      <p className="mt-0.5 text-[11px] text-ink-mist">{label}</p>
    </div>
  );
}
