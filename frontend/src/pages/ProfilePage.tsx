import { RewardBundleChips } from "@/components/rewards/RewardBundleView";
import SoundSetting from "@/components/profile/SoundSetting";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchFeatureFlags } from "@/api/featureFlags";
import { fetchLeagueStatus } from "@/api/leagues";
import { fetchMyGifts } from "@/api/gifts";
import { fetchClubPass, fetchSeasonPass } from "@/api/monetization";
import {
  fetchMyAttention, fetchMyBadges, fetchMyProfile, fetchMyTransactions, fetchMyTrophies, updateMySettings,
} from "@/api/profile";
import ShareButton from "@/components/common/ShareButton";
import { UserBadge } from "@/components/common/UserBadge";
import ProfileMuse from "@/components/muses/ProfileMuse";
import { MyPlayerEntry } from "@/components/myPlayer/MyPlayerEntry";
import AcademyShowcase from "@/components/path/AcademyShowcase";
import { ShowcaseRow } from "@/components/profile/Showcase";
import LoginCalendar from "@/components/profile/LoginCalendar";
import ThemeSetting from "@/components/profile/ThemeSetting";
import MonetizationEntries from "@/components/shop/MonetizationEntries";
import { BuyCoinsModal } from "@/components/shop/CoinPackages";
import {
  IconChevronLeft,
  IconChevronRight,
  IconCoin,
  IconEdit,
  IconFire,
  IconGift,
  IconScroll,
  IconSwap,
  IconTag,
  IconTools,
  IconTrophy,
  IconUsers,
} from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { backgroundClass, frameClass } from "@/lib/cosmetics";
import { PRIVACY_POLICY_URL, USER_AGREEMENT_URL } from "@/lib/legalLinks";
import { TX_TYPE_LABELS } from "@/lib/transactionLabels";
import { hapticNotify, openLink } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { UserTrophy } from "@/types";

function dayStreakLabel(days: number): string {
  const mod10 = days % 10;
  const mod100 = days % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return "дня";
  return "дней";
}

/** 95500 → «95,5К», 1 250 000 → «1,3М». */
function compact(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}М`;
  if (Math.abs(n) >= 10_000) return `${(n / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}К`;
  return n.toLocaleString("ru-RU");
}

type Section = "collection" | "heroes" | "friends" | "rewards" | "settings";
const SECTION_TITLES: Record<Section, string> = {
  collection: "Зал славы",
  heroes: "Мои герои",
  friends: "Друзья",
  rewards: "Награды",
  settings: "Настройки",
};

/** «Профиль»: a player-card header (place in the league, the numbers as card
 * stats, a pencil for the settings), four group tiles, the daily calendar.
 * Each tile opens its section at /profile/<section>. */
export default function ProfilePage() {
  const { section: rawSection } = useParams<{ section?: string }>();
  const section = rawSection && rawSection in SECTION_TITLES ? (rawSection as Section) : null;
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const setUser = useAuthStore((s) => s.setUser);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [showTx, setShowTx] = useState(false);
  const [showBuyCoins, setShowBuyCoins] = useState(false);
  const [showDocuments, setShowDocuments] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: attention } = useQuery({ queryKey: ["attention"], queryFn: fetchMyAttention, refetchInterval: 60000 });
  const { data: leagueStatus } = useQuery({ queryKey: ["league-status"], queryFn: fetchLeagueStatus });
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags });
  const { data: badges } = useQuery({ queryKey: ["profile", "badges"], queryFn: fetchMyBadges });
  const { data: trophies } = useQuery({ queryKey: ["profile", "trophies"], queryFn: fetchMyTrophies });
  const { data: myGifts } = useQuery({ queryKey: ["gifts", "mine"], queryFn: fetchMyGifts });
  const { data: clubPass } = useQuery({ queryKey: ["club-pass"], queryFn: fetchClubPass });
  const { data: season } = useQuery({ queryKey: ["season-pass"], queryFn: fetchSeasonPass });
  const pinnedGifts = myGifts?.filter((g) => g.is_pinned) ?? [];
  const [selectedTrophy, setSelectedTrophy] = useState<UserTrophy | null>(null);
  const { data: transactions } = useQuery({
    queryKey: ["transactions"],
    queryFn: () => fetchMyTransactions(1),
    enabled: showTx,
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
  const frame = frameClass(profile.cosmetics?.frame);
  const background = backgroundClass(profile.cosmetics?.background);
  const league = leagueStatus && flags?.leagues_enabled !== false ? leagueStatus.current_league : null;
  const wins = profile.matches_won + profile.tactics_matches_won + profile.penalty_matches_won;
  const draws = profile.matches_drawn + profile.tactics_matches_drawn + profile.penalty_matches_drawn;
  const losses = profile.matches_lost + profile.tactics_matches_lost + profile.penalty_matches_lost;
  const rewardsWaiting = (clubPass?.is_active && !clubPass.daily_claimed_today ? 1 : 0) + (season?.claimable ?? 0);

  const modals = (
    <>
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
    </>
  );

  if (section) {
    return (
      <div className="flex flex-col gap-4">
        <button onClick={() => navigate("/profile")} className="flex items-center gap-1 self-start text-sm text-accent-lime">
          <IconChevronLeft size={16} />
          Профиль
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">{SECTION_TITLES[section]}</h1>

        {section === "collection" && (
          <>
            <button
              onClick={() => navigate(`/users/${user.id}/hall`)}
              className="relative flex items-center gap-3 overflow-hidden rounded-2xl border border-amber-300/30 bg-gradient-to-r from-[#3b2414] via-[#1a3628] to-[#0c1712] p-4 text-left active:scale-[0.98]"
              data-testid="open-my-hall"
            >
              <span className="text-4xl drop-shadow">🏛</span>
              <span className="min-w-0 flex-1">
                <span className="block font-display text-base font-bold text-amber-100">Мой зал славы</span>
                <span className="block text-caption text-ink-mist">Картины, кубки и подарки — обустрой комнату</span>
              </span>
              <span className="rounded-full bg-amber-300/20 px-3 py-1.5 text-micro font-bold text-amber-100">Войти</span>
            </button>
            {profile.showcase?.length ? <ShowcaseRow cards={profile.showcase} title="Моя витрина" /> : null}
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
                          <img decoding="async" loading="lazy" src={staticUrl(t.trophy.image_path) ?? undefined} className="h-full w-full object-cover" />
                        ) : (
                          <span className="text-2xl">{t.trophy.icon}</span>
                        )}
                      </div>
                      <span className="w-full truncate text-center text-micro text-ink-mist">{t.trophy.name}</span>
                    </button>
                  ))}
                </div>
              </section>
            )}
            {profile.rarest_card && (
              <section className="flex items-center gap-3 rounded-2xl bg-rarity-legendary/10 p-4">
                <img decoding="async" loading="lazy"
                  src={staticUrl(profile.rarest_card.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                  alt={profile.rarest_card.display_name}
                  className="h-16 w-16 rounded-xl object-cover"
                />
                <div>
                  <p className="text-caption text-rarity-legendary">Самая редкая карточка</p>
                  <p className="font-display text-sm font-bold text-ink-chalk">{profile.rarest_card.display_name}</p>
                </div>
              </section>
            )}
            <MonetizationEntries showStyle={false} showClubPass={false} showSeason={false} />
          </>
        )}

        {section === "heroes" && (
          <>
            <MyPlayerEntry />
            <ProfileMuse />
            <AcademyShowcase userId={user.id} />
          </>
        )}

        {section === "friends" && (
          <>
            <RowLink
              onClick={() => navigate("/friends")}
              icon={<IconUsers size={16} className="text-accent-lime" />}
              title="Друзья"
              right={!!attention?.friend_requests && (
                <span className="rounded-full bg-accent-lime px-2 py-0.5 font-mono text-micro font-bold text-bg-base">
                  {attention.friend_requests} новых
                </span>
              )}
            />
            <RowLink
              onClick={() => navigate("/gifts")}
              icon={<IconGift size={16} className="text-rarity-epic" />}
              title="Подарки"
              right={pinnedGifts.length > 0 ? (
                <span className="flex -space-x-2">
                  {pinnedGifts.slice(0, 3).map((g) => (
                    <span key={g.id} className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-full border-2 border-bg-surface bg-rarity-epic/10">
                      {g.gift_set.image_path ? (
                        <img decoding="async" loading="lazy" src={staticUrl(g.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
                      ) : (
                        <IconGift size={14} className="text-rarity-epic" />
                      )}
                    </span>
                  ))}
                </span>
              ) : (
                <span className="text-xs text-ink-mist-dim">Закрепи любимые подарки</span>
              )}
            />
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
                    Тебе +{profile.referral_referrer_reward.toLocaleString("ru-RU")}, другу +
                    {profile.referral_referred_reward.toLocaleString("ru-RU")} — когда друг поиграет{" "}
                    {profile.referral_active_days ?? 3} дня
                  </span>
                </div>
              )}
              {!!profile.referral_milestones?.length && (
                <div className="mt-2 flex flex-col gap-1">
                  {profile.referral_milestones.map((m) => (
                    <div
                      key={m.count}
                      className={`flex items-center gap-2 rounded-xl px-3 py-1.5 text-xs ${
                        m.reached ? "bg-accent-lime/10 text-accent-lime" : "bg-white/5 text-ink-mist"
                      }`}
                    >
                      <span className="w-16 shrink-0 font-bold">{m.reached ? "✓ " : ""}{m.count} друзей</span>
                      <RewardBundleChips bundle={m.reward} compact />
                    </div>
                  ))}
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
                  className="shrink-0 rounded-lg bg-floodlight px-2 py-1 text-caption font-bold text-bg-base"
                >
                  Копировать
                </button>
              </div>
            </section>
          </>
        )}

        {section === "rewards" && (
          <>
            <MonetizationEntries showStyle={false} showArtifacts={false} showEquipment={false} />
            <button
              onClick={() => setShowBuyCoins(true)}
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-amber-400 py-3 text-sm font-bold text-bg-base active:scale-95"
            >
              <IconCoin size={16} />
              Купить монеты за ⭐
            </button>
          </>
        )}

        {section === "settings" && (
          <>
            <MonetizationEntries showArtifacts={false} showClubPass={false} showSeason={false} showEquipment={false} />
            {badges && badges.length > 0 && (
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
                <p className="mt-2 text-caption text-ink-mist-dim">
                  Нажми на значок, чтобы показать его рядом со своим именем. Нажми ещё раз, чтобы снять.
                </p>
              </section>
            )}
            <section className="rounded-2xl bg-bg-surface p-4">
              <p className="flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
                <IconSwap size={16} className="text-accent-cyan" />
                Обмены
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
              <p className="mt-1 text-caption text-ink-mist-dim">
                Если отключено, тебя не будет видно в поиске игроков и тебе не смогут предложить обмен. Сам ты по-прежнему сможешь предлагать обмены.
              </p>
            </section>
            <ThemeSetting />
            <SoundSetting />
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
                        <p className="font-mono text-micro text-ink-mist-dim">{new Date(tx.created_at).toLocaleString("ru-RU")}</p>
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
          </>
        )}
        {modals}
      </div>
    );
  }

  const stats: [string, string][] = [
    [compact(user.balance), "Монеты"],
    [compact(profile.total_cards), "Карты"],
    [compact(profile.unique_cards), "Уник."],
    [compact(profile.packs_opened), "Паки"],
    [`${wins}-${draws}-${losses}`, "Матчи"],
    [`${profile.daily_login_streak}`, "Серия"],
  ];

  return (
    <div className="flex flex-col gap-4">
      {/* The player card */}
      <section
        className={`relative overflow-hidden rounded-3xl border border-amber-300/40 p-4 ${background ?? "bg-gradient-to-b from-[#3d2e10] via-[#1f1a0c] to-[#0f100c]"}`}
        data-testid="profile-card"
      >
        <button
          onClick={() => navigate("/profile/settings")}
          aria-label="Настройки"
          className="absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-full bg-black/30 text-amber-100 ring-1 ring-amber-200/30 active:scale-90"
          data-testid="profile-edit"
        >
          <IconEdit size={16} />
        </button>
        <div className="flex items-start gap-3">
          <button onClick={() => navigate("/league")} className="flex w-16 shrink-0 flex-col items-center pt-1 text-center active:scale-95">
            <span className="font-display text-3xl font-black leading-none text-amber-200">#{profile.league_rank}</span>
            <span className="mt-1 line-clamp-2 text-[10px] font-bold uppercase leading-tight tracking-wide text-amber-100/70">
              {league?.name ?? "рейтинг"}
            </span>
            {league?.image_path && <img src={staticUrl(league.image_path) ?? undefined} className="mt-1 h-7 w-7 rounded-full object-cover" />}
          </button>
          <div className="flex min-w-0 flex-1 flex-col items-center pr-10">
            <span className={`rounded-full ${frame ? `p-[3px] ${frame}` : ""}`}>
              <img decoding="async" loading="lazy"
                src={user.avatar_url ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt="avatar"
                className={`h-20 w-20 rounded-full object-cover ${frame ? "ring-2 ring-bg-base" : "ring-2 ring-amber-300"}`}
              />
            </span>
          </div>
        </div>
        <p className="mt-2 flex items-center justify-center gap-1.5 text-center font-display text-xl font-bold text-ink-chalk">
          {user.first_name} {user.last_name}
          <UserBadge badge={user.active_badge} />
        </p>
        <p className="text-center text-xs text-amber-100/60">
          {user.username ? `@${user.username} · ` : ""}с нами с {new Date(user.created_at).toLocaleDateString("ru-RU")}
        </p>
        <div className="mt-2 flex flex-wrap justify-center gap-1.5">
          {profile.club_pass_active && (
            <span className="rounded-full bg-emerald-400/15 px-2.5 py-0.5 text-caption font-semibold text-emerald-300">Клубный абонемент</span>
          )}
          {profile.daily_login_streak > 0 && (
            <span className="flex items-center gap-1 rounded-full bg-orange-500/15 px-2.5 py-0.5 text-caption font-bold text-orange-300">
              <IconFire size={12} />
              {profile.daily_login_streak} {dayStreakLabel(profile.daily_login_streak)} подряд
            </span>
          )}
        </div>
        <div className="my-3 h-px bg-gradient-to-r from-transparent via-amber-300/50 to-transparent" />
        <button onClick={() => setShowDetails((v) => !v)} className="grid w-full grid-cols-3 gap-y-2 text-center active:opacity-80" data-testid="profile-stats">
          {stats.map(([value, label]) => (
            <span key={label} className="flex flex-col">
              <span className="font-mono text-lg font-bold leading-tight text-amber-100">{value}</span>
              <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-amber-100/50">{label}</span>
            </span>
          ))}
        </button>
        {showDetails && (
          <div className="mt-3 grid grid-cols-3 gap-1.5 rounded-2xl bg-black/25 p-2 text-center text-caption">
            {[
              ["Arena", profile.matches_won, profile.matches_drawn, profile.matches_lost],
              ["Тактико", profile.tactics_matches_won, profile.tactics_matches_drawn, profile.tactics_matches_lost],
              ["Пенальти", profile.penalty_matches_won, profile.penalty_matches_drawn, profile.penalty_matches_lost],
            ].map(([mode, w, d, l]) => (
              <span key={mode as string} className="flex flex-col">
                <span className="font-mono font-bold text-ink-chalk">{w}-{d}-{l}</span>
                <span className="text-[10px] text-ink-mist">{mode} П-Н-П</span>
              </span>
            ))}
          </div>
        )}
      </section>

      {/* The four groups */}
      <div className="grid grid-cols-2 gap-2.5">
        <GroupTile
          emoji="🏛"
          title="Зал славы"
          text="Витрина, трофеи, экипировка"
          tone="from-[#4a3412] to-[#1a1408] border-amber-300/30"
          onClick={() => navigate("/profile/collection")}
        />
        <GroupTile
          emoji="⚽"
          title="Мои герои"
          text="Мой игрок, муза, академия"
          tone="from-[#123a2a] to-[#08160f] border-emerald-300/25"
          onClick={() => navigate("/profile/heroes")}
        />
        <GroupTile
          emoji="🤝"
          title="Друзья"
          text="Подарки и приглашения"
          tone="from-[#13304a] to-[#08121c] border-sky-300/25"
          badge={attention?.friend_requests || null}
          onClick={() => navigate("/profile/friends")}
        />
        <GroupTile
          emoji="🎁"
          title="Награды"
          text="Абонемент, пропуск, монеты"
          tone="from-[#3a1846] to-[#14081a] border-fuchsia-300/25"
          badge={rewardsWaiting || null}
          onClick={() => navigate("/profile/rewards")}
        />
      </div>

      <LoginCalendar />
      {modals}
    </div>
  );
}

function GroupTile({ emoji, title, text, tone, badge, onClick }: {
  emoji: string; title: string; text: string; tone: string; badge?: number | null; onClick: () => void;
}) {
  return (
    <button onClick={onClick} className={`relative flex min-h-[104px] flex-col justify-between rounded-2xl border bg-gradient-to-br p-3 text-left active:scale-[0.97] ${tone}`}>
      <span className="text-3xl drop-shadow">{emoji}</span>
      <span>
        <span className="block font-display text-base font-bold text-ink-chalk">{title}</span>
        <span className="block text-[11px] leading-tight text-ink-mist">{text}</span>
      </span>
      {!!badge && (
        <span className="absolute right-2.5 top-2.5 rounded-full bg-accent-lime px-2 py-0.5 font-mono text-micro font-bold text-bg-base">{badge}</span>
      )}
    </button>
  );
}

function RowLink({ onClick, icon, title, right }: { onClick: () => void; icon: ReactNode; title: string; right?: ReactNode }) {
  return (
    <button onClick={onClick} className="flex items-center justify-between rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.99]">
      <span className="flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
        {icon}
        {title}
      </span>
      <span className="flex items-center gap-2">
        {right}
        <IconChevronRight size={16} className="text-ink-mist-dim" />
      </span>
    </button>
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
            <img decoding="async" loading="lazy" src={staticUrl(trophy.trophy.image_path) ?? undefined} className="h-full w-full object-cover" />
          ) : (
            <span className="text-4xl">{trophy.trophy.icon}</span>
          )}
        </div>
        <p className="mt-3 font-display text-lg font-bold text-ink-chalk">{trophy.trophy.name}</p>
        {trophy.trophy.description && <p className="mt-1 text-xs text-ink-mist">{trophy.trophy.description}</p>}
        {trophy.message && (
          <p className="mt-3 rounded-xl bg-amber-400/10 px-3 py-2 text-xs italic text-amber-300">«{trophy.message}»</p>
        )}
        <p className="mt-2 text-caption text-ink-mist-dim">
          Вручено {new Date(trophy.granted_at).toLocaleDateString("ru-RU")}
        </p>
        <ShareButton kind="trophy" id={trophy.id} className="mt-4" />
        <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
          Закрыть
        </button>
      </motion.div>
    </div>
  );
}
