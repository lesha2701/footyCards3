import type { GrantedRewards, LoginCalendar, RewardBundle } from "@/types";

export function isEmptyBundle(bundle: RewardBundle | null | undefined): boolean {
  return !bundle || !(bundle.coins || bundle.pack_name || bundle.card_rarity || bundle.badge || bundle.cosmetic);
}

/** "85 монет + пак «Базовый»" — one line for a reward slot. */
export function dayRewardLabel(reward: RewardBundle | undefined): string | null {
  if (!reward) return null;
  const extra = reward.pack_name ? `пак «${reward.pack_name}»`
    : reward.card_rarity ? "карточка"
      : reward.cosmetic ? `«${reward.cosmetic.name}»`
        : reward.badge ? `значок «${reward.badge.name}»` : null;
  if (extra && reward.coins) return `${reward.coins} монет + ${extra}`;
  return extra ?? (reward.coins ? `${reward.coins} монет` : null);
}

/** "8/31 дней · сегодня: 85 монет" — the calendar is the reason to come
 * back tomorrow, so it is shown where the reward is collected. */
export function streakLine(calendar: LoginCalendar, readyToday: boolean): string {
  const todayIdx = calendar.days.findIndex((d) => d.date === calendar.today);
  const today = todayIdx >= 0 ? calendar.days[todayIdx] : undefined;
  const tomorrow = todayIdx >= 0 ? calendar.days[todayIdx + 1] : undefined;
  const progress = `${calendar.claimed_count}/${calendar.days_in_month} дней`;
  const reward = readyToday ? dayRewardLabel(today?.reward) : dayRewardLabel(tomorrow?.reward);
  if (!reward) return readyToday ? progress : "Уже забрано · завтра новая";
  return readyToday ? `${progress} · сегодня: ${reward}` : `Забрано · завтра: ${reward}`;
}

export function grantedExtras(granted: GrantedRewards): string[] {
  return [
    ...granted.cards.map((c) => `карточка ${c.player.display_name}`),
    granted.pack_name ? `пак «${granted.pack_name}»` : null,
    granted.cosmetic ? `«${granted.cosmetic.name}»` : null,
    granted.badge ? `значок «${granted.badge.name}»` : null,
  ].filter(Boolean) as string[];
}

export function formatCountdown(ms: number): string {
  if (ms <= 0) return "00:00:00";
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}
