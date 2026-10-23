import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { claimClubPassDaily, createClubPassInvoice, fetchClubPass, setClubPassAutoRenew } from "@/api/monetization";
import { UserBadge } from "@/components/common/UserBadge";
import { IconCheck, IconClock, IconCoin, IconGift, IconPack, IconPlay, IconStar, IconTicket, IconTrophy } from "@/components/icons";
import { GrantedRewardModal } from "@/components/rewards/RewardBundleView";
import { frameClass } from "@/lib/cosmetics";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import { RARITY_LABELS } from "@/lib/rarity";
import type { GrantedRewards, RewardBundle } from "@/types";

function monthlyText(b: RewardBundle): string {
  return [
    b.coins ? `${b.coins} монет` : null,
    b.pack_name ? `пак «${b.pack_name}»` : null,
    b.card_rarity ? `${RARITY_LABELS[b.card_rarity].toLowerCase()} карточка` : null,
  ].filter(Boolean).join(" + ");
}

function Perk({ icon, text }: { icon: JSX.Element; text: string }) {
  return (
    <li className="flex items-center gap-3 text-sm text-ink-chalk">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-400/10 text-emerald-300">
        {icon}
      </span>
      {text}
    </li>
  );
}

/** «Клубный абонемент»: a monthly Telegram Stars subscription. */
export default function ClubPassPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: pass } = useQuery({ queryKey: ["club-pass"], queryFn: fetchClubPass });
  const [error, setError] = useState<string | null>(null);
  const [granted, setGranted] = useState<GrantedRewards | null>(null);

  const refresh = () => {
    for (const key of [["club-pass"], ["profile", "me"], ["profile", "badges"], ["cosmetics"], ["collection"]]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Что-то пошло не так"));

  const buy = useMutation({
    mutationFn: () => payShopWithStars(createClubPassInvoice),
    onSuccess: (status) => {
      if (status === "paid") hapticNotify("success");
      setError(null);
      refresh();
    },
    onError,
  });
  const daily = useMutation({
    mutationFn: claimClubPassDaily,
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      setGranted(data);
      setError(null);
      refresh();
    },
    onError,
  });
  const autoRenew = useMutation({
    mutationFn: (value: boolean) => setClubPassAutoRenew(value),
    onSuccess: (data) => {
      queryClient.setQueryData(["club-pass"], data);
      setError(null);
    },
    onError,
  });

  if (!pass) return null;
  const { perks } = pass;
  const expires = pass.expires_at ? new Date(pass.expires_at).toLocaleDateString("ru-RU", { day: "numeric", month: "long" }) : null;

  return (
    <div className="flex flex-col gap-5">
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-500/30 via-bg-surface to-bg-surface p-5">
        <p className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconTicket size={22} className="text-emerald-300" />
          Клубный абонемент
        </p>
        {pass.is_active ? (
          <p className="mt-1 text-sm text-emerald-300">
            Активен до {expires}
            {pass.auto_renew ? " · продлится автоматически" : " · автопродление выключено"}
          </p>
        ) : (
          <p className="mt-1 text-sm text-ink-mist">Бонусы каждый день — {pass.stars_price} ⭐ в месяц</p>
        )}

        <ul className="mt-4 flex flex-col gap-2.5">
          {perks.monthly_bonus && (
            <Perk icon={<IconGift size={15} />} text={`Сразу и каждый месяц: ${monthlyText(perks.monthly_bonus)}`} />
          )}
          {perks.daily_coins > 0 && <Perk icon={<IconCoin size={15} />} text={`+${perks.daily_coins} монет каждый день`} />}
          {perks.daily_pack?.pack_name && (
            <Perk icon={<IconPack size={15} />} text={`Бесплатный пак «${perks.daily_pack.pack_name}» каждый день`} />
          )}
          {perks.extra_rewarded_attempts > 0 && (
            <Perk icon={<IconPlay size={15} />} text={`+${perks.extra_rewarded_attempts} награждаемых попытки в каждой мини-игре`} />
          )}
          {perks.season_xp_bonus_pct > 0 && (
            <Perk icon={<IconTrophy size={15} />} text={`+${perks.season_xp_bonus_pct}% опыта сезонного пропуска`} />
          )}
          {perks.free_catchups > 0 && (
            <Perk icon={<IconClock size={15} />} text={`${perks.free_catchups} бесплатных догона пропущенных дней в месяц`} />
          )}
          {perks.frame && (
            <Perk
              icon={<span className={`block h-5 w-5 rounded-full p-[2px] ${frameClass(perks.frame.style_key) ?? ""}`}><span className="block h-full w-full rounded-full bg-bg-surface" /></span>}
              text={`Эксклюзивная рамка «${perks.frame.name}»`}
            />
          )}
          {perks.badge && <Perk icon={<UserBadge badge={perks.badge} />} text={`Значок «${perks.badge.name}»`} />}
          {perks.status > 0 && <Perk icon={<IconStar size={15} />} text={`+${perks.status} статуса «Моему игроку», пока абонемент активен`} />}
          {perks.ad_free && <Perk icon={<IconStar size={15} />} text="Без рекламы, когда она появится" />}
        </ul>
      </section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {pass.is_active ? (
        <>
          <button
            onClick={() => daily.mutate()}
            disabled={pass.daily_claimed_today || daily.isPending}
            className="flex items-center justify-center gap-2 rounded-2xl bg-floodlight py-3.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            {pass.daily_claimed_today ? <><IconCheck size={16} /> Бонус на сегодня получен</> : "Забрать ежедневный бонус"}
          </button>
          <button
            onClick={() => autoRenew.mutate(!pass.auto_renew)}
            disabled={autoRenew.isPending}
            className="rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist disabled:opacity-40"
          >
            {pass.auto_renew ? "Отключить автопродление" : "Включить автопродление"}
          </button>
          <p className="text-center text-caption text-ink-mist-dim">
            Без автопродления абонемент просто закончится {expires}. Эксклюзивная рамка и значок действуют, пока абонемент активен.
          </p>
        </>
      ) : pass.enabled ? (
        <>
          <button
            onClick={() => buy.mutate()}
            disabled={buy.isPending}
            className="rounded-2xl bg-amber-400 py-3.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            {buy.isPending ? "Оплата..." : `Оформить за ${pass.stars_price} ⭐ / месяц`}
          </button>
          <p className="text-center text-caption text-ink-mist-dim">
            Подписка Telegram Stars на 30 дней, продлевается автоматически. Отменить можно в любой момент здесь или в
            настройках Telegram. Звёзды не выводятся и не обмениваются на деньги.
          </p>
        </>
      ) : (
        <p className="text-center text-sm text-ink-mist">Абонемент сейчас недоступен</p>
      )}

      {granted && (
        <GrantedRewardModal title="Бонус абонемента" subtitle="Заходи завтра за новым" granted={granted} onClose={() => setGranted(null)} />
      )}
    </div>
  );
}
